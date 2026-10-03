-- =========================================================
-- 010_embeddings.sql：pgvector 语义检索基建（Phase 4D）
-- 前置：数据库镜像须为 pgvector/pgvector:pg16（docker-compose.yml 已切换）
-- 维度 1024 对齐 BAAI/bge-m3（中英双语），改维度需同步 backend/.env 的 EMBEDDINGS_DIM
-- HNSW 索引在回填完成后由 embed_backfill 提示创建（空表上建索引无意义）
-- =========================================================
SET search_path TO mining, public;

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE mining.works           ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE mining.document_chunks ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE mining.work_chunks     ADD COLUMN IF NOT EXISTS embedding vector(1024);

COMMENT ON COLUMN mining.works.embedding           IS '摘要向量（bge-m3 口径 1024 维），embed_backfill 回填';
COMMENT ON COLUMN mining.document_chunks.embedding IS '分段内容向量（1024 维），embed_backfill 回填';
COMMENT ON COLUMN mining.work_chunks.embedding     IS '分段内容向量（1024 维），embed_backfill 回填';
