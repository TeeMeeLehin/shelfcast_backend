"""
tasks/ingestion_tasks.py

Celery tasks for the ingestion pipeline.
All heavy processing runs here — never in the FastAPI request cycle.
"""
import logging
from celery import Celery
from celery.schedules import crontab
import os

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("shelfcast", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Africa/Accra",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "run-nightly-signal-collection": {
            "task": "tasks.run_nightly_collection",
            "schedule": crontab(hour=1, minute=0),  # 01:00 AM
        },
    }
)


@celery_app.task(name="tasks.ingest_csv", bind=True, max_retries=3)
def ingest_csv_task(self, tenant_id: str, job_id: str, file_bytes_hex: str, filename: str, default_city: str | None = None):
    """
    Run the full CSV ingestion pipeline then trigger SKU classification.
    file_bytes_hex: hex-encoded bytes (Celery can't serialize raw bytes natively).
    default_city: the uploading user's registered city, used as fallback for rows with no city column.
    """
    from ingestion.csv_importer import run_csv_import

    try:
        file_bytes = bytes.fromhex(file_bytes_hex)
        result = run_csv_import(tenant_id, job_id, file_bytes, filename, default_city)

        # Trigger classification as a follow-up task
        classify_skus_task.delay(tenant_id)

        return result

    except Exception as exc:
        logger.error("ingest_csv_task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.classify_skus", bind=True, max_retries=2)
def classify_skus_task(self, tenant_id: str):
    """Run GPT-4o classification on all pending SKUs for a tenant."""
    from ai.classifier import classify_unclassified_skus

    try:
        return classify_unclassified_skus(tenant_id)
    except Exception as exc:
        logger.error("classify_skus_task failed for tenant %s: %s", tenant_id, exc)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="tasks.sync_quickbooks", bind=True, max_retries=3)
def sync_quickbooks_task(self, tenant_id: str, integration_id: str):
    """
    Incremental QuickBooks sync for a tenant.
    Fetches items and sales since last_sync_at.
    """
    from app.db import supabase
    from ingestion.quickbooks import QuickBooksAdapter
    from ingestion.cleaner import clean_rows
    from ingestion.normaliser import normalise
    from datetime import datetime, timezone

    try:
        # Load integration record
        rec = supabase.table("integrations").select("*").eq("id", integration_id).single().execute()
        integration = rec.data

        # Mark as syncing
        supabase.table("integrations").update({"sync_status": "syncing"}).eq("id", integration_id).execute()

        adapter = QuickBooksAdapter(integration, tenant_id)
        since = integration.get("last_sync_at")
        since_dt = datetime.fromisoformat(str(since)) if since else None

        # Fetch
        catalogue_data = adapter.fetch_catalogue()
        sales_data = adapter.fetch_sales_history(since=since_dt)
        all_records = catalogue_data + sales_data

        # Create a synthetic ingestion job
        job_res = supabase.table("ingestion_jobs").insert({
            "tenant_id": tenant_id,
            "source": "quickbooks",
            "status": "processing",
        }).execute()
        job_id = job_res.data[0]["id"]

        # Reuse the cleaning + normalisation pipeline
        fake_column_map = {f: f for f in ["sku_id", "sku_name", "units_sold", "stock_level", "revenue", "sale_date", "city"]}
        clean, quarantine_rows = clean_rows(all_records, fake_column_map, tenant_id)
        normalised = normalise(clean, tenant_id, job_id, source="quickbooks")

        if normalised["catalogue_rows"]:
            supabase.table("catalogue").upsert(normalised["catalogue_rows"], on_conflict="tenant_id,sku_id").execute()
        if normalised["sales_rows"]:
            supabase.table("sales_history").upsert(normalised["sales_rows"], on_conflict="tenant_id,sku_id,sale_date,city").execute()

        # Update integration and job
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("integrations").update({
            "sync_status": "idle",
            "last_sync_at": now,
        }).eq("id", integration_id).execute()
        supabase.table("ingestion_jobs").update({
            "status": "complete",
            "clean_rows": len(clean),
            "rejected_rows": len(quarantine_rows),
            "completed_at": now,
        }).eq("id", job_id).execute()

        classify_skus_task.delay(tenant_id)
        return {"synced_records": len(clean)}

    except Exception as exc:
        logger.error("QuickBooks sync failed for tenant %s: %s", tenant_id, exc, exc_info=True)
        from app.db import supabase as db
        db.table("integrations").update({"sync_status": "error"}).eq("id", integration_id).execute()
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="tasks.sync_lightspeed", bind=True, max_retries=3)
def sync_lightspeed_task(self, tenant_id: str, integration_id: str):
    """
    Incremental Lightspeed sync for a tenant.
    Fetches items and sales since last_sync_at.
    """
    from app.db import supabase
    from ingestion.lightspeed import LightspeedAdapter
    from ingestion.cleaner import clean_rows
    from ingestion.normaliser import normalise
    from datetime import datetime, timezone

    try:
        # Load integration record
        rec = supabase.table("integrations").select("*").eq("id", integration_id).single().execute()
        integration = rec.data

        # Mark as syncing
        supabase.table("integrations").update({"sync_status": "syncing"}).eq("id", integration_id).execute()

        adapter = LightspeedAdapter(integration, tenant_id)
        since = integration.get("last_sync_at")
        since_dt = datetime.fromisoformat(str(since)) if since else None

        # Fetch
        catalogue_data = adapter.fetch_catalogue()
        sales_data = adapter.fetch_sales_history(since=since_dt)
        all_records = catalogue_data + sales_data

        # Create a synthetic ingestion job
        job_res = supabase.table("ingestion_jobs").insert({
            "tenant_id": tenant_id,
            "source": "lightspeed",
            "status": "processing",
        }).execute()
        job_id = job_res.data[0]["id"]

        # Reuse the cleaning + normalisation pipeline
        fake_column_map = {f: f for f in ["sku_id", "sku_name", "units_sold", "stock_level", "revenue", "sale_date", "city"]}
        clean, quarantine_rows = clean_rows(all_records, fake_column_map, tenant_id)
        normalised = normalise(clean, tenant_id, job_id, source="lightspeed")

        if normalised["catalogue_rows"]:
            supabase.table("catalogue").upsert(normalised["catalogue_rows"], on_conflict="tenant_id,sku_id").execute()
        if normalised["sales_rows"]:
            supabase.table("sales_history").upsert(normalised["sales_rows"], on_conflict="tenant_id,sku_id,sale_date,city").execute()

        # Update integration and job
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("integrations").update({
            "sync_status": "idle",
            "last_sync_at": now,
        }).eq("id", integration_id).execute()
        supabase.table("ingestion_jobs").update({
            "status": "complete",
            "clean_rows": len(clean),
            "rejected_rows": len(quarantine_rows),
            "completed_at": now,
        }).eq("id", job_id).execute()

        classify_skus_task.delay(tenant_id)
        return {"synced_records": len(clean)}

    except Exception as exc:
        logger.error("Lightspeed sync failed for tenant %s: %s", tenant_id, exc, exc_info=True)
        from app.db import supabase as db
        db.table("integrations").update({"sync_status": "error"}).eq("id", integration_id).execute()
        raise self.retry(exc=exc, countdown=120)
