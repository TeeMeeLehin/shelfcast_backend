from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from app.db import get_db
from app.deps import get_current_tenant, require_admin
from typing import List, Optional

router = APIRouter()

class CatalogueUpdateRequest(BaseModel):
    sku_name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[float] = None
    stock_level: Optional[float] = None
    match_terms: Optional[List[str]] = None
    is_active: Optional[bool] = None

@router.get("/stats")
async def get_catalogue_stats(tenant_id: str = Depends(get_current_tenant)):
    """
    Returns high-level analytics for the tenant's catalogue.
    """
    db = get_db()
    
    try:
        # Fetch all brands and categories for this tenant to compute stats
        res = db.table("catalogue").select("brand, category, classification_status").eq("tenant_id", tenant_id).execute()
        data = res.data or []
        
        total_skus = len(data)
        brands = set()
        categories = set()
        pending_count = 0
        needs_review_count = 0
        
        for item in data:
            if item.get("brand"):
                brands.add(item["brand"])
            if item.get("category"):
                categories.add(item["category"])
            
            status = item.get("classification_status")
            if status == "pending":
                pending_count += 1
            elif status == "needs_review":
                needs_review_count += 1
                
        return {
            "total_skus": total_skus,
            "unique_brands": len(brands),
            "unique_categories": len(categories),
            "status_breakdown": {
                "pending": pending_count,
                "needs_review": needs_review_count,
                "classified": total_skus - pending_count - needs_review_count
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_catalogue(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    brand: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    tenant_id: str = Depends(get_current_tenant)
):
    """
    Returns a paginated list of products in the catalogue.
    """
    db = get_db()
    offset = (page - 1) * page_size
    
    query = db.table("catalogue").select("*", count="exact").eq("tenant_id", tenant_id)
    
    if brand:
        query = query.eq("brand", brand)
    if category:
        query = query.eq("category", category)
    if search:
        query = query.ilike("sku_name", f"%{search}%")
        
    res = query.order("sku_name", desc=False).range(offset, offset + page_size - 1).execute()
    
    return {
        "items": res.data,
        "total": res.count,
        "page": page,
        "page_size": page_size
    }


@router.get("/{sku_id}")
async def get_product_detail(sku_id: str, tenant_id: str = Depends(get_current_tenant)):
    """
    Fetch full details for a specific product.
    """
    db = get_db()
    res = db.table("catalogue").select("*").eq("tenant_id", tenant_id).eq("sku_id", sku_id).single().execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Product not found")
        
    return res.data

@router.patch("/{sku_id}")
async def update_product(
    sku_id: str,
    request: CatalogueUpdateRequest,
    tenant_id: str = Depends(get_current_tenant),
    current_user: dict = Depends(require_admin)
):
    """
    Update catalogue item fields. Admin-only access.
    """
    db = get_db()
    
    # Verify SKU exists and belongs to tenant
    existing = db.table("catalogue").select("*").eq("tenant_id", tenant_id).eq("sku_id", sku_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Build update dict with only provided fields
    update_data = {}
    if request.sku_name is not None:
        update_data["sku_name"] = request.sku_name
    if request.brand is not None:
        update_data["brand"] = request.brand
    if request.category is not None:
        update_data["category"] = request.category
    if request.unit_price is not None:
        update_data["unit_price"] = request.unit_price
    if request.stock_level is not None:
        update_data["stock_level"] = request.stock_level
    if request.match_terms is not None:
        update_data["match_terms"] = request.match_terms
    if request.is_active is not None:
        update_data["is_active"] = request.is_active
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    try:
        res = db.table("catalogue").update(update_data).eq("tenant_id", tenant_id).eq("sku_id", sku_id).execute()
        return {
            "message": "Product updated successfully",
            "sku_id": sku_id,
            "updated_fields": list(update_data.keys())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
