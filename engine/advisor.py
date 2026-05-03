import logging
from datetime import datetime, timezone, timedelta
from app.db import supabase

logger = logging.getLogger(__name__)

class InvestmentAdvisor:
    """
    Translates SKU-level intelligence into financial and stocking advice.
    Powering the Command Center, Market Opportunities, and Demand Velocity pages.
    """
    
    def get_dashboard_summary(self, tenant_id: str) -> dict:
        """
        Calculates aggregate metrics for the Command Center.
        """
        latest_run_date = self._get_latest_run_date(tenant_id)
        if not latest_run_date:
            return self._empty_summary()
            
        # Try joining, but fallback if FK relationship isn't cached yet
        try:
            res = supabase.table("intelligence_runs").select("*, catalogue(sku_name, unit_price, stock_level, category)")\
                .eq("tenant_id", tenant_id).eq("run_date", latest_run_date).execute()
            runs = res.data or []
        except Exception as e:
            logger.warning(f"Join failed, falling back to manual fetch: {e}")
            res = supabase.table("intelligence_runs").select("*").eq("tenant_id", tenant_id).eq("run_date", latest_run_date).execute()
            runs = res.data or []
            # Manual join
            skus_res = supabase.table("catalogue").select("sku_id, sku_name, unit_price, stock_level, category").eq("tenant_id", tenant_id).execute()
            sku_map = {s["sku_id"]: s for s in skus_res.data}
            for r in runs:
                r["catalogue"] = sku_map.get(r["sku_id"], {})

        capital_at_risk = 0
        opportunity_value = 0
        total_inventory_value = 0
        
        for run in runs:
            # Handle both joined and manual formats
            sku_info = run.get("catalogue", {})
            price = float(sku_info.get("unit_price", 0) or 0)
            stock = float(sku_info.get("stock_level", 0) or 0)
            score = run.get("signal_score", 50)
            
            val = price * stock
            total_inventory_value += val
            
            if score < 40 and stock > 0:
                capital_at_risk += val
            if score > 75 and stock < 20:
                opportunity_value += (price * 50) # Projected missed volume
                
        return {
            "run_date": latest_run_date,
            "metrics": {
                "total_inventory_value": round(total_inventory_value, 2),
                "capital_at_risk": round(capital_at_risk, 2),
                "opportunity_value": round(opportunity_value, 2),
                "health_score": round(self._calculate_health_score(runs), 1)
            }
        }
                
        return {
            "run_date": latest_run_date,
            "metrics": {
                "total_inventory_value": round(total_inventory_value, 2),
                "capital_at_risk": round(capital_at_risk, 2),
                "opportunity_value": round(opportunity_value, 2),
                "health_score": round(self._calculate_health_score(runs), 1)
            }
        }

    def get_stocking_actions(self, tenant_id: str) -> dict:
        """Categorizes SKUs for the Market Opportunities page."""
        runs = self._get_latest_runs(tenant_id)
        if not runs: return {"buy_now": [], "offload": []}
        
        buy_now = []
        offload = []
        for run in runs:
            sku_info = run.get("catalogue", {})
            score = run.get("signal_score", 50)
            item = {
                "sku_id": run["sku_id"], "sku_name": sku_info.get("sku_name"),
                "score": score, "stock": sku_info.get("stock_level", 0),
                "reason": (run.get("narrative") or "N/A").split(".")[0] + "."
            }
            if score > 75: buy_now.append(item)
            elif score < 35: offload.append(item)
        return {
            "buy_now": sorted(buy_now, key=lambda x: x["score"], reverse=True)[:20],
            "offload": sorted(offload, key=lambda x: x["score"])[:20]
        }

    def get_demand_velocity(self, tenant_id: str):
        """Ranks SKUs by turnover potential."""
        runs = self._get_latest_runs(tenant_id)
        # Ranks by score (potential) vs current stock (friction)
        velocity = []
        for r in runs:
            score = r.get("signal_score", 0)
            stock = r.get("catalogue", {}).get("stock_level", 0)
            velocity.append({
                "sku_id": r["sku_id"],
                "sku_name": r.get("catalogue", {}).get("sku_name"),
                "velocity_score": score,
                "stock_status": "Low" if stock < 20 else "Healthy"
            })
        return sorted(velocity, key=lambda x: x["velocity_score"], reverse=True)[:30]

    def get_category_intelligence(self, tenant_id: str):
        """Aggregates scores by category."""
        runs = self._get_latest_runs(tenant_id)
        cats = {}
        for r in runs:
            c = r.get("catalogue", {}).get("category", "General")
            if c not in cats: cats[c] = []
            cats[c].append(r.get("signal_score", 50))
        
        result = []
        for name, scores in cats.items():
            avg = sum(scores) / len(scores)
            result.append({
                "category": name,
                "sentiment_score": round(avg, 1),
                "status": "Surging" if avg > 70 else ("Softening" if avg < 40 else "Stable")
            })
        return sorted(result, key=lambda x: x["sentiment_score"], reverse=True)

    def get_critical_alerts(self, tenant_id: str):
        """Scans for high-severity anomalies."""
        runs = self._get_latest_runs(tenant_id)
        alerts = []
        for r in runs:
            score = r.get("signal_score", 50)
            sku_name = r.get("catalogue", {}).get("sku_name", r["sku_id"])
            if score > 92:
                alerts.append({"type": "Hyper-Demand", "severity": "high", "text": f"Extreme search surge detected for {sku_name}."})
            elif score < 15:
                alerts.append({"type": "Liquidation Warning", "severity": "high", "text": f"Critical sentiment drop for {sku_name}. Recommend immediate offload."})
        return alerts

    def _get_latest_runs(self, tenant_id: str):
        """Helper to get latest hydrated runs."""
        date = self._get_latest_run_date(tenant_id)
        if not date: return []
        try:
            res = supabase.table("intelligence_runs").select("*, catalogue(sku_name, unit_price, stock_level, category)")\
                .eq("tenant_id", tenant_id).eq("run_date", date).execute()
            return res.data or []
        except:
            res = supabase.table("intelligence_runs").select("*").eq("tenant_id", tenant_id).eq("run_date", date).execute()
            runs = res.data or []
            skus_res = supabase.table("catalogue").select("sku_id, sku_name, unit_price, stock_level, category").eq("tenant_id", tenant_id).execute()
            sku_map = {s["sku_id"]: s for s in skus_res.data}
            for r in runs: r["catalogue"] = sku_map.get(r["sku_id"], {})
            return runs

    def get_sku_root_cause(self, sku_id: str) -> dict:
        """
        Provides detailed analysis for the Root Cause Analysis page.
        """
        # Fetch latest run for this SKU
        res = supabase.table("intelligence_runs").select("*").eq("sku_id", sku_id).order("run_date", desc=True).limit(1).execute()
        if not res.data:
            return {"error": "No intelligence data found for this SKU."}
            
        run = res.data[0]
        
        # We also need the raw signals that were processed for this SKU's match terms
        # This is a bit complex in a single call, but we can return the breakdown stored in the run
        return {
            "sku_id": sku_id,
            "current_score": run.get("signal_score"),
            "narrative": run.get("narrative"),
            "score_breakdown": run.get("score_breakdown"),
            "alerts": run.get("alerts", []),
            "last_updated": run.get("run_date")
        }

    def _get_latest_run_date(self, tenant_id: str):
        res = supabase.table("intelligence_runs").select("run_date").eq("tenant_id", tenant_id).order("run_date", desc=True).limit(1).execute()
        return res.data[0]["run_date"] if res.data else None

    def _calculate_health_score(self, runs):
        if not runs: return 0
        return sum(r.get("signal_score", 50) for r in runs) / len(runs)

    def _empty_summary(self):
        return {"metrics": {"total_inventory_value": 0, "capital_at_risk": 0, "opportunity_value": 0, "health_score": 0}}

advisor = InvestmentAdvisor()
