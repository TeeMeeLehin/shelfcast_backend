import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from app.db import get_db
from app.deps import get_current_user
from tasks.ingestion_tasks import ingest_csv_task

router = APIRouter()

@router.post("/csv", status_code=status.HTTP_202_ACCEPTED)
async def ingest_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    data_type: str = "sales", # "sales" or "catalogue"
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a CSV file for asynchronous processing.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    db = get_db()
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]

    # Get user preferences for default city tagging
    user_res = db.table("users").select("cities").eq("id", user_id).single().execute()
    cities_list = (user_res.data or {}).get("cities") or []
    default_city = cities_list[0] if cities_list else None

    # 1. Create the ingestion_job record
    job_id = str(uuid.uuid4())
    db.table("ingestion_jobs").insert({
        "id": job_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "filename": file.filename,
        "data_type": data_type,
        "status": "pending"
    }).execute()

    # 2. Read file content
    content = await file.read()
    
    # 3. Queue the background task
    background_tasks.add_task(
        ingest_csv_task, 
        job_id, 
        content, 
        data_type, 
        tenant_id, 
        default_city
    )

    return {
        "message": "Upload successful. Processing in background.",
        "job_id": job_id
    }

@router.get("/status/{job_id}")
async def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    res = db.table("ingestion_jobs").select("*").eq("id", job_id).single().execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Job not found.")
        
    return res.data
