import sys
import os
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import supabase
from ai.narrator import narrator_engine
from engine.scorer import scoring_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recompile():
    logger.info("Fetching failed intelligence narratives...")
    # Find runs where generation failed
    res = supabase.table("intelligence_runs").select("*").ilike("narrative", "%failed%").execute()
    runs = res.data or []
    
    if not runs:
        logger.info("No failed narratives found.")
        return

    logger.info(f"Found {len(runs)} narratives to recompile.")
    
    for run in runs:
        try:
            # Re-calculate the context (matched signals) for this SKU
            score_data = scoring_engine.calculate_sku_score(
                tenant_id=run["tenant_id"],
                sku_id=run["sku_id"],
                run_date=run["run_date"]
            )
            
            # Fetch SKU Name for context
            sku_res = supabase.table("catalogue").select("sku_name").eq("sku_id", run["sku_id"]).execute()
            sku_name = sku_res.data[0]["sku_name"] if sku_res.data else "Unknown SKU"
            
            # Generate new narrative using OpenAI
            new_narrative = narrator_engine.generate_sku_narrative(
                tenant_id=run["tenant_id"],
                sku_id=run["sku_id"],
                sku_name=sku_name
            )
            
            # Update the DB
            supabase.table("intelligence_runs").update({"narrative": new_narrative}).eq("id", run["id"]).execute()
            logger.info(f"Updated narrative for SKU: {run['sku_id']}")
            
        except Exception as e:
            logger.error(f"Failed to recompile {run['sku_id']}: {e}")

if __name__ == "__main__":
    recompile()
