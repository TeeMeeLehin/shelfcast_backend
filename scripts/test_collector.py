import sys
import os
import logging
import json

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collectors import (
    RSSCollector,
    GNewsCollector,
    NewsAPICollector,
    RedditCollector,
    TrendsCollector,
    SocialCollector,
    CompetitorCollector
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTORS = {
    "rss": RSSCollector,
    "gnews": GNewsCollector,
    "newsapi": NewsAPICollector,
    "reddit": RedditCollector,
    "trends": TrendsCollector,
    "social": SocialCollector,
    "competitor": CompetitorCollector
}

def run_test(name: str, keyword: str = None):
    collector_cls = COLLECTORS.get(name.lower())
    if not collector_cls:
        print(f"Error: Unknown collector '{name}'. Available: {list(COLLECTORS.keys())}")
        return

    logger.info(f"Testing collector: {collector_cls.__name__} (Keyword: {keyword})")
    
    collector = collector_cls()
    
    # Keyword-based vs General Pulse
    try:
        if name.lower() in ["trends", "social"]:
            if not keyword:
                print(f"Error: Collector '{name}' requires a --keyword argument.")
                return
            results = collector.collect(keyword=keyword)
        elif name.lower() == "competitor":
            # For testing competitor, we'll use a sample brand and mock URL
            results = collector.collect(
                url="https://www.jumia.com.gh/catalog/?q=milo", 
                brand_or_category="Milo", 
                competitor_name="Jumia"
            )
        else:
            # General pulse collectors
            results = collector.collect()
            
        print("\n" + "="*50)
        print(f"RESULTS FOR {name.upper()}: {len(results)} found")
        print("="*50)
        
        for r in results:
            print(f"\n- Source: {r.source}")
            print(f"  Score: {r.score}")
            print(f"  Type: {r.signal_type}")
            if r.keyword: print(f"  Keyword: {r.keyword}")
            if r.raw_content:
                preview = r.raw_content[:150].replace("\n", " ")
                print(f"  Content: {preview}...")
        print("="*50 + "\n")
        
    except Exception as e:
        logger.error(f"Collector failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_collector.py <collector_name> [--keyword <keyword>]")
        print(f"Example: python scripts/test_collector.py reddit")
        print(f"Example: python scripts/test_collector.py trends --keyword 'Milo'")
        sys.exit(1)

    name = sys.argv[1]
    keyword = None
    if "--keyword" in sys.argv:
        idx = sys.argv.index("--keyword")
        if idx + 1 < len(sys.argv):
            keyword = sys.argv[idx + 1]

    run_test(name, keyword)
