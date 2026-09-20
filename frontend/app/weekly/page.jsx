import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function WeeklyList() {
  const data = await api("/api/weekly");
  return (
    <>
      <div className="page-head">
        <h1>每周精选</h1>
        <div className="sub">
          矿业信息以周为单位聚合最有价值 —— 每期按主题精选 Top 20，替代低密度的实时热榜。
        </div>
      </div>
      {data.digests.length === 0 ? (
        <div className="empty">
          <div className="big">📰</div>
          还没有周报 —— 在首页运行采集管线后自动生成。
        </div>
      ) : (
        data.digests.map((d) => (
          <Link className="digest-card" key={d.digest_id} href={`/weekly/${d.digest_id}`}>
            <h2>{d.title}</h2>
            <div className="sub">
              {d.summary} · 生成于{" "}
              {new Date(d.generated_at).toLocaleString("zh-CN")}
            </div>
          </Link>
        ))
      )}
    </>
  );
}
