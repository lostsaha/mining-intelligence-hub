import Link from "next/link";
import { api, scoreColor } from "@/lib/api";

export const dynamic = "force-dynamic";

const MOMENTUM_STYLE = {
  emerging: { bg: "#7c3aed", zh: "新兴" },
  rising: { bg: "#dc2626", zh: "快速升温" },
  steady: { bg: "#15803d", zh: "平稳" },
  cooling: { bg: "#2563eb", zh: "降温" },
  watch: { bg: "#a8a29e", zh: "观察中" },
};

function YearBars({ yearly }) {
  if (!yearly || yearly.length === 0) return null;
  const max = Math.max(...yearly.map((y) => y.count), 1);
  return (
    <div className="year-bars" title={yearly.map((y) => `${y.year}: ${y.count} 篇`).join("  ")}>
      {yearly.map((y) => (
        <div key={y.year} className="yb-col">
          <div
            className="yb-bar"
            style={{ height: `${Math.max(8, (y.count / max) * 40)}px` }}
          />
          <span className="yb-year">'{String(y.year).slice(2)}</span>
        </div>
      ))}
    </div>
  );
}

export default async function RadarPage({ searchParams }) {
  const params = await searchParams;
  const parent = params.parent || null;
  const level = parent ? 2 : 1;

  const [data, chipsData] = await Promise.all([
    api(`/api/radar?level=${level}${parent ? `&parent=${encodeURIComponent(parent)}` : ""}`),
    api("/api/radar?level=1"),
  ]);

  return (
    <>
      <div className="page-head">
        <h1>前沿技术雷达</h1>
        <div className="sub">
          热度 = 0.45 × 论文增速（近12月 vs 前12月） + 0.30 × 近12月产量 + 0.25 × 专家聚集度 ·
          交叉信号用于识别正在形成或升温的技术方向
        </div>
      </div>

      <div className="chips">
        <Link href="/radar" className={`chip ${!parent ? "active" : ""}`}>
          大类视图
        </Link>
        {chipsData.items.map((t) => (
          <Link
            key={t.slug}
            href={`/radar?parent=${t.slug}`}
            className={`chip ${parent === t.slug ? "active" : ""}`}
          >
            {t.name_zh}
          </Link>
        ))}
      </div>

      <div className="radar-list">
        {data.items.map((t, i) => {
          const m = MOMENTUM_STYLE[t.momentum] || MOMENTUM_STYLE.steady;
          return (
            <div className="radar-row" key={t.slug}>
              <div className="radar-rank" style={{ color: i < 3 ? "#c2410c" : "#a8a29e" }}>
                {String(i + 1).padStart(2, "0")}
              </div>
              <div className="radar-main">
                <div className="radar-title">
                  <span className="radar-name">{t.name_zh}</span>
                  <span className="badge" style={{ background: m.bg, color: "#fff" }}>
                    {m.zh}
                  </span>
                  {t.new_experts > 0 && (
                    <span className="badge" style={{ background: "#f5f5f4", color: "#7c3aed" }}>
                      +{t.new_experts} 新专家
                    </span>
                  )}
                </div>
                <div className="meta">
                  近12月 <b>{t.w12}</b> 篇（去年同期 {t.wprev}，×{t.growth_ratio}）·
                  新增被引 {t.c12} · 活跃专家 {t.experts} 人 · 累计 {t.total} 篇
                </div>
              </div>
              <YearBars yearly={t.yearly} />
              <div className="score" style={{ color: scoreColor(t.heat) }}>
                {Math.round(t.heat)}
                <small>热度</small>
              </div>
            </div>
          );
        })}
      </div>
      {data.items.length === 0 && (
        <div className="empty">
          <div className="big">📡</div>该类目下暂无语料。
        </div>
      )}
    </>
  );
}
