"use client";

import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { useRouter } from "next/navigation";

const NODE_COLOR = {
  category: "#c2410c",
  subtopic: "#ea580c",
  expert: "#44403c",
};

export default function GraphView({ data }) {
  const containerRef = useRef(null);
  const router = useRouter();
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (!containerRef.current || !data) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...data.nodes.map((n) => ({ data: { ...n } })),
        ...data.edges.map((e, i) => ({ data: { ...e, id: `e${i}` } })),
      ],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": (ele) => NODE_COLOR[ele.data("type")] || "#44403c",
            color: "#1c1917",
            "font-size": 11,
            "text-valign": "bottom",
            "text-margin-y": 5,
            width: "data(size)",
            height: "data(size)",
          },
        },
        {
          selector: "node[type='category']",
          style: { "font-size": 16, "font-weight": 700, color: "#c2410c" },
        },
        {
          selector: "edge",
          style: {
            width: (ele) => Math.min(6, 0.8 + (ele.data("weight") || 1) * 0.5),
            "line-color": (ele) =>
              ele.data("kind") === "coauthor" ? "#94a3b8"
              : ele.data("kind") === "works" ? "#fdba74" : "#e7e5e4",
            "curve-style": "bezier",
            opacity: 0.6,
          },
        },
      ],
      layout: { name: "cose", animate: true, padding: 40, nodeOverlap: 12 },
      wheelSensitivity: 0.25,
    });

    cy.on("tap", "node", (evt) => {
      const d = evt.target.data();
      if (d.type === "expert") {
        setSelected(d);
      } else if (d.type === "subtopic") {
        setSelected(d);
      } else {
        setSelected(null);
      }
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) setSelected(null);
    });

    return () => cy.destroy();
  }, [data]);

  return (
    <div style={{ position: "relative" }}>
      <div ref={containerRef} className="graph-container" />
      <div className="graph-legend">
        <span><i style={{ background: NODE_COLOR.category }} /> 大类</span>
        <span><i style={{ background: NODE_COLOR.subtopic }} /> 子主题</span>
        <span><i style={{ background: NODE_COLOR.expert }} /> 专家（点击查看卡片）</span>
        <span><i style={{ background: "#fdba74" }} /> 论文关系</span>
        <span><i style={{ background: "#94a3b8" }} /> 合作关系</span>
      </div>
      {selected && selected.type === "expert" && (
        <div className="graph-popup">
          <div className="gp-name">{selected.label}</div>
          <div className="gp-sub">
            {selected.institution || "机构未知"}
            {selected.h_index && ` · h-index ${selected.h_index}`}
            {selected.topic_works && ` · 该领域 ${selected.topic_works} 篇`}
          </div>
          <button onClick={() => router.push(`/experts/${selected.person_id}`)}>
            查看专家卡片 →
          </button>
        </div>
      )}
    </div>
  );
}
