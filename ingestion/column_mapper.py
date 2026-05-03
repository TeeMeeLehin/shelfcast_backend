"""
ingestion/column_mapper.py

Fuzzy header detection for CSV files.
Maps real-world, messy column headers to ShelfCast's unified field names.
"""
from difflib import SequenceMatcher

# Canonical field name → list of known aliases (lowercase, stripped)
COLUMN_ALIASES: dict[str, list[str]] = {
    "sku_id":       ["sku", "sku id", "sku_id", "product code", "item code", "barcode",
                     "product id", "item id", "code", "ref", "reference"],
    "sku_name":     ["product name", "item name", "description", "product description",
                     "name", "product", "item", "article name", "article"],
    "units_sold":   ["total sold", "qty sold", "units sold", "quantity sold", "sales qty",
                     "sold qty", "quantity", "qty", "units", "sales units", "volume"],
    "stock_level":  ["left over", "current stock", "stock on hand", "closing stock",
                     "inventory", "stock level", "balance", "remaining", "available qty",
                     "on hand", "stock"],
    "revenue":      ["revenue", "total revenue", "sales value", "amount", "total amount",
                     "value", "turnover", "net sales", "gross sales", "total sales"],
    "sale_date":    ["date", "sale date", "transaction date", "period", "order date",
                     "sales date", "invoice date", "tx date", "timestamp"],
    "city":         ["city", "branch", "location", "store", "region", "area",
                     "branch name", "outlet", "shop", "warehouse"],
    "price":        ["price", "unit price", "selling price", "retail price",
                     "unit cost", "cost price"],
    "total_inputted": ["total inputted", "total received", "total in", "received qty",
                       "intake", "total purchased"],
}

REQUIRED_FIELDS = {"sku_id"}
FUZZY_THRESHOLD = 0.75  # Minimum similarity ratio to accept a fuzzy match


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def map_columns(raw_headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """
    Map raw CSV headers to canonical field names.

    Returns:
        mapping: {canonical_field: raw_header} for all matched fields
        unmatched: list of required fields that could not be matched
    """
    normalised = [h.lower().strip().replace("_", " ") for h in raw_headers]
    mapping: dict[str, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        best_match = None
        best_score = 0.0

        for raw, norm in zip(raw_headers, normalised):
            # Exact match first
            if norm in aliases:
                best_match = raw
                best_score = 1.0
                break

            # Fuzzy fallback
            for alias in aliases:
                score = _similarity(norm, alias)
                if score > best_score:
                    best_score = score
                    best_match = raw

        if best_match and best_score >= FUZZY_THRESHOLD:
            mapping[canonical] = best_match

    unmatched = [f for f in REQUIRED_FIELDS if f not in mapping]
    return mapping, unmatched
