"""
ingestion/lightspeed.py

Lightspeed Retail (X-Series / R-Series) ERP adapter.
Uses the Lightspeed REST API to fetch inventory and sales data.

Supports:
  - Lightspeed X-Series (cloud POS) — REST API v1
  - Lightspeed R-Series (legacy retail) — REST API v3 (different base URL)

OAuth 2.0 is handled by the same pattern as QuickBooks:
  backend-to-backend, tokens encrypted at rest in integrations table.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import requests

from ingestion.erp_adapter import ERPAdapter
from ingestion.quickbooks import _encrypt, _decrypt  # Reuse same Fernet helpers

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Lightspeed X-Series (cloud POS) constants
# ─────────────────────────────────────────────────────────────────────────────
LS_CLIENT_ID = os.getenv("LIGHTSPEED_CLIENT_ID", "")
LS_CLIENT_SECRET = os.getenv("LIGHTSPEED_CLIENT_SECRET", "")
LS_REDIRECT_URI = os.getenv("LIGHTSPEED_REDIRECT_URI", "http://localhost:8000/integrations/lightspeed/callback")
LS_AUTH_URL = "https://cloud.merchantos.com/oauth/authorize.php"
LS_TOKEN_URL = "https://cloud.merchantos.com/oauth/access_token.php"
LS_API_BASE = "https://api.lightspeedapp.com/API/V3/Account"

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30


def build_lightspeed_auth_url(state_token: str, account_id: str | None = None) -> str:
    params = {
        "response_type": "code",
        "client_id":     LS_CLIENT_ID,
        "redirect_uri":  LS_REDIRECT_URI,
        "scope":         "employee:all systemuseraccount:all",
        "state":         state_token,
    }
    return f"{LS_AUTH_URL}?{urlencode(params)}"


def exchange_lightspeed_code(code: str) -> dict:
    resp = requests.post(
        LS_TOKEN_URL,
        data={
            "grant_type":   "authorization_code",
            "client_id":    LS_CLIENT_ID,
            "client_secret": LS_CLIENT_SECRET,
            "code":         code,
            "redirect_uri": LS_REDIRECT_URI,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token":  _encrypt(data["access_token"]),
        "refresh_token": _encrypt(data.get("refresh_token", "")),
        "expires_in":    data.get("expires_in", 3600),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lightspeed Adapter
# ─────────────────────────────────────────────────────────────────────────────

class LightspeedAdapter(ERPAdapter):
    """
    Lightspeed R-Series (REST V3) adapter.
    Fetches Items → catalogue and Sales → sales_history.
    """

    def __init__(self, integration_record: dict, tenant_id: str):
        super().__init__(integration_record, tenant_id)
        self._integration = integration_record
        meta = integration_record.get("meta") or {}
        self.account_id = meta.get("account_id") or integration_record.get("realm_id")
        self._access_token: str | None = None

    def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._access_token:
            return self._access_token

        expires_at = self._integration.get("token_expires_at")
        needs_refresh = True
        if expires_at:
            exp = datetime.fromisoformat(str(expires_at))
            needs_refresh = exp < datetime.now(timezone.utc) + timedelta(minutes=5)

        if needs_refresh:
            from app.db import supabase
            refresh_token = _decrypt(self._integration["refresh_token"])
            resp = requests.post(
                LS_TOKEN_URL,
                data={
                    "grant_type":    "refresh_token",
                    "client_id":     LS_CLIENT_ID,
                    "client_secret": LS_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            updated = {
                "access_token":    _encrypt(data["access_token"]),
                "refresh_token":   _encrypt(data.get("refresh_token", refresh_token)),
                "token_expires_at": (
                    datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
                ).isoformat(),
            }
            supabase.table("integrations").update(updated).eq("id", self._integration["id"]).execute()
            self._access_token = data["access_token"]
        else:
            self._access_token = _decrypt(self._integration["access_token"])

        return self._access_token

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{LS_API_BASE}/{self.account_id}/{endpoint}"
        headers = {"Authorization": f"Bearer {self._ensure_token()}"}
        resp = requests.get(url, headers=headers, params=params or {},
                            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        resp.raise_for_status()
        return resp.json()

    def fetch_catalogue(self) -> list[dict]:
        """Fetch all active items from Lightspeed."""
        data = self._get("Item.json", params={"archived": "false", "limit": 100})
        items = data.get("Item", [])
        if isinstance(items, dict):
            items = [items]  # Single result is returned as dict, not list

        result = []
        for item in items:
            result.append({
                "sku_id":      item.get("customSku") or item.get("systemSku") or item.get("itemID"),
                "sku_name":    item.get("description", ""),
                "price":       float(item.get("Prices", {}).get("ItemPrice", [{}])[0].get("amount", 0) or 0),
                "stock_level": float(item.get("ItemShops", {}).get("ItemShop", [{}])[0].get("qoh", 0) or 0),
            })
        return result

    def fetch_sales_history(self, since: datetime | None = None) -> list[dict]:
        """Fetch completed sales from Lightspeed since a given date."""
        params = {
            "completed": "true",
            "limit":     100,
        }
        if since:
            params["timeStamp"] = f">,{since.strftime('%Y-%m-%dT%H:%M:%S+00:00')}"

        data = self._get("Sale.json", params=params)
        sales = data.get("Sale", [])
        if isinstance(sales, dict):
            sales = [sales]

        records = []
        for sale in sales:
            sale_date = (sale.get("timeStamp") or "")[:10]
            shop_name = sale.get("Shop", {}).get("name")
            for line in (sale.get("SaleLines", {}).get("SaleLine") or []):
                if isinstance(line, dict):
                    item_ref = line.get("Item", {})
                    records.append({
                        "sku_id":     line.get("itemID"),
                        "sku_name":   item_ref.get("description", ""),
                        "units_sold": float(line.get("unitQuantity", 0) or 0),
                        "revenue":    float(line.get("subtotal", 0) or 0),
                        "sale_date":  sale_date,
                        "city":       shop_name,
                    })
        return records

    def fetch_stock_levels(self) -> list[dict]:
        data = self._get("ItemShop.json", params={"limit": 100})
        items = data.get("ItemShop", [])
        if isinstance(items, dict):
            items = [items]
        return [
            {"sku_id": i.get("itemID"), "stock_level": float(i.get("qoh", 0) or 0)}
            for i in items
        ]

    def test_connection(self) -> bool:
        try:
            self._get("Account.json")
            return True
        except Exception:
            return False
