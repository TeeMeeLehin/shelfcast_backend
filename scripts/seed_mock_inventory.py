import os
import sys
import random
import logging

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_mock_inventory(tenant_id: str):
    """
    Updates the existing catalogue for a tenant with realistic 
    mock prices and stock levels for Phase 5 testing.
    """
    logger.info(f"Seeding mock prices and stock for tenant {tenant_id}...")
    
    # Fetch all SKUs for this tenant
    res = supabase.table("catalogue").select("sku_id, category").eq("tenant_id", tenant_id).execute()
    skus = res.data or []
    
    if not skus:
        logger.warning(f"No SKUs found for tenant {tenant_id}.")
        return

    logger.info(f"Found {len(skus)} SKUs. Updating...")
    
    for sku in skus:
        # Generate a realistic price (GHS 5.00 to GHS 150.00)
        # Higher prices for electronics, lower for perishables
        category = (sku.get("category") or "").lower()
        
        if "electronics" in category or "appliances" in category:
            price = random.uniform(200.0, 2500.0)
            stock = random.randint(5, 50)
        elif "beverages" in category or "confectionery" in category:
            price = random.uniform(5.0, 45.0)
            stock = random.randint(100, 1000)
        else:
            price = random.uniform(10.0, 150.0)
            stock = random.randint(20, 500)
            
        try:
            supabase.table("catalogue").update({
                "unit_price": round(price, 2),
                "stock_level": stock
            }).eq("sku_id", sku["sku_id"]).execute()
        except Exception as e:
            logger.error(f"Failed to update SKU {sku['sku_id']}: {e}")
            
    logger.info("Mock inventory seeding complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/seed_mock_inventory.py <tenant_id>")
    else:
        seed_mock_inventory(sys.argv[1])
