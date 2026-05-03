import logging
import os
import requests
from datetime import datetime, timezone
import random   

from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

class TrendsCollector(BaseCollector):
    """
    Fetches Google Trends data via SerpApi.
    Collects Interest Over Time, Related Topics, and Related Queries for context.
    """

    def collect(self, keyword: str, geo: str = "GH", **kwargs) -> list[CollectorResult]:
        if not keyword:
            return []
        
        if self.mock_mode:
            logger.info(f"[MOCK] Generating AI trends for: {keyword}")
            avg_interest = random.randint(10, 95)
            # Use AI to generate a realistic explanation of the trend
            contents = self._mock_signals(keyword=keyword, source="google_trends", count=1)
            raw_content = contents[0] if contents else f"MOCK: {keyword} is trending due to increased seasonal demand."
            
            return [CollectorResult(
                source="google_trends",
                signal_type="keyword_based",
                score=self._safe_score(avg_interest),
                keyword=keyword,
                raw_content=raw_content,
                signal_data={"avg_interest": avg_interest, "is_mock": True},
                geo=geo
            )]
        
        if not SERPAPI_KEY:
            logger.warning("SERPAPI_KEY not found. Skipping Google Trends collection.")
            return []

        try:
            # 1. Fetch Interest Over Time
            params = {
                "engine": "google_trends",
                "q": keyword,
                "geo": geo,
                "data_type": "TIMESERIES",
                "api_key": SERPAPI_KEY
            }
            
            response = requests.get("https://serpapi.com/search", params=params)
            data = response.json()
            
            if "error" in data:
                logger.error("SerpApi Trends error: %s", data["error"])
                return []

            # Calculate average interest score from timeseries
            timeseries = data.get("interest_over_time", {}).get("timeline_data", [])
            avg_interest = 0
            if timeseries:
                # Some entries might have multiple values if comparing, but here q is a single string
                scores = [day.get("values", [{}])[0].get("extracted_value", 0) for day in timeseries]
                avg_interest = sum(scores) / len(scores) if scores else 0
            
            score = self._safe_score(avg_interest, max_val=100.0)

            # 2. Fetch Related Queries for context (This is the "meaningful" info)
            # We do a second call to get RELATED_QUERIES
            params["data_type"] = "RELATED_QUERIES"
            query_res = requests.get("https://serpapi.com/search", params=params).json()
            
            related_queries = []
            top_queries = query_res.get("related_queries", {}).get("top", [])
            rising_queries = query_res.get("related_queries", {}).get("rising", [])
            
            for q in (top_queries + rising_queries):
                query_text = q.get("query")
                if query_text:
                    related_queries.append(query_text)

            # Build raw_content from related queries to give the AI Tagger something to work with
            content_str = ""
            if related_queries:
                content_str = f"Related trending queries for '{keyword}' in {geo}: " + ", ".join(related_queries[:10])

            return [CollectorResult(
                source="google_trends",
                signal_type="keyword_based",
                score=score,
                keyword=keyword,
                raw_content=content_str,
                signal_data={
                    "avg_interest": avg_interest,
                    "related_queries": related_queries,
                    "timeline": timeseries[:5] # Sample for storage
                },
                geo=geo,
            )]

        except Exception as e:
            logger.error("SerpApi Trends collector failed for keyword '%s': %s", keyword, e)
            return []
