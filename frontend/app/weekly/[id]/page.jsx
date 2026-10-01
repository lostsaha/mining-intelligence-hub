import { ItemRow } from "../../components/item-list";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function WeeklyDetail({ params }) {
  const { id } = await params;
  const digest = await api(`/api/weekly/${id}`);
  return (
    <>
      <div className="page-head">
        <h1>{digest.title}</h1>
        <div className="sub">{digest.summary}</div>
      </div>

      {(digest.disclosures || []).length > 0 && (
        <section className="topic-section disclosure-box">
          <h2>📄 技术报告与披露提示</h2>
          <div className="sub" style={{ marginBottom: 6 }}>
            本周出现资源量/储量/可研类消息。按证据链原则（新闻 → 交易所公告 → 技术报告），
            重大决策请以 A-/S0 一手披露为准：SEC EDGAR / ASX 公告 / 公司官网技术报告。
          </div>
          {digest.disclosures.map((d) => (
            <div className="item" key={d.item_id}>
              <div className="score" style={{ color: "#b45309" }}>报告</div>
              <div className="body">
                <div className="title">
                  <a href={d.url} target="_blank" rel="noopener noreferrer">{d.title}</a>
                </div>
                <div className="meta">
                  <span>{d.source_name}</span>
                  {d.summary_zh && <div className="summary" style={{ marginTop: 2 }}>{d.summary_zh}</div>}
                </div>
              </div>
            </div>
          ))}
        </section>
      )}

      {digest.groups.map((g) => (
        <section className="topic-section" key={g.slug}>
          <h2>{g.name_zh}</h2>
          {g.items.map((item) => (
            <ItemRow key={item.item_id} item={item} />
          ))}
        </section>
      ))}
    </>
  );
}
