import logging
from datetime import datetime, timezone
from celery import shared_task
from app.db import supabase

from ai.tagger import signal_tagger
from engine.scorer import scoring_engine
from ai.narrator import narrator_engine

logger = logging.getLogger(__name__)

@shared_task(name="tasks.run_intelligence_pipeline")
def run_intelligence_pipeline(tenant_id: str | None = None, sync: bool = False, ingestion_job_id: str | None = None):
    """
    Orchestrates the entire Phase 4 Intelligence Layer.
    1. Tag unprocessed raw signals.
    2. Score active SKUs.
    3. Generate narratives.
    4. Save to intelligence_runs.
    
    ingestion_job_id: if provided, writes stage updates back to the ingestion_job
    so the frontend can track end-to-end progress via GET /ingest/status/{job_id}.
    """
    def _update_ingest_stage(stage: str):
        if ingestion_job_id:
            supabase.table("ingestion_jobs").update({
                "pipeline_stage": stage
            }).eq("id", ingestion_job_id).execute()

    logger.info("Starting Intelligence Pipeline...")
    _update_ingest_stage("tagging_signals")
    
    # Step 1: AI Enrichment (Tagging)
    # Reverted to 200 to avoid OpenAI 429 Rate Limits
    processed_count = signal_tagger.process_unprocessed_signals(batch_size=200)
    logger.info(f"Tagged {processed_count} new raw signals.")
    _update_ingest_stage("scoring_skus")
    
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
        # Fetch tenant_id for this SKU (required for tenant isolation)
        cat_t = supabase.table("catalogue").select("tenant_id").eq("sku_id", sku["sku_id"]).execute()
        if not cat_t.data:
            logger.warning(f"SKU {sku['sku_id']} not found in catalogue, skipping.")
            continue
            
        real_tenant_id = cat_t.data[0]["tenant_id"]
        if not real_tenant_id:
            logger.error(f"SKU {sku['sku_id']} has no tenant_id, skipping for security.")
            continue
        
        # Score
        score_data = scoring_engine.calculate_sku_score(
            tenant_id=real_tenant_id,
            sku_id=sku["sku_id"],
            run_date=run_date
        )
        
        if not score_data:
            continue

        _update_ingest_stage("generating_insights")
            
        # Narrate (now requires tenant_id for context_builder integration)
        narrative = narrator_engine.generate_sku_narrative(
            tenant_id=real_tenant_id,
            sku_id=sku["sku_id"],
            sku_name=sku["sku_name"]
        )        
        # Prepare DB row
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
            
    # Save to Intelligence Runs (using upsert to prevent duplicates)
    if intelligence_results:
        try:
            for row in intelligence_results:
                supabase.table("intelligence_runs").upsert(row, on_conflict="tenant_id,sku_id,run_date").execute()
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

    # Mark the originating ingestion job as fully complete
    _update_ingest_stage("complete")
        
    return {"status": "success", "processed_signals": processed_count, "skus_analyzed": len(intelligence_results)}


@shared_task(name="tasks.send_manager_digests")
def send_manager_digests():
    """
    Sends morning email digests to all active tenants.
    Scheduled to run at 06:00 AM daily.
    """
    import os
    import resend
    from datetime import datetime, timezone
    
    logger.info("Starting manager digest email task...")
    
    # Get all active tenants
    tenants_res = supabase.table("tenants").select("id, name").execute()
    tenants = tenants_res.data or []
    
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        logger.error("RESEND_API_KEY not configured, skipping digest emails.")
        return {"status": "skipped", "reason": "no_api_key"}
    
    resend.api_key = resend_api_key
    sender_email = os.getenv("DIGEST_FROM_EMAIL", "digest@resend.dev")
    if "<" not in sender_email:
        sender_email = f"ShelfCast Intelligence <{sender_email}>"
    
    sent_count = 0
    
    for tenant in tenants:
        tenant_id = tenant["id"]
        tenant_name = tenant["name"]
        
        try:
            # Get latest intelligence runs for this tenant
            run_date = datetime.now(timezone.utc).date().isoformat()
            runs_res = supabase.table("intelligence_runs").select("*").eq("tenant_id", tenant_id).eq("run_date", run_date).execute()
            runs = runs_res.data or []
            
            if not runs:
                logger.info(f"No intelligence runs for tenant {tenant_id}, skipping digest.")
                continue
            
            # Get top 3 SKUs
            top_skus = sorted(runs, key=lambda x: x.get("signal_score", 0), reverse=True)[:3]
            top_skus_summary = [
                {
                    "sku_id": s["sku_id"],
                    "score": s["signal_score"],
                    "narrative": s["narrative"]
                }
                for s in top_skus
            ]
            
            # Simple anomaly detection (scores < 20 or > 90)
            anomalies = []
            for run in runs:
                score = run.get("signal_score", 50)
                if score > 90:
                    anomalies.append(f"Extreme demand surge detected for SKU {run['sku_id']}")
                elif score < 20:
                    anomalies.append(f"Critical sentiment drop for SKU {run['sku_id']}")
            
            # Generate digest using narrator
            digest = narrator_engine.generate_manager_digest(tenant_id, top_skus_summary, anomalies)
            
            # Get all managers for this tenant
            users_res = supabase.table("users").select("email, role").eq("tenant_id", tenant_id).execute()
            managers = [u for u in users_res.data if u.get("role") in ["admin", "manager"]]
            
            if not managers:
                logger.info(f"No managers found for tenant {tenant_id}, skipping digest.")
                continue
            
            # Send email to each manager
            for manager in managers:
                try:
                    resend.Emails.send({
                        "from": sender_email,
                        "to": manager["email"],
                        "subject": f"ShelfCast Morning Intelligence Brief - {tenant_name}",
                        "html": f"""
                            <h2>Good Morning from ShelfCast</h2>
                            <h3>Executive Summary</h3>
                            <p>{digest.get('executive_summary', 'No summary available.')}</p>
                            
                            <h3>Top Movers Analysis</h3>
                            <p>{digest.get('top_movers_analysis', 'No analysis available.')}</p>
                            
                            <h3>Market Anomalies</h3>
                            <p>{digest.get('market_anomalies', 'No anomalies detected.')}</p>
                            
                            <h3>Strategic Advice</h3>
                            <p>{digest.get('strategic_advice', 'No advice available.')}</p>
                            
                            <p><em>This is an automated intelligence brief from ShelfCast.</em></p>
                        """
                    })
                    sent_count += 1
                except Exception as email_err:
                    logger.error(f"Failed to send digest to {manager['email']}: {email_err}")
                    
        except Exception as tenant_err:
            logger.error(f"Failed to process digest for tenant {tenant_id}: {tenant_err}")
    
    logger.info(f"Sent {sent_count} manager digest emails.")
    return {"status": "success", "emails_sent": sent_count}
