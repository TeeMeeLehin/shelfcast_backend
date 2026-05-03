"""
collectors/newsapi_collector.py

Keyword-less collector.
Uses NewsAPI.org to fetch general business and retail news about Ghana.
Env: NEWSAPI_KEY
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
import random

from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "0f8c7712f5a74e46a4be2f37450cc6a7")
NEWSAPI_BASE = "https://newsapi.org/v2/everything"


class NewsAPICollector(BaseCollector):
    """
    Fetches articles related to Ghana business/retail from NewsAPI.
    Results are general_pulse signals.
    """

    def collect(self, **kwargs) -> list[CollectorResult]:
        if self.mock_mode:
            logger.info("[MOCK] Generating NewsAPI signals...")
            contents = self._mock_signals(source="newsapi", count=2)
            return [
                CollectorResult(
                    source="newsapi",
                    signal_type="general_pulse",
                    score=random.randint(40, 90),
                    raw_content=c,
                    signal_data={"is_mock": True}
                ) for c in contents
            ]

        if not NEWSAPI_KEY:
            logger.warning("NEWSAPI_KEY not set — skipping NewsAPI collection.")
            return []

        # Target articles published in the last 48 hours
        from_date = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")

        query = "(Ghana) AND (business OR retail OR economy OR FMCG OR inflation OR cedi)"

        results = []
        try:
            articles = self._fetch(query, from_date)
            for article in articles:
                title = article.get("title") or ""
                desc = article.get("description") or ""
                content = article.get("content") or ""
                
                # Filter out obvious non-news (like "[Removed]")
                if title == "[Removed]":
                    continue

                full_text = f"{title}\n\n{desc}\n\n{content}"
                
                results.append(CollectorResult(
                    source="newsapi",
                    signal_type="general_pulse",
                    score=50,  # Base neutral score
                    keyword=None,
                    raw_content=full_text[:4000],
                    signal_data={
                        "title":       title,
                        "url":         article.get("url"),
                        "publishedAt": article.get("publishedAt"),
                        "source_name": article.get("source", {}).get("name"),
                        "author":      article.get("author"),
                    },
                    geo="Ghana",
                ))
        except Exception as e:
            logger.error("NewsAPI collector failed: %s", e)

        return results

    def _fetch(self, query: str, from_date: str, max_results: int = 15) -> list[dict]:
        resp = requests.get(
            NEWSAPI_BASE,
            params={
                "q":        query,
                "language": "en",
                "sortBy":   "relevancy",
                "from":     from_date,
                "pageSize": max_results,
                "apiKey":   NEWSAPI_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("articles", [])
