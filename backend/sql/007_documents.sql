-- =========================================================
-- 007_documents.sql：统一文献库（书籍/标准/报告）
-- 依据顾问记录 §4：documents + versions + chunks(页码/段落定位)
-- 证据问答(4A)的页码级引用依赖本表的 chunks
-- =========================================================
SET search_path TO mining, public;

-- 统一文献表（论文在 works，书籍/标准/报告在此；后续可迁移合并）
CREATE TABLE IF NOT EXISTS documents (
    document_id   BIGSERIAL PRIMARY KEY,
    title_en      TEXT NOT NULL,
    title_zh      TEXT,
    authors       TEXT,
    year          INT,
    doc_type      TEXT NOT NULL DEFAULT 'book',   -- book/standard/report
    publisher     TEXT,
    source_dir    TEXT,                            -- 本地目录（溯源）
    access_status TEXT NOT NULL DEFAULT 'private-owned', -- 个人藏书·本地使用
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_dir)
);

-- 版本表：同一作品的中英文/不同格式载体
CREATE TABLE IF NOT EXISTS document_versions (
    version_id   BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    lang         TEXT NOT NULL,                   -- en/zh
    format       TEXT NOT NULL,                   -- pdf/md/epub
    file_path    TEXT NOT NULL UNIQUE,
    file_size    BIGINT,
    parse_status TEXT NOT NULL DEFAULT 'pending', -- pending/parsed/failed/skipped
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 分段表：章节级分段，内容清洗后供全文检索与（后续）向量化
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id      BIGSERIAL PRIMARY KEY,
    document_id   BIGINT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    version_id    BIGINT NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    lang          TEXT NOT NULL,
    chunk_index   INT NOT NULL,
    section_path  TEXT,                            -- 如 "3 GEOLOGICAL MODEL / 3.4 Stereonets"
    content       TEXT NOT NULL,
    char_count    INT NOT NULL,
    embedding     JSONB,                           -- 4D 阶段启用 pgvector 后迁移
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_version ON document_chunks(version_id);
CREATE INDEX IF NOT EXISTS idx_versions_document ON document_versions(document_id);

-- 全文检索（中英混排用 simple 配置，分词依赖内容本身；后续可换 zhparser）
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_chunks_search ON document_chunks USING gin(search_vector);
CREATE OR REPLACE FUNCTION chunks_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple', coalesce(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_chunks_search ON document_chunks;
CREATE TRIGGER trg_chunks_search
BEFORE INSERT OR UPDATE OF content ON document_chunks
FOR EACH ROW EXECUTE FUNCTION chunks_search_vector_update();

-- 目录骨架（中文 EPUB 权威结构参照）
ALTER TABLE mining.documents ADD COLUMN IF NOT EXISTS raw_toc JSONB;
