export const metadata = { title: "关于 · 矿业前沿情报站" };

export default function About() {
  return (
    <>
      <div className="page-head">
        <h1>关于本平台</h1>
        <div className="sub">矿业垂直领域的前沿情报聚合 · 项目规划 v1.0</div>
      </div>
      <div style={{ background: "#fff", border: "1px solid var(--line)", borderRadius: 8, padding: "20px 24px", marginTop: 16, lineHeight: 1.9, fontSize: 14.5 }}>
        <p><b>这是什么？</b><br />
          参考 aihot（精选信源 + AI 预筛）与 Hacker News（单列信息流 + 排名）的聚合模式，为矿业行业定制的情报平台。完整规划见项目根目录 <code>PROJECT_PLAN.md</code>。</p>
        <p><b>为什么和一般资讯站不一样？</b><br />
          矿业信息与热点远少于互联网行业，更新以周/月为单位。因此本平台：<br />
          · 每天只采集一次精选白名单信源，而非海量抓取；<br />
          · 主打「每周精选」而非实时热榜；<br />
          · 时间衰减半衰期 14 天（HN 是小时级），好内容不会被快速冲走；<br />
          · 排序靠多因子算法：矿业相关性 35% + 信源权威度 25% + 新鲜度 20% + 内容深度 20%。</p>
        <p><b>评分怎么来的？</b><br />
          每条内容由 LLM（或关键词启发式回退）判定矿业相关性、归类到 14 个矿业主题（露天采矿、边坡稳定、矿山水文、钻爆、AI 与数字矿山等），再结合信源权威度与新鲜度计算综合分。加密货币挖矿等噪音内容会被直接过滤并记录原因。</p>
        <p><b>未来路线</b><br />
          Phase 2 将接入 OpenAlex 学术数据库，按《矿业专家—文献—技术知识图谱》设计自动发现并跟踪全球 100 位矿业专家；Phase 3 构建知识图谱与前沿技术雷达。</p>
      </div>
    </>
  );
}
