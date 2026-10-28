"use client";

import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "信息流"],
  ["/weekly", "周报"],
  ["/ask", "问答"],
  ["/experts", "专家"],
  ["/admissions", "名册"],
  ["/radar", "雷达"],
  ["/graph", "图谱"],
  ["/works", "文献"],
  ["/journals", "期刊"],
  ["/sources", "信源"],
  ["/about", "关于"],
];

export default function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="main">
      {LINKS.map(([href, label]) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <a key={href} href={href} className={active ? "active" : ""}>
            {label}
          </a>
        );
      })}
    </nav>
  );
}
