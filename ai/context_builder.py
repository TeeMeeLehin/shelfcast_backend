"""
ai/context_builder.py

MANDATORY single entry point for all LLM prompt assembly.
Enforces tenant isolation at the AI layer per architecture spec Section 12.3.

CRITICAL: This is the only module allowed to build context objects for LLM prompts.
All queries MUST include explicit tenant_id scoping. No raw DB rows in prompts.
"""
import logging
from datetime import datetime, date, timedelta
from app.db import supabase

logger = logging.getLogger(__name__)


def build_sku_context(tenant_id: str, sku_id: str, run_date: date | str = None) -> dict:
    """
    Build sanitised context for SKU-level intelligence narrative generation.
    
    Args:
        tenant_id: REQUIRED. Tenant UUID for RLS scoping.
        sku_id: SKU identifier
        run_date: Optional date for historical context (defaults to today)
    
    Returns:
        Sanitised context dict with NO tenant_id, NO PII, NO raw DB rows.
    
    Raises:
        ValueError: If tenant_id is None or empty
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for context building")
    
    if not run_date:
        run_date = date.today().isoformat()
    elif isinstance(run_date, date):
        run_date = run_date.isoformat()
    
    # All queries explicitly scoped to tenant_id
    # Fetch SKU details
    cat_res = supabase.table("catalogue").select("sku_name, brand, category, match_terms").eq(
        "tenant_id", tenant_id
    ).eq("sku_id", sku_id).execute()
    
    if not cat_res.data:
        logger.warning(f"SKU {sku_id} not found for tenant {tenant_id}")
        return {}
    
    sku_data = cat_res.data[0]
    
    # Fetch latest intelligence run
    intel_res = supabase.table("intelligence_runs").select("signal_score, score_breakdown, alerts").eq(
        "tenant_id", tenant_id
    ).eq("sku_id", sku_id).eq("run_date", run_date).execute()
    
    intel_data = intel_res.data[0] if intel_res.data else {}
    
    # Fetch recent sales history (last 30 days)
    lookback = (datetime.fromisoformat(run_date) - timedelta(days=30)).date().isoformat()
    sales_res = supabase.table("sales_history").select("units_sold, revenue, sale_date, city").eq(
        "tenant_id", tenant_id
    ).eq("sku_id", sku_id).gte("sale_date", lookback).order("sale_date", desc=True).limit(30).execute()
    
    sales_data = sales_res.data or []
    
    # Compute velocity trend from sales data
    if len(sales_data) >= 14:
        recent_7 = sum(s["units_sold"] for s in sales_data[:7])
        prev_7 = sum(s["units_sold"] for s in sales_data[7:14])
        if prev_7 > 0:
            growth = (recent_7 - prev_7) / prev_7
            velocity_trend = "accelerating" if growth > 0.1 else ("decelerating" if growth < -0.1 else "stable")
        else:
            velocity_trend = "insufficient_data"
    else:
        velocity_trend = "insufficient_data"
    
    # Fetch geo patterns
    geo_res = supabase.table("geo_patterns").select("city, avg_daily_units, velocity_trend, deviation_vs_national").eq(
        "tenant_id", tenant_id
    ).eq("sku_id", sku_id).order("avg_daily_units", desc=True).limit(3).execute()
    
    top_cities = [
        {
            "city": g["city"],
            "avg_daily_units": g["avg_daily_units"],
            "trend": g["velocity_trend"]
        }
        for g in (geo_res.data or [])
    ]
    
    # Build sanitised context (NO tenant_id, NO PII)
    return {
        "sku_name": sku_data.get("sku_name"),
        "brand": sku_data.get("brand"),
        "category": sku_data.get("category"),
        "composite_score": intel_data.get("signal_score", 50),
        "score_breakdown": intel_data.get("score_breakdown", {}),
        "velocity_trend": velocity_trend,
        "top_cities": top_cities,
        "active_alerts": intel_data.get("alerts", []),
        "recent_sales_count": len(sales_data),
    }


def build_manager_digest_context(tenant_id: str, run_date: date | str = None) -> dict:
    """
    Build sanitised context for manager digest email generation.
    
    Args:
        tenant_id: REQUIRED. Tenant UUID for RLS scoping.
        run_date: Optional date (defaults to today)
    
    Returns:
        Sanitised context dict with top SKUs and anomalies.
    
    Raises:
        ValueError: If tenant_id is None or empty
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for context building")
    
    if not run_date:
        run_date = date.today().isoformat()
    elif isinstance(run_date, date):
        run_date = run_date.isoformat()
    
    # Fetch top 5 SKUs by score for this tenant
    intel_res = supabase.table("intelligence_runs").select(
        "sku_id, signal_score, narrative, alerts"
    ).eq("tenant_id", tenant_id).eq("run_date", run_date).order(
        "signal_score", desc=True
    ).limit(5).execute()
    
    top_skus = []
    for run in (intel_res.data or []):
        # Fetch SKU name
        cat_res = supabase.table("catalogue").select("sku_name").eq(
            "tenant_id", tenant_id
        ).eq("sku_id", run["sku_id"]).execute()
        
        sku_name = cat_res.data[0]["sku_name"] if cat_res.data else run["sku_id"]
        
        top_skus.append({
            "sku_name": sku_name,
            "score": run["signal_score"],
            "narrative": run["narrative"],
            "has_alerts": len(run.get("alerts", [])) > 0
        })
    
    # Identify anomalies (scores > 90 or < 20)
    anomalies = []
    for sku in top_skus:
        if sku["score"] > 90:
            anomalies.append(f"Extreme demand surge for {sku['sku_name']}")
        elif sku["score"] < 20:
            anomalies.append(f"Critical sentiment drop for {sku['sku_name']}")
    
    return {
        "top_skus": top_skus,
        "anomalies": anomalies,
        "run_date": run_date,
    }
