import sys
import os
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import supabase
from tasks.signal_tasks import run_nightly_collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_pipeline(tenant_id: str | None = None):
    """
    Triggers the nightly signal collection pipeline manually for testing.
    This will use MOCK_COLLECTION if enabled in .env.
    """
    msg = f"Starting Manual Signal Pipeline Test {'for all' if not tenant_id else f'for tenant {tenant_id}'}..."
    logger.info(msg)
    
    # Run the main orchestration task synchronously to avoid needing Redis for this test
    logger.info("Dispatched run_nightly_collection (SYNC)...")
    result = run_nightly_collection(tenant_id=tenant_id, sync=True)
    
    print("\n" + "="*50)
    print("PIPELINE TEST COMPLETE")
    print("="*50)
    print(f"Keywords Tracked:    {result.get('keywords')}")
    print(f"Competitors Tracked: {result.get('competitors')}")
    print("\nCheck your 'raw_signals' table in Supabase for incoming mock data.")
    print("="*50 + "\n")

if __name__ == "__main__":
    t_id = sys.argv[1] if len(sys.argv) > 1 else None
    test_pipeline(tenant_id=t_id)
