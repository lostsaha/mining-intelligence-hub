"""纯函数/静态契约测试：不依赖数据库、网络或 LLM。"""
from pathlib import Path

from app.api.ask import _extract_terms, _validate_citations
from app.experts.collect_admitted import global_classify
from app.process import digest, heuristic
from app.process.llm import _as_bool

ROOT = Path(__file__).resolve().parents[1]


def test_heuristic_rejects_finance_and_ambiguity():
    for title in (
        "Gold prices rise as investors seek safety",
        "Copper wire demand is booming",
        "Gold price recovery continues",
        "Copper demand recovery lifts prices",
        "Mining stocks rally on copper price",
        "Mining the moon: lunar resource rush",
        "Bitcoin mining hash rate hits record",
    ):
        result = heuristic.classify(title, "")
        assert result["relevant"] is False, (title, result)


def test_heuristic_accepts_real_mining_context():
    for title in (
        "Copper mine expansion approved in Chile",
        "Tailings dam safety review after heavy rain",
        "Gold recovery circuit optimization",
        "BHP approves Escondida expansion",
        "露天矿边坡监测新方法",
        "Underground mine ventilation upgrade",
    ):
        result = heuristic.classify(title, "")
        assert result["relevant"] is True, (title, result)


def test_global_classify_requires_mining_context():
    flat = [
        {"topic_id": 1, "level": 2, "en": ["machine learning"], "zh": []},
        {"topic_id": 2, "level": 2, "en": ["slope stability"], "zh": []},
    ]
    generic = "Machine learning for tabular data"
    assert global_classify(generic, generic.lower(), flat) == []
    mining = "Slope stability analysis at an open pit"
    hits = global_classify(mining, mining.lower(), flat)
    assert hits and hits[0][0] == 2


def test_chinese_terms_cover_core_phrase():
    zh, _ = _extract_terms("露天矿边坡监测有哪些方法")
    assert "边坡监测" in zh
    zh2, _ = _extract_terms("尾矿库溃坝风险如何评估")
    assert "溃坝风险" in zh2


def test_citation_validation_flags_out_of_range():
    assert _validate_citations("结论 [1][2]", 2) == []
    assert _validate_citations("结论 [1][9]", 2) == [9]
    assert _validate_citations("结论 [0]", 1) == [0]


def test_digest_respects_per_topic_cap():
    items = []
    for i in range(40):
        items.append({
            "item_id": i,
            "primary_topic": "a" if i % 2 == 0 else "b",
            "final_score": 100 - i,
        })
    selected = digest.select_items(items)
    counts = {}
    for item in selected:
        counts[item["primary_topic"]] = counts.get(item["primary_topic"], 0) + 1
    assert len(selected) <= digest.GLOBAL_TOP
    assert all(n <= digest.PER_TOPIC_TOP for n in counts.values()), counts


def test_llm_bool_parsing_is_strict():
    assert _as_bool("false") is False
    assert _as_bool("true") is True
    assert _as_bool(False, default=True) is False
    assert _as_bool("是") is True


def test_upgrade_migration_contracts():
    sql = (ROOT / "sql" / "011_upgrade.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS mining.journal_metrics" in sql
    assert "ALTER COLUMN embedding TYPE vector(1024)" in sql
    assert "uq_expert_history_person_date" in sql
    assert "CREATE TABLE IF NOT EXISTS mining.ask_logs" in sql
    assert "idx_items_status_time" in sql
