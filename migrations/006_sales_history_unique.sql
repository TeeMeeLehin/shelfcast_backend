-- 006_sales_history_unique.sql
-- Add a unique constraint to sales_history to enable idempotent upserts for ingestion
-- This prevents duplicate inventory snapshots or double-counted sales on retry.

-- We use NULLS NOT DISTINCT (supported in PG 15+) so that a row with a NULL city 
-- conflicts with another row with a NULL city, preventing duplicates where city is unknown.
ALTER TABLE sales_history
  ADD CONSTRAINT sales_history_tenant_sku_date_city_key 
  UNIQUE NULLS NOT DISTINCT (tenant_id, sku_id, sale_date, city);
