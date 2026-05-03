-- 013_append_log_rpc.sql
-- Atomic helper to append logs to a pipeline job without race conditions.

CREATE OR REPLACE FUNCTION append_pipeline_log(job_id UUID, message TEXT)
RETURNS VOID AS $$
BEGIN
  UPDATE pipeline_jobs
  SET logs = logs || jsonb_build_object(
    't', now(),
    'm', message
  ),
  updated_at = now()
  WHERE id = job_id;
END;
$$ LANGUAGE plpgsql;
