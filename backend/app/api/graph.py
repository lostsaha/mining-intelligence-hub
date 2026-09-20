"""知识图谱子图 API：以主题为中心的 专家—子主题—合作者 网络（PostgreSQL 图查询）。"""
from __future__ import annotations

from fastapi import HTTPException

from .. import db


def subgraph(topic_slug: str, expert_limit: int = 24, min_shared: int = 2) -> dict:
    topic = db.query_one(
        "SELECT topic_id, slug, name_zh, name_en, level, parent_id FROM mining.topics WHERE slug = %s",
        (topic_slug,),
    )
    if not topic:
        raise HTTPException(404, "topic not found")

    if topic["level"] == 1:
        category = topic
    else:
        category = db.query_one(
            "SELECT topic_id, slug, name_zh, name_en, level, parent_id FROM mining.topics WHERE topic_id = %s",
            (topic["parent_id"],),
        )

    nodes: list[dict] = []
    edges: list[dict] = []

    # 中心节点 = 大类
    nodes.append({
        "id": f"topic:{category['slug']}", "label": category["name_zh"],
        "type": "category", "size": 60,
    })

    # 子主题节点（含量化）
    subtopics = db.query(
        """
        SELECT t.topic_id, t.slug, t.name_zh,
               COUNT(wt.work_id) AS works,
               (SELECT COUNT(DISTINCT pt.person_id) FROM mining.person_topic pt
                WHERE pt.topic_id = t.topic_id) AS experts
        FROM mining.topics t
        LEFT JOIN mining.work_topic wt ON wt.topic_id = t.topic_id
        WHERE t.parent_id = %s
        GROUP BY t.topic_id, t.slug, t.name_zh
        ORDER BY works DESC
        """,
        (category["topic_id"],),
    )
    sub_ids = {s["slug"] for s in subtopics}
    for s in subtopics:
        if s["works"] > 0:
            nodes.append({
                "id": f"topic:{s['slug']}", "label": s["name_zh"], "type": "subtopic",
                "size": max(18, min(44, 10 + s["works"] // 4)),
                "works": s["works"], "experts": s["experts"],
            })
            edges.append({
                "source": f"topic:{category['slug']}", "target": f"topic:{s['slug']}",
                "weight": 1, "kind": "structure",
            })

    # 专家节点：该类目下按主题作品数取前 N
    experts = db.query(
        """
        SELECT p.person_id, p.display_name, p.final_score, p.is_selected,
               (p.raw_data->>'h_index') AS h_index,
               i.name AS institution,
               SUM(pt.works_count) AS topic_works
        FROM mining.person_topic pt
        JOIN mining.persons p ON p.person_id = pt.person_id
        JOIN mining.topics t ON t.topic_id = pt.topic_id
        LEFT JOIN mining.institutions i ON i.institution_id = p.current_institution_id
        WHERE p.is_selected AND (t.slug = %s OR t.parent_id = %s)
        GROUP BY p.person_id, p.display_name, p.final_score, p.is_selected,
                 p.raw_data, i.name
        ORDER BY topic_works DESC, p.final_score DESC
        LIMIT %s
        """,
        (category["slug"], category["topic_id"], expert_limit),
    )
    expert_ids: list[int] = []
    for e in experts:
        expert_ids.append(e["person_id"])
        nodes.append({
            "id": f"expert:{e['person_id']}", "label": e["display_name"],
            "type": "expert", "size": max(16, min(40, 12 + int(e["topic_works"] or 0))),
            "score": float(e["final_score"] or 0), "institution": e["institution"],
            "h_index": e["h_index"], "topic_works": int(e["topic_works"] or 0),
            "person_id": e["person_id"],
        })

    # 专家 → 主攻子主题（在该类目内 works 最多的子主题）
    for e in experts:
        top_sub = db.query_one(
            """
            SELECT t.slug FROM mining.person_topic pt
            JOIN mining.topics t ON t.topic_id = pt.topic_id
            WHERE pt.person_id = %s AND t.parent_id = %s
            ORDER BY pt.works_count DESC LIMIT 1
            """,
            (e["person_id"], category["topic_id"]),
        )
        target = f"topic:{top_sub['slug']}" if top_sub and top_sub["slug"] in sub_ids \
            else f"topic:{category['slug']}"
        edges.append({
            "source": f"expert:{e['person_id']}", "target": target,
            "weight": max(1, int(e["topic_works"] or 0) // 3), "kind": "works",
        })

    # 合作者边（限定在入选专家集合内，共作 ≥ min_shared 才连线）
    if len(expert_ids) >= 2:
        for r in db.query(
            """
            SELECT pw1.person_id AS a, pw2.person_id AS b, COUNT(*) AS shared
            FROM mining.person_work pw1
            JOIN mining.person_work pw2
              ON pw1.work_id = pw2.work_id
             AND pw1.person_id < pw2.person_id
            WHERE pw1.person_id = ANY(%s) AND pw2.person_id = ANY(%s)
            GROUP BY pw1.person_id, pw2.person_id
            HAVING COUNT(*) >= %s
            ORDER BY shared DESC
            LIMIT 120
            """,
            (expert_ids, expert_ids, min_shared),
        ):
            edges.append({
                "source": f"expert:{r['a']}", "target": f"expert:{r['b']}",
                "weight": int(r["shared"]), "kind": "coauthor",
                "shared": int(r["shared"]),
            })

    return {
        "category": {"slug": category["slug"], "name_zh": category["name_zh"],
                     "name_en": category["name_en"]},
        "nodes": nodes, "edges": edges,
    }
