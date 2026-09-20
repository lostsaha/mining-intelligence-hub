-- =========================================================
-- Phase 2：专家模块建表（002_experts.sql）
-- 节点/关系命名与《寻找活跃矿业专家.pdf》中的 MELTG 设计保持一致，
-- topics 表沿用 001_init.sql（本阶段补充 level=2 子主题）。
-- =========================================================
SET search_path TO mining, public;

-- 1. 机构
CREATE TABLE IF NOT EXISTS institutions (
    institution_id BIGSERIAL PRIMARY KEY,
    openalex_id    TEXT UNIQUE,
    ror_id         TEXT UNIQUE,
    name           TEXT NOT NULL,
    name_zh        TEXT,
    country_code   CHAR(2),
    institution_type TEXT,            -- education/company/government/...
    website        TEXT,
    raw_data       JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. 人物（专家）
CREATE TABLE IF NOT EXISTS persons (
    person_id     BIGSERIAL PRIMARY KEY,
    openalex_id   TEXT UNIQUE,
    orcid         TEXT UNIQUE,
    display_name  TEXT NOT NULL,
    country_code  CHAR(2),
    current_institution_id BIGINT REFERENCES institutions(institution_id),

    -- 语料内统计
    corpus_works       INT NOT NULL DEFAULT 0,
    corpus_citations   INT NOT NULL DEFAULT 0,
    first_year         INT,
    last_year          INT,
    coauthor_count     INT NOT NULL DEFAULT 0,

    -- 评分（0~100）
    mining_relevance_score NUMERIC(6,2),
    research_impact_score  NUMERIC(6,2),
    recent_activity_score  NUMERIC(6,2),
    topic_depth_score      NUMERIC(6,2),
    industry_score         NUMERIC(6,2),
    collaboration_score    NUMERIC(6,2),
    expert_score           NUMERIC(6,2),
    coverage_score         NUMERIC(6,2),
    final_score            NUMERIC(6,2),
    expert_rank            INT,

    is_selected    BOOLEAN NOT NULL DEFAULT FALSE,   -- 进入 Top 100
    summary_zh     TEXT,                             -- 模板/LLM 生成的中文简介
    raw_data       JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. 人物—机构
CREATE TABLE IF NOT EXISTS person_institution (
    person_id      BIGINT NOT NULL REFERENCES persons(person_id) ON DELETE CASCADE,
    institution_id BIGINT NOT NULL REFERENCES institutions(institution_id) ON DELETE CASCADE,
    is_current     BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (person_id, institution_id)
);

-- 4. 学术作品（与资讯条目 items 分离，仅收录 OpenAlex 采语料）
CREATE TABLE IF NOT EXISTS works (
    work_id         BIGSERIAL PRIMARY KEY,
    openalex_id     TEXT UNIQUE,
    doi             TEXT UNIQUE,
    title           TEXT NOT NULL,
    abstract        TEXT,
    work_type       TEXT,
    publication_year INT,
    publication_date DATE,
    cited_by_count  INT NOT NULL DEFAULT 0,
    source_name     TEXT,                -- 期刊/会议名
    is_open_access  BOOLEAN,
    raw_data        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. 人物—作品
CREATE TABLE IF NOT EXISTS person_work (
    person_id  BIGINT NOT NULL REFERENCES persons(person_id) ON DELETE CASCADE,
    work_id    BIGINT NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    author_position INT,
    PRIMARY KEY (person_id, work_id)
);

-- 6. 作品—主题（归入本体子主题）
CREATE TABLE IF NOT EXISTS work_topic (
    work_id  BIGINT NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    topic_id BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    relevance NUMERIC(4,3) DEFAULT 1.0,
    PRIMARY KEY (work_id, topic_id)
);

-- 7. 人物—主题（专家画像核心关系）
CREATE TABLE IF NOT EXISTS person_topic (
    person_id      BIGINT NOT NULL REFERENCES persons(person_id) ON DELETE CASCADE,
    topic_id       BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    relevance      NUMERIC(4,3),
    works_count    INT NOT NULL DEFAULT 0,
    citation_count INT NOT NULL DEFAULT 0,
    first_year     INT,
    last_year      INT,
    PRIMARY KEY (person_id, topic_id)
);

-- 8. 作品引用（仅保留语料内部边）
CREATE TABLE IF NOT EXISTS work_citation (
    citing_work_id BIGINT NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    cited_work_id  BIGINT NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    PRIMARY KEY (citing_work_id, cited_work_id),
    CHECK (citing_work_id <> cited_work_id)
);

-- 9. 评分历史（每月重算后追加，观察专家上升/下降趋势）
CREATE TABLE IF NOT EXISTS expert_score_history (
    score_id  BIGSERIAL PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES persons(person_id) ON DELETE CASCADE,
    score_date DATE NOT NULL,
    mining_relevance_score NUMERIC(6,2),
    research_impact_score  NUMERIC(6,2),
    recent_activity_score  NUMERIC(6,2),
    topic_depth_score      NUMERIC(6,2),
    industry_score         NUMERIC(6,2),
    collaboration_score    NUMERIC(6,2),
    expert_score  NUMERIC(6,2),
    coverage_score NUMERIC(6,2),
    final_score   NUMERIC(6,2),
    rank INT
);

-- 10. 证据（每条"专家—主题"关系可追溯：语料作品 + 引用 + 时间跨度）
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id   BIGSERIAL PRIMARY KEY,
    entity_type   TEXT NOT NULL,          -- person/person_topic/...
    entity_id     BIGINT NOT NULL,
    evidence_type TEXT NOT NULL,          -- corpus_works/key_works/institution/...
    claim         JSONB NOT NULL,         -- 结构化证据内容
    source_url    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 11. 采集运行记录
CREATE TABLE IF NOT EXISTS expert_pipeline_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    run_type      TEXT NOT NULL,          -- collect/build/full
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    works_collected INT NOT NULL DEFAULT 0,
    candidates    INT NOT NULL DEFAULT 0,
    selected      INT NOT NULL DEFAULT 0,
    detail        JSONB
);

-- =========================================================
-- 索引
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_persons_final_score ON persons(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_persons_openalex ON persons(openalex_id);
CREATE INDEX IF NOT EXISTS idx_works_year ON works(publication_year);
CREATE INDEX IF NOT EXISTS idx_works_citations ON works(cited_by_count DESC);
CREATE INDEX IF NOT EXISTS idx_person_work_work ON person_work(work_id);
CREATE INDEX IF NOT EXISTS idx_work_topic_topic ON work_topic(topic_id);
CREATE INDEX IF NOT EXISTS idx_person_topic_topic ON person_topic(topic_id);
CREATE INDEX IF NOT EXISTS idx_work_citation_cited ON work_citation(cited_work_id);
CREATE INDEX IF NOT EXISTS idx_expert_history_person ON expert_score_history(person_id, score_date DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(entity_type, entity_id);
