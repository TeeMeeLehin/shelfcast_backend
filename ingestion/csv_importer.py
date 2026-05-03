"""
ingestion/csv_importer.py

Orchestrates the full CSV ingestion pipeline:
  1. Parse the file (CSV or Excel)
  2. Map columns
  3. Clean rows (Pass 1 + Pass 2)
  4. Normalise to schema
  5. Write to DB
  6. Dispatch GPT-4o classification task
"""
import io
import logging
from datetime import datetime, timezone

import pandas as pd

from app.db import supabase
from ingestion.column_mapper import map_columns
from ingestion.cleaner import clean_rows
from ingestion.normaliser import normalise

logger = logging.getLogger(__name__)


def _read_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV or XLSX into a DataFrame."""
    lower = filename.lower()
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    else:
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return pd.read_csv(io.BytesIO(file_bytes), dtype=str, encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not decode CSV file. Please save as UTF-8.")


def run_csv_import(
    tenant_id: str,
    job_id: str,
    file_bytes: bytes,
    filename: str,
    default_city: str | None = None,
) -> dict:
    """
    Full import pipeline. Called by the Celery task.
    Updates the ingestion_job row in-place and returns a result summary.
    """
    db = supabase

    # Mark job as processing
    db.table("ingestion_jobs").update({
        "status":     "processing",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()

    try:
        # 1. Parse
        df = _read_file(file_bytes, filename)
        raw_rows = df.where(pd.notna(df), None).to_dict(orient="records")
        total_rows = len(raw_rows)

        # 2. Map columns
        column_map, unmatched = map_columns(list(df.columns))
        if unmatched:
            raise ValueError(
                f"Could not detect required columns: {unmatched}. "
                f"Please rename your columns to include: "
                f"'SKU' (or 'Product Code') and 'Product Name'."
            )

        # 3. Clean
        clean, quarantine_rows = clean_rows(raw_rows, column_map, tenant_id)

        # 4. Normalise (pass default_city for rows with no city column)
        normalised = normalise(clean, tenant_id, job_id, source="csv", default_city=default_city)

        # 4.5. Backfill names for SKUs that were missing names in this CSV
        # (This handles the case where a Sales History CSV has only SKU IDs)
        unknown_skus = list(set(r["sku_id"] for r in clean if r["sku_name"] == "(Unknown Product)"))
        if unknown_skus:
            # Fetch existing names from catalogue in batches to avoid URL length limits
            name_map = {}
            batch_size = 200
            for i in range(0, len(unknown_skus), batch_size):
                batch = unknown_skus[i : i + batch_size]
                res = db.table("catalogue").select("sku_id, sku_name").eq("tenant_id", tenant_id).in_("sku_id", batch).execute()
                for row in res.data:
                    name_map[row["sku_id"]] = row["sku_name"]
            
            # Apply backfill to both catalogue and sales rows
            for cat_row in normalised["catalogue_rows"]:
                if cat_row["sku_name"] == "(Unknown Product)":
                    cat_row["sku_name"] = name_map.get(cat_row["sku_id"], "(Unknown Product)")
            
            for sale_row in normalised["sales_rows"]:
                if sale_row.get("sku_name") == "(Unknown Product)":
                    sale_row["sku_name"] = name_map.get(sale_row["sku_id"], "(Unknown Product)")

        # 5. Write catalogue (upsert on sku_id + tenant_id)
        # CRITICAL: Do NOT upsert catalogue rows that still have "(Unknown Product)" 
        # as we don't want to create "empty" catalogue entries with no names.
        valid_cat_rows = [r for r in normalised["catalogue_rows"] if r["sku_name"] != "(Unknown Product)"]
        if valid_cat_rows:
            db.table("catalogue").upsert(
                valid_cat_rows,
                on_conflict="tenant_id,sku_id",
            ).execute()

        # 6. Write sales_history (upsert to prevent duplicate records on retry)
        if normalised["sales_rows"]:
            db.table("sales_history").upsert(
                normalised["sales_rows"],
                on_conflict="tenant_id,sku_id,sale_date,city",
            ).execute()

        # 7. Write quarantine rows
        if quarantine_rows:
            qrows = [
                {
                    "tenant_id":        tenant_id,
                    "job_id":           job_id,
                    "raw_data":         q["raw_data"],
                    "rejection_reason": q["rejection_reason"],
                }
                for q in quarantine_rows
            ]
            db.table("ingestion_quarantine").insert(qrows).execute()

        # 8. Update job status
        clean_count = len(clean)
        rejected_count = len(quarantine_rows)
        status = "complete" if rejected_count == 0 else "partial"

        db.table("ingestion_jobs").update({
            "status":        status,
            "total_rows":    total_rows,
            "clean_rows":    clean_count,
            "rejected_rows": rejected_count,
            "completed_at":  datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).execute()

        logger.info(
            "Job %s complete. %d clean, %d quarantined (format: %s).",
            job_id, clean_count, rejected_count, normalised["format"]
        )

        return {
            "job_id":        job_id,
            "status":        status,
            "total_rows":    total_rows,
            "clean_rows":    clean_count,
            "rejected_rows": rejected_count,
            "data_format":   normalised["format"],
        }

    except Exception as exc:
        logger.error("Ingestion job %s failed: %s", job_id, exc, exc_info=True)
        db.table("ingestion_jobs").update({
            "status":       "failed",
            "error_summary": [{"reason": str(exc)}],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).execute()
        raise
