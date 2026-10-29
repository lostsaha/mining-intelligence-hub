r"""RAG 评测跑分器：逐题调 ask()（LLM 实跑），按金标准评分，输出报告。
用法：python scripts/run_rag_eval.py [--limit N]（结果存 docs/rag_eval_report.md + .json）
指标：来源命中率（金标准关键词出现在任一引用标题）、必答关键词命中率（出现在回答）、
answered 率、引用 [n] 有效性。
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from app.api.ask import ask  # noqa: E402
from app import config  # noqa: E402

EVAL = Path(r"E:\syn\矿业聚合平台\backend\data\rag_eval.json")
OUT_MD = Path(r"E:\syn\矿业聚合平台\docs\rag_eval_report.md")
OUT_JSON = Path(r"E:\syn\矿业聚合平台\docs\rag_eval_report.json")


def main() -> int:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    if not config.LLM_ENABLED:
        print("LLM 未启用（.env），评测无意义")
        return 1
    data = json.loads(EVAL.read_text(encoding="utf-8"))
    qs = data["questions"][: limit] if limit else data["questions"]
    results = []
    for i, item in enumerate(qs, 1):
        q = item["q"]
        t0 = time.time()
        try:
            r = ask(q, topk=8)
        except Exception as exc:
            results.append({"q": q, "error": str(exc)[:120]})
            print(f"[{i}/{len(qs)}] ERROR {str(exc)[:60]}")
            continue
        titles = " | ".join(str(c.get("title") or "") for c in r.get("citations", []))
        answer = r.get("answer") or ""
        src_hit = any(s.lower() in titles.lower() for s in item["sources"])
        kw_hit = [k for k in item["answer_kw"] if k in answer]
        kw_ok = len(kw_hit) >= max(1, len(item["answer_kw"]) - 1)
        n_refs = [int(x) for x in re.findall(r"\[(\d+)\]", answer)]
        ref_ok = all(1 <= n <= len(r.get("citations", [])) for n in n_refs)
        results.append({
            "q": q, "status": r["evidence_status"], "n_evidence": r["evidence_count"],
            "src_hit": src_hit, "kw_hit": kw_hit, "kw_ok": kw_ok,
            "ref_ok": ref_ok, "took_ms": r.get("took_ms"),
            "hit_titles": [s for s in item["sources"] if s.lower() in titles.lower()],
        })
        print(f"[{i}/{len(qs)}] {r['evidence_status']:9s} 来源{'✓' if src_hit else '✗'} "
              f"关键词{'✓' if kw_ok else '✗'} 引用{'✓' if ref_ok else '✗'} {q[:36]}")

    n = len(results)
    ok = [r for r in results if "error" not in r]
    summary = {
        "total": n,
        "source_hit_rate": round(sum(r["src_hit"] for r in ok) / max(1, len(ok)), 3),
        "keyword_rate": round(sum(r["kw_ok"] for r in ok) / max(1, len(ok)), 3),
        "ref_valid_rate": round(sum(r["ref_ok"] for r in ok) / max(1, len(ok)), 3),
        "answered_rate": round(sum(r["status"] in ("answered", "partial") for r in ok) / max(1, len(ok)), 3),
    }
    print("\n== 汇总 ==")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    OUT_JSON.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# RAG 评测报告", "",
          f"- 题数 {summary['total']} · 来源命中 {summary['source_hit_rate']:.0%} · "
          f"关键词 {summary['keyword_rate']:.0%} · 引用有效 {summary['ref_valid_rate']:.0%} · "
          f"answered {summary['answered_rate']:.0%}", ""]
    for r in ok:
        md.append(f"- [{'✓' if r['src_hit'] else '✗'}{'✓' if r['kw_ok'] else '✗'}] {r['q']}")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"报告 → {OUT_MD.name} / {OUT_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
