-- =========================================================
-- 008_work_chunks.sql：论文级分段（页码级证据语料）
-- 数据源：H:\00\zotero 的 MinerU 解析 MD（对应 Zotero PDF 全文）
-- /ask 证据问答从这里取"原文片段"
-- =========================================================
SET search_path TO mining, public;

CREATE TABLE IF NOT EXISTS work_chunks (
    chunk_id     BIGSERIAL PRIMARY KEY,
    work_id      BIGINT NOT NULL REFERENCES mining.works(work_id) ON DELETE CASCADE,
    lang         TEXT NOT NULL DEFAULT 'en',
    chunk_index  INT NOT NULL,
    section_path TEXT,
    content      TEXT NOT NULL,
    char_count   INT NOT NULL,
    md_source    TEXT,                                   -- MD 文件路径（溯源）
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (work_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_work_chunks_work ON work_chunks(work_id);

ALTER TABLE work_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_work_chunks_search ON work_chunks USING gin(search_vector);
CREATE OR REPLACE FUNCTION work_chunks_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple', coalesce(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_work_chunks_search ON work_chunks;
CREATE TRIGGER trg_work_chunks_search
BEFORE INSERT OR UPDATE OF content ON work_chunks
FOR EACH ROW EXECUTE FUNCTION work_chunks_search_update();
