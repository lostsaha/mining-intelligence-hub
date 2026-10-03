"""/ask 证据问答（Phase 4A）：全库分段检索 → LLM 基于证据作答。

响应四段式（PROJECT_PLAN §10.6）：
{question, answer, evidence_status, citations[], limitations, took_ms}
- evidence_status: answered（证据作答）| partial（LLM 判定证据不足）| no_evidence（语料无命中）| llm_disabled（未配 LLM，只还证据）
- citations: [{n, source_type, title, section_path, page, snippet}]
- 检索：英文词 → tsvector(simple)；中文短语 → ILIKE（009_ask.sql 的 pg_trgm 索引加速）
- 用法：GET /api/ask?q=...&topk=6
"""
from __future__ import annotations

import re
import time

import httpx

from .. import config, db
from ..process.llm import _extract_json

try:  # embeddings 可选：未配置时向量检索分支整体跳过
    from .. import emb as _emb
except Exception:
    _emb = None

_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_EN_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
_PAGE_RE = re.compile(r"\[p(\d+)(?:-(\d+))?\]\s*$")
_EN_STOP = {
    "the", "and", "for", "with", "what", "how", "why", "when", "which",
    "are", "was", "were", "is", "of", "in", "on", "to", "at", "by", "from",
    "does", "do", "did", "can", "could", "should", "would", "will", "shall",
    "there", "their", "this", "that", "these", "those", "have", "has", "had",
    "not", "but", "its", "it's", "about", "into", "than", "then", "them",
}
_SNIPPET_LEN = 320
_PROMPT_SNIPPET_LEN = 520
_PER_TITLE_CAP = 3  # 同一本书/同一篇论文最多取几段，保证证据多样性

ASK_SYSTEM_PROMPT = """你是资深矿业工程专家助手。严格依据给出的【证据】回答用户问题：
- 用中文回答，条理清晰（可用短标题、列表）；来自证据的论断末尾标注对应编号，如 [1][3]
- 只允许使用证据中的信息，不得编造；证据之间冲突时如实指出
- 证据不足以完整回答时：answer 给出能答的部分并注明哪部分缺少依据；limitations 写清还缺什么、建议查证方向
只输出一个 JSON 对象：{"answer": "...", "sufficient": true/false, "limitations": "..."}
sufficient=true 表示证据足以支撑核心结论；false 表示只能部分回答或无法回答。"""


def _extract_terms(q: str) -> tuple[list[str], list[str]]:
    """问题 → (中文短语列表, 英文词列表)，保持出现顺序、去重。
    中文长句切 4-gram（LLM 关闭时的回退分词），英文取实义词。"""
    seen: set[str] = set()
    zh: list[str] = []
    for run in _CJK_RE.findall(q):
        if len(run) <= 5:
            cand = [run]
        else:  # 整句无法直接 ILIKE，滑窗切分
            cand = [run[i:i + 4] for i in range(0, len(run) - 3, 2)]
        for c in cand:
            if c not in seen:
                seen.add(c)
                zh.append(c)
    en: list[str] = []
    for w in _EN_RE.findall(q):
        lw = w.lower()
        if lw not in _EN_STOP and lw not in seen and len(lw) >= 3:
            seen.add(lw)
            en.append(lw)
    return zh[:8], en[:8]


_KEYWORDS_SYSTEM = """你是矿业文献检索助手。把用户的中文/英文问题改写为适合全文检索的关键词：
- keywords_en: 3~6 个英文检索词（矿业术语的规范英文表达，如 slope monitoring、mine water control）
- keywords_zh: 3~6 个中文检索词（2~6 字的领域短语，去掉"哪些/如何"等虚词）
只输出 JSON：{"keywords_en": [...], "keywords_zh": [...]}"""


def _llm_keywords(q: str) -> tuple[list[str], list[str]]:
    """LLM 把问题改写为中英检索词（顺带跨语言翻译）；失败返回空由调用方回退。"""
    payload = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _KEYWORDS_SYSTEM},
            {"role": "user", "content": q},
        ],
    }
    try:
        resp = httpx.post(
            f"{config.LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = _extract_json(resp.json()["choices"][0]["message"]["content"])
        zh = [str(t).strip() for t in (data.get("keywords_zh") or []) if str(t).strip()]
        en = [str(t).strip().lower() for t in (data.get("keywords_en") or []) if str(t).strip()]
        return zh[:6], en[:6]
    except Exception:
        return [], []


def _tsquery(en_terms: list[str]) -> str:
    """英文检索词（可能是多词短语）拆成单词，OR 组合成 to_tsquery 入参。"""
    words: list[str] = []
    for t in en_terms:
        for w in re.split(r"[^a-z0-9\-]+", t.lower()):
            if w and len(w) >= 2 and w not in words:
                words.append(w)
    return " | ".join(words)


def _snippet(content: str, terms: list[str]) -> str:
    """围绕首个命中词截取窗口片段。"""
    pos = -1
    low = content.lower()
    for t in terms:
        p = low.find(t.lower())
        if p >= 0 and (pos < 0 or p < pos):
            pos = p
    if pos < 0:
        pos = 0
    start = max(0, pos - _SNIPPET_LEN // 2)
    piece = content[start:start + _SNIPPET_LEN]
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + _SNIPPET_LEN < len(content) else ""
    return f"{prefix}{piece}{suffix}"


def _search_chunks(
    table: str, zh: list[str], tsq: str, per_term_limit: int
) -> dict[int, dict]:
    """检索一张分段表，返回 {chunk_id: hit_dict}，score = ts*2 + 0.8*短语命中数。"""
    if table == "document_chunks":
        base_sql = """
            SELECT c.chunk_id AS id, c.section_path, c.content, c.lang,
                   COALESCE(d.title_zh, d.title_en) AS title,
                   ts_rank(c.search_vector, to_tsquery('simple', %s)) AS ts_score
            FROM mining.document_chunks c
            JOIN mining.documents d USING (document_id)
            WHERE c.search_vector @@ to_tsquery('simple', %s)
            ORDER BY ts_score DESC LIMIT %s"""
        ilike_sql = """
            SELECT c.chunk_id AS id, c.section_path, c.content, c.lang,
                   COALESCE(d.title_zh, d.title_en) AS title,
                   0::float AS ts_score
            FROM mining.document_chunks c
            JOIN mining.documents d USING (document_id)
            WHERE c.content ILIKE %s LIMIT %s"""
        source = "book"
    else:  # work_chunks
        base_sql = """
            SELECT c.chunk_id AS id, c.section_path, c.content, c.lang,
                   w.title, w.publication_year,
                   ts_rank(c.search_vector, to_tsquery('simple', %s)) AS ts_score
            FROM mining.work_chunks c
            JOIN mining.works w USING (work_id)
            WHERE c.search_vector @@ to_tsquery('simple', %s)
            ORDER BY ts_score DESC LIMIT %s"""
        ilike_sql = """
            SELECT c.chunk_id AS id, c.section_path, c.content, c.lang,
                   w.title, w.publication_year,
                   0::float AS ts_score
            FROM mining.work_chunks c
            JOIN mining.works w USING (work_id)
            WHERE c.content ILIKE %s LIMIT %s"""
        source = "paper"

    hits: dict[int, dict] = {}
    terms = [t for t in re.findall(r"[a-z0-9\-]+", tsq)]
    if tsq:
        for r in db.query(base_sql, (tsq, tsq, per_term_limit * 2)):
            hits[r["id"]] = {
                "id": r["id"], "source": source, "title": r["title"],
                "section_path": r["section_path"], "lang": r["lang"],
                "year": r.get("publication_year") if source == "paper" else None,
                "content": r["content"], "score": float(r["ts_score"] or 0) * 2.0,
            }
    for phrase in zh:
        for r in db.query(ilike_sql, (f"%{phrase}%", per_term_limit)):
            h = hits.get(r["id"])
            if h is None:
                h = hits[r["id"]] = {
                    "id": r["id"], "source": source, "title": r["title"],
                    "section_path": r["section_path"], "lang": r["lang"],
                    "year": r.get("publication_year") if source == "paper" else None,
                    "content": r["content"], "score": 0.0,
                }
            h["score"] += 0.8
    for h in hits.values():
        h["snippet"] = _snippet(h["content"], terms + zh)
    return hits


def _vector_hits(query: str, table: str, topk: int) -> dict[int, dict]:
    """pgvector 余弦近邻（仅当有向量且语料已回填时生效）。"""
    if _emb is None or not _emb.EMBEDDINGS_ENABLED:
        return {}
    n = db.query_one(f"SELECT COUNT(*) AS n FROM mining.{table} WHERE embedding IS NOT NULL")["n"]
    if n == 0:
        return {}
    try:
        vec = _emb.embed([query])[0]
    except Exception:
        return {}
    vec_lit = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    if table == "document_chunks":
        sql = """
            SELECT c.chunk_id AS id, c.section_path, c.content, c.lang,
                   COALESCE(d.title_zh, d.title_en) AS title,
                   1 - (c.embedding <=> %s::vector) AS score
            FROM mining.document_chunks c
            JOIN mining.documents d USING (document_id)
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector LIMIT %s"""
    else:
        sql = """
            SELECT c.chunk_id AS id, c.section_path, c.content, c.lang,
                   w.title, w.publication_year,
                   1 - (c.embedding <=> %s::vector) AS score
            FROM mining.work_chunks c
            JOIN mining.works w USING (work_id)
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector LIMIT %s"""
    source = "book" if table == "document_chunks" else "paper"
    out = {}
    for r in db.query(sql, (vec_lit, vec_lit, topk)):
        out[r["id"]] = {
            "id": r["id"], "source": source, "title": r["title"],
            "section_path": r["section_path"], "lang": r["lang"],
            "year": r.get("publication_year") if source == "paper" else None,
            "content": r["content"], "score": 1.2 * float(r["score"] or 0),
        }
    return out


def _collect_evidence(q: str, topk: int) -> list[dict]:
    zh, en = _extract_terms(q)
    if config.LLM_ENABLED:  # LLM 改写检索词（含中→英翻译），失败回退正则切分
        llm_zh, llm_en = _llm_keywords(q)
        seen = set(zh) | set(en)
        for t in llm_zh + llm_en:
            if t and t not in seen:
                seen.add(t)
                (zh if _CJK_RE.search(t) else en).append(t)
        zh, en = zh[:8], en[:8]
    tsq = _tsquery(en)
    merged = {}
    for table in ("document_chunks", "work_chunks"):
        for cid, h in _search_chunks(table, zh, tsq, per_term_limit=topk * 2).items():
            merged[(h["source"], cid)] = h
        for cid, h in _vector_hits(q, table, topk).items():  # 语义召回（有向量时叠加）
            key = (h["source"], cid)
            if key in merged:
                merged[key]["score"] += h["score"] * 0.5
            else:
                merged[key] = h
    ranked = sorted(merged.values(), key=lambda h: h["score"], reverse=True)
    _terms = re.findall(r"[a-z0-9\-]+", tsq)  # 向量命中无 snippet，统一在此补齐
    for h in ranked:
        if "snippet" not in h:
            h["snippet"] = _snippet(h["content"], _terms + zh)

    picked, per_title = [], {}
    for h in ranked:
        n = per_title.get(h["title"], 0)
        if n >= _PER_TITLE_CAP:
            continue
        per_title[h["title"]] = n + 1
        picked.append(h)
        if len(picked) >= topk * 2:
            break

    evidence = []
    for i, h in enumerate(picked, 1):
        page = None
        m = _PAGE_RE.search(h["section_path"] or "")
        if m:
            page = f"p{m.group(1)}" + (f"-{m.group(2)}" if m.group(2) else "")
        evidence.append({
            "n": i,
            "source_type": h["source"],
            "title": h["title"],
            "section_path": (h["section_path"] or "")[:200] or None,
            "page": page,
            "lang": h["lang"],
            "snippet": h["snippet"],
        })
    return evidence


def _llm_answer(q: str, evidence: list[dict]) -> dict:
    lines = []
    for e in evidence:
        sec = e["section_path"] or "（无章节信息）"
        lines.append(f"[{e['n']}] 《{e['title']}》 {sec}\n{e['snippet']}")
    prompt = f"【问题】{q}\n\n【证据】\n" + "\n\n".join(lines)

    payload = {
        "model": config.LLM_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": ASK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    last_error: Exception | None = None
    for _ in range(2):
        try:
            resp = httpx.post(
                f"{config.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                json=payload,
                timeout=90.0,
            )
            resp.raise_for_status()
            data = _extract_json(resp.json()["choices"][0]["message"]["content"])
            return {
                "answer": (data.get("answer") or "").strip(),
                "sufficient": bool(data.get("sufficient", True)),
                "limitations": (data.get("limitations") or "").strip() or None,
            }
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"LLM ask failed: {last_error}")


def ask(question: str, topk: int = 6) -> dict:
    t0 = time.time()
    question = (question or "").strip()
    if not question:
        raise ValueError("问题不能为空")
    topk = max(3, min(int(topk), 10))

    evidence = _collect_evidence(question, topk)
    result = {
        "question": question,
        "answer": None,
        "evidence_status": "answered",
        "citations": evidence,
        "limitations": None,
        "evidence_count": len(evidence),
        "took_ms": int((time.time() - t0) * 1000),
    }
    if not evidence:
        result["evidence_status"] = "no_evidence"
        result["answer"] = "当前语料（书籍分段 + 论文分段）中没有检索到与该问题相关的内容。"
        result["limitations"] = (
            "语料覆盖有限：书籍以露天矿边坡/爆破/规划/经济类英文专著与 GB/T 煤矿术语为主，"
            "论文为 Zotero 个人文库已解析部分。可尝试换用英文关键词，或补充相关文献后重试。"
        )
        return result
    if not config.LLM_ENABLED:
        result["evidence_status"] = "llm_disabled"
        result["answer"] = "未配置 LLM（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），以下为检索到的原文证据。"
        return result

    llm = _llm_answer(question, evidence)
    result["answer"] = llm["answer"] or None
    result["limitations"] = llm["limitations"]
    result["evidence_status"] = "answered" if llm["sufficient"] else "partial"
    result["took_ms"] = int((time.time() - t0) * 1000)
    return result
