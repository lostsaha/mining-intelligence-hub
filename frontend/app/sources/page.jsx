import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  const data = await api("/api/sources");
  return (
    <>
      <div className="page-head">
        <h1>信源目录</h1>
        <div className="sub">
          白名单制 · 按四层体系组织（专家 → 公司 → 组织 → 期刊/媒体）·
          权威度参与条目综合评分
        </div>
      </div>
      {data.layers.map((layer) => (
        <section key={layer.layer}>
          <h2 className="layer-title">
            第 {["一", "二", "三", "四"][layer.layer - 1]}层 · {layer.name}
            <span className="badge" style={{ marginLeft: 8 }}>
              {layer.sources.length} 个
            </span>
          </h2>
          <div className="source-grid">
            {layer.sources.map((s) => (
              <div className="source-card" key={s.source_id}>
                <div className="name">
                  <span>{s.name}</span>
                  {!s.active && <span className="badge inactive">停用</span>}
                </div>
                <div className="stat">
                  权威度 {s.authority_weight}/10 · 已收录 {s.approved_count} 条
                  {s.lang === "zh" && " · 中文"}
                </div>
                {s.notes && <div className="stat">{s.notes}</div>}
              </div>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
