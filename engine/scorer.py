import logging
from datetime import datetime, timedelta, timezone
from app.db import supabase

logger = logging.getLogger(__name__)

class ScoringEngine:
    """
    Calculates the composite intelligence score (0-100) for a given SKU
    by combining external market signals and internal sales velocity.
    """
    
    def calculate_sku_score(self, tenant_id: str, sku_id: str, run_date: str = None) -> dict:
        """
        Calculates the score and returns the breakdown.
        """
        if not run_date:
            run_date = datetime.now(timezone.utc).date().isoformat()
            
        logger.info(f"Calculating score for SKU {sku_id} on {run_date}...")
        
        # 1. Fetch SKU details (for match terms)
        cat_res = supabase.table("catalogue").select("*").eq("tenant_id", tenant_id).eq("sku_id", sku_id).execute()
        if not cat_res.data:
            logger.warning(f"SKU {sku_id} not found in catalogue.")
            return None
        sku_data = cat_res.data[0]
        
        match_terms = sku_data.get("match_terms", [])
        brand = sku_data.get("brand")
        category = sku_data.get("category")
        
        # Build search entities list (lowercase)
        search_entities = [t.lower() for t in match_terms]
        if brand: search_entities.append(brand.lower())
        if category: search_entities.append(category.lower())
        search_entities = list(set(search_entities))
        
        # 2. Fetch Processed Signals (Last 48 hours to be safe)
        lookback = (datetime.fromisoformat(run_date) - timedelta(days=2)).isoformat()
        
        # In a real SQL query, we'd use ANY or overlaps. 
        # Using Supabase client, we fetch all processed recent signals for the tenant (or global)
        # and filter in memory for MVP simplicity.
        sig_res = supabase.table("raw_signals").select("*").eq("is_processed", True).gte("collected_at", lookback).execute()
        
        matched_signals = []
        for sig in sig_res.data:
            sig_keyword = (sig.get("keyword") or "").lower()
            sig_entities = [e.lower() for e in sig.get("entities", [])]
            
            # Match logic: if the signal keyword or any extracted entity matches our SKU's search terms
            if sig_keyword in search_entities or any(e in search_entities for e in sig_entities):
                matched_signals.append(sig)
                
        # 3. Calculate External Signal Score
        external_score = 50 # Base neutral
        if matched_signals:
            total_impact = 0
            weighted_sentiment = 0
            
            for sig in matched_signals:
                impact = sig.get("impact_score", 10)
                sentiment = sig.get("sentiment_score", 50)
                
                # Sentiment is 0-100. Shift to -50 to +50 for weighting
                shifted_sentiment = sentiment - 50 
                weighted_sentiment += (shifted_sentiment * impact)
                total_impact += impact
                
            if total_impact > 0:
                # Average weighted sentiment (-50 to +50)
                avg_shifted = weighted_sentiment / total_impact
                external_score = 50 + avg_shifted # Back to 0-100 scale
                
        # Clamp external score
        external_score = max(0, min(100, external_score))
        
        # 4. Fetch Sales Velocity (Internal Data)
        # Look at last 7 days vs previous 7 days
        sales_score = 50 # Neutral default
        try:
            sales_res = supabase.table("sales_history").select("units_sold, sale_date").eq("tenant_id", tenant_id).eq("sku_id", sku_id).order("sale_date", desc=True).limit(14).execute()
            if sales_res.data and len(sales_res.data) > 7:
                sales = sorted(sales_res.data, key=lambda x: x["sale_date"], reverse=True)
                recent_7 = sum(s["units_sold"] for s in sales[:7])
                prev_7 = sum(s["units_sold"] for s in sales[7:14])
                
                if prev_7 > 0:
                    growth = (recent_7 - prev_7) / prev_7
                    # Clamp growth to [-1.0, 1.0] and map to 0-100
                    sales_score = 50 + (max(-1.0, min(1.0, growth)) * 50)
        except Exception as e:
            logger.error(f"Error calculating sales velocity for {sku_id}: {e}")
            
        # 5. Calculate Composite Score
        # 60% External Market Signals, 40% Internal Sales
        composite_score = (external_score * 0.6) + (sales_score * 0.4)
        
        return {
            "composite_score": round(composite_score, 1),
            "score_breakdown": {
                "external_signals_score": round(external_score, 1),
                "internal_sales_score": round(sales_score, 1),
                "signals_matched": len(matched_signals)
            },
            "matched_signals": matched_signals # Useful for the Narrator
        }

scoring_engine = ScoringEngine()
