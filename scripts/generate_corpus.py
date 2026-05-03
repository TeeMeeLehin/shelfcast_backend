import sys
import os
import json
import logging
from collections import Counter

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_tenant_corpus(tenant_id: str):
    logger.info(f"Generating Keyword Corpus for Tenant: {tenant_id}")
    
    # 1. Fetch all active classified items for the tenant
    res = supabase.table("catalogue").select("brand, category, match_terms").eq(
        "tenant_id", tenant_id
    ).eq("is_active", True).execute()
    
    data = res.data or []
    total_skus = len(data)
    
    if total_skus == 0:
        logger.warning("No active items found for this tenant.")
        return

    # 2. Extract and Aggregate
    brands = set()
    categories = set()
    all_match_terms = []
    
    for row in data:
        brand = row.get("brand")
        if brand and brand.lower().strip() not in ["none", "unknown", "nan", ""]:
            brands.add(brand.strip())
            
        category = row.get("category")
        if category and category.lower().strip() not in ["none", "unknown", "nan", ""]:
            categories.add(category.strip())
            
        terms = row.get("match_terms") or []
        for t in terms:
            t_clean = t.strip().lower()
            if t_clean:
                all_match_terms.append(t_clean)

    # 3. Frequency Analysis
    term_counts = Counter(all_match_terms)
    unique_match_terms = list(term_counts.keys())
    
    # 4. Build Final Corpus Object
    corpus = {
        "metadata": {
            "tenant_id": tenant_id,
            "total_skus_processed": total_skus,
            "counts": {
                "unique_brands": len(brands),
                "unique_categories": len(categories),
                "unique_match_terms": len(unique_match_terms),
                "total_unique_keywords": len(brands | categories | set(unique_match_terms))
            }
        },
        "brands": sorted(list(brands)),
        "categories": sorted(list(categories)),
        "top_match_terms": [
            {"term": term, "frequency": count} 
            for term, count in term_counts.most_common(50)
        ],
        "all_unique_match_terms": sorted(unique_match_terms)
    }

    # 5. Save to File
    filename = f"corpus_{tenant_id[:8]}.json"
    with open(filename, "w") as f:
        json.dump(corpus, f, indent=2)
        
    # 6. Summary Output
    print("\n" + "="*50)
    print(f"CORPUS GENERATION COMPLETE: {filename}")
    print("="*50)
    print(f"Total SKUs:          {total_skus}")
    print(f"Unique Brands:       {len(brands)}")
    print(f"Unique Categories:   {len(categories)}")
    print(f"Unique Match Terms:  {len(unique_match_terms)}")
    print("-" * 50)
    
    # Calculate density
    unique_count = corpus["metadata"]["counts"]["total_unique_keywords"]
    keywords_per_1000 = (unique_count / total_skus) * 1000 if total_skus > 0 else 0
    print(f"Keyword Density:     ~{int(keywords_per_1000)} keywords per 1000 SKUs")
    print("="*50 + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_corpus.py <tenant_id>")
        sys.exit(1)
        
    tenant_id = sys.argv[1]
    generate_tenant_corpus(tenant_id)
