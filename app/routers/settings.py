from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from app.db import get_db
from app.deps import get_current_user, require_admin
from typing import List, Optional

router = APIRouter()

class SettingsUpdateRequest(BaseModel):
    locations: Optional[List[dict]] = None  # [{"city": "Accra", "country": "Ghana"}]
    notification_preferences: Optional[dict] = None

class CompetitorSourceCreate(BaseModel):
    competitor_name: str
    url: HttpUrl
    target_value: str  # Brand or category to track
    is_active: bool = True

class CompetitorSourceUpdate(BaseModel):
    competitor_name: Optional[str] = None
    url: Optional[HttpUrl] = None
    target_value: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """
    Returns tenant settings including locations and notification preferences.
    """
    db = get_db()
    tenant_id = current_user["tenant_id"]
    
    try:
        res = db.table("tenants").select("name, locations, notification_preferences").eq("id", tenant_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return {
            "tenant_name": res.data.get("name"),
            "locations": res.data.get("locations", []),
            "notification_preferences": res.data.get("notification_preferences", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/")
async def update_settings(
    request: SettingsUpdateRequest,
    current_user: dict = Depends(require_admin)
):
    """
    Update tenant settings. Admin-only access.
    """
    db = get_db()
    tenant_id = current_user["tenant_id"]
    
    update_data = {}
    if request.locations is not None:
        update_data["locations"] = request.locations
    if request.notification_preferences is not None:
        update_data["notification_preferences"] = request.notification_preferences
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    try:
        db.table("tenants").update(update_data).eq("id", tenant_id).execute()
        return {
            "message": "Settings updated successfully",
            "updated_fields": list(update_data.keys())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@router.get("/competitors")
async def list_competitor_sources(current_user: dict = Depends(get_current_user)):
    """
    Returns all competitor tracking sources for the tenant.
    """
    db = get_db()
    tenant_id = current_user["tenant_id"]
    
    try:
        res = db.table("competitor_sources").select("*").eq("tenant_id", tenant_id).order("competitor_name").execute()
        return {"competitors": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/competitors")
async def create_competitor_source(
    request: CompetitorSourceCreate,
    current_user: dict = Depends(require_admin)
):
    """
    Add a new competitor tracking source. Admin-only access.
    """
    db = get_db()
    tenant_id = current_user["tenant_id"]
    
    try:
        res = db.table("competitor_sources").insert({
            "tenant_id": tenant_id,
            "competitor_name": request.competitor_name,
            "url": str(request.url),
            "target_value": request.target_value,
            "is_active": request.is_active
        }).execute()
        
        return {
            "message": "Competitor source created successfully",
            "competitor": res.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Creation failed: {str(e)}")

@router.patch("/competitors/{competitor_id}")
async def update_competitor_source(
    competitor_id: str,
    request: CompetitorSourceUpdate,
    current_user: dict = Depends(require_admin)
):
    """
    Update a competitor tracking source. Admin-only access.
    """
    db = get_db()
    tenant_id = current_user["tenant_id"]
    
    # Verify competitor belongs to tenant
    existing = db.table("competitor_sources").select("*").eq("id", competitor_id).eq("tenant_id", tenant_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Competitor source not found")
    
    update_data = {}
    if request.competitor_name is not None:
        update_data["competitor_name"] = request.competitor_name
    if request.url is not None:
        update_data["url"] = str(request.url)
    if request.target_value is not None:
        update_data["target_value"] = request.target_value
    if request.is_active is not None:
        update_data["is_active"] = request.is_active
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    try:
        db.table("competitor_sources").update(update_data).eq("id", competitor_id).eq("tenant_id", tenant_id).execute()
        return {
            "message": "Competitor source updated successfully",
            "competitor_id": competitor_id,
            "updated_fields": list(update_data.keys())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

@router.delete("/competitors/{competitor_id}")
async def delete_competitor_source(
    competitor_id: str,
    current_user: dict = Depends(require_admin)
):
    """
    Delete a competitor tracking source. Admin-only access.
    """
    db = get_db()
    tenant_id = current_user["tenant_id"]
    
    # Verify competitor belongs to tenant
    existing = db.table("competitor_sources").select("*").eq("id", competitor_id).eq("tenant_id", tenant_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Competitor source not found")
    
    try:
        db.table("competitor_sources").delete().eq("id", competitor_id).eq("tenant_id", tenant_id).execute()
        return {"message": "Competitor source deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")
