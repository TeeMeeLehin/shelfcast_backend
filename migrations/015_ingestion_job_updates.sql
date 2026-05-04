-- 015_ingestion_job_updates.sql
-- Synchronizes ingestion_jobs table with Phase 5 requirements.

ALTER TABLE ingestion_jobs 
ADD COLUMN IF NOT EXISTS data_type TEXT DEFAULT 'sales';

-- Refresh schema cache
NOTIFY pgrst, 'reload schema';
