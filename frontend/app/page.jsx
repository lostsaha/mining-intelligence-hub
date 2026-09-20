import Link from "next/link";
import { api } from "@/lib/api";
import ItemList from "./components/item-list";
import PipelineButton from "./components/pipeline-button";

export const dynamic = "force-dynamic";

export default async function Home({ searchParams }) {
  const params = await searchParams;
  const topic = params.topic || null;

  const [topicsData, itemsData, stats] = await Promise.all([
    api("/api/topics"),
    api(`/api/items?days=30&limit=120${topic ? `&topic=${encodeURIComponent(topic)}` : ""}`),
    api("/api/stats"),
  ]);

  return (
    <>
      <div className="page-head">
        <h1>矿业信息流</h1>
        <div className="sub">
          过去 30 天 · {itemsData.total} 条精选 · 信源 {stats.sources.active} 个 ·
          累计采集 {stats.items.total} 条
          {stats.last_run?.finished_at &&
            ` · 上次采集 ${new Date(stats.last_run.finished_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}`}
        </div>
        <PipelineButton />
      </div>

      <div className="chips">
        <Link href="/" className={`chip ${!topic ? "active" : ""}`}>
          全部
        </Link>
        {topicsData.topics
          .filter((t) => t.item_count > 0)
          .map((t) => (
            <Link
              key={t.slug}
              href={`/?topic=${t.slug}`}
              className={`chip ${topic === t.slug ? "active" : ""}`}
            >
              {t.name_zh}
              <span className="n">{t.item_count}</span>
            </Link>
          ))}
      </div>

      <ItemList items={itemsData.items} />
    </>
  );
}
