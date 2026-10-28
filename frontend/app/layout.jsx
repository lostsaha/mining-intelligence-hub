import "./globals.css";
import NavLinks from "./components/nav-links";

export const metadata = {
  title: "矿业前沿情报站 · Mining Intelligence Hub",
  description: "矿业垂直领域的前沿信息聚合：精选信源、AI 过滤、主题频道与每周精选",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="site">
          <div className="container">
            <a className="brand" href="/">
              ⛏ 矿业前沿
              <small>Mining Intelligence Hub</small>
            </a>
            <NavLinks />
          </div>
        </header>
        <main className="container">{children}</main>
        <footer className="site">
          <div className="container foot-grid">
            <div>
              <div className="foot-brand">⛏ 矿业前沿情报站</div>
              <div>每日采集精选信源 · AI 过滤打分 · 按矿业主题组织</div>
            </div>
            <div>
              <div className="foot-h">数据</div>
              <a href="/works">文献检索</a> · <a href="/journals">期刊排名</a> ·{" "}
              <a href="/graph">知识图谱</a>
            </div>
            <div>
              <div className="foot-h">项目</div>
              设计原则见 <a href="/about">项目规划</a> · 语义检索由
              pgvector + bge-m3 驱动
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
