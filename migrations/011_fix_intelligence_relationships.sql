-- 011_fix_intelligence_relationships.sql
-- Link intelligence_runs to catalogue to allow for high-performance joins.

-- 1. Ensure sku_id is unique in catalogue (required for FK)
-- In a multi-tenant system, we usually reference the ID, but for the advisor we use sku_id.
-- We'll add a unique constraint on sku_id if it doesn't have one.
ALTER TABLE catalogue ADD CONSTRAINT catalogue_sku_unique UNIQUE (sku_id);

-- 2. Add the foreign key to intelligence_runs
ALTER TABLE intelligence_runs
  ADD CONSTRAINT fk_intelligence_catalogue
  FOREIGN KEY (sku_id) REFERENCES catalogue(sku_id)
  ON DELETE CASCADE;
