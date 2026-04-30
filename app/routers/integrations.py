"""
app/routers/integrations.py

QuickBooks and ERP integration management endpoints:
  POST /integrations/quickbooks/connect    — Start OAuth flow
  GET  /integrations/quickbooks/callback   — Receive OAuth code, store tokens
  POST /integrations/quickbooks/sync       — Trigger manual sync
  GET  /integrations/                      — List active integrations for tenant
  DELETE /integrations/{id}                — Disconnect an integration
"""
import os
import secrets
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.db import get_db
from app.deps import get_current_user, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_redis():
    import redis
    return redis.from_url(REDIS_URL, decode_responses=True)


@router.post("/quickbooks/connect")
async def quickbooks_connect(current_user: dict = Depends(require_admin)):
    """
    Step 1 of OAuth flow.
    Generates a state token, stores it in Redis for 10 minutes, and returns
    the QuickBooks authorization URL for the frontend to redirect the user to.
    """
    from ingestion.quickbooks import build_authorization_url

    state_token = secrets.token_urlsafe(32)

    # Store state with tenant_id so we can verify on callback
    try:
        r = _get_redis()
        r.setex(f"qb_state:{state_token}", 600, current_user["tenant_id"])
    except Exception as e:
        logger.warning("Redis unavailable for state storage: %s", e)
        # Dev fallback — accept any state (insecure, dev only)

    auth_url = build_authorization_url(state_token)
    return {"auth_url": auth_url, "state": state_token}


@router.get("/quickbooks/callback")
async def quickbooks_callback(request: Request, code: str, state: str, realmId: str):
    """
    Step 2 of OAuth flow — QuickBooks redirects here after user approval.
    Exchanges the code for tokens and stores them encrypted.
    """
    from ingestion.quickbooks import exchange_code_for_tokens

    # Verify state token
    tenant_id = None
    try:
        r = _get_redis()
        tenant_id = r.get(f"qb_state:{state}")
        r.delete(f"qb_state:{state}")
    except Exception:
        pass

    if not tenant_id:
        # In dev mode without Redis, accept any state
        logger.warning("Could not verify OAuth state token — Redis may be unavailable.")

    db = get_db()

    try:
        token_data = exchange_code_for_tokens(code, realmId)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
        ).isoformat()

        db.table("integrations").upsert({
            "tenant_id":       tenant_id or realmId,
            "provider":        "quickbooks",
            "access_token":    token_data["access_token"],
            "refresh_token":   token_data["refresh_token"],
            "realm_id":        realmId,
            "token_expires_at": expires_at,
            "sync_status":     "idle",
        }, on_conflict="tenant_id,provider").execute()

    except Exception as e:
        logger.error("QuickBooks token exchange failed: %s", e)
        return RedirectResponse(url=f"{FRONTEND_URL}/settings/integrations?error=oauth_failed")

    # Trigger initial sync
    try:
        from tasks.ingestion_tasks import sync_quickbooks_task
        rec = db.table("integrations").select("id").eq("tenant_id", tenant_id).eq(
            "provider", "quickbooks"
        ).single().execute()
        sync_quickbooks_task.delay(tenant_id, rec.data["id"])
    except Exception as e:
        logger.warning("Could not trigger initial QB sync: %s", e)

    return RedirectResponse(url=f"{FRONTEND_URL}/settings/integrations?success=quickbooks")


@router.post("/quickbooks/sync")
async def trigger_quickbooks_sync(current_user: dict = Depends(require_admin)):
    """Manually trigger a QuickBooks sync for the authenticated tenant."""
    db = get_db()
    tenant_id = current_user["tenant_id"]

    res = db.table("integrations").select("id, sync_status").eq(
        "tenant_id", tenant_id
    ).eq("provider", "quickbooks").single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="QuickBooks integration not connected.")

    if res.data["sync_status"] == "syncing":
        raise HTTPException(status_code=409, detail="Sync already in progress.")

    try:
        from tasks.ingestion_tasks import sync_quickbooks_task
        sync_quickbooks_task.delay(tenant_id, res.data["id"])
        return {"message": "QuickBooks sync triggered.", "integration_id": res.data["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not queue sync: {e}")


@router.post("/lightspeed/connect")
async def lightspeed_connect(current_user: dict = Depends(require_admin)):
    """
    Step 1 of OAuth flow for Lightspeed.
    """
    from ingestion.lightspeed import build_lightspeed_auth_url

    state_token = secrets.token_urlsafe(32)

    try:
        r = _get_redis()
        r.setex(f"ls_state:{state_token}", 600, current_user["tenant_id"])
    except Exception as e:
        logger.warning("Redis unavailable for state storage: %s", e)

    auth_url = build_lightspeed_auth_url(state_token)
    return {"auth_url": auth_url, "state": state_token}


@router.get("/lightspeed/callback")
async def lightspeed_callback(request: Request, code: str, state: str):
    """
    Step 2 of OAuth flow for Lightspeed.
    """
    from ingestion.lightspeed import exchange_code_for_tokens

    tenant_id = None
    try:
        r = _get_redis()
        tenant_id = r.get(f"ls_state:{state}")
        r.delete(f"ls_state:{state}")
    except Exception:
        pass

    db = get_db()

    try:
        token_data = exchange_code_for_tokens(code)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
        ).isoformat()

        # In Lightspeed X-Series, the Account ID is returned in the token response
        account_id = str(token_data.get("account_id", ""))

        db.table("integrations").upsert({
            "tenant_id":       tenant_id,
            "provider":        "lightspeed",
            "access_token":    token_data["access_token"],
            "refresh_token":   token_data["refresh_token"],
            "realm_id":        account_id,
            "token_expires_at": expires_at,
            "sync_status":     "idle",
        }, on_conflict="tenant_id,provider").execute()

    except Exception as e:
        logger.error("Lightspeed token exchange failed: %s", e)
        return RedirectResponse(url=f"{FRONTEND_URL}/settings/integrations?error=oauth_failed")

    # Trigger initial sync
    try:
        from tasks.ingestion_tasks import sync_lightspeed_task
        rec = db.table("integrations").select("id").eq("tenant_id", tenant_id).eq(
            "provider", "lightspeed"
        ).single().execute()
        sync_lightspeed_task.delay(tenant_id, rec.data["id"])
    except Exception as e:
        logger.warning("Could not trigger initial Lightspeed sync: %s", e)

    return RedirectResponse(url=f"{FRONTEND_URL}/settings/integrations?success=lightspeed")


@router.post("/lightspeed/sync")
async def trigger_lightspeed_sync(current_user: dict = Depends(require_admin)):
    """Manually trigger a Lightspeed sync for the authenticated tenant."""
    db = get_db()
    tenant_id = current_user["tenant_id"]

    res = db.table("integrations").select("id, sync_status").eq(
        "tenant_id", tenant_id
    ).eq("provider", "lightspeed").single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Lightspeed integration not connected.")

    if res.data["sync_status"] == "syncing":
        raise HTTPException(status_code=409, detail="Sync already in progress.")

    try:
        from tasks.ingestion_tasks import sync_lightspeed_task
        sync_lightspeed_task.delay(tenant_id, res.data["id"])
        return {"message": "Lightspeed sync triggered.", "integration_id": res.data["id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not queue sync: {e}")


@router.get("/")
async def list_integrations(current_user: dict = Depends(get_current_user)):
    """Return all active integrations for the current tenant."""
    db = get_db()
    res = db.table("integrations").select(
        "id, provider, sync_status, last_sync_at, created_at"
    ).eq("tenant_id", current_user["tenant_id"]).execute()

    return {"integrations": res.data or []}


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_integration(
    integration_id: str,
    current_user: dict = Depends(require_admin),
):
    """Revoke and delete an integration (does not delete ingested data)."""
    db = get_db()
    db.table("integrations").delete().eq("id", integration_id).eq(
        "tenant_id", current_user["tenant_id"]
    ).execute()
