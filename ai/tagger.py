import logging
import json
import os
from openai import OpenAI
from app.db import supabase

logger = logging.getLogger(__name__)

class SignalTagger:
    """
    Enriches raw signals by extracting sentiment, impact score, and entities using GPT-4o.
    """
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def process_unprocessed_signals(self, batch_size: int = 50) -> int:
        """
        Fetches a batch of unprocessed raw signals and tags them.
        Returns the number of signals processed.
        """
        logger.info(f"Fetching up to {batch_size} unprocessed signals...")
        res = supabase.table("raw_signals").select("*").eq("is_processed", False).limit(batch_size).execute()
        signals = res.data or []
        
        if not signals:
            logger.info("No unprocessed signals found.")
            return 0
            
        processed_count = 0
        for signal in signals:
            try:
                tagged_data = self._tag_signal(signal)
                if tagged_data:
                    # Update the signal in the database
                    supabase.table("raw_signals").update({
                        "sentiment_score": tagged_data.get("sentiment_score", 50),
                        "impact_score": tagged_data.get("impact_score", 0),
                        "entities": tagged_data.get("entities", []),
                        "is_processed": True
                    }).eq("id", signal["id"]).execute()
                    processed_count += 1
            except Exception as e:
                logger.error(f"Error processing signal {signal.get('id')}: {e}")
                
        logger.info(f"Successfully processed {processed_count} signals.")
        return processed_count

    def _tag_signal(self, signal: dict) -> dict | None:
        """
        Calls GPT-4o to analyze a single signal.
        """
        content = signal.get("raw_content")
        # If no raw content, we can't do much NLP analysis. Just mark it processed.
        if not content:
            # Fallback to signal_data if it exists and is somewhat stringifiable
            sig_data = signal.get("signal_data", {})
            if isinstance(sig_data, dict) and "related_queries" in sig_data:
                content = "Related queries: " + ", ".join(sig_data["related_queries"])
            else:
                return {"sentiment_score": 50, "impact_score": 10, "entities": []}

        prompt = f"""
        Analyze the following market signal from Ghana.
        
        Content: "{content}"
        Source: {signal.get('source', 'unknown')}
        Associated Keyword: {signal.get('keyword', 'none')}
        
        Extract the following:
        1. 'sentiment_score': An integer from 0 (very negative) to 100 (very positive), where 50 is neutral.
        2. 'impact_score': An integer from 0 (no impact on retail demand/sales) to 100 (massive impact, e.g., huge price hike, viral trend, major stockout).
        3. 'entities': A list of specific brands, retailers, or product categories explicitly mentioned.
        
        Output as a valid JSON object. Example:
        {{"sentiment_score": 75, "impact_score": 60, "entities": ["Melcom", "Milo", "Beverage"]}}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert retail data analyst. Output MUST be valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            res_content = response.choices[0].message.content
            return json.loads(res_content)
        except Exception as e:
            logger.error(f"LLM tagging failed for signal: {e}")
            return None

# Singleton
signal_tagger = SignalTagger()
