import { dayKey, scoreColor } from "@/lib/api";

function Summary({ item }) {
  const text = item.summary_zh || item.summary_raw || "";
  if (!text) return null;
  const trimmed = text.length > 140 ? `${text.slice(0, 140)}…` : text;
  return <div className="summary">{trimmed}</div>;
}

export function ItemRow({ item }) {
  const topics = item.topics || [];
  return (
    <div className="item">
      <div className="score" style={{ color: scoreColor(item.final_score || 0) }}>
        {Math.round(item.final_score || 0)}
        <small>分</small>
      </div>
      <div className="body">
        <div className="title">
          <a href={item.url} target="_blank" rel="noopener noreferrer">
            {item.title}
          </a>
        </div>
        <div className="meta">
          <span>{item.source_name}</span>
          <span className="sep" />
          <span>
            {item.published_at ? new Date(item.published_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "时间未知"}
          </span>
          {topics.map((t) => (
            <span key={t.slug} className="tag">{t.name_zh}</span>
          ))}
        </div>
        <Summary item={item} />
      </div>
    </div>
  );
}

export default function ItemList({ items }) {
  if (!items || items.length === 0) {
    return (
      <div className="empty">
        <div className="big">⛏</div>
        暂无内容 —— 点击首页「运行采集管线」，或稍后再来看看。
        <br />
        矿业行业更新节奏较慢，周精选是最适合的阅读方式。
      </div>
    );
  }
  const groups = new Map();
  for (const item of items) {
    const key = dayKey(item.published_at || item.collected_at);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return (
    <>
      {[...groups.entries()].map(([day, dayItems]) => (
        <section className="day-group" key={day}>
          <div className="day-label">{day}</div>
          {dayItems.map((item) => (
            <ItemRow key={item.item_id} item={item} />
          ))}
        </section>
      ))}
    </>
  );
}
