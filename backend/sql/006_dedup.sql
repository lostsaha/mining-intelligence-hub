-- P0：标题级新闻去重
-- 背景：同一条新闻经 5 个信源各自入库（BHP/Amazon 案例），信息流与周报被稀释
SET search_path TO mining, public;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE mining.items ADD COLUMN IF NOT EXISTS title_norm TEXT;

CREATE INDEX IF NOT EXISTS idx_items_title_norm ON mining.items (title_norm);
CREATE INDEX IF NOT EXISTS idx_items_title_norm_trgm ON mining.items USING gin (title_norm gin_trgm_ops);
