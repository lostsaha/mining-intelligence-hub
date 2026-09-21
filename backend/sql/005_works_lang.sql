-- 中文文献语料：works 增加语言字段
ALTER TABLE mining.works ADD COLUMN IF NOT EXISTS lang TEXT;
CREATE INDEX IF NOT EXISTS idx_works_lang ON mining.works(lang);
