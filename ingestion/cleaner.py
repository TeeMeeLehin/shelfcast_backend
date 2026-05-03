"""
ingestion/cleaner.py

Two-pass data cleaning pipeline.
Pass 1: Structural validation — hard rules, row is valid or quarantined.
Pass 2: Semantic cleaning — soft rules, normalisation, deduplication.
"""
import re
import hashlib
from datetime import datetime, date


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

TEST_RECORD_PATTERNS = [
    re.compile(r"^product\s+[0-9.]+$", re.IGNORECASE),
    re.compile(r"^test", re.IGNORECASE),
    re.compile(r"^sample", re.IGNORECASE),
    re.compile(r"^testing\s+", re.IGNORECASE),
    re.compile(r"^dummy", re.IGNORECASE),
    re.compile(r"^placeholder", re.IGNORECASE),
]

INVALID_SKU_PATTERNS = [
    re.compile(r"^-\d+$"),             # Negative numbers e.g. "-1"
    re.compile(r"^\.\d+$"),            # Leading decimal e.g. ".02634"
    re.compile(r"^0+$"),               # All zeros
]

KNOWN_GHANAIAN_CITIES = {
    "accra", "kumasi", "tamale", "takoradi", "cape coast", "sunyani",
    "koforidua", "wa", "bolgatanga", "ho", "tema", "sekondi"
}

SIZE_SUFFIX_PATTERN = re.compile(
    r"\s+[-–]?\s*("
    r"\d+(\.\d+)?\s*(ml|l|g|kg|oz|gm|pcs|pcs|pc|cm|mm|\"|\')?"
    r"|[xX][sSmMlLxX]+"          # Clothing sizes
    r"|-\s*\w+\s*-\s*\w+"        # Colour-size combos like "-Blue-L"
    r")$",
    re.IGNORECASE
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_test_record(name: str) -> bool:
    return any(p.match(name.strip()) for p in TEST_RECORD_PATTERNS)


def _is_invalid_sku(sku: str) -> bool:
    s = str(sku).strip()
    return any(p.match(s) for p in INVALID_SKU_PATTERNS)


def _normalise_name(name: str) -> str:
    """Title-case, strip whitespace, collapse multiple spaces."""
    return re.sub(r"\s+", " ", name.strip()).title()


def _strip_variant_suffix(name: str) -> str:
    """Return the base product name without size/colour/variant suffixes."""
    return SIZE_SUFFIX_PATTERN.sub("", name).strip()


def _row_hash(tenant_id: str, row: dict, name_normalised: str) -> str:
    """Hash the entire row to detect strict exact duplicates, allowing multiple sales transactions for the same SKU."""
    raw = (
        f"{tenant_id}:{row.get('sku_id', '')}:{name_normalised.lower()}:"
        f"{row.get('sale_date', '')}:{row.get('city', '')}:"
        f"{row.get('units_sold', 0)}:{row.get('revenue', 0)}"
    )
    return hashlib.md5(raw.encode()).hexdigest()


def _coerce_numeric(value, field_name: str) -> tuple[float | None, str | None]:
    """Returns (coerced_value, error_reason)."""
    if value is None or str(value).strip() in ("", "nan", "NaN", "None", "null"):
        return 0.0, None
    try:
        return float(str(value).replace(",", "").strip()), None
    except (ValueError, TypeError):
        return None, f"non_numeric_{field_name}"


def _coerce_date(value) -> tuple[date | None, str | None]:
    if value is None or str(value).strip() in ("", "nan"):
        return None, "invalid_date"
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value, None
    # Clean the string: take only the first part if it has a space (e.g. "2026-02-20 02:51:42" -> "2026-02-20")
    s = str(value).strip()
    if " " in s:
        s = s.split(" ")[0]

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date(), None
        except ValueError:
            continue
    return None, "invalid_date"


def _normalise_city(city: str | None) -> str | None:
    if not city or str(city).strip().lower() in ("", "nan", "none"):
        return None
    c = str(city).strip().lower()
    # Fuzzy match known cities
    for known in KNOWN_GHANAIAN_CITIES:
        if known in c:
            return known.title()
    return str(city).strip().title()


# ─────────────────────────────────────────────────────────────────────────────
# Pass 1 — Structural Validation
# ─────────────────────────────────────────────────────────────────────────────

def pass1_structural(row: dict, column_map: dict) -> tuple[dict | None, str | None]:
    """
    Validates that a row has a usable structure.
    Returns (clean_row, None) on success or (None, rejection_reason) on failure.
    """
    get = lambda field: row.get(column_map.get(field))

    sku_raw = get("sku_id")
    name_raw = get("sku_name")

    # 1. Missing SKU
    if sku_raw is None or str(sku_raw).strip().lower() in ("nan", "", "none"):
        return None, "missing_sku"

    sku = str(sku_raw).strip()

    # 2. Invalid SKU format
    if _is_invalid_sku(sku):
        return None, "invalid_sku_format"

    # 3. Handle product name (optional if SKU is present for sales history matching)
    name = str(name_raw).strip() if name_raw is not None and str(name_raw).strip().lower() not in ("nan", "", "none") else "(Unknown Product)"

    # 4. Coerce numeric fields
    units_raw = get("units_sold")
    stock_raw = get("stock_level")
    revenue_raw = get("revenue")

    units, err = _coerce_numeric(units_raw, "units_sold")
    if err:
        return None, err
    stock, err = _coerce_numeric(stock_raw, "stock_level")
    if err:
        return None, err
    revenue, err = _coerce_numeric(revenue_raw, "revenue")
    if err:
        return None, err

    # 5. Date validation (optional field — only reject if present and unparseable)
    date_raw = get("sale_date")
    sale_date = None
    if date_raw and str(date_raw).strip().lower() not in ("nan", "", "none"):
        sale_date, err = _coerce_date(date_raw)
        if err:
            return None, err

    return {
        "sku_id":       sku,
        "sku_name":     name,
        "units_sold":   units or 0.0,
        "stock_level":  stock or 0.0,
        "revenue":      revenue or 0.0,
        "sale_date":    sale_date,
        "city":         get("city"),
        "price":        _coerce_numeric(get("price"), "price")[0],
    }, None


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — Semantic Cleaning
# ─────────────────────────────────────────────────────────────────────────────

def pass2_semantic(row: dict, seen_hashes: set, tenant_id: str) -> tuple[dict | None, str | None]:
    """
    Enriches and normalises a structurally valid row.
    Returns (enriched_row, None) on success or (None, rejection_reason) if row
    is a test record or exact duplicate.
    """
    name_raw = row["sku_name"]
    name_normalised = _normalise_name(name_raw)

    # 1. Test/phantom record detection
    if _is_test_record(name_normalised):
        return None, "test_record"

    # 2. Exact duplicate detection within this import batch
    row_hash = _row_hash(tenant_id, row, name_normalised)
    if row_hash in seen_hashes:
        return None, "duplicate_row"
    seen_hashes.add(row_hash)

    # 3. Zero-activity flag
    is_active = not (
        row["units_sold"] == 0.0
        and row["stock_level"] == 0.0
        and row["revenue"] == 0.0
    )

    # 4. Variant detection — strip size/colour suffixes to find base name
    base_name = _strip_variant_suffix(name_normalised)
    is_variant = base_name.lower() != name_normalised.lower()

    # 5. City normalisation
    city_normalised = _normalise_city(row.get("city"))

    # 6. Revenue inference from price × units if revenue is missing
    revenue = row["revenue"]
    if revenue == 0.0 and row.get("price") and row["units_sold"] > 0:
        revenue = round(row["price"] * row["units_sold"], 2)

    return {
        **row,
        "sku_name":           name_normalised,
        "base_name":          base_name,
        "is_variant":         is_variant,
        "is_active":          is_active,
        "city":               city_normalised,
        "revenue":            revenue,
        "_row_hash":          row_hash,
    }, None


# ─────────────────────────────────────────────────────────────────────────────
# Public interface
# ─────────────────────────────────────────────────────────────────────────────

import math as _math

def _sanitize_raw(row: dict) -> dict:
    """
    Replace any float NaN / Inf values in a raw CSV row with None so the dict
    can be safely serialised to JSON (JSONB). Pandas leaves NaN in cells that
    were empty in the CSV file.
    """
    out = {}
    for k, v in row.items():
        if isinstance(v, float) and (_math.isnan(v) or _math.isinf(v)):
            out[k] = None
        else:
            out[k] = v
    return out


def clean_rows(
    raw_rows: list[dict],
    column_map: dict,
    tenant_id: str,
) -> tuple[list[dict], list[dict]]:
    """
    Run both cleaning passes over a list of raw rows.

    Returns:
        clean: list of fully cleaned, normalised row dicts
        quarantine: list of {raw_data, rejection_reason} dicts
    """
    clean = []
    quarantine = []
    seen_hashes: set = set()

    for raw in raw_rows:
        # Sanitize before any use — removes Pandas NaN from empty CSV cells
        safe_raw = _sanitize_raw(raw)

        # Pass 1
        validated, reason = pass1_structural(safe_raw, column_map)
        if validated is None:
            quarantine.append({"raw_data": safe_raw, "rejection_reason": reason})
            continue

        # Pass 2
        enriched, reason = pass2_semantic(validated, seen_hashes, tenant_id)
        if enriched is None:
            quarantine.append({"raw_data": safe_raw, "rejection_reason": reason})
            continue

        clean.append(enriched)

    return clean, quarantine
