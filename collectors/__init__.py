"""
collectors/__init__.py

Exposes all collectors for easy import.
"""
from collectors.base import BaseCollector, CollectorResult
from collectors.news_rss import RSSCollector
from collectors.gnews import GNewsCollector
from collectors.newsapi_collector import NewsAPICollector
from collectors.reddit import RedditCollector
from collectors.trends import TrendsCollector
from collectors.social import SocialCollector
from collectors.competitor import CompetitorCollector

__all__ = [
    "BaseCollector",
    "CollectorResult",
    "RSSCollector",
    "GNewsCollector",
    "NewsAPICollector",
    "RedditCollector",
    "TrendsCollector",
    "SocialCollector",
    "CompetitorCollector",
]
