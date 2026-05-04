-- Track where each tenant is in the signup flow so the frontend can resume.
-- onboarding_step: 1 = registered, 2 = preferences saved, 3 = trial accepted
-- trial_started_at: stamped when the user clicks "Go to Dashboard" on step 3

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS onboarding_step SMALLINT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;
