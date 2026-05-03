"""
collectors/social.py

Keyword-based collector.
Implements the Abstract Social Collector pattern for enterprise-grade flexibility.
Includes a Mock adapter for local testing and an Apify adapter stub.
"""
import logging
import os
import random
from typing import Protocol
from datetime import datetime, timezone

from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)


class SocialProvider(Protocol):
    """Interface for social media providers (Apify, BrightData, Mock, etc.)"""
    def fetch_mentions(self, keyword: str, platform: str) -> dict:
        ...


class MockSocialProvider(SocialProvider):
    """Returns realistic mock data for local development."""
    def fetch_mentions(self, keyword: str, platform: str) -> dict:
        base_volume = random.randint(10, 500)
        return {
            "volume": base_volume,
            "engagement": base_volume * random.randint(2, 10),
            "top_hashtags": [f"#{keyword.replace(' ', '')}", "#Ghana", "#Trending"],
            "sentiment_estimate": random.choice([-10, 0, 20, 50, 80]),
        }


class ApifySocialProvider(SocialProvider):
    """
    Stub for Apify integration.
    Requires APIFY_TOKEN and specific actor IDs.
    """
    def __init__(self):
        self.token = os.getenv("APIFY_TOKEN")
        # In a real setup, we would import ApifyClient here
        # from apify_client import ApifyClient
        # self.client = ApifyClient(self.token)

    def fetch_mentions(self, keyword: str, platform: str) -> dict:
        if not self.token:
            logger.warning("APIFY_TOKEN missing, falling back to mock data.")
            return MockSocialProvider().fetch_mentions(keyword, platform)
            
        # Placeholder for actual Apify actor execution
        # actor_id = "tiktok_actor_id" if platform == "tiktok" else "twitter_actor_id"
        # run = self.client.actor(actor_id).call(run_input={"search": keyword, "country": "GH"})
        # return self._parse_apify_dataset(self.client.dataset(run["defaultDatasetId"]).iterate_items())
        
        return MockSocialProvider().fetch_mentions(keyword, platform)


class SocialCollector(BaseCollector):
    """
    Fetches keyword mentions from TikTok and X (Twitter).
    """
    
    def __init__(self, provider: SocialProvider | None = None):
        super().__init__()
        # Default to Apify stub (which falls back to mock if no token)
        self.provider = provider or ApifySocialProvider()

    def collect(self, keyword: str, **kwargs) -> list[CollectorResult]:
        if not keyword:
            return []

        results = []
        platforms = ["tiktok", "x"]

        for platform in platforms:
            try:
                if self.mock_mode:
                    logger.info(f"[MOCK] Generating AI social signals for: {keyword} on {platform}")
                    contents = self._mock_signals(keyword=keyword, source=platform, count=1)
                    raw_content = contents[0] if contents else None
                    data = MockSocialProvider().fetch_mentions(keyword, platform)
                else:
                    data = self.provider.fetch_mentions(keyword, platform)
                    raw_content = None # Placeholder if provider doesn't return text yet
                
                # Normalise score based on engagement volume (arbitrary logic for MVP)
                # Let's say 1000 engagement = 100 score
                score = self._safe_score(data.get("engagement", 0), max_val=1000.0)

                results.append(CollectorResult(
                    source=platform,
                    signal_type="keyword_based",
                    score=score,
                    keyword=keyword,
                    raw_content=raw_content,
                    signal_data=data,
                    geo="Ghana",
                ))
            except Exception as e:
                logger.error("Social collector failed for %s on %s: %s", keyword, platform, e)

        return results
