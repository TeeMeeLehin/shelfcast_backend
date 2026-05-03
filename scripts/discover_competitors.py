"""
scripts/discover_competitors.py

Utility script to automatically populate the `competitor_sources` table.
It queries the active catalogue for unique brands and performs programmatic searches
to find competitor product pages on target retailers (e.g., Jumia GH, Melcom).
"""
import os
import time
import logging
import requests
from urllib.parse import quote_plus
from app.db import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# Target retailers to monitor
TARGET_RETAILERS = [
    {"name": "Jumia GH", "domain": "jumia.com.gh"},
    {"name": "Melcom", "domain": "melcom.com"},
]


def _search_google(query: str) -> str | None:
    """Returns the first Google Search result URL for a query."""
    if not SERPAPI_KEY:
        # Mock mode if no SerpAPI key
        # In a real environment without SerpAPI, we could use beautifulsoup on Google
        # but that gets blocked instantly. For MVP demonstration, return a mock URL.
        logger.info(f"[MOCK] Searched for: {query}")
        return f"https://mock-retailer.com/search?q={quote_plus(query)}"
        
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "engine": "google",
                "gl": "gh", # Ghana
                "api_key": SERPAPI_KEY,
                "num": 3
            },
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        
        organic = data.get("organic_results", [])
        if organic:
            return organic[0].get("link")
            
    except Exception as e:
        logger.error("Search failed for query '%s': %s", query, e)
        
    return None


def run_discovery():
    """Main discovery loop."""
    logger.info("Starting competitor discovery...")
    
    # 1. Fetch all active distinct brands and their tenant IDs
    # Since Supabase PostgREST doesn't support easy DISTINCT without RPC,
    # we'll fetch all and filter in Python.
    res = supabase.table("catalogue").select("tenant_id, brand").eq("is_active", True).execute()
    
    # Map of tenant_id -> set(brands)
    tenant_brands = {}
    for row in res.data:
        t_id = row["tenant_id"]
        brand = row.get("brand")
        if brand and str(brand).strip().lower() not in ("nan", "none", "", "unknown"):
            if t_id not in tenant_brands:
                tenant_brands[t_id] = set()
            tenant_brands[t_id].add(brand.strip())
            
    total_found = 0
            
    for t_id, brands in tenant_brands.items():
        logger.info("Processing %d brands for tenant %s", len(brands), t_id)
        
        for brand in brands:
            for retailer in TARGET_RETAILERS:
                # E.g., site:jumia.com.gh "Nestle Milo"
                query = f"site:{retailer['domain']} \"{brand}\""
                url = _search_google(query)
                
                if url:
                    try:
                        supabase.table("competitor_sources").upsert({
                            "tenant_id": t_id,
                            "target_type": "brand",
                            "target_value": brand,
                            "competitor_name": retailer["name"],
                            "url": url,
                            "is_active": True
                        }, on_conflict="tenant_id,target_type,target_value,url").execute()
                        logger.info("Saved %s URL for %s", retailer["name"], brand)
                        total_found += 1
                    except Exception as e:
                        logger.error("Failed to insert %s URL for %s: %s", retailer["name"], brand, e)
                
                time.sleep(1) # Rate limit protection

    logger.info("Discovery complete. Added %d new competitor URLs.", total_found)


if __name__ == "__main__":
    run_discovery()
