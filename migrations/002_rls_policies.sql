-- 002_rls_policies.sql
-- Implement Row Level Security policies based on app_metadata JWT claims

-- Function to extract tenant_id from JWT app_metadata
-- Created in public schema to avoid 'permission denied for schema auth'
CREATE OR REPLACE FUNCTION public.get_auth_tenant_id() RETURNS uuid AS $$
  SELECT (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid;
$$ LANGUAGE SQL STABLE;

-- Ensure RLS is enabled on all core tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalogue ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE geo_patterns ENABLE ROW LEVEL SECURITY;

-- 1. Users Policy
CREATE POLICY "Tenant isolation for users" ON users
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

-- 2. Catalogue Policy
CREATE POLICY "Tenant isolation for catalogue" ON catalogue
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

-- 3. Sales History Policy
CREATE POLICY "Tenant isolation for sales_history" ON sales_history
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

-- 4. Signal Scores Policy
CREATE POLICY "Tenant isolation for signal_scores" ON signal_scores
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

-- 5. Intelligence Runs Policy
CREATE POLICY "Tenant isolation for intelligence_runs" ON intelligence_runs
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

-- 6. Geo Patterns Policy
CREATE POLICY "Tenant isolation for geo_patterns" ON geo_patterns
  FOR ALL
  USING (tenant_id = public.get_auth_tenant_id())
  WITH CHECK (tenant_id = public.get_auth_tenant_id());

-- Note: raw_signals does not have a tenant_id column because signals are collected globally.
-- We must restrict raw_signals reads at the application layer or add a tenant link table.
-- For MVP, raw_signals are accessed via backend service role only during pipeline execution.
-- We can add a policy to block public reads.
CREATE POLICY "Deny all public access to raw_signals" ON raw_signals
  FOR ALL USING (false);
