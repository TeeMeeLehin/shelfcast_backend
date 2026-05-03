-- 008_enhanced_signals_schema.sql
-- Upgrades the raw_signals table to handle both keyword-based and
-- keyword-less (general_pulse) signals, with AI-tagged entity extraction.

-- 1. Make keyword nullable — general_pulse rows have no specific keyword
ALTER TABLE raw_signals ALTER COLUMN keyword DROP NOT NULL;

-- 2. Upgrade the score column to integer (0-100 scale per the scoring design)
ALTER TABLE raw_signals ALTER COLUMN score TYPE INT USING ROUND(score * 100)::INT;

-- 3. Add new columns
ALTER TABLE raw_signals
    ADD COLUMN IF NOT EXISTS signal_type     TEXT    DEFAULT 'keyword_based'
        CHECK (signal_type IN ('keyword_based', 'general_pulse')),
    ADD COLUMN IF NOT EXISTS raw_content     TEXT,
    ADD COLUMN IF NOT EXISTS entities        JSONB   DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS sentiment_score INT     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS impact_score    INT     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_processed    BOOLEAN DEFAULT FALSE;

-- 4. Index for efficient querying of unprocessed general_pulse signals
CREATE INDEX IF NOT EXISTS idx_raw_signals_unprocessed
    ON raw_signals (signal_type, is_processed)
    WHERE signal_type = 'general_pulse' AND is_processed = FALSE;

-- 5. Index for efficient querying by source and collection time
CREATE INDEX IF NOT EXISTS idx_raw_signals_source_collected
    ON raw_signals (source, collected_at DESC);
