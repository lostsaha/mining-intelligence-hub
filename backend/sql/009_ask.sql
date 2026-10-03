-- =========================================================
-- 009_ask.sql：/ask 证据问答检索加速
-- 英文检索走既有 tsvector(simple)；中文短语走 ILIKE，
-- pg_trgm GIN 索引避免 6 万+ 分段的全表扫描
-- =========================================================
SET search_path TO mining, public;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_document_chunks_trgm
    ON mining.document_chunks USING gin (content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_work_chunks_trgm
    ON mining.work_chunks USING gin (content gin_trgm_ops);
