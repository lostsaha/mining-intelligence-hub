import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const TIER_COLOR = {
  S0: "#991b1b", "A-": "#c2410c", "A": "#b45309",
  "B+": "#1d4ed8", "B": "#15803d", "B-": "#7c3aed", C: "#6b7280", D: "#a8a29e",
};

export default async function SourcesPage() {
  const data = await api("/api/sources");
  return (
    <>
      <div className="page-head">
        <h1>全球矿业信源金字塔</h1>
        <div className="sub">
          八级信源体系：S0 政府/监管 · A 国际标准 · A- 公司披露 · B+ 商业数据库 ·
          B 专业媒体 · B- 学术文献 · C 专家渠道 · D 普通媒体/论坛
        </div>
      </div>
      {data.tiers.map((layer) => (
        <section key={layer.tier}>
          <h2 className="layer-title">
            <span className="tier-badge" style={{ background: TIER_COLOR[layer.tier] || "#57534e" }}>
              {layer.tier}
            </span>
            {layer.name}
            <span className="badge" style={{ marginLeft: 8 }}>
              {layer.sources.length} 个
            </span>
          </h2>
          <div className="sub" style={{ marginBottom: 6 }}>{layer.description}</div>
          <div className="source-grid">
            {layer.sources.map((s) => {
              const collectible = Boolean(s.feed_url) && s.active;
              return (
                <div className="source-card" key={s.source_id}>
                  <div className="name">
                    <span>{s.name}</span>
                    <span className={`badge ${collectible ? "" : "inactive"}`}>
                      {collectible ? "采集中" : s.feed_url ? "停用" : "人工查阅"}
                    </span>
                  </div>
                  <div className="stat">
                    权威度 {s.authority_weight}/10 · 已收录 {s.approved_count} 条
                    {s.lang === "zh" && " · 中文"}
                  </div>
                  {s.notes && <div className="stat">{s.notes}</div>}
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </>
  );
}
