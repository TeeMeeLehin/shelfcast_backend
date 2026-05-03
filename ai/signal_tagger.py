"""
ai/signal_tagger.py

AI Pipeline for tagging keyword-less (general_pulse) signals.
Uses GPT-4o to extract referenced brands, categories, and macro-economic events,
assigning sentiment and impact scores.
"""
import json
import logging
import os
from datetime import datetime, timezone

from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Strict JSON schema for guaranteed parser safety
TAGGING_SCHEMA = {
    "name": "tag_signal_entities",
    "description": "Extract relevant market entities and score sentiment/impact.",
    "parameters": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "description": "List of discovered entities.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["brand", "category", "macro"],
                            "description": "brand (e.g. Nestle), category (e.g. Beverages), or macro (e.g. Inflation)",
                        },
                        "value": {
                            "type": "string",
                            "description": "The specific name of the entity.",
                        }
                    },
                    "required": ["type", "value"]
                }
            },
            "sentiment_score": {
                "type": "integer",
                "description": "Score from -100 (very negative) to 100 (very positive).",
            },
            "impact_score": {
                "type": "integer",
                "description": "Score from 0 (irrelevant) to 100 (high market impact).",
            }
        },
        "required": ["entities", "sentiment_score", "impact_score"]
    }
}


def process_unprocessed_signals() -> int:
    """
    Fetch all unprocessed 'general_pulse' signals from raw_signals,
    run them through GPT-4o, and update the DB.
    Returns the number of signals processed.
    """
    from app.db import supabase

    try:
        res = supabase.table("raw_signals").select("id, raw_content, source").eq(
            "signal_type", "general_pulse"
        ).eq("is_processed", False).limit(50).execute()
        
        signals = res.data
        if not signals:
            return 0
            
        processed_count = 0
        for sig in signals:
            try:
                tagged_data = _tag_content(sig["raw_content"], sig["source"])
                
                # Update the row
                supabase.table("raw_signals").update({
                    "entities": tagged_data["entities"],
                    "sentiment_score": tagged_data["sentiment_score"],
                    "impact_score": tagged_data["impact_score"],
                    "is_processed": True,
                }).eq("id", sig["id"]).execute()
                
                processed_count += 1
            except Exception as inner_e:
                logger.error("Failed to tag signal %s: %s", sig["id"], inner_e)
                # Mark processed anyway to prevent infinite loops on bad data
                supabase.table("raw_signals").update({"is_processed": True}).eq("id", sig["id"]).execute()

        return processed_count

    except Exception as e:
        logger.error("Error in process_unprocessed_signals: %s", e)
        return 0


def _tag_content(content: str, source: str) -> dict:
    if not content or len(content.strip()) < 20:
        return {"entities": [], "sentiment_score": 0, "impact_score": 0}
        
    prompt = f"""
    You are an expert market analyst for the Ghanaian retail sector.
    Analyze the following content from {source}.
    Identify any brands, product categories, or macro-economic events that would affect retail sales.
    
    Content:
    {content[:3000]}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        functions=[TAGGING_SCHEMA],
        function_call={"name": "tag_signal_entities"},
        temperature=0.1,
    )
    
    try:
        raw_args = response.choices[0].message.function_call.arguments
        return json.loads(raw_args)
    except Exception:
        return {"entities": [], "sentiment_score": 0, "impact_score": 0}
