-- =========================================================
-- 011_upgrade.sql：审计修复与生产化补强
-- 1) 修复 pgvector / JSONB embedding 类型冲突
-- 2) 补 journal_metrics 正式建表（原先只在脚本里建）
-- 3) 问答日志/引用持久化
-- 4) 评分历史唯一约束、状态约束
-- 5) 列表分页与全文检索索引
-- 6) 常用查询索引
-- 本迁移可重复执行。
-- =========================================================
SET search_path TO mining, public;

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------
-- 1. embedding：007 建的是 JSONB，010 的 ADD COLUMN IF NOT EXISTS 会静默跳过。
--    这里把 JSONB 列原地改为 vector(1024)，旧 JSONB 值无法安全转换，统一置空。
-- ---------------------------------------------------------
DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'mining'
      AND table_name = 'document_chunks'
      AND column_name = 'embedding';

    IF col_type = 'jsonb' THEN
        EXECUTE 'ALTER TABLE mining.document_chunks '
                'ALTER COLUMN embedding TYPE vector(1024) USING NULL';
        RAISE NOTICE 'document_chunks.embedding 已从 JSONB 迁移为 vector(1024)，旧值已清空';
    END IF;
END $$;

ALTER TABLE mining.works           ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE mining.document_chunks ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE mining.work_chunks     ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- ---------------------------------------------------------
-- 2. journal_metrics：scripts/import_journal_metrics.py 原先自建，fresh DB 上 API 会 500。
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS mining.journal_metrics (
    journal       TEXT PRIMARY KEY,
    norm_name     TEXT NOT NULL,
    issn          TEXT,
    eissn         TEXT,
    if_2025       REAL,
    jcr_quartile  TEXT,
    jcr_category  TEXT,
    cas_category  TEXT,
    cas_quartile  TEXT,
    cas_rank      TEXT,
    cas_top       TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE mining.journal_metrics
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_journal_metrics_norm
    ON mining.journal_metrics (norm_name);
CREATE INDEX IF NOT EXISTS idx_journal_metrics_if
    ON mining.journal_metrics (if_2025 DESC NULLS LAST);

-- ---------------------------------------------------------
-- 3. 问答日志与引用：保留问题、回答、证据状态、引用元数据，便于审计与复现。
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS mining.ask_logs (
    ask_id          BIGSERIAL PRIMARY KEY,
    question        TEXT NOT NULL,
    answer          TEXT,
    evidence_status TEXT NOT NULL,
    evidence_count  INT NOT NULL DEFAULT 0,
    limitations     TEXT,
    model           TEXT,
    took_ms         INT,
    client_hash     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ask_logs_created
    ON mining.ask_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ask_logs_status
    ON mining.ask_logs (evidence_status, created_at DESC);

CREATE TABLE IF NOT EXISTS mining.ask_citations (
    ask_id       BIGINT NOT NULL REFERENCES mining.ask_logs(ask_id) ON DELETE CASCADE,
    citation_no  INT NOT NULL,
    source_type  TEXT,
    title        TEXT,
    section_path TEXT,
    page         TEXT,
    lang         TEXT,
    authors      TEXT,
    year         INT,
    doi          TEXT,
    url          TEXT,
    snippet      TEXT,
    PRIMARY KEY (ask_id, citation_no)
);
CREATE INDEX IF NOT EXISTS idx_ask_citations_doi
    ON mining.ask_citations (doi) WHERE doi IS NOT NULL;

-- ---------------------------------------------------------
-- 4. 约束：旧库可能已有非法值，统一用 NOT VALID 只约束新写入。
-- ---------------------------------------------------------
ALTER TABLE mining.items DROP CONSTRAINT IF EXISTS items_status_check;
ALTER TABLE mining.items ADD CONSTRAINT items_status_check
    CHECK (status IN ('pending', 'approved', 'rejected')) NOT VALID;

ALTER TABLE mining.sources DROP CONSTRAINT IF EXISTS sources_tier_check;
ALTER TABLE mining.sources ADD CONSTRAINT sources_tier_check
    CHECK (tier IS NULL OR tier IN ('S0', 'A', 'A-', 'B+', 'B', 'B-', 'C', 'D')) NOT VALID;

ALTER TABLE mining.expert_admissions DROP CONSTRAINT IF EXISTS admissions_match_status_check;
ALTER TABLE mining.expert_admissions ADD CONSTRAINT admissions_match_status_check
    CHECK (match_status IN ('pending', 'matched', 'created', 'unmatched')) NOT VALID;

-- 评分历史：同一天同一人只保留一条；先清历史重复，再建唯一索引。
DELETE FROM mining.expert_score_history a
USING mining.expert_score_history b
WHERE a.person_id = b.person_id
  AND a.score_date = b.score_date
  AND a.score_id < b.score_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_expert_history_person_date
    ON mining.expert_score_history (person_id, score_date);

-- ---------------------------------------------------------
-- 5. 列表/检索索引：/api/items 的 q 走 pg_trgm；分页走状态+时间复合索引。
-- ---------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_items_status_time
    ON mining.items (status, (COALESCE(published_at, collected_at)) DESC);
CREATE INDEX IF NOT EXISTS idx_items_title_trgm
    ON mining.items USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_items_summary_zh_trgm
    ON mining.items USING gin (summary_zh gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_works_title_trgm
    ON mining.works USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_works_abstract_trgm
    ON mining.works USING gin (abstract gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_works_source_name_trgm
    ON mining.works USING gin (source_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_sources_active_feed
    ON mining.sources (active) WHERE active AND feed_url IS NOT NULL;

-- ---------------------------------------------------------
-- 6. 其他常用查询
-- ---------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_collect_runs_started
    ON mining.collect_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_persons_selected_score
    ON mining.persons (is_selected, final_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_evidence_entity_type
    ON mining.evidence (entity_type, entity_id, evidence_type);

COMMENT ON TABLE mining.ask_logs IS '问答审计日志：问题、回答、证据状态与耗时';
COMMENT ON TABLE mining.ask_citations IS '问答引用：与 ask_logs 一对多，保留 DOI/URL 便于溯源';
COMMENT ON TABLE mining.journal_metrics IS 'JCR/中科院分区指标，由 scripts/import_journal_metrics.py 导入';
