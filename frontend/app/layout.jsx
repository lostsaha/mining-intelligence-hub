import "./globals.css";

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
            <nav className="main">
              <a href="/">信息流</a>
              <a href="/weekly">周报</a>
              <a href="/experts">专家</a>
              <a href="/admissions">名册</a>
              <a href="/radar">雷达</a>
              <a href="/graph">图谱</a>
              <a href="/works">文献</a>
              <a href="/sources">信源</a>
              <a href="/about">关于</a>
            </nav>
          </div>
        </header>
        <main className="container">{children}</main>
        <footer className="site">
          矿业前沿情报站 · 每日采集精选信源，AI 过滤打分，按矿业主题组织 ·
          设计原则见 <a href="/about">项目规划</a>
        </footer>
      </body>
    </html>
  );
}
