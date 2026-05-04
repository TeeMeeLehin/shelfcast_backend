-- 014_user_locations_refactor.sql
-- Refactors the users table to support multiple monitoring cities.

-- 1. Transform users table
ALTER TABLE users RENAME COLUMN city TO cities;
ALTER TABLE users ALTER COLUMN cities TYPE JSONB USING jsonb_build_array(cities);
ALTER TABLE users ALTER COLUMN cities SET DEFAULT '[]'::jsonb;

-- 2. Ensure tenants table is flexible for two-stage signup
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS locations JSONB DEFAULT '[]'::jsonb;
ALTER TABLE tenants ALTER COLUMN name DROP NOT NULL;
