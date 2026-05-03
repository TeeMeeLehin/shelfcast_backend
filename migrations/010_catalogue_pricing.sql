-- 010_catalogue_pricing.sql
-- Adds unit_price column to catalogue for financial impact calculations.

ALTER TABLE catalogue
  ADD COLUMN IF NOT EXISTS unit_price NUMERIC(12, 2) DEFAULT 0;
