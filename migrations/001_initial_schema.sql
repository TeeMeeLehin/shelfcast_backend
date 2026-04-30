-- 001_initial_schema.sql
-- Initial schema for ShelfCast Backend

-- 1. Tenants Table
CREATE TABLE IF NOT EXISTS tenants (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  plan         TEXT DEFAULT 'mvp',
  timezone     TEXT DEFAULT 'Africa/Accra',
  digest_time  TIME DEFAULT '07:00',
  is_active    BOOLEAN DEFAULT TRUE,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Users Table
CREATE TABLE IF NOT EXISTS users (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email        TEXT UNIQUE NOT NULL,
  role         TEXT DEFAULT 'manager',  -- admin | manager
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Catalogue Table
CREATE TABLE IF NOT EXISTS catalogue (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sku_id       TEXT NOT NULL,
  sku_name     TEXT NOT NULL,
  brand        TEXT,
  category     TEXT,
  match_terms  TEXT[],  -- keywords used for signal matching
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, sku_id)
);

-- 4. Sales History Table
CREATE TABLE IF NOT EXISTS sales_history (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sku_id       TEXT NOT NULL,
  sku_name     TEXT,
  category     TEXT,
  brand        TEXT,
  units_sold   INT DEFAULT 0,
  revenue      FLOAT DEFAULT 0.0,
  stock_level  INT DEFAULT 0,
  city         TEXT,
  country      TEXT DEFAULT 'GH',
  sale_date    DATE NOT NULL,
  source       TEXT, -- 'csv' | 'quickbooks' | 'erp'
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Raw Signals Table (Append-only)
CREATE TABLE IF NOT EXISTS raw_signals (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source       TEXT NOT NULL, -- 'google_trends'|'newsapi'|'tiktok'|'instagram'|'x'|'competitor'
  keyword      TEXT NOT NULL,
  signal_data  JSONB,         -- raw response payload
  score        FLOAT,         -- normalised 0-1 signal strength
  geo          TEXT,          -- city or country code
  collected_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Signal Scores Table
CREATE TABLE IF NOT EXISTS signal_scores (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sku_id       TEXT NOT NULL,
  run_date     DATE NOT NULL,
  composite_score FLOAT,
  score_breakdown JSONB,      -- {social, search, competitor, news, internal}
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Intelligence Runs Table
CREATE TABLE IF NOT EXISTS intelligence_runs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sku_id        TEXT NOT NULL,
  run_date      DATE NOT NULL,
  signal_score  FLOAT,        -- composite 0-100
  score_breakdown JSONB,
  narrative     TEXT,         -- LLM-generated summary
  alerts        JSONB,        -- array of alert objects
  geo_insight   JSONB,        -- city-level pattern summary
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Geo Patterns Table
CREATE TABLE IF NOT EXISTS geo_patterns (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sku_id        TEXT NOT NULL,
  city          TEXT NOT NULL,
  avg_daily_units FLOAT,
  velocity_trend  TEXT,       -- 'accelerating'|'stable'|'decelerating'
  deviation_vs_national FLOAT,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Events Calendar
CREATE TABLE IF NOT EXISTS events_calendar (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_name    TEXT NOT NULL,
  start_date    DATE NOT NULL,
  end_date      DATE NOT NULL,
  region_scope  TEXT,        -- 'national' | 'Greater Accra' | etc.
  affected_categories TEXT[], -- categories likely to see demand shift
  demand_multiplier FLOAT DEFAULT 1.0,
  lead_window_days INT DEFAULT 7,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 10. City Profiles
CREATE TABLE IF NOT EXISTS city_profiles (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  city_name     TEXT UNIQUE NOT NULL,
  region        TEXT,
  population_segment TEXT,
  key_cultural_factors TEXT[],
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security (RLS) Policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalogue ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE geo_patterns ENABLE ROW LEVEL SECURITY;

-- Policy template (assumes tenant_id exists in JWT)
-- CREATE POLICY tenant_isolation ON <table_name>
--   FOR ALL
--   USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid)
--   WITH CHECK (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- Note: We'll apply specific policies via Supabase UI or more detailed migrations
-- once the auth flow is fully tested.
