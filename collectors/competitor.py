"""
collectors/competitor.py

Keyword-based collector (technically URL-based but linked to brand/category).
Uses ScraperAPI to bypass bot protection on Ghanaian retail sites (Jumia, Melcom, etc.).
Env: SCRAPERAPI_KEY
"""
import logging
import os
import re

import requests
import random
from bs4 import BeautifulSoup

from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "")


class CompetitorCollector(BaseCollector):
    """
    Scrapes competitor URLs to track price changes and stock availability.
    """

    def collect(self, url: str, brand_or_category: str, competitor_name: str, **kwargs) -> list[CollectorResult]:
        if not url:
            return []

        if self.mock_mode:
            logger.info(f"[MOCK] Generating competitor data for: {brand_or_category} at {competitor_name}")
            return [CollectorResult(
                source="competitor",
                signal_type="keyword_based",
                score=random.randint(40, 60),
                keyword=brand_or_category,
                raw_content=f"MOCK: {competitor_name} pricing for {brand_or_category}.",
                signal_data={
                    "competitor": competitor_name,
                    "url": url,
                    "price": random.uniform(50.0, 500.0),
                    "in_stock": random.choice([True, True, False]), # Mostly in stock
                    "is_mock": True
                },
                geo="Ghana"
            )]

        try:
            html = self._fetch_html(url)
            if not html:
                return []

            price, in_stock = self._parse_html(html, competitor_name)
            
            # If we couldn't parse a price, it's a failed scrape
            if price is None:
                logger.warning("Could not parse price from %s at %s", competitor_name, url)
                return []

            # A lower price from a competitor is a strong signal (high score)
            # For MVP, we just assign a base score, but intelligence_tasks will
            # correlate this against our tenant's price.
            
            return [CollectorResult(
                source="competitor",
                signal_type="keyword_based",
                score=50, 
                keyword=brand_or_category,
                raw_content=None,
                signal_data={
                    "competitor": competitor_name,
                    "url": url,
                    "price": price,
                    "in_stock": in_stock,
                },
                geo="Ghana",
            )]

        except Exception as e:
            logger.error("Competitor collector failed for %s: %s", url, e)
            return []

    def _fetch_html(self, url: str) -> str | None:
        """Fetch HTML using ScraperAPI if available, else direct request."""
        try:
            if SCRAPERAPI_KEY:
                payload = {'api_key': SCRAPERAPI_KEY, 'url': url}
                resp = requests.get('http://api.scraperapi.com', params=payload, timeout=30)
            else:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                resp = requests.get(url, headers=headers, timeout=15)
            
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error("Failed to fetch HTML for %s: %s", url, e)
            return None

    def _parse_html(self, html: str, competitor_name: str) -> tuple[float | None, bool]:
        """
        Extensible parser for specific Ghanaian sites.
        Returns (price, in_stock).
        """
        soup = BeautifulSoup(html, "html.parser")
        name = competitor_name.lower()
        
        price = None
        in_stock = True

        if "jumia" in name:
            # Jumia price tag: <span dir="ltr" data-price="120.00">GH₵ 120.00</span>
            # Or <span class="-b -ltr -tal -fs24">GH₵ 120.00</span>
            price_tag = soup.find("span", {"dir": "ltr", "data-price": True})
            if price_tag:
                price = float(price_tag["data-price"])
            else:
                price_elem = soup.find("span", text=re.compile(r"GH₵"))
                if price_elem:
                    price = self._extract_price(price_elem.text)
                    
            out_of_stock = soup.find(text=re.compile(r"out of stock", re.IGNORECASE))
            if out_of_stock:
                in_stock = False

        elif "melcom" in name:
            # Melcom price usually has class "price"
            price_elem = soup.find(class_="price")
            if price_elem:
                price = self._extract_price(price_elem.text)

        else:
            # Generic fallback — look for GH₵, GHS, or ₵
            price_elem = soup.find(text=re.compile(r"(GH₵|GHS|₵)\s*\d+"))
            if price_elem:
                price = self._extract_price(price_elem)

        return price, in_stock

    def _extract_price(self, text: str) -> float | None:
        """Extract first numeric value from a string."""
        match = re.search(r"[\d,]+(\.\d+)?", text)
        if match:
            return float(match.group().replace(",", ""))
        return None
