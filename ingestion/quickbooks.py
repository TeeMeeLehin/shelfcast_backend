"""
ingestion/quickbooks.py

QuickBooks Online integration:
  - OAuth 2.0 backend flow (no frontend token handling)
  - Token storage (encrypted) in integrations table
  - Data sync: Items → catalogue, Sales → sales_history
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet

from app.db import supabase
from ingestion.erp_adapter import ERPAdapter

logger = logging.getLogger(__name__)

QB_BASE_URL = "https://quickbooks.api.intuit.com/v3/company"
QB_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QB_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

QB_CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID", "")
QB_CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
QB_REDIRECT_URI = os.getenv("QUICKBOOKS_REDIRECT_URI", "http://localhost:8000/integrations/quickbooks/callback")
QB_SCOPES = "com.intuit.quickbooks.accounting"

# Encryption key for token storage.
# Must be a Fernet key: run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
# and set TOKEN_ENCRYPTION_KEY in your .env
_FERNET_KEY_STR = os.getenv("TOKEN_ENCRYPTION_KEY", "")
_IS_DEV = os.getenv("APP_ENV", "production").lower() == "development"

if not _FERNET_KEY_STR:
    if _IS_DEV:
        import warnings
        warnings.warn(
            "TOKEN_ENCRYPTION_KEY is not set. OAuth tokens will be stored in PLAINTEXT. "
            "This is acceptable only in development.",
            stacklevel=1,
        )
        _fernet = None
    else:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY environment variable is required in production. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
else:
    _fernet = Fernet(_FERNET_KEY_STR.encode())


def _encrypt(value: str) -> str:
    if not _fernet:
        return value  # Dev-only plaintext fallback
    return _fernet.encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    if not _fernet:
        return value  # Dev-only plaintext fallback
    try:
        return _fernet.decrypt(value.encode()).decode()
    except Exception as e:
        raise ValueError(f"Failed to decrypt token — key mismatch or corrupt data: {e}") from e


# ─────────────────────────────────────────────────────────────────────────────
# OAuth 2.0 Helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_authorization_url(state_token: str) -> str:
    """Generate the QB authorization URL to redirect the user to."""
    params = {
        "client_id":     QB_CLIENT_ID,
        "scope":         QB_SCOPES,
        "redirect_uri":  QB_REDIRECT_URI,
        "response_type": "code",
        "state":         state_token,
    }
    return f"{QB_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str, realm_id: str) -> dict:
    """Exchange the authorization code for access + refresh tokens."""
    resp = requests.post(
        QB_TOKEN_URL,
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": QB_REDIRECT_URI,
        },
        auth=(QB_CLIENT_ID, QB_CLIENT_SECRET),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token":    _encrypt(data["access_token"]),
        "refresh_token":   _encrypt(data["refresh_token"]),
        "expires_in":      data.get("expires_in", 3600),
        "realm_id":        realm_id,
    }


def refresh_access_token(integration: dict) -> dict:
    """Use the stored refresh token to obtain a new access token."""
    refresh_token = _decrypt(integration["refresh_token"])
    resp = requests.post(
        QB_TOKEN_URL,
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        },
        auth=(QB_CLIENT_ID, QB_CLIENT_SECRET),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token":    _encrypt(data["access_token"]),
        "refresh_token":   _encrypt(data.get("refresh_token", refresh_token)),
        "token_expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
        ).isoformat(),
    }


def ensure_fresh_token(integration: dict) -> str:
    """Return a valid decrypted access token, refreshing if needed."""
    expires_at = integration.get("token_expires_at")
    needs_refresh = True
    if expires_at:
        exp = datetime.fromisoformat(str(expires_at))
        needs_refresh = exp < datetime.now(timezone.utc) + timedelta(minutes=5)

    if needs_refresh:
        updated = refresh_access_token(integration)
        supabase.table("integrations").update(updated).eq("id", integration["id"]).execute()
        return _decrypt(updated["access_token"])

    return _decrypt(integration["access_token"])


# ─────────────────────────────────────────────────────────────────────────────
# Data Sync
# ─────────────────────────────────────────────────────────────────────────────

class QuickBooksAdapter(ERPAdapter):
    """QuickBooks-specific ERP adapter."""

    def __init__(self, integration_record: dict, tenant_id: str):
        super().__init__(integration_record, tenant_id)
        self.realm_id = integration_record["realm_id"]
        self._integration = integration_record
        self._access_token: str | None = None

    def _get_token(self) -> str:
        if not self._access_token:
            self._access_token = ensure_fresh_token(self._integration)
        return self._access_token

    def _query(self, sql: str) -> list[dict]:
        url = f"{QB_BASE_URL}/{self.realm_id}/query"
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
        }
        resp = requests.get(url, params={"query": sql}, headers=headers, timeout=30)
        resp.raise_for_status()
        body = resp.json().get("QueryResponse", {})
        # QB returns different top-level keys depending on entity type
        for key in body:
            if isinstance(body[key], list):
                return body[key]
        return []

    def fetch_catalogue(self) -> list[dict]:
        """Fetch all Inventory items from QuickBooks."""
        items = self._query("SELECT * FROM Item WHERE Type='Inventory' MAXRESULTS 1000")
        return [
            {
                "sku_id":    item.get("Sku") or item.get("Id"),
                "sku_name":  item.get("Name", ""),
                "price":     item.get("UnitPrice"),
                "stock_level": item.get("QtyOnHand", 0),
            }
            for item in items
        ]

    def fetch_sales_history(self, since: datetime | None = None) -> list[dict]:
        """Fetch SalesReceipts and Invoices since the given datetime."""
        records = []
        date_filter = ""
        if since:
            date_str = since.strftime("%Y-%m-%d")
            date_filter = f" WHERE MetaData.LastUpdatedTime >= '{date_str}'"

        for entity in ("SalesReceipt", "Invoice"):
            docs = self._query(f"SELECT * FROM {entity}{date_filter} MAXRESULTS 1000")
            for doc in docs:
                sale_date = (doc.get("TxnDate") or "")[:10]
                city = doc.get("BillAddr", {}).get("City")
                for line in doc.get("Line", []):
                    detail = line.get("SalesItemLineDetail", {})
                    if not detail:
                        continue
                    records.append({
                        "sku_id":     detail.get("ItemRef", {}).get("value"),
                        "sku_name":   detail.get("ItemRef", {}).get("name", ""),
                        "units_sold": detail.get("Qty", 0),
                        "revenue":    line.get("Amount", 0),
                        "sale_date":  sale_date,
                        "city":       city,
                    })
        return records

    def fetch_stock_levels(self) -> list[dict]:
        items = self._query("SELECT Id, Sku, Name, QtyOnHand FROM Item WHERE Type='Inventory' MAXRESULTS 1000")
        return [
            {"sku_id": i.get("Sku") or i.get("Id"), "stock_level": i.get("QtyOnHand", 0)}
            for i in items
        ]

    def test_connection(self) -> bool:
        try:
            self._query("SELECT COUNT(*) FROM Item")
            return True
        except Exception:
            return False
