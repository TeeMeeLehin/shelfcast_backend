import json
import logging
from collections import Counter
from app.db import supabase

logger = logging.getLogger(__name__)

class CorpusManager:
    """
    Handles extraction and synthesis of keywords from a tenant's catalogue.
    This defines 'what' the system should be looking for in the market.
    """
    
    def generate_tenant_corpus(self, tenant_id: str) -> dict:
        logger.info(f"Synthesizing Keyword Corpus for Tenant: {tenant_id}")
        
        # 1. Fetch all active items
        res = supabase.table("catalogue").select("brand, category, match_terms").eq(
            "tenant_id", tenant_id
        ).eq("is_active", True).execute()
        
        data = res.data or []
        total_skus = len(data)
        
        if total_skus == 0:
            logger.warning("No active items found for this tenant. Corpus will be empty.")
            return {}

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

        # 3. Frequency Analysis & Filtering
        term_counts = Counter(all_match_terms)
        sorted_terms = term_counts.most_common()
        
        # Take top 40% of match terms by frequency to filter out noise
        top_count = max(min(10, len(sorted_terms)), int(len(sorted_terms) * 0.4))
        filtered_match_terms = {t[0] for t in sorted_terms[:top_count]}
        
        # 4. Collapse into a single unique set
        collapsed_search_terms = set()
        for s in [brands, categories, filtered_match_terms]:
            for item in s:
                clean_item = item.lower().strip()
                if clean_item:
                    collapsed_search_terms.add(clean_item)

        # 5. Build Final Corpus Object
        corpus = {
            "metadata": {
                "tenant_id": tenant_id,
                "total_skus_processed": total_skus,
                "counts": {
                    "unique_brands": len(brands),
                    "unique_categories": len(categories),
                    "unique_match_terms_raw": len(term_counts),
                    "filtered_match_terms": len(filtered_match_terms),
                    "final_search_terms": len(collapsed_search_terms)
                }
            },
            "search_terms": sorted(list(collapsed_search_terms)),
            "breakdown": {
                "brands": sorted(list(brands)),
                "categories": sorted(list(categories)),
                "filtered_match_terms": sorted(list(filtered_match_terms))
            }
        }

        # 6. Persist locally
        filename = f"corpus_{tenant_id[:8]}.json"
        with open(filename, "w") as f:
            json.dump(corpus, f, indent=2)
            
        logger.info(f"Smart Corpus synthesized: {len(collapsed_search_terms)} unique search terms (from {total_skus} SKUs).")
        return corpus

corpus_manager = CorpusManager()
