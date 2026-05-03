import logging
import json
import random
from app.db import supabase
from openai import OpenAI
import os

logger = logging.getLogger(__name__)

class MockAIGenerator:
    """
    Uses GPT-4o to generate high-fidelity mock signals for testing the intelligence layer.
    """
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate_signals(self, keyword: str, source: str, count: int = 3) -> list[str]:
        """
        Generates realistic content for a specific source and keyword.
        """
        source_context = {
            "reddit": "detailed Reddit posts or comments from r/ghana discussing product prices, quality, or retail experiences.",
            "x": "short, punchy tweets (X posts) about brand trends or shopping in Ghana. Include hashtags and local slang.",
            "tiktok": "TikTok video captions or comment transcripts about product reviews, unboxing, or shopping hauls in Accra.",
            "newsapi": "formal news headlines and lead paragraphs about business, retail, or the economy in Ghana.",
            "rss_news": "local Ghanaian news article snippets from JoyOnline or Graphic about trade and market conditions.",
            "google_trends": "explanations of why this brand/keyword is trending in Ghana right now (e.g., a specific promotion or shortage)."
        }

        context = source_context.get(source, "general market signals from Ghana.")
        
        prompt = f"""
        Generate exactly {count} unique, highly realistic {context}
        The keyword to focus on is: '{keyword}'.
        
        CRITICAL REQUIREMENTS:
        1. Mention specific Ghanaian locations (Accra Mall, Kumasi Kejetia, Takoradi).
        2. Mention specific retailers (Melcom, Shoprite, Jumia Ghana, Kikuu, Palace).
        3. Include realistic consumer sentiment (frustration with prices, excitement about deals, etc.).
        4. RETURN ONLY A JSON OBJECT with a "signals" key containing an array of strings.
        
        Example: {{"signals": ["First signal content...", "Second signal content..."]}}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a data generator for a retail intelligence platform in Ghana. Output MUST be valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            res_content = response.choices[0].message.content
            data = json.loads(res_content)
            
            if "signals" in data and isinstance(data["signals"], list):
                return [str(s) for s in data["signals"]]
            
            return []
        except Exception as e:
            logger.error(f"Failed to generate AI mock content for {keyword} ({source}): {e}")
            return []

# Singleton instance
mock_ai = MockAIGenerator()
