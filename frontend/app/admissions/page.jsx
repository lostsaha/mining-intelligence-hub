import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const TIER_LABEL = { T1: "院士/泰斗", T2: "院校教授", T3: "企业骨干", T4: "标准指南" };

export default async function AdmissionsPage() {
  const data = await api("/api/admissions");
  const { rows, dual } = data;

  return (
    <>
      <div className="page-head">
        <h1>固定名册 × 算法榜对照</h1>
        <div className="sub">
          固定名册（{data.total} 人）是权威基准：院士/泰斗直通、院校教授、企业骨干、标准指南编写者 ·
          与算法 Top 100 交叉对照形成三类信号
        </div>
      </div>

      <div className="adm-stats">
        <div className="adm-stat good">
          <div className="n">{data.dual_count}</div>双重入选（高置信）
        </div>
        <div className="adm-stat warn">
          <div className="n">{data.blind_spot_count}</div>仅名册（算法盲区）
        </div>
        <div className="adm-stat">
          <div className="n">{data.algo_only_count}</div>仅算法（无认证）
        </div>
        <div className="adm-stat">
          <div className="n">{data.independent_count}</div>独立记录（语料外）
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>按层级分布</h2>
        <div className="chips" style={{ paddingTop: 4 }}>
          {Object.entries(data.by_tier).sort().map(([t, n]) => (
            <span key={t} className="chip">{TIER_LABEL[t] || t}<span className="n">{n}</span></span>
          ))}
        </div>
        <div className="card-note">
          算法盲区说明：名册权威人士未进入算法 Top 100，通常因为语料语言偏差（中文/俄语区）、
          工程实践型专家论文产量低、或高龄泰斗近年不发文——这正是固定名册兜底的价值。
        </div>
      </div>

      <h2 className="layer-title">双重入选 · 算法榜 ∩ 名册（{data.dual_count}）</h2>
      <div className="adm-grid">
        {dual.filter((r) => r.is_selected).map((r) => (
          <Link key={r.roster_key} href={`/experts/${r.person_id}`} className="source-card">
            <div className="name">
              <span>{r.name_zh || r.full_name}</span>
              <span className="badge" style={{ background: "#dcfce7", color: "#15803d" }}>
                #{r.expert_rank}
              </span>
            </div>
            <div className="stat">{TIER_LABEL[r.tier]} · {r.channel} · 综合分 {Math.round(r.final_score || 0)}</div>
            <div className="stat">{r.basis}</div>
          </Link>
        ))}
      </div>

      <h2 className="layer-title">算法盲区 · 名册认证但未入算法榜（{data.blind_spot_count}）</h2>
      <div className="adm-grid">
        {data.blind_spot.map((r) => (
          <div className="source-card" key={r.roster_key}>
            <div className="name">
              <span>{r.name_zh || r.full_name}</span>
              <span className="badge" style={{ background: "#fef3c7", color: "#b45309" }}>
                {TIER_LABEL[r.tier]}
              </span>
            </div>
            <div className="stat">{r.affiliation || r.institution_name || ""} {r.country_code || ""}</div>
            <div className="stat">{r.basis}</div>
          </div>
        ))}
      </div>

      <h2 className="layer-title">独立记录 · OpenAlex 未建档（{data.independent_count}）</h2>
      <div className="adm-grid">
        {data.independent.map((r) => (
          <div className="source-card" key={r.roster_key}>
            <div className="name">
              <span>{r.name_zh || r.full_name}</span>
              <span className="badge inactive">语料外</span>
            </div>
            <div className="stat">{TIER_LABEL[r.tier]} · {r.channel}</div>
            <div className="stat">{r.review_note}</div>
          </div>
        ))}
      </div>
    </>
  );
}
