from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db import get_db

security = HTTPBearer()

def get_current_user(token: HTTPAuthorizationCredentials = Depends(security)):
    try:
        supabase = get_db()
        # gotrue_client.get_user natively validates the token signature (handles ES256/HS256)
        # and checks against the server if the token was revoked.
        user_res = supabase.auth.get_user(token.credentials)
        
        user = user_res.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload. User not found.",
            )

        user_id = user.id
        app_metadata = user.app_metadata or {}
        tenant_id = app_metadata.get("tenant_id")
        
        if not user_id or not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload. Missing user_id or tenant_id.",
            )
            
        return {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "role": app_metadata.get("role", "manager"),
            "email": user.email
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_tenant(user: dict = Depends(get_current_user)):
    return user["tenant_id"]

def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required."
        )
    return user
