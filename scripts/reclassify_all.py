import sys
import os
import logging

# Ensure project root is in sys.path so 'app' and 'ai' modules can be found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import supabase
from ai.classifier import classify_unclassified_skus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_reclassification(target_tenant_id: str | None = None):
    if target_tenant_id:
        logger.info(f"Targeting specific tenant: {target_tenant_id}")
        # Verify tenant exists
        res = supabase.table("tenants").select("id, name").eq("id", target_tenant_id).execute()
        tenants = res.data or []
        if not tenants:
            logger.error(f"Tenant ID '{target_tenant_id}' not found.")
            return
    else:
        logger.info("Fetching all active tenants...")
        res = supabase.table("tenants").select("id, name").execute()
        tenants = res.data or []
    
    if not tenants:
        logger.warning("No tenants found.")
        return

    for tenant in tenants:
        tenant_id = tenant["id"]
        tenant_name = tenant["name"]
        
        logger.info(f"Processing classification for tenant: {tenant_name} ({tenant_id})")
        try:
            stats = classify_unclassified_skus(tenant_id)
            logger.info(f"Result for {tenant_name}: {stats}")
        except Exception as e:
            logger.error(f"Failed to classify for {tenant_name}: {e}")

if __name__ == "__main__":
    # Check for tenant ID argument
    tenant_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_reclassification(tenant_id_arg)
