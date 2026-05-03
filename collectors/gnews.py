"""
collectors/gnews.py

Keyword-less collector.
Uses GNews.io API to fetch latest Ghana-specific news articles.
Free tier: 100 requests/day, 10 articles/request.
Env: GNEWS_API_KEY
"""
import logging
import os

import requests

from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")
GNEWS_BASE = "https://gnews.io/api/v4/top-headlines"


class GNewsCollector(BaseCollector):
    """
    Fetches top business/retail-relevant news for Ghana from GNews.io.
    Results are general_pulse signals — no specific keyword required.
    """

    def collect(self, **kwargs) -> list[CollectorResult]:
        if not GNEWS_API_KEY:
            logger.warning("GNEWS_API_KEY not set — skipping GNews collection.")
            return []

        results = []

        # Target: Business headlines and local Ghanaian news
        queries = [
            ("business", "Ghana business retail"),
            ("economy",  "Ghana economy prices inflation"),
        ]

        for topic, q in queries:
            try:
                articles = self._fetch(q)
                for article in articles:
                    content = f"{article.get('title', '')}\n\n{article.get('description', '')}\n\n{article.get('content', '')}"
                    results.append(CollectorResult(
                        source="gnews",
                        signal_type="general_pulse",
                        score=50,   # AI will refine impact_score
                        keyword=None,
                        raw_content=content[:4000],
                        signal_data={
                            "title":       article.get("title"),
                            "url":         article.get("url"),
                            "publishedAt": article.get("publishedAt"),
                            "source_name": article.get("source", {}).get("name"),
                            "topic":       topic,
                        },
                        geo="Ghana",
                    ))
            except Exception as e:
                logger.error("GNews collector failed for topic '%s': %s", topic, e)

        return results

    def _fetch(self, query: str, max_results: int = 10) -> list[dict]:
        resp = requests.get(
            GNEWS_BASE,
            params={
                "q":        query,
                "country":  "gh",
                "lang":     "en",
                "max":      max_results,
                "apikey":   GNEWS_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("articles", [])
