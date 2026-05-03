"""
collectors/reddit.py

Keyword-less collector.
Scrapes recent posts from r/ghana using PRAW (Python Reddit API Wrapper).
Env: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
"""
import logging
import os
import hashlib

import praw
import random
from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "ShelfCast/1.0 by RetailIntelligence")


class RedditCollector(BaseCollector):
    """
    Scrapes 'hot' and 'new' posts from r/ghana to capture grassroots consumer sentiment.
    Returns general_pulse signals.
    """

    def collect(self, **kwargs) -> list[CollectorResult]:
        if self.mock_mode:
            logger.info("[MOCK] Generating Reddit signals...")
            contents = self._mock_signals(source="reddit", count=3)
            return [
                CollectorResult(
                    source="reddit",
                    signal_type="general_pulse",
                    score=random.randint(30, 70),
                    raw_content=c,
                    signal_data={"is_mock": True}
                ) for c in contents
            ]

        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            logger.warning("Reddit API credentials not set — skipping Reddit collection.")
            return []

        try:
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent=REDDIT_USER_AGENT,
            )
            
            subreddit = reddit.subreddit("ghana")
            results = []
            
            # Fetch top 15 hot posts
            for post in subreddit.hot(limit=15):
                # Skip stickied mod posts
                if post.stickied:
                    continue
                    
                raw_content = f"{post.title}\n\n{post.selftext}"
                
                # Only include text-heavy posts or relevant discussions
                if len(raw_content.strip()) < 50 and not post.url:
                    continue

                results.append(CollectorResult(
                    source="reddit",
                    signal_type="general_pulse",
                    score=50, # Neutral base
                    keyword=None,
                    raw_content=raw_content[:4000],
                    signal_data={
                        "title":        post.title,
                        "url":          f"https://reddit.com{post.permalink}",
                        "score":        post.score,
                        "num_comments": post.num_comments,
                        "created_utc":  post.created_utc,
                        "content_hash": hashlib.md5(raw_content.encode()).hexdigest()
                    },
                    geo="Ghana",
                ))

            return results

        except Exception as e:
            logger.error("Reddit collector failed: %s", e)
            return []
