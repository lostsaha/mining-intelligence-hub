import Link from "next/link";
import { api } from "@/lib/api";
import GraphView from "./graph-view";

export const dynamic = "force-dynamic";

export default async function GraphPage({ searchParams }) {
  const params = await searchParams;
  const topic = params.topic || "geotech-slope";

  const [chipsData, graph] = await Promise.all([
    api("/api/radar?level=1"),
    api(`/api/graph?topic=${encodeURIComponent(topic)}&expert_limit=24`),
  ]);

  return (
    <>
      <div className="page-head">
        <h1>矿业知识图谱</h1>
        <div className="sub">
          MELTG 图谱可视化（PostgreSQL 图查询）：大类 → 子主题 → 专家 → 合作者网络 ·
          节点大小 = 论文量 / 评分 · 点击专家节点查看详情
        </div>
      </div>

      <div className="chips">
        {chipsData.items.map((t) => (
          <Link
            key={t.slug}
            href={`/graph?topic=${t.slug}`}
            className={`chip ${topic === t.slug ? "active" : ""}`}
          >
            {t.name_zh}
          </Link>
        ))}
      </div>

      <GraphView data={graph} />
    </>
  );
}
