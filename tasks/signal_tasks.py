"""
tasks/signal_tasks.py

Celery tasks for Phase 3 external signal collection and orchestration.
"""
import logging
import os
from datetime import datetime, timezone

from celery import shared_task
from app.db import supabase

logger = logging.getLogger(__name__)

# Import collectors
from collectors import (
    RSSCollector,
    GNewsCollector,
    NewsAPICollector,
    RedditCollector,
    TrendsCollector,
    SocialCollector,
    CompetitorCollector,
)

@shared_task(name="tasks.run_nightly_collection")
def run_nightly_collection(tenant_id: str | None = None, sync: bool = False):
    """
    Main orchestration task.
    """
    msg = f"Starting signal collection for {'all tenants' if not tenant_id else f'tenant {tenant_id}'}..."
    logger.info(msg)
    
    # 1. Trigger Keyword-less Collectors
    if sync: dispatch_general_collectors()
    else: dispatch_general_collectors.delay()
    
    # 2. Smart Corpus Extraction
    # Uses the deduplicated, frequency-filtered "Golden List"
    from ai.corpus import corpus_manager
    corpus_data = corpus_manager.generate_tenant_corpus(tenant_id)
    final_corpus = corpus_data.get("search_terms", [])
    
    logger.info(f"Using Smart Corpus: {len(final_corpus)} unique keywords for collection.")
            
    # If running synchronously (bootstrap mode), limit to top 5 keywords
    # to prevent the frontend from timing out (collection takes ~2s per keyword).
    # The remaining keywords will be naturally picked up in the next nightly run.
    if sync and len(final_corpus) > 5:
        logger.info(f"Bootstrap mode: Limiting sync collection to top 5 keywords from {len(final_corpus)} total.")
        final_corpus = final_corpus[:5]
            
    for term in final_corpus:
        if sync: dispatch_keyword_collectors(term)
        else: dispatch_keyword_collectors.delay(term)
            
    # 3. Trigger Competitor Scraping
    comp_query = supabase.table("competitor_sources").select("*").eq("is_active", True)
    if tenant_id:
        comp_query = comp_query.eq("tenant_id", tenant_id)
    res_comp = comp_query.execute()
    
    for comp in res_comp.data:
        if sync: 
            dispatch_competitor_scraper(
                url=comp["url"], 
                target_value=comp["target_value"],
                competitor_name=comp["competitor_name"]
            )
        else:
            dispatch_competitor_scraper.delay(
                url=comp["url"], 
                target_value=comp["target_value"],
                competitor_name=comp["competitor_name"]
            )
        
    return {"status": "dispatched", "keywords": len(final_corpus), "competitors": len(res_comp.data)}


@shared_task(name="tasks.dispatch_general_collectors")
def dispatch_general_collectors():
    """Run all macro/keyword-less collectors."""
    collectors = [
        RSSCollector(),
        GNewsCollector(),
        NewsAPICollector(),
        RedditCollector()
    ]
    
    total_inserted = 0
    for collector in collectors:
        try:
            results = collector.collect()
            if results:
                rows = [r.to_db_row() for r in results]
                supabase.table("raw_signals").insert(rows).execute()
                total_inserted += len(rows)
        except Exception as e:
            logger.error("Error running general collector %s: %s", type(collector).__name__, e)
            
    # After collecting, trigger the AI tagger
    if total_inserted > 0:
        from tasks.signal_tasks import process_general_signals_task
        process_general_signals_task.delay()
        
    return {"inserted": total_inserted}


@shared_task(name="tasks.dispatch_keyword_collectors")
def dispatch_keyword_collectors(keyword: str):
    """Run keyword-specific collectors for a single match term."""
    collectors = [
        TrendsCollector(),
        SocialCollector()
    ]
    
    total_inserted = 0
    for collector in collectors:
        try:
            results = collector.collect(keyword=keyword)
            if results:
                rows = [r.to_db_row() for r in results]
                supabase.table("raw_signals").insert(rows).execute()
                total_inserted += len(rows)
        except Exception as e:
            logger.error("Error running keyword collector %s for '%s': %s", type(collector).__name__, keyword, e)
            
    return {"keyword": keyword, "inserted": total_inserted}


@shared_task(name="tasks.dispatch_competitor_scraper")
def dispatch_competitor_scraper(url: str, target_value: str, competitor_name: str):
    """Run competitor scraper for a specific URL."""
    try:
        collector = CompetitorCollector()
        results = collector.collect(url=url, brand_or_category=target_value, competitor_name=competitor_name)
        
        if results:
            rows = [r.to_db_row() for r in results]
            supabase.table("raw_signals").insert(rows).execute()
            
            # Update last scraped timestamp
            now = datetime.now(timezone.utc).isoformat()
            supabase.table("competitor_sources").update({"last_scraped_at": now}).eq("url", url).execute()
            
            return {"url": url, "inserted": len(rows)}
    except Exception as e:
        logger.error("Error running competitor scraper for %s: %s", url, e)
        
    return {"url": url, "inserted": 0}


@shared_task(name="tasks.process_general_signals_task")
def process_general_signals_task():
    """Runs the AI pipeline to tag raw general_pulse signals."""
    from ai.tagger import signal_tagger
    try:
        count = signal_tagger.process_unprocessed_signals()
        return {"processed": count}
    except Exception as e:
        logger.error("process_general_signals_task failed: %s", e)
        return {"processed": 0}
