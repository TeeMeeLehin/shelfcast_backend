"""
app/routers/ingest.py

CSV ingestion endpoints:
  POST /ingest/csv           — Upload a CSV/XLSX file to begin ingestion
  GET  /ingest/status/{id}   — Poll job progress
  GET  /ingest/quarantine    — List rows pending human review
  PATCH /ingest/quarantine/{id} — Accept or discard a quarantined row
"""
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from pydantic import BaseModel
from typing import Literal

from app.db import get_db
from app.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class QuarantineResolution(BaseModel):
    resolution: Literal["accepted", "discarded"]


@router.post("/csv", status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept a CSV or XLSX file upload and dispatch an async ingestion job.
    Returns a job_id to poll for progress.
    """
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Upload a CSV or XLSX file.")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {MAX_FILE_SIZE_MB}MB.")

    db = get_db()
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]

    # Fetch the uploading user's city to use as a default for rows without a city column
    user_res = db.table("users").select("city").eq("id", user_id).single().execute()
    default_city = (user_res.data or {}).get("city")

    # Create the ingestion_job record immediately (pending)
    job_res = db.table("ingestion_jobs").insert({
        "tenant_id": tenant_id,
        "source":    "csv",
        "status":    "pending",
        "file_name": file.filename,
    }).execute()
    job_id = job_res.data[0]["id"]

    # Dispatch to Celery, fall back to synchronous if Redis is unavailable
    try:
        from tasks.ingestion_tasks import ingest_csv_task
        ingest_csv_task.delay(
            tenant_id,
            job_id,
            file_bytes.hex(),
            file.filename,
            default_city,
        )
    except Exception as celery_err:
        logger.warning("Celery unavailable (%s). Running ingestion synchronously.", celery_err)
        try:
            from ingestion.csv_importer import run_csv_import
            run_csv_import(tenant_id, job_id, file_bytes, file.filename, default_city)
        except Exception as import_err:
            raise HTTPException(
                status_code=500,
                detail=f"Ingestion failed: {str(import_err)}"
            )

    return {"job_id": job_id, "status": "pending", "file_name": file.filename}


@router.get("/status/{job_id}")
async def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """Poll the status and progress of an ingestion job."""
    db = get_db()
    res = db.table("ingestion_jobs").select("*").eq("id", job_id).eq(
        "tenant_id", current_user["tenant_id"]
    ).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")

    job = res.data
    progress = 0
    if job["total_rows"] and job["total_rows"] > 0:
        progress = round(((job["clean_rows"] or 0) + (job["rejected_rows"] or 0)) / job["total_rows"] * 100)

    return {**job, "progress_percent": progress}


@router.get("/quarantine")
async def list_quarantine(current_user: dict = Depends(get_current_user)):
    """Return all rows currently pending review in the quarantine table."""
    db = get_db()
    res = db.table("ingestion_quarantine").select("*").eq(
        "tenant_id", current_user["tenant_id"]
    ).eq("resolution", "pending").order("created_at", desc=True).execute()

    return {"quarantined": res.data or [], "count": len(res.data or [])}


@router.patch("/quarantine/{quarantine_id}")
async def resolve_quarantine(
    quarantine_id: str,
    body: QuarantineResolution,
    current_user: dict = Depends(get_current_user),
):
    """Accept or discard a quarantined row. Accepted rows are inserted into the catalogue."""
    db = get_db()
    res = db.table("ingestion_quarantine").select("*").eq("id", quarantine_id).eq(
        "tenant_id", current_user["tenant_id"]
    ).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Quarantine record not found.")

    row = res.data

    # If accepted, manually insert the raw data into the catalogue
    if body.resolution == "accepted":
        raw = row["raw_data"]
        db.table("catalogue").upsert({
            "tenant_id":             current_user["tenant_id"],
            "sku_id":                raw.get("sku_id") or raw.get("SKU") or str(uuid.uuid4())[:8],
            "sku_name":              raw.get("sku_name") or raw.get("Product Name", "Unnamed"),
            "classification_status": "pending",
            "source":                "manual_review",
            "is_active":             True,
        }, on_conflict="tenant_id,sku_id").execute()

    # Update resolution status
    db.table("ingestion_quarantine").update({
        "resolution":  body.resolution,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", quarantine_id).execute()

    return {"message": f"Row {body.resolution}.", "quarantine_id": quarantine_id}
