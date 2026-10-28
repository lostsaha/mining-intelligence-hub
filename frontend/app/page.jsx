import Link from "next/link";
import { api, formatDateTime, dayKey } from "@/lib/api";
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

  const topTopics = topicsData.topics
    .filter((t) => t.item_count > 0)
    .sort((a, b) => b.item_count - a.item_count);
  const days = [...new Set(itemsData.items.map((i) => dayKey(i.published_at || i.collected_at)))];
  const activeSources = stats.sources?.active ?? "-";

  const side = (
    <aside className="side-panel">
      <div className="card side-card">
        <h2>本站概况</h2>
        <div className="side-stats">
          <div className="ss-row">
            <span>30 天精选</span>
            <b>{itemsData.total}</b>
          </div>
          <div className="ss-row">
            <span>活跃信源</span>
            <b>{activeSources}</b>
          </div>
          <div className="ss-row">
            <span>累计采集</span>
            <b>{stats.items.total}</b>
          </div>
          <div className="ss-row">
            <span>最近采集</span>
            <b>
              {stats.last_run?.finished_at ? formatDateTime(stats.last_run.finished_at) : "—"}
            </b>
          </div>
        </div>
        <PipelineButton />
      </div>

      <div className="card side-card">
        <h2>主题频道</h2>
        <div className="side-topics">
          {topTopics.map((t) => (
            <Link
              key={t.slug}
              href={`/?topic=${t.slug}`}
              className={`side-topic ${topic === t.slug ? "active" : ""}`}
            >
              <span>{t.name_zh}</span>
              <span className="n">{t.item_count}</span>
            </Link>
          ))}
        </div>
        <Link href="/" className={`side-all ${!topic ? "active" : ""}`}>
          查看全部主题
        </Link>
      </div>

      <div className="card side-card side-cta">
        <h2>证据问答</h2>
        <p>向全库书籍、标准与 2,158 篇论文提问，回答附原文引用。</p>
        <Link href="/ask" className="side-btn">
          进入问答 →
        </Link>
      </div>
    </aside>
  );

  return (
    <>
      <div className="page-head">
        <h1>矿业信息流</h1>
        <div className="sub">
          过去 30 天 · {itemsData.total} 条精选 · 信源 {activeSources} 个 ·
          累计采集 {stats.items.total} 条
          {stats.last_run?.finished_at &&
            ` · 上次采集 ${formatDateTime(stats.last_run.finished_at)}`}
        </div>
        <PipelineButton />
      </div>

      <div className="chips">
        <Link href="/" className={`chip ${!topic ? "active" : ""}`}>
          全部
        </Link>
        {topTopics.slice(0, 12).map((t) => (
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

      <div className={`home-grid ${topic ? "no-side" : ""}`}>
        <div className="feed-col">
          <ItemList items={itemsData.items} />
          <div className="day-jump">
            覆盖日期：{days[0]} → {days[days.length - 1] || ""}
          </div>
        </div>
        {!topic && side}
      </div>
    </>
  );
}
