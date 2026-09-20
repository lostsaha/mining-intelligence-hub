import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function WorksPage({ searchParams }) {
  const params = await searchParams;
  const q = params.q || null;
  const topic = params.topic || null;
  const sort = params.sort || "citations";

  const [data, topicsData] = await Promise.all([
    api(
      `/api/works?limit=40&sort=${sort}` +
        `${q ? `&q=${encodeURIComponent(q)}` : ""}` +
        `${topic ? `&topic=${encodeURIComponent(topic)}` : ""}`,
    ),
    api("/api/radar?level=1"),
  ]);

  return (
    <>
      <div className="page-head">
        <h1>文献检索</h1>
        <div className="sub">
          语料内 {data.total} 篇论文（标题/摘要检索）· 可按被引量或年份排序 ·
          作者可跳转专家卡片
        </div>
        <form className="search-bar" action="/works" method="get">
          {topic && <input type="hidden" name="topic" value={topic} />}
          <input type="hidden" name="sort" value={sort} />
          <input name="q" defaultValue={q || ""} placeholder="搜索标题或摘要关键词…" />
          <button type="submit">搜索</button>
        </form>
      </div>

      <div className="chips">
        <Link href={`/works${q ? `?q=${encodeURIComponent(q)}` : ""}`} className={`chip ${!topic ? "active" : ""}`}>
          全部主题
        </Link>
        {topicsData.items.map((t) => (
          <Link
            key={t.slug}
            href={`/works?topic=${t.slug}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
            className={`chip ${topic === t.slug ? "active" : ""}`}
          >
            {t.name_zh}
          </Link>
        ))}
        <span style={{ flex: 1 }} />
        <Link
          href={`/works?sort=citations${topic ? `&topic=${topic}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
          className={`chip ${sort === "citations" ? "active" : ""}`}
        >
          按被引
        </Link>
        <Link
          href={`/works?sort=year${topic ? `&topic=${topic}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`}
          className={`chip ${sort === "year" ? "active" : ""}`}
        >
          按年份
        </Link>
      </div>

      {data.works.length === 0 ? (
        <div className="empty">
          <div className="big">📄</div>没有匹配的论文，换个关键词试试。
        </div>
      ) : (
        <div className="work-results">
          {data.works.map((w) => {
            const link = w.doi || null;
            return (
              <div className="item" key={w.work_id}>
                <div className="score" style={{ color: "#57534e" }}>
                  {w.publication_year || "—"}
                  <small>年</small>
                </div>
                <div className="body">
                  <div className="title">
                    {link ? (
                      <a href={link} target="_blank" rel="noopener noreferrer">{w.title}</a>
                    ) : (
                      w.title
                    )}
                  </div>
                  <div className="meta">
                    <span>被引 {w.cited_by_count}</span>
                    {w.source_name && (
                      <>
                        <span className="sep" />
                        <span>{w.source_name}</span>
                      </>
                    )}
                    {(w.topics || []).map((t) => (
                      <span key={t.slug} className="tag">{t.name_zh}</span>
                    ))}
                  </div>
                  {(w.authors || []).length > 0 && (
                    <div className="meta" style={{ marginTop: 4 }}>
                      {(w.authors || []).map((a) =>
                        a.selected ? (
                          <Link key={a.person_id} href={`/experts/${a.person_id}`} className="tag" style={{ background: "#fff3ea" }}>
                            👤 {a.name}
                          </Link>
                        ) : (
                          <span key={a.person_id} style={{ fontSize: 12.5 }}>{a.name}</span>
                        ),
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
