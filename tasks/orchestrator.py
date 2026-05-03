import logging
import traceback
from datetime import datetime, date
from app.db import supabase
from ai.corpus import corpus_manager
from tasks.signal_tasks import run_nightly_collection
from ai.tagger import signal_tagger
from tasks.intelligence_tasks import run_intelligence_pipeline

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    """
    Stateful orchestrator that manages the Discovery-to-Insight pipeline.
    Supports checkpointing, resumption, and verbose logging.
    """
    
    STAGES = ["corpus", "harvesting", "tagging", "scoring", "insights"]

    def init_job(self, tenant_id: str) -> str:
        """Initialize a new job or return an existing one for today."""
        today = date.today().isoformat()
        res = supabase.table("pipeline_jobs").select("id, status, current_stage").eq("tenant_id", tenant_id).eq("run_date", today).execute()
        
        if res.data:
            job = res.data[0]
            if job["status"] == "completed":
                logger.info(f"Job already completed for today: {job['id']}")
            return job["id"]
            
        # Create new job
        new_job = supabase.table("pipeline_jobs").insert({
            "tenant_id": tenant_id,
            "status": "pending",
            "current_stage": "start",
            "logs": [{"t": datetime.now().isoformat(), "m": "Pipeline initialized."}]
        }).execute()
        
        return new_job.data[0]["id"]

    def run_full_pipeline(self, job_id: str):
        """Executes the pipeline stages sequentially with checkpointing."""
        res = supabase.table("pipeline_jobs").select("*").eq("id", job_id).execute()
        if not res.data: return
        job = res.data[0]
        tenant_id = job["tenant_id"]

        self._log(job_id, f"Starting pipeline execution for tenant {tenant_id}...")
        
        try:
            # Stage 1: Corpus Synthesis
            if self._should_run(job, "corpus"):
                self._update_stage(job_id, "corpus")
                corpus_manager.generate_tenant_corpus(tenant_id)
                self._log(job_id, "Stage: Corpus Synthesis - COMPLETE")

            # Stage 2: Signal Harvesting
            if self._should_run(job, "harvesting"):
                self._update_stage(job_id, "harvesting")
                # Run synchronously for this orchestration
                run_nightly_collection(tenant_id=tenant_id, sync=True)
                self._log(job_id, "Stage: Signal Harvesting - COMPLETE")

            # Stage 3: AI Tagging
            if self._should_run(job, "tagging"):
                self._update_stage(job_id, "tagging")
                signal_tagger.process_unprocessed_signals(batch_size=500)
                self._log(job_id, "Stage: AI Tagging - COMPLETE")

            # Stage 4: Scoring & Insights (Scoring -> Narratives -> Digest)
            if self._should_run(job, "scoring"):
                self._update_stage(job_id, "scoring")
                run_intelligence_pipeline(tenant_id=tenant_id)
                self._log(job_id, "Stage: Scoring & Insights - COMPLETE")

            # Finalize
            supabase.table("pipeline_jobs").update({
                "status": "completed",
                "current_stage": "done",
                "updated_at": datetime.now().isoformat()
            }).eq("id", job_id).execute()
            self._log(job_id, "PIPELINE EXECUTION SUCCESSFUL")

        except Exception as e:
            error_detail = traceback.format_exc()
            logger.error(f"Pipeline failed at stage {job['current_stage']}: {e}")
            supabase.table("pipeline_jobs").update({
                "status": "failed",
                "error_message": str(e),
                "metadata": {"traceback": error_detail},
                "updated_at": datetime.now().isoformat()
            }).eq("id", job_id).execute()
            self._log(job_id, f"CRITICAL FAILURE: {str(e)}")

    def _should_run(self, job: dict, stage: str) -> bool:
        """Determines if a stage should be run based on current progress."""
        if job["status"] == "completed": return False
        
        # Mapping stages to order
        order = {s: i for i, s in enumerate(self.STAGES)}
        current_idx = order.get(job["current_stage"], -1)
        target_idx = order.get(stage)
        
        return target_idx > current_idx

    def _update_stage(self, job_id: str, stage: str):
        supabase.table("pipeline_jobs").update({
            "current_stage": stage,
            "status": "running",
            "updated_at": datetime.now().isoformat()
        }).eq("id", job_id).execute()

    def _log(self, job_id: str, message: str):
        logger.info(f"[JOB {job_id[:8]}] {message}")
        # Append to DB logs
        supabase.rpc("append_pipeline_log", {
            "job_id": job_id, 
            "message": message
        }).execute()

orchestrator = PipelineOrchestrator()
