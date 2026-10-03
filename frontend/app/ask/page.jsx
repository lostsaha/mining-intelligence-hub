"use client";

import { useState } from "react";

const API_URL = process.env.API_URL || "http://127.0.0.1:8100";

const EXAMPLES = [
  "露天矿边坡监测有哪些常用方法？",
  "矿井突水预警有哪些技术手段？",
  "pre-split blasting design open pit",
  "Open Pit Mine Planning 中如何确定经济合理剥采比？",
];

const STATUS_LABEL = {
  answered: { text: "✅ 基于语料证据作答", cls: "ok" },
  partial: { text: "⚠️ 证据部分覆盖，结论仅供参考", cls: "warn" },
  no_evidence: { text: "❌ 语料中未检索到相关内容", cls: "warn" },
  llm_disabled: { text: "🔧 未配置 LLM，仅返回原文证据", cls: "warn" },
};

export default function AskPage() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function run(question) {
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await fetch(
        `${API_URL}/api/ask?q=${encodeURIComponent(question.trim())}`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setData(await res.json());
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>证据问答</h1>
        <div className="sub">
          从已入库的书籍分段（含页码）与论文分段（Zotero 全文）中检索原文证据，
          LLM 仅基于证据作答并标注引用编号 —— 证据不足时会明确说明。
        </div>
        <form
          className="search-bar"
          onSubmit={(e) => {
            e.preventDefault();
            run(q);
          }}
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="向语料提问，如：露天矿边坡监测有哪些方法？"
          />
          <button type="submit" disabled={loading || !q.trim()}>
            {loading ? "检索与作答中…" : "提问"}
          </button>
        </form>
        <div className="chips">
          {EXAMPLES.map((x) => (
            <button
              key={x}
              type="button"
              className="chip"
              style={{ cursor: "pointer" }}
              onClick={() => {
                setQ(x);
                run(x);
              }}
            >
              {x}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="card">正在检索全库分段并调用 LLM 作答，约需 10~60 秒…</div>}
      {error && <div className="card" style={{ color: "#b91c1c" }}>出错了：{error}</div>}

      {data && (
        <>
          <div className="card">
            <div style={{ marginBottom: 8 }}>
              <span
                className="chip active"
                title={`证据 ${data.evidence_count} 段 · 耗时 ${data.took_ms} ms`}
              >
                {(STATUS_LABEL[data.evidence_status] || {}).text || data.evidence_status}
              </span>
              <span className="chip">证据 {data.evidence_count} 段</span>
              <span className="chip">{(data.took_ms / 1000).toFixed(1)}s</span>
            </div>
            {data.answer ? (
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.75 }}>{data.answer}</div>
            ) : (
              <div style={{ color: "var(--muted, #666)" }}>（无综合作答，请看下方原文证据）</div>
            )}
            {data.limitations && (
              <div
                style={{
                  marginTop: 12,
                  padding: "8px 12px",
                  borderLeft: "3px solid #d97706",
                  background: "rgba(217,119,6,.08)",
                  fontSize: 13,
                  whiteSpace: "pre-wrap",
                }}
              >
                ⚠️ 局限说明：{data.limitations}
              </div>
            )}
          </div>

          <h2 style={{ margin: "20px 0 8px", fontSize: 18 }}>引用证据（{data.citations.length}）</h2>
          {data.citations.map((c) => (
            <div className="card" key={c.n} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "baseline" }}>
                <span className="chip active">[{c.n}]</span>
                <strong>{c.title}</strong>
                <span className="chip">{c.source_type === "book" ? "书籍" : "论文"}</span>
                {c.section_path && <span className="chip">{c.section_path}</span>}
                {c.page && <span className="chip">第 {c.page.replace("p", "")} 页</span>}
                {c.year && <span className="chip">{c.year}</span>}
              </div>
              <p style={{ margin: "8px 0 0", fontSize: 13.5, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                {c.snippet}
              </p>
            </div>
          ))}
        </>
      )}
    </>
  );
}
