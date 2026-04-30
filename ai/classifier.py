"""
ai/classifier.py

GPT-4o SKU classifier with Ghanaian market localisation.
Runs on unclassified SKUs after ingestion.
"""
import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BATCH_SIZE = 20

# ─────────────────────────────────────────────────────────────────────────────
# Local Context — Ghana-specific product knowledge
# ─────────────────────────────────────────────────────────────────────────────

GHANAIAN_MARKET_CONTEXT = """
You are classifying products sold in Ghanaian retail stores.

Key Ghanaian market context to guide your classification:
- "Indomie" is the generic consumer term for ALL instant noodles (not just the brand).
- "Omo" is used as a generic term for laundry detergent powder.
- "Milo" refers to the Nestlé chocolate malt drink.
- "Frytol" is a leading Ghanaian vegetable/sunflower oil brand.
- "Kasapreko" is a Ghanaian spirits/bitters brand.
- "Shito" is a Ghanaian pepper sauce.
- "Blessed Child" is a Ghanaian food brand (cereals, sugar, shito).
- "Maggi" / "Tasty Tom" / "Gino" are common tomato paste/seasoning brands.
- "Peak" / "Cowbell" / "Nido" are common powdered milk brands.
- Product names frequently embed size variants (e.g. "1l", "400g", "5kg", "2pcs").
- Category labels should reflect what a Ghanaian retailer would use:
  e.g. "Beverages", "Cooking Oil", "Cereals & Baby Food", "Personal Care",
  "Household Cleaning", "Electronics", "Furniture", "Mobile Phones".

Always prefer specific categories over vague ones (e.g. "Instant Noodles" > "Food").
"""

CLASSIFICATION_SCHEMA = """
Return a JSON array where each element has:
{
  "sku_id": "...",
  "brand": "Brand name or null if generic/unknown",
  "category": "Product category (specific)",
  "match_terms": ["keyword1", "keyword2", ...],
  "confidence": "high" | "medium" | "low"
}

match_terms should include:
- English product name keywords
- Local/generic names used in Ghana
- Relevant Twi/local language equivalents if known (e.g. "aduane" for food)
- Minimum 3 terms, maximum 8 terms

Respond with ONLY the JSON array — no prose, no markdown.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_batch(skus: list[dict]) -> list[dict]:
    """
    Classify a batch of SKUs using GPT-4o.

    Args:
        skus: list of {"sku_id": ..., "sku_name": ...}

    Returns:
        list of classification results
    """
    sku_list = "\n".join(
        f'{i+1}. [SKU: {s["sku_id"]}] {s["sku_name"]}'
        for i, s in enumerate(skus)
    )

    prompt = (
        f"Classify the following {len(skus)} products:\n\n"
        f"{sku_list}\n\n"
        f"{CLASSIFICATION_SCHEMA}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": GHANAIAN_MARKET_CONTEXT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)

        # Handle both {"results": [...]} and direct array
        if isinstance(data, list):
            return data
        for key in data:
            if isinstance(data[key], list):
                return data[key]
        return []

    except Exception as e:
        logger.error("GPT-4o classification failed for batch: %s", e)
        return []


def _is_low_confidence(result: dict) -> bool:
    if result.get("confidence") == "low":
        return True
    if result.get("brand", "").lower() in ("unknown", ""):
        return True
    if result.get("category", "").lower() in ("unknown", "general", "other", ""):
        return True
    if len(result.get("match_terms", [])) < 3:
        return True
    return False


def classify_unclassified_skus(tenant_id: str) -> dict:
    """
    Fetch all pending-classification SKUs for a tenant and run GPT-4o on them.
    Updates the catalogue table with results.
    Returns a summary dict.
    """
    from app.db import supabase

    # Fetch unclassified SKUs
    res = supabase.table("catalogue").select("sku_id, sku_name").eq(
        "tenant_id", tenant_id
    ).eq(
        "classification_status", "pending"
    ).is_("brand", "null").execute()

    skus = res.data or []
    if not skus:
        logger.info("No unclassified SKUs for tenant %s.", tenant_id)
        return {"classified": 0, "needs_review": 0}

    classified = 0
    needs_review = 0

    # Process in batches
    for i in range(0, len(skus), BATCH_SIZE):
        batch = skus[i: i + BATCH_SIZE]
        results = classify_batch(batch)

        for result in results:
            sku_id = result.get("sku_id")
            if not sku_id:
                continue

            low_conf = _is_low_confidence(result)
            status = "needs_review" if low_conf else "classified"

            supabase.table("catalogue").update({
                "brand":                 result.get("brand"),
                "category":              result.get("category"),
                "match_terms":           result.get("match_terms", []),
                "classification_status": status,
            }).eq("tenant_id", tenant_id).eq("sku_id", sku_id).execute()

            if low_conf:
                needs_review += 1
            else:
                classified += 1

    logger.info(
        "Classification for tenant %s: %d classified, %d need review.",
        tenant_id, classified, needs_review,
    )
    return {"classified": classified, "needs_review": needs_review}
