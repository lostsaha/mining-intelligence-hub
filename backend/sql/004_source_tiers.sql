-- =========================================================
-- Phase 3.5：信源金字塔（S0–S7 八级体系）
-- 来源：《全球矿业信源分析.pdf》——社交媒体适合"发现"，
-- 专业数据库适合"定位"，一手文件适合"验证"
-- =========================================================
ALTER TABLE mining.sources ADD COLUMN IF NOT EXISTS tier TEXT;
CREATE INDEX IF NOT EXISTS idx_sources_tier ON mining.sources(tier);
