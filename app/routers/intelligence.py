from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from app.deps import get_current_user
from tasks.orchestrator import orchestrator
from app.db import supabase
from typing import Optional

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

@router.get("/")
async def list_intelligence_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    run_date: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns paginated list of latest intelligence runs with optional filters.
    """
    tenant_id = current_user["tenant_id"]
    offset = (page - 1) * page_size
    
    # Get latest run_date if not specified
    if not run_date:
        latest_res = supabase.table("intelligence_runs").select("run_date").eq("tenant_id", tenant_id).order("run_date", desc=True).limit(1).execute()
        if latest_res.data:
            run_date = latest_res.data[0]["run_date"]
        else:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
    
    query = supabase.table("intelligence_runs").select("*, catalogue(sku_name, brand, category)", count="exact").eq("tenant_id", tenant_id).eq("run_date", run_date)
    
    if min_score is not None:
        query = query.gte("signal_score", min_score)
    if max_score is not None:
        query = query.lte("signal_score", max_score)
    
    res = query.order("signal_score", desc=True).range(offset, offset + page_size - 1).execute()
    
    return {
        "items": res.data,
        "total": res.count,
        "page": page,
        "page_size": page_size,
        "run_date": run_date
    }

@router.get("/{sku_id}")
async def get_sku_intelligence(
    sku_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns full intelligence detail for a specific SKU (latest run).
    """
    tenant_id = current_user["tenant_id"]
    
    # Get latest run for this SKU
    res = supabase.table("intelligence_runs").select("*, catalogue(sku_name, brand, category, unit_price, stock_level)").eq("tenant_id", tenant_id).eq("sku_id", sku_id).order("run_date", desc=True).limit(1).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="No intelligence data found for this SKU")
    
    return res.data[0]

@router.get("/{sku_id}/history")
async def get_sku_intelligence_history(
    sku_id: str,
    days: int = Query(30, ge=1, le=90),
    current_user: dict = Depends(get_current_user)
):
    """
    Returns time series of intelligence runs for a specific SKU.
    """
    tenant_id = current_user["tenant_id"]
    
    res = supabase.table("intelligence_runs").select("run_date, signal_score, score_breakdown, narrative").eq("tenant_id", tenant_id).eq("sku_id", sku_id).order("run_date", desc=True).limit(days).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="No intelligence history found for this SKU")
    
    return {
        "sku_id": sku_id,
        "history": res.data,
        "days_returned": len(res.data)
    }
