import Link from "next/link";
import { ItemRow } from "../../components/item-list";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TopicPage({ params }) {
  const { slug } = await params;
  const topic = await api(`/api/topics/${slug}`);
  return (
    <>
      <div className="page-head">
        <h1>{topic.name_zh}</h1>
        <div className="sub">
          {topic.name_en} · {topic.items.length} 条 · 按综合评分排序（权威度 + 相关性 +
          新鲜度 + 深度）
        </div>
      </div>
      <div className="chips">
        <Link href="/" className="chip">← 返回全部主题</Link>
      </div>
      {topic.items.length === 0 ? (
        <div className="empty">
          <div className="big">⛏</div>该主题下暂无内容，运行采集管线后会有更多。
        </div>
      ) : (
        topic.items.map((item) => <ItemRow key={item.item_id} item={item} />)
      )}
    </>
  );
}
