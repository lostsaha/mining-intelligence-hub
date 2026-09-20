import Link from "next/link";
import { api, scoreColor } from "@/lib/api";

export const dynamic = "force-dynamic";

function ScoreBars({ person }) {
  const dims = [
    ["mining_relevance_score", "矿业相关性", "35%"],
    ["research_impact_score", "学术影响力", "20%"],
    ["recent_activity_score", "近期活跃", "15%"],
    ["topic_depth_score", "主题深度", "10%"],
    ["industry_score", "行业相关", "10%"],
    ["collaboration_score", "合作网络", "10%"],
  ];
  return (
    <div className="score-bars">
      {dims.map(([key, label, weight]) => {
        const v = Number(person[key] || 0);
        return (
          <div className="score-bar-row" key={key}>
            <span className="sb-label">{label}</span>
            <div className="sb-track">
              <div className="sb-fill" style={{ width: `${Math.min(100, v)}%` }} />
            </div>
            <span className="sb-value">{Math.round(v)}<small> {weight}</small></span>
          </div>
        );
      })}
    </div>
  );
}

export default async function ExpertDetail({ params }) {
  const { id } = await params;
  let data;
  try {
    data = await api(`/api/experts/${id}`);
  } catch {
    return (
      <div className="empty">
        <div className="big">🧑‍🔬</div>未找到该专家。
        <br />
        <Link href="/experts">← 返回专家榜单</Link>
      </div>
    );
  }
  const p = data.person;
  const evidenceMap = Object.fromEntries(
    (data.evidence || []).map((e) => [e.evidence_type, e.claim]),
  );
  const keyWorks = evidenceMap.key_works || {};
  const selection = evidenceMap.selection || {};
  const childTopics = data.topics.filter((t) => t.level === 2);
  const catTopics = data.topics.filter((t) => t.level === 1);

  return (
    <>
      <div className="page-head">
        <div className="sub">
          <Link href="/experts">← 专家榜单</Link>
          {p.expert_rank && ` · 全球排名 #${p.expert_rank}`}
        </div>
        <h1>
          {p.display_name}
          {p.admission_tier && (
            <span className={`admission-badge t${p.admission_tier}`} style={{ fontSize: 13, verticalAlign: "middle", marginLeft: 10 }}>
              {p.admission_tier === "T1" ? "院士/泰斗" : p.admission_tier === "T2" ? "院校教授" : p.admission_tier === "T3" ? "企业骨干" : "标准指南"}
            </span>
          )}
        </h1>
        <div className="sub">
          {p.institution_name || "机构未知"}
          {p.country_code && ` · ${p.country_code}`}
          {p.orcid && (
            <>
              {" · "}
              <a
                href={`https://orcid.org/${p.orcid}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                ORCID
              </a>
            </>
          )}
          {p.openalex_id && (
            <>
              {" · "}
              <a href={p.openalex_id} target="_blank" rel="noopener noreferrer">
                OpenAlex
              </a>
            </>
          )}
        </div>
        {p.admission_basis && (
          <div className="sub" style={{ color: "var(--accent)" }}>
            认证依据：{p.admission_basis}
          </div>
        )}
      </div>

      <div className="expert-card-grid">
        {/* 左列：评分与研究方向 */}
        <div className="card">
          <h2>综合评分</h2>
          <div className="big-score" style={{ color: scoreColor(p.final_score || 0) }}>
            {Math.round(p.final_score || 0)}
            <small>/100</small>
          </div>
          <ScoreBars person={p} />
          <div className="card-note">
            最终分 = 0.70 × Expert Score + 0.30 × Coverage（多样性补充）
          </div>
        </div>

        <div className="card">
          <h2>研究方向</h2>
          <div className="topic-rows">
            {(childTopics.length ? childTopics : catTopics).slice(0, 8).map((t) => {
              const maxW = Math.max(...(childTopics.length ? childTopics : catTopics).map((x) => Number(x.works_count || 0)), 1);
              const w = Number(t.works_count || 0);
              return (
                <div className="score-bar-row" key={t.slug}>
                  <span className="sb-label" title={t.name_en}>{t.name_zh}</span>
                  <div className="sb-track">
                    <div className="sb-fill" style={{ width: `${(w / maxW) * 100}%` }} />
                  </div>
                  <span className="sb-value">{w} 篇</span>
                </div>
              );
            })}
          </div>
          {p.summary_zh && <div className="card-note">{p.summary_zh}</div>}
        </div>

        {/* 右列：代表作品与网络 */}
        <div className="card">
          <h2>代表作品（经典）</h2>
          <ul className="work-list">
            {(keyWorks.classic || []).map((w) => (
              <li key={w.work_id}>
                <span className="work-title">{w.title}</span>
                <span className="work-meta">
                  {w.year || "—"} · 被引 {w.citations || 0}
                </span>
              </li>
            ))}
            {!(keyWorks.classic || []).length && <li>暂无</li>}
          </ul>
          <h2 style={{ marginTop: 18 }}>近 5 年高被引</h2>
          <ul className="work-list">
            {(keyWorks.recent || []).map((w) => (
              <li key={w.work_id}>
                <span className="work-title">{w.title}</span>
                <span className="work-meta">
                  {w.year || "—"} · 被引 {w.citations || 0}
                </span>
              </li>
            ))}
            {!(keyWorks.recent || []).length && <li>暂无</li>}
          </ul>
        </div>

        <div className="card">
          <h2>主要合作者</h2>
          <div className="chips">
            {data.coauthors.map((c) => (
              <Link
                key={c.person_id}
                href={c.is_selected ? `/experts/${c.person_id}` : "/experts"}
                className="chip"
              >
                {c.display_name}
                <span className="n">{c.shared_works}</span>
              </Link>
            ))}
            {!data.coauthors.length && <span className="sub">暂无</span>}
          </div>

          <h2 style={{ marginTop: 18 }}>为什么被选中？</h2>
          <ul className="evidence-list">
            <li>
              语料内 <b>{selection.corpus_works ?? p.corpus_works}</b> 篇矿业相关论文，
              累计被引 <b>{selection.corpus_citations ?? p.corpus_citations}</b> 次，
              其中近 5 年 <b>{selection.works_5y ?? "—"}</b> 篇；
            </li>
            <li>
              覆盖 <b>{selection.distinct_topics ?? data.topics.length}</b> 个矿业技术主题；
            </li>
            <li>综合评分各维度如左图所示，全部基于可追溯的语料证据（Evidence）计算。</li>
          </ul>

          {data.history.length > 1 && (
            <>
              <h2 style={{ marginTop: 18 }}>评分趋势</h2>
              <div className="sub">
                {data.history
                  .map((h) => `${h.score_date}: ${Math.round(h.final_score)} (#${h.rank ?? "-"})`)
                  .join(" → ")}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
