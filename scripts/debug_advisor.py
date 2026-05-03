import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.db import supabase
from engine.advisor import advisor

T_ID = "7a012b56-9bd3-4ba6-972f-de473103ab47"

print(f"--- DIAGNOSTICS FOR TENANT {T_ID} ---")

# 1. Check Catalogue Pricing
cat = supabase.table("catalogue").select("sku_id, unit_price, stock_level").eq("tenant_id", T_ID).limit(5).execute()
print(f"Catalogue Sample: {cat.data}")

# 2. Check Intelligence Runs
runs = supabase.table("intelligence_runs").select("id, run_date, signal_score").eq("tenant_id", T_ID).order("run_date", desc=True).limit(5).execute()
print(f"Latest Intelligence Runs: {runs.data}")

# 3. Check Advisor Logic
summary = advisor.get_dashboard_summary(T_ID)
print(f"Advisor Summary: {summary}")

actions = advisor.get_stocking_actions(T_ID)
print(f"Buy Now Count: {len(actions.get('buy_now', []))}")
print(f"Offload Count: {len(actions.get('offload', []))}")
