import sys
import os
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tasks.intelligence_tasks import run_intelligence_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_intelligence(tenant_id: str | None = None):
    """
    Manually triggers the Phase 4 Intelligence Pipeline for testing.
    This will tag raw signals, score SKUs, and generate narratives.
    """
    logger.info("Starting Phase 4: Intelligence Pipeline Test...")
    
    # Run the pipeline synchronously
    # We call it with sync=True (though the task itself doesn't use the flag for logic yet, we just call the func)
    result = run_intelligence_pipeline(tenant_id=tenant_id)
    
    print("\n" + "="*50)
    print("INTELLIGENCE PIPELINE COMPLETE")
    print("="*50)
    print(f"Signals Tagged:    {result.get('processed_signals')}")
    print(f"SKUs Analyzed:     {result.get('skus_analyzed')}")
    print("\nCheck your 'intelligence_runs' and 'raw_signals' (is_processed=True) tables in Supabase.")
    print("="*50 + "\n")

if __name__ == "__main__":
    t_id = sys.argv[1] if len(sys.argv) > 1 else None
    test_intelligence(tenant_id=t_id)
