import Link from "next/link";
import { api, scoreColor } from "@/lib/api";

export const dynamic = "force-dynamic";

function RankBadge({ rank }) {
  const color = rank <= 3 ? "#c2410c" : rank <= 10 ? "#ea580c" : "#9a3412";
  return (
    <div className="rank-badge" style={{ background: color }}>
      #{rank}
    </div>
  );
}

export default async function ExpertsPage({ searchParams }) {
  const params = await searchParams;
  const topic = params.topic || null;
  const q = params.q || null;
  const tier = params.tier || null;

  const [meta, data] = await Promise.all([
    api("/api/experts/meta"),
    api(
      `/api/experts?limit=150${topic ? `&topic=${encodeURIComponent(topic)}` : ""}${
        q ? `&q=${encodeURIComponent(q)}` : ""
      }${tier ? `&tier=${encodeURIComponent(tier)}` : ""}`,
    ),
  ]);

  const tierChips = [
    { key: "certified", label: "🎖 认证专家" },
    { key: "T1", label: "院士/泰斗" },
    { key: "T2", label: "院校教授" },
    { key: "T3", label: "企业骨干" },
    { key: "T4", label: "标准指南" },
  ];

  return (
    <>
      <div className="page-head">
        <h1>全球矿业专家 Top {meta.total}</h1>
        <div className="sub">
          依据 OpenAlex 学术语料自动发现：MiningExpertScore（相关性 35% · 影响力 20% ·
          活跃度 15% · 主题深度 10% · 行业 10% · 合作 10%）× Coverage 多样性约束 ·
          叠加 <Link href="/admissions">固定名册</Link> 认证对比
        </div>
        <form className="search-bar" action="/experts" method="get">
          {topic && <input type="hidden" name="topic" value={topic} />}
          {tier && <input type="hidden" name="tier" value={tier} />}
          <input
            name="q"
            defaultValue={q || ""}
            placeholder="搜索专家姓名或机构（支持中文名）…"
          />
          <button type="submit">搜索</button>
        </form>
      </div>

      <div className="chips">
        <Link href="/experts" className={`chip ${!tier ? "active" : ""}`}>
          算法榜
        </Link>
        {tierChips.map((t) => (
          <Link
            key={t.key}
            href={`/experts?tier=${t.key}`}
            className={`chip ${tier === t.key ? "active" : ""}`}
          >
            {t.label}
          </Link>
        ))}
        <span style={{ flex: 1 }} />
        <Link href="/admissions" className="chip">名册对照 →</Link>
      </div>

      <div className="chips">
        <Link href="/experts" className={`chip ${!topic ? "active" : ""}`}>
          全部
          <span className="n">{meta.total}</span>
        </Link>
        {meta.categories.map((c) => (
          <Link
            key={c.slug}
            href={`/experts?topic=${c.slug}`}
            className={`chip ${topic === c.slug ? "active" : ""}`}
          >
            {c.name_zh}
            <span className="n">{c.expert_count}</span>
          </Link>
        ))}
      </div>

      {data.experts.length === 0 ? (
        <div className="empty">
          <div className="big">🧑‍🔬</div>
          还没有专家数据 —— 先在服务器运行
          <code> python -m app.experts.run</code> 采集 OpenAlex 语料。
        </div>
      ) : (
        <div className="expert-list">
          {data.experts.map((e) => (
            <Link
              key={e.person_id}
              href={`/experts/${e.person_id}`}
              className="expert-row"
            >
              <RankBadge rank={e.expert_rank} />
              <div className="body">
                <div className="title">
                  {e.admission_name_zh || e.display_name}
                  {e.admission_tier && (
                    <span className={`admission-badge t${e.admission_tier}`}>
                      {e.admission_tier === "T1" ? "院士/泰斗" : e.admission_tier === "T2" ? "教授" : e.admission_tier === "T3" ? "企业骨干" : "标准指南"}
                    </span>
                  )}
                  {e.h_index && <span className="hindex">h-index {e.h_index}</span>}
                </div>
                <div className="meta">
                  <span>{e.institution_name || "机构未知"}</span>
                  {e.country_code && (
                    <>
                      <span className="sep" />
                      <span>{e.country_code}</span>
                    </>
                  )}
                  <span className="sep" />
                  <span>{e.corpus_works} 篇 · 被引 {e.corpus_citations}</span>
                </div>
                {e.summary_zh && <div className="summary">{e.summary_zh}</div>}
                <div className="meta" style={{ marginTop: 4 }}>
                  {(e.topics || []).map((t) => (
                    <span key={t.slug} className="tag">{t.name_zh}</span>
                  ))}
                </div>
              </div>
              <div className="score" style={{ color: scoreColor(e.final_score || 0) }}>
                {Math.round(e.final_score || 0)}
                <small>分</small>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
