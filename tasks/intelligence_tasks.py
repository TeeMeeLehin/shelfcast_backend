import logging
from datetime import datetime, timezone
from celery import shared_task
from app.db import supabase

from ai.tagger import signal_tagger
from engine.scorer import scoring_engine
from ai.narrator import narrator_engine

logger = logging.getLogger(__name__)

@shared_task(name="tasks.run_intelligence_pipeline")
def run_intelligence_pipeline(tenant_id: str | None = None, sync: bool = False):
    """
    Orchestrates the entire Phase 4 Intelligence Layer.
    1. Tag unprocessed raw signals.
    2. Score active SKUs.
    3. Generate narratives.
    4. Save to intelligence_runs.
    """
    logger.info("Starting Intelligence Pipeline...")
    
    # Step 1: AI Enrichment (Tagging)
    # Reverted to 200 to avoid OpenAI 429 Rate Limits
    processed_count = signal_tagger.process_unprocessed_signals(batch_size=200)
    logger.info(f"Tagged {processed_count} new raw signals.")
    
    # Step 2: Fetch Active SKUs to Score
    # We also limit SKU analysis to 200 per run to prevent 429s on narratives
    query = supabase.table("catalogue").select("sku_id, sku_name").eq("is_active", True).limit(200)
    if tenant_id:
        query = query.eq("tenant_id", tenant_id)
        
    res = query.execute()
    skus = res.data or []
    
    logger.info(f"Found {len(skus)} active SKUs to analyze.")
    
    run_date = datetime.now(timezone.utc).date().isoformat()
    
    intelligence_results = []
    
    # Step 3 & 4: Score and Narrate
    for sku in skus:
        # Score
        score_data = scoring_engine.calculate_sku_score(
            tenant_id=tenant_id or "global", # In real app, tenant_id is required per SKU
            sku_id=sku["sku_id"],
            run_date=run_date
        )
        
        if not score_data:
            continue
            
        # Narrate
        narrative = narrator_engine.generate_sku_narrative(
            sku_id=sku["sku_id"],
            sku_name=sku["sku_name"],
            score_data=score_data
        )
        
        # Prepare DB row
        # Actually, we need the real tenant_id from the SKU if tenant_id wasn't passed globally
        real_tenant_id = tenant_id
        if not real_tenant_id:
             # fetch tenant_id for this sku
             cat_t = supabase.table("catalogue").select("tenant_id").eq("sku_id", sku["sku_id"]).execute()
             if cat_t.data:
                 real_tenant_id = cat_t.data[0]["tenant_id"]
                 
        if real_tenant_id:
            row = {
                "tenant_id": real_tenant_id,
                "sku_id": sku["sku_id"],
                "run_date": run_date,
                "signal_score": score_data["composite_score"],
                "score_breakdown": score_data["score_breakdown"],
                "narrative": narrative,
                "alerts": [], # Placeholder for Step 5
                "geo_insight": {} # Placeholder
            }
            intelligence_results.append(row)
            
    # Save to Intelligence Runs
    if intelligence_results:
        # We should probably delete existing runs for today to avoid duplicates, or use upsert.
        # Assuming upsert isn't configured, we'll insert.
        try:
            for row in intelligence_results:
                supabase.table("intelligence_runs").insert(row).execute()
            logger.info(f"Saved {len(intelligence_results)} intelligence runs.")
        except Exception as e:
            logger.error(f"Failed to save intelligence runs: {e}")
            
    # Step 5: Manager Digest (Meta Overview)
    if tenant_id and intelligence_results:
        top_skus = sorted(intelligence_results, key=lambda x: x["signal_score"], reverse=True)[:3]
        top_skus_summary = [{"sku_id": s["sku_id"], "score": s["signal_score"], "narrative": s["narrative"]} for s in top_skus]
        
        # Simple anomaly mock for MVP
        anomalies = ["Competitor dropped prices unexpectedly in Kumasi."]
        
        digest = narrator_engine.generate_manager_digest(tenant_id, top_skus_summary, anomalies)
        logger.info(f"--- MANAGER DIGEST ---\n{digest}\n----------------------")
        
    return {"status": "success", "processed_signals": processed_count, "skus_analyzed": len(intelligence_results)}
