-- =========================================================
-- 矿业前沿情报聚合平台 MVP 建表
-- schema 风格与《寻找活跃矿业专家.pdf》中的 mining schema 保持一致，
-- 后续阶段可直接并入 persons/works/institutions 等图谱表。
-- =========================================================

CREATE SCHEMA IF NOT EXISTS mining;
SET search_path TO mining, public;

-- 1. 主题体系（种子为 13 大类，来自 Mining Ontology V0.1）
CREATE TABLE IF NOT EXISTS topics (
    topic_id    BIGSERIAL PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name_zh     TEXT NOT NULL,
    name_en     TEXT NOT NULL,
    parent_id   BIGINT REFERENCES topics(topic_id) ON DELETE SET NULL,
    level       INT NOT NULL DEFAULT 1,
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. 信源（四层体系白名单）
CREATE TABLE IF NOT EXISTS sources (
    source_id        BIGSERIAL PRIMARY KEY,
    slug             TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    name_zh          TEXT,
    layer            INT NOT NULL DEFAULT 4,          -- 1专家 2公司 3组织 4期刊/会议/媒体
    source_type      TEXT NOT NULL DEFAULT 'news',    -- news/journal/org/company/expert/blog
    feed_url         TEXT,
    site_url         TEXT,
    lang             TEXT NOT NULL DEFAULT 'en',
    authority_weight NUMERIC(4,1) NOT NULL DEFAULT 5, -- 1~10
    active           BOOLEAN NOT NULL DEFAULT TRUE,
    last_fetched_at  TIMESTAMPTZ,
    notes            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. 条目
CREATE TABLE IF NOT EXISTS items (
    item_id          BIGSERIAL PRIMARY KEY,
    source_id        BIGINT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    url              TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL,
    author           TEXT,
    summary_raw      TEXT,                            -- RSS 自带摘要
    summary_zh       TEXT,                            -- LLM/启发式生成的中文一句话摘要
    item_type        TEXT NOT NULL DEFAULT 'news',    -- news/paper/report/conference/company/expert
    lang             TEXT NOT NULL DEFAULT 'en',
    published_at     TIMESTAMPTZ,
    collected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 评分（0~1，final_score 为 0~100）
    mining_relevance NUMERIC(4,3),
    authority        NUMERIC(4,3),
    freshness        NUMERIC(4,3),
    depth            NUMERIC(4,3),
    final_score      NUMERIC(6,2),

    status           TEXT NOT NULL DEFAULT 'pending', -- pending/approved/rejected
    status_source    TEXT,                            -- llm/heuristic
    reject_reason    TEXT,

    raw_data         JSONB,
    processed_at     TIMESTAMPTZ
);

-- 4. 条目↔主题
CREATE TABLE IF NOT EXISTS item_topic (
    item_id          BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
    topic_id         BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    relevance        NUMERIC(4,3) DEFAULT 1.0,
    PRIMARY KEY (item_id, topic_id)
);

-- 5. 周报
CREATE TABLE IF NOT EXISTS weekly_digests (
    digest_id    BIGSERIAL PRIMARY KEY,
    week_start   DATE NOT NULL UNIQUE,                -- 周一日期
    title        TEXT NOT NULL,
    summary      TEXT,
    item_count   INT NOT NULL DEFAULT 0,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS digest_item (
    digest_id BIGINT NOT NULL REFERENCES weekly_digests(digest_id) ON DELETE CASCADE,
    item_id   BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
    topic_id  BIGINT REFERENCES topics(topic_id),
    rank      INT NOT NULL,
    PRIMARY KEY (digest_id, item_id)
);

-- 6. 采集运行记录（可观测性）
CREATE TABLE IF NOT EXISTS collect_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    sources_ok    INT NOT NULL DEFAULT 0,
    sources_failed INT NOT NULL DEFAULT 0,
    items_new     INT NOT NULL DEFAULT 0,
    detail        JSONB
);

-- =========================================================
-- 索引
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_items_status_score ON items(status, final_score DESC);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_item_topic_topic ON item_topic(topic_id);
CREATE INDEX IF NOT EXISTS idx_digest_item_item ON digest_item(item_id);
