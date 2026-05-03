"""
collectors/news_rss.py

Keyword-less collector.
Scrapes RSS feeds from major Ghanaian news/blog sites daily.
Sources: JoyOnline, Graphic Online, CitiNewsroom.
"""
import logging
import hashlib
from datetime import datetime, timezone

import feedparser
import requests
import random
from bs4 import BeautifulSoup

from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Known Ghanaian news RSS feeds
# Add new feeds here — no code changes needed elsewhere.
# ─────────────────────────────────────────────────────────────────────────────
FEEDS = [
    {
        "source":   "joyonline",
        "url":      "https://www.myjoyonline.com/feed/",
        "category": "general",
    },
    # {
    #     "source":   "graphic_online",
    #     "url":      "https://www.graphic.com.gh/",
    #     "category": "general",
    # },
    # {
    #     "source":   "citinewsroom",
    #     "url":      "https://citinewsroom.com/feed/",
    #     "category": "general",
    # },
    # {
    #     "source":   "ghanaweb_business",
    #     "url":      "https://www.ghanaweb.com/GhanaHomePage/business/business.rss",
    #     "category": "business",
    # },
]

# Maximum articles to pull per feed per run (keeps costs manageable for AI tagging)
MAX_ARTICLES_PER_FEED = 20


class RSSCollector(BaseCollector):
    """
    Collects the latest articles from Ghanaian news RSS feeds.
    Returns general_pulse signals with raw_content for downstream AI tagging.
    """

    def collect(self, **kwargs) -> list[CollectorResult]:
        if self.mock_mode:
            logger.info("[MOCK] Generating RSS news signals...")
            contents = self._mock_signals(source="rss_news", count=4)
            return [
                CollectorResult(
                    source="rss_news",
                    signal_type="general_pulse",
                    score=random.randint(50, 95),
                    raw_content=c,
                    signal_data={"is_mock": True}
                ) for c in contents
            ]

        results = []
        for feed in FEEDS:
            try:
                items = self._fetch_feed(feed["source"], feed["url"])
                results.extend(items)
            except Exception as e:
                logger.error("RSS collector failed for %s: %s", feed["source"], e)
        return results

    def _fetch_feed(self, source: str, url: str) -> list[CollectorResult]:
        parsed = feedparser.parse(url)
        items = parsed.entries[:MAX_ARTICLES_PER_FEED]
        results = []

        for entry in items:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")

            # Try to get full article text for better AI tagging
            body = self._fetch_article_text(link)
            raw_content = f"{title}\n\n{body or summary}"

            results.append(CollectorResult(
                source=source,
                signal_type="general_pulse",
                score=50,           # neutral base score; AI will refine impact_score
                keyword=None,
                raw_content=raw_content[:4000],  # truncate for LLM context window
                signal_data={
                    "title":       title,
                    "link":        link,
                    "published":   entry.get("published", ""),
                    "content_hash": hashlib.md5(raw_content.encode()).hexdigest(),
                },
                geo="Ghana",
            ))

        return results

    def _fetch_article_text(self, url: str) -> str | None:
        """Best-effort extraction of article body text."""
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "ShelfCastBot/1.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Most news sites wrap article body in <article> or <p> tags
            article = soup.find("article")
            if article:
                return article.get_text(separator=" ", strip=True)
            paragraphs = soup.find_all("p")
            return " ".join(p.get_text(strip=True) for p in paragraphs[:15])
        except Exception:
            return None
