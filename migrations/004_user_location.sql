-- 004_user_location.sql
-- Add city/country to users table for geo-intelligence city inference

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS city    TEXT,
  ADD COLUMN IF NOT EXISTS country TEXT DEFAULT 'Ghana';

-- Add Lightspeed to integrations provider constraint (if applicable)
-- Note: integrations.provider has no CHECK constraint, so nothing needed here.

COMMENT ON COLUMN users.city IS
  'The city where this user/manager primarily operates. Used as default city for data they upload.';
COMMENT ON COLUMN users.country IS
  'Country of operation. Defaults to Ghana for the primary pilot market.';
