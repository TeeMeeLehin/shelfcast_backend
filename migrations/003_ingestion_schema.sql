-- 003_ingestion_schema.sql
-- Phase 2: Ingestion pipeline infrastructure

-- 1. Ingestion Jobs — audit trail for every import
CREATE TABLE IF NOT EXISTS ingestion_jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  source          TEXT NOT NULL, -- 'csv' | 'quickbooks' | 'erp'
  status          TEXT DEFAULT 'pending', -- pending | processing | complete | failed | partial
  file_name       TEXT,
  total_rows      INT DEFAULT 0,
  clean_rows      INT DEFAULT 0,
  rejected_rows   INT DEFAULT 0,
  error_summary   JSONB,         -- [{row, reason}]
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Ingestion Quarantine — parking lot for bad rows awaiting human review
CREATE TABLE IF NOT EXISTS ingestion_quarantine (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  job_id           UUID NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  raw_data         JSONB NOT NULL,
  rejection_reason TEXT NOT NULL, -- 'missing_sku' | 'invalid_sku_format' | 'missing_product_name' | etc.
  resolution       TEXT DEFAULT 'pending', -- pending | accepted | discarded
  resolved_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Integrations — OAuth tokens + ERP credentials per tenant (encrypted at app layer)
CREATE TABLE IF NOT EXISTS integrations (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider         TEXT NOT NULL, -- 'quickbooks' | 'sap' | 'netsuite' | 'generic_rest'
  access_token     TEXT,          -- AES-128 encrypted
  refresh_token    TEXT,          -- AES-128 encrypted
  token_expires_at TIMESTAMPTZ,
  realm_id         TEXT,          -- QuickBooks company ID
  last_sync_at     TIMESTAMPTZ,
  sync_status      TEXT DEFAULT 'idle', -- idle | syncing | error
  meta             JSONB,         -- field mappings, endpoint config, etc.
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (tenant_id, provider)
);

-- 4. Extend catalogue with classification status and variant support
ALTER TABLE catalogue
  ADD COLUMN IF NOT EXISTS classification_status TEXT DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS is_active             BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS variant_of            TEXT,       -- parent sku_id if this is a variant
  ADD COLUMN IF NOT EXISTS source                TEXT,       -- 'csv' | 'quickbooks' | 'erp' | 'manual'
  ADD COLUMN IF NOT EXISTS ingestion_job_id      UUID REFERENCES ingestion_jobs(id);

-- 5. Enable RLS on new tenant-scoped tables
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_quarantine ENABLE ROW LEVEL SECURITY;
ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant isolation for ingestion_jobs" ON ingestion_jobs
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

CREATE POLICY "Tenant isolation for ingestion_quarantine" ON ingestion_quarantine
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

CREATE POLICY "Tenant isolation for integrations" ON integrations
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());
