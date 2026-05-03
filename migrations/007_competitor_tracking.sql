-- 007_competitor_tracking.sql
-- Creates the competitor_sources table.
-- Competitor URLs are mapped at the BRAND or CATEGORY level, not per-SKU.
-- This is intentional: one URL covers all SKUs sharing the same brand/category.

CREATE TABLE IF NOT EXISTS competitor_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    target_type     TEXT NOT NULL CHECK (target_type IN ('brand', 'category')),
    target_value    TEXT NOT NULL,          -- e.g. 'Nestle' or 'Beverages'
    competitor_name TEXT NOT NULL,          -- e.g. 'Melcom', 'Jumia GH'
    url             TEXT NOT NULL,          -- scraped product/listing URL
    is_active       BOOLEAN DEFAULT TRUE,
    last_scraped_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, target_type, target_value, url)
);

-- RLS: tenants can only see their own competitor sources
ALTER TABLE competitor_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation_competitor_sources" ON competitor_sources
    USING (tenant_id = (current_setting('request.jwt.claims', true)::jsonb->>'tenant_id')::uuid);
