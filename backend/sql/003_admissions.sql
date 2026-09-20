-- =========================================================
-- Phase 3.5：全球矿业专家固定名册（认证对比基础）
-- 设计：名册是"固定基准"，与算法 Top 100 交叉对照产生
--   双重入选（高置信）/ 仅名册（算法盲区）/ 仅算法（新发现）
-- =========================================================
SET search_path TO mining, public;

CREATE TABLE IF NOT EXISTS expert_admissions (
    admission_id     BIGSERIAL PRIMARY KEY,
    roster_key       TEXT NOT NULL UNIQUE,           -- 名册唯一键（对应 yaml）
    full_name        TEXT NOT NULL,                  -- OpenAlex 检索用拉丁/原文名
    name_zh          TEXT,
    tier             TEXT NOT NULL CHECK (tier IN ('T1','T2','T3','T4')),
    channel          TEXT NOT NULL,                  -- 院士/会士/教授/企业/标准指南/奖项
    affiliation      TEXT,
    country_code     CHAR(2),
    basis            TEXT NOT NULL,                  -- 入选依据（证据）
    person_id        BIGINT REFERENCES mining.persons(person_id) ON DELETE SET NULL,
    match_status     TEXT NOT NULL DEFAULT 'pending',-- pending/matched/created/unmatched
    match_confidence NUMERIC(4,3),
    review_note      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admissions_person ON expert_admissions(person_id);
CREATE INDEX IF NOT EXISTS idx_admissions_tier ON expert_admissions(tier);
CREATE INDEX IF NOT EXISTS idx_admissions_status ON expert_admissions(match_status);
