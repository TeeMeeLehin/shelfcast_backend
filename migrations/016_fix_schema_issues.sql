-- Fix 1: Add missing onboarding columns to tenants table (from 015_onboarding_step)
ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS onboarding_step SMALLINT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;

-- Fix 2: Add missing UNIQUE constraint to intelligence_runs so ON CONFLICT upserts work
ALTER TABLE intelligence_runs 
  ADD CONSTRAINT intelligence_runs_tenant_sku_date_key UNIQUE (tenant_id, sku_id, run_date);
