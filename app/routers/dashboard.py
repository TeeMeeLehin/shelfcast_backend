from fastapi import APIRouter, Depends, Query
from app.deps import get_current_user
from engine.advisor import advisor

router = APIRouter()

@router.get("/summary")
async def get_dashboard_summary(current_user: dict = Depends(get_current_user)):
    """
    Command Center: Aggregate financial and health metrics.
    """
    tenant_id = current_user["tenant_id"]
    return advisor.get_dashboard_summary(tenant_id)

@router.get("/intelligence")
async def get_demand_intelligence(current_user: dict = Depends(get_current_user)):
    """
    Demand Intelligence: Category-level trends.
    """
    return advisor.get_category_intelligence(current_user["tenant_id"])

@router.get("/opportunities")
async def get_market_opportunities(current_user: dict = Depends(get_current_user)):
    """
    Market Opportunities: Buy Now / Offload lists.
    """
    tenant_id = current_user["tenant_id"]
    return advisor.get_stocking_actions(tenant_id)

@router.get("/velocity")
async def get_demand_velocity(current_user: dict = Depends(get_current_user)):
    """
    Demand Velocity: Turnover speed rankings.
    """
    return advisor.get_demand_velocity(current_user["tenant_id"])

@router.get("/alerts")
async def get_critical_alerts(current_user: dict = Depends(get_current_user)):
    """
    Critical Alerts: Anomalies and threats.
    """
    return advisor.get_critical_alerts(current_user["tenant_id"])

@router.get("/skus/{sku_id}/root-cause")
async def get_root_cause(sku_id: str, current_user: dict = Depends(get_current_user)):
    """
    Root Cause Analysis: Why is this SKU's score moving?
    """
    return advisor.get_sku_root_cause(sku_id)
