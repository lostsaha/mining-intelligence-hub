import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function JournalsPage({ searchParams }) {
  const params = await searchParams;
  const q = params.q || null;
  const sort = params.sort || "citations";

  const data = await api(
    `/api/journals?limit=100&sort=${sort}${q ? `&q=${encodeURIComponent(q)}` : ""}`,
  );
  const max = Math.max(...data.journals.map((j) => Number(j[sort === "avg" ? "avg_citations" : sort === "papers" ? "papers" : "total_citations"]) || 0), 1);

  const sorts = [
    { key: "citations", label: "按总被引" },
    { key: "avg", label: "按篇均被引" },
    { key: "papers", label: "按论文量" },
    { key: "name", label: "按名称" },
  ];

  return (
    <>
      <div className="page-head">
        <h1>期刊排名</h1>
        <div className="sub">
          语料内 {data.total} 种期刊（矿业论文 ≥5 篇才收录）·
          篇均被引可作期刊质量参考（非官方影响因子）·
          点击期刊名可看其全部论文
        </div>
        <form className="search-bar" action="/journals" method="get">
          <input type="hidden" name="sort" value={sort} />
          <input name="q" defaultValue={q || ""} placeholder="搜索期刊名…" />
          <button type="submit">搜索</button>
        </form>
      </div>

      <div className="chips">
        {sorts.map((s) => (
          <Link
            key={s.key}
            href={`/journals?sort=${s.key}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
            className={`chip ${sort === s.key ? "active" : ""}`}
          >
            {s.label}
          </Link>
        ))}
      </div>

      <div className="journal-list">
        {data.journals.map((j, i) => {
          const metric =
            sort === "avg" ? Number(j.avg_citations)
            : sort === "papers" ? Number(j.papers)
            : Number(j.total_citations);
          const share = j.papers > 0 ? Math.round((j.mining_papers / j.papers) * 100) : 0;
          return (
            <div className="journal-row" key={j.journal}>
              <div className="radar-rank" style={{ color: i < 3 ? "#c2410c" : "#a8a29e" }}>
                {String(i + 1).padStart(2, "0")}
              </div>
              <div className="radar-main">
                <div className="radar-title">
                  <Link
                    href={`/works?journal=${encodeURIComponent(j.journal)}`}
                    className="radar-name"
                  >
                    {j.journal}
                  </Link>
                </div>
                <div className="meta">
                  论文 <b>{j.papers}</b>（矿业 {j.mining_papers} · {share}%）·
                  总被引 {j.total_citations} · 篇均 {j.avg_citations} ·
                  {j.since_year}–{j.to_year}
                </div>
                <div className="sb-track" style={{ marginTop: 6, maxWidth: 420 }}>
                  <div
                    className="sb-fill"
                    style={{ width: `${(metric / max) * 100}%` }}
                  />
                </div>
              </div>
              <div className="score" style={{ color: "#c2410c" }}>
                {sort === "avg" ? j.avg_citations : j.total_citations}
                <small>{sort === "avg" ? "篇均" : "被引"}</small>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
