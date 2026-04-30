"""
ingestion/erp_adapter.py

Abstract ERP adapter base class + GenericRestAdapter for configurable REST APIs.
All ERP-specific integrations (QuickBooks, SAP, NetSuite) extend ERPAdapter.
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30


class ERPAdapter(ABC):
    """
    Base class for all ERP integrations.
    Subclasses must implement fetch_catalogue, fetch_sales_history, fetch_stock_levels.
    """

    def __init__(self, config: dict, tenant_id: str):
        self.config = config
        self.tenant_id = tenant_id

    @abstractmethod
    def fetch_catalogue(self) -> list[dict]:
        """Return list of product/item records."""
        ...

    @abstractmethod
    def fetch_sales_history(self, since: datetime) -> list[dict]:
        """Return list of sales records since the given datetime."""
        ...

    @abstractmethod
    def fetch_stock_levels(self) -> list[dict]:
        """Return list of current stock level records."""
        ...

    def test_connection(self) -> bool:
        """Override to provide a lightweight connectivity check."""
        return True

    def _map_record(self, record: dict, field_map: dict) -> dict:
        """Apply a field mapping dict to a raw API record."""
        return {
            canonical: record.get(raw_key)
            for canonical, raw_key in field_map.items()
            if raw_key in record
        }


class GenericRestAdapter(ERPAdapter):
    """
    Configurable REST adapter for any JSON API.
    Configuration is stored in integrations.meta and follows this shape:

    {
      "base_url": "https://api.customer-erp.com/v2",
      "auth": {
        "type": "api_key",      # or "bearer" | "basic"
        "header": "X-API-Key",
        "value": "sk-..."       # stored encrypted, decrypted before use
      },
      "endpoints": {
        "catalogue": "/products",
        "sales": "/sales-orders",
        "stock": "/inventory"
      },
      "field_map": {
        "sku_id":     "productCode",
        "sku_name":   "productDescription",
        "units_sold": "quantityOrdered",
        "revenue":    "lineTotal",
        "sale_date":  "orderDate",
        "city":       "deliveryCity"
      }
    }
    """

    def __init__(self, config: dict, tenant_id: str):
        super().__init__(config, tenant_id)
        self.base_url = config["base_url"].rstrip("/")
        self.field_map = config.get("field_map", {})
        self._session = self._build_session(config.get("auth", {}))

    def _build_session(self, auth_config: dict) -> requests.Session:
        session = requests.Session()
        auth_type = auth_config.get("type", "none")

        if auth_type == "api_key":
            session.headers[auth_config["header"]] = auth_config["value"]
        elif auth_type == "bearer":
            session.headers["Authorization"] = f"Bearer {auth_config['value']}"
        elif auth_type == "basic":
            session.auth = (auth_config["username"], auth_config["password"])

        return session

    def _get(self, endpoint: str, params: dict | None = None) -> list[dict]:
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self._session.get(
                url, params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
            )
            resp.raise_for_status()
            data = resp.json()
            # Handle both list and {"items": [...]} shapes
            return data if isinstance(data, list) else data.get("items", data.get("data", []))
        except requests.RequestException as e:
            logger.error("GenericRestAdapter GET %s failed: %s", url, e)
            raise

    def fetch_catalogue(self) -> list[dict]:
        endpoint = self.config.get("endpoints", {}).get("catalogue", "/products")
        records = self._get(endpoint)
        return [self._map_record(r, self.field_map) for r in records]

    def fetch_sales_history(self, since: datetime) -> list[dict]:
        endpoint = self.config.get("endpoints", {}).get("sales", "/sales")
        params = {"since": since.isoformat()} if since else {}
        records = self._get(endpoint, params=params)
        return [self._map_record(r, self.field_map) for r in records]

    def fetch_stock_levels(self) -> list[dict]:
        endpoint = self.config.get("endpoints", {}).get("stock", "/inventory")
        records = self._get(endpoint)
        return [self._map_record(r, self.field_map) for r in records]

    def test_connection(self) -> bool:
        try:
            endpoint = next(iter(self.config.get("endpoints", {}).values()), "/")
            self._get(endpoint)
            return True
        except Exception:
            return False


def get_adapter(integration_record: dict, tenant_id: str) -> ERPAdapter:
    """
    Factory. Returns the correct adapter based on the integration provider.
    """
    provider = integration_record["provider"]
    config = integration_record.get("meta") or {}

    if provider == "generic_rest":
        return GenericRestAdapter(config, tenant_id)
    elif provider == "quickbooks":
        from ingestion.quickbooks import QuickBooksAdapter
        return QuickBooksAdapter(integration_record, tenant_id)
    elif provider == "lightspeed":
        from ingestion.lightspeed import LightspeedAdapter
        return LightspeedAdapter(integration_record, tenant_id)
    else:
        raise NotImplementedError(f"ERP adapter not yet implemented for provider: {provider}")
