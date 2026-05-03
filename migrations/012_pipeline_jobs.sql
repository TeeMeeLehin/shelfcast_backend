-- 012_pipeline_jobs.sql
-- Tracks the state and resilience of the Discovery-to-Insight pipeline.

CREATE TABLE IF NOT EXISTS pipeline_jobs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  run_date         DATE NOT NULL DEFAULT CURRENT_DATE,
  status           TEXT DEFAULT 'pending', -- pending | running | completed | failed
  current_stage    TEXT DEFAULT 'start',   -- corpus | harvesting | tagging | scoring | insights
  logs             JSONB DEFAULT '[]'::jsonb,
  error_message    TEXT,
  metadata         JSONB DEFAULT '{}'::jsonb,
  started_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (tenant_id, run_date)
);

-- Index for quick status checks
CREATE INDEX IF NOT EXISTS idx_pipeline_status ON pipeline_jobs(tenant_id, run_date, status);
