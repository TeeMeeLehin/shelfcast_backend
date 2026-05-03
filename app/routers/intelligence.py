from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from app.deps import get_current_user
from tasks.orchestrator import orchestrator
from app.db import supabase

router = APIRouter()

@router.post("/run-full")
async def trigger_full_pipeline(
    background_tasks: BackgroundTasks, 
    current_user: dict = Depends(get_current_user)
):
    """
    Triggers the Discovery-to-Insight pipeline.
    Starts from Corpus Synthesis and ends with Manager Digest.
    Supports resumption if a previous job for today failed.
    """
    tenant_id = current_user["tenant_id"]
    try:
        job_id = orchestrator.init_job(tenant_id)
        # Run in background to avoid timeout
        background_tasks.add_task(orchestrator.run_full_pipeline, job_id)
        return {
            "job_id": job_id,
            "status": "started",
            "message": "Full intelligence pipeline initiated in background."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/run/{job_id}/status")
async def get_pipeline_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Returns the live status and logs for a pipeline job.
    """
    res = supabase.table("pipeline_jobs").select("*").eq("id", job_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return res.data[0]
