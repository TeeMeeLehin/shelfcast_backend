"""
ingestion/normaliser.py

Maps cleaned rows to ShelfCast's unified database schema.
Detects whether data is an inventory snapshot or transactional sales history.
"""
from datetime import date, datetime


# ─────────────────────────────────────────────────────────────────────────────
# Format Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_format(clean_rows: list[dict]) -> str:
    """
    Detect whether the data represents:
      - 'inventory_snapshot': stock levels with no per-row dates
      - 'sales_transactions': time-series rows each with a sale_date
      - 'combined': has both
    """
    has_dates = sum(1 for r in clean_rows if r.get("sale_date") is not None)
    has_stock = sum(1 for r in clean_rows if r.get("stock_level", 0) > 0)

    if has_dates > 0 and has_stock > 0:
        return "combined"
    elif has_dates > 0:
        return "sales_transactions"
    else:
        return "inventory_snapshot"


# ─────────────────────────────────────────────────────────────────────────────
# Normalisers
# ─────────────────────────────────────────────────────────────────────────────

def to_catalogue_rows(
    clean_rows: list[dict],
    tenant_id: str,
    job_id: str,
    source: str = "csv",
) -> list[dict]:
    """Build catalogue upsert rows from clean data."""
    seen_skus: set = set()
    rows = []

    for r in clean_rows:
        sku_id = r["sku_id"]
        if sku_id in seen_skus:
            continue
        seen_skus.add(sku_id)

        rows.append({
            "tenant_id":             tenant_id,
            "sku_id":                sku_id,
            "sku_name":              r["sku_name"],
            "brand":                 None,    # Filled by classifier
            "category":              None,    # Filled by classifier
            "match_terms":           [],      # Filled by classifier
            "classification_status": "pending",
            "is_active":             r.get("is_active", True),
            "variant_of":            None,    # TODO: variant grouping post-classification
            "source":                source,
            "ingestion_job_id":      job_id,
        })

    return rows


def to_sales_history_rows(
    clean_rows: list[dict],
    tenant_id: str,
    job_id: str,
    default_date: date | None = None,
    default_city: str | None = None,
) -> list[dict]:
    """
    Build sales_history insert rows.
    For inventory snapshots with no date, default_date is used (upload date).
    For rows with no city, default_city (the uploading user's registered city) is used.
    """
    today = default_date or date.today()
    aggregated = {}

    import math

    # DB schema: units_sold INT, stock_level INT, revenue FLOAT
    # Safely coerce — raw data may arrive as strings, floats, or None/NaN
    def _int(val, default=0) -> int:
        if val is None:
            return default
        try:
            fval = float(val)
            return default if math.isnan(fval) else int(fval)
        except (ValueError, TypeError):
            return default

    def _float(val, default=0.0) -> float:
        if val is None:
            return default
        try:
            fval = float(val)
            return default if math.isnan(fval) else fval
        except (ValueError, TypeError):
            return default

    for r in clean_rows:
        sale_date = str(r.get("sale_date") or today)
        city = r.get("city") or default_city
        sku_id = r["sku_id"]
        
        key = (sku_id, city, sale_date)
        u_sold = _int(r.get("units_sold"))
        rev = _float(r.get("revenue"))
        
        if key not in aggregated:
            aggregated[key] = {
                "tenant_id":   tenant_id,
                "sku_id":      sku_id,
                "sku_name":    r.get("sku_name"),
                "units_sold":  u_sold,
                "revenue":     rev,
                "city":        city,
                "sale_date":   sale_date,
            }
        else:
            aggregated[key]["units_sold"] += u_sold
            aggregated[key]["revenue"] += rev

    return list(aggregated.values())


def normalise(
    clean_rows: list[dict],
    tenant_id: str,
    job_id: str,
    source: str = "csv",
    default_city: str | None = None,
) -> dict:
    """
    Entry point. Returns all rows needed for DB writes.
    """
    fmt = detect_format(clean_rows)

    catalogue_rows = to_catalogue_rows(clean_rows, tenant_id, job_id, source)

    # For inventory snapshots, use stock_level as the units_sold for the
    # sales_history row so the data is queryable as a time-series snapshot.
    if fmt in ("inventory_snapshot", "combined"):
        import math
        def _safe_float(v):
            if v is None: return 0.0
            try:
                f = float(v)
                return 0.0 if math.isnan(f) else f
            except (ValueError, TypeError):
                return 0.0

        stock_map = {r["sku_id"]: _safe_float(r.get("stock_level")) for r in clean_rows}
        # Inject stock_level into each clean_row for to_sales_history_rows
        for r in clean_rows:
            if r.get("units_sold") is None:
                r["units_sold"] = stock_map.get(r["sku_id"], 0.0)
        # Also stamp it on catalogue rows for the stock_level column
        for cat_row in catalogue_rows:
            cat_row["stock_level"] = stock_map.get(cat_row["sku_id"], 0.0)

    sales_rows = to_sales_history_rows(
        clean_rows,
        tenant_id,
        job_id,
        default_date=date.today() if fmt == "inventory_snapshot" else None,
        default_city=default_city,
    )

    return {
        "format":          fmt,
        "catalogue_rows":  catalogue_rows,
        "sales_rows":      sales_rows,
    }

