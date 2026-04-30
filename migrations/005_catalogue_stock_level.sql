-- 005_catalogue_stock_level.sql
-- Adds stock_level column to catalogue for inventory snapshots.
-- stock_level = the quantity on hand at time of upload.

ALTER TABLE catalogue
  ADD COLUMN IF NOT EXISTS stock_level NUMERIC(12, 2) DEFAULT 0;
