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
