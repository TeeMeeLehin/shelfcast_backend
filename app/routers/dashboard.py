from fastapi import APIRouter, Depends
from app.deps import get_current_user
from engine.advisor import advisor

router = APIRouter()


@router.get("/summary")
async def get_dashboard_summary(current_user: dict = Depends(get_current_user)):
    """
    Command Center: Aggregate financial and health metrics.
    Returns capital_at_risk, opportunity_value, and health_score.
    """
    tenant_id = current_user["tenant_id"]
    result = advisor.get_dashboard_summary(tenant_id)
    return {"data": result}


@router.get("/opportunities")
async def get_market_opportunities(current_user: dict = Depends(get_current_user)):
    """
    Market Opportunities: AI-driven Buy Now / Offload recommendations.
    """
    tenant_id = current_user["tenant_id"]
    result = advisor.get_stocking_actions(tenant_id)
    return {"data": result}


@router.get("/intelligence")
async def get_demand_intelligence(current_user: dict = Depends(get_current_user)):
    """
    Demand Intelligence: Category-level market sentiment and external trends.
    """
    tenant_id = current_user["tenant_id"]
    result = advisor.get_category_intelligence(tenant_id)
    return {"data": result}


@router.get("/velocity")
async def get_demand_velocity(current_user: dict = Depends(get_current_user)):
    """
    Demand Velocity: Inventory turnover potential and capital rotation speed rankings.
    """
    tenant_id = current_user["tenant_id"]
    result = advisor.get_demand_velocity(tenant_id)
    return {"data": result}


@router.get("/alerts")
async def get_critical_alerts(current_user: dict = Depends(get_current_user)):
    """
    Critical Alerts: Real-time market anomalies and inventory threats.
    """
    tenant_id = current_user["tenant_id"]
    result = advisor.get_critical_alerts(tenant_id)
    return {"data": result}


@router.get("/skus/{sku_id}/root-cause")
async def get_root_cause(sku_id: str, current_user: dict = Depends(get_current_user)):
    """
    Root Cause Analysis: Narrative and score breakdown for a specific SKU.
    """
    tenant_id = current_user["tenant_id"]
    result = advisor.get_sku_root_cause(tenant_id, sku_id)
    return {"data": result}
