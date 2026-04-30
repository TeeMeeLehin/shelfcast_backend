from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.db import get_db
from app.deps import get_current_user, require_admin
import os
import resend
from supabase import create_client

router = APIRouter()

class SignupRequest(BaseModel):
    tenant_name: str
    email: EmailStr
    password: str
    city: Optional[str] = None        # Primary operating city for geo-intelligence
    country: str = "Ghana"            # Default market

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "manager"
    city: Optional[str] = None        # City where this manager operates

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest):
    supabase = get_db()
    if not supabase:
        raise HTTPException(status_code=500, detail="Database client not initialized")
        
    try:
        # 1. Create the tenant first to get the generated tenant_id
        # We use service_role to bypass RLS for this initial creation
        tenant_res = supabase.table("tenants").insert({
            "name": request.tenant_name
        }).execute()
        
        if not tenant_res.data:
            raise HTTPException(status_code=500, detail="Failed to create tenant")
            
        tenant_id = tenant_res.data[0]["id"]
        
        # 2. Create the user in Supabase Auth via Admin API
        # Store tenant_id in app_metadata so it gets included in the JWT
        auth_res = supabase.auth.admin.create_user({
            "email": request.email,
            "password": request.password,
            "email_confirm": True, # Auto-confirm for MVP
            "app_metadata": {
                "tenant_id": tenant_id,
                "role": "admin"
            }
        })
        
        user_id = auth_res.user.id
        
        # 3. Create the user record in the public.users table (with location)
        supabase.table("users").insert({
            "id": user_id,
            "tenant_id": tenant_id,
            "email": request.email,
            "role": "admin",
            "city": request.city,
            "country": request.country,
        }).execute()
        
        # 4. Automatically log them in to return a session using a temporary client
        # to avoid polluting the global service_role client with a user session.
        temp_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))
        login_res = temp_client.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        return {
            "message": "Tenant and admin user created successfully",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "access_token": login_res.session.access_token,
            "refresh_token": login_res.session.refresh_token
        }
        
    except Exception as e:
        # Naive rollback: if something fails, try to delete the tenant
        if 'tenant_id' in locals():
            supabase.table("tenants").delete().eq("id", tenant_id).execute()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(request: LoginRequest):
    temp_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))
    try:
        auth_res = temp_client.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        return {
            "access_token": auth_res.session.access_token,
            "refresh_token": auth_res.session.refresh_token,
            "user": auth_res.user
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")

@router.post("/invite", status_code=status.HTTP_200_OK)
async def invite_user(request: InviteRequest, current_user: dict = Depends(require_admin)):
    supabase = get_db()
    tenant_id = current_user["tenant_id"]

    # 1. Check if we've reached the 4 user limit
    users_res = supabase.table("users").select("id").eq("tenant_id", tenant_id).execute()
    if len(users_res.data) >= 5:  # 1 admin + 4 managers
        raise HTTPException(status_code=400, detail="Maximum user limit reached for this tenant.")

    try:
        import secrets, string

        # 2. Generate a secure temporary password the invitee will use on first login.
        #    Using create_user (not invite_user_by_email) decouples user creation from
        #    email delivery — the user row is committed regardless of SMTP health.
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        temp_password = "".join(secrets.choice(alphabet) for _ in range(16))

        auth_res = supabase.auth.admin.create_user({
            "email": request.email,
            "password": temp_password,
            "email_confirm": True,  # pre-confirm so they can log in immediately
            "app_metadata": {
                "tenant_id": tenant_id,
                "role": request.role,
            },
            "user_metadata": {
                "city": request.city,
            }
        })

        invited_user_id = auth_res.user.id

        # 3. Create the user record in public.users (with location)
        supabase.table("users").insert({
            "id": invited_user_id,
            "tenant_id": tenant_id,
            "email": request.email,
            "role": request.role,
            "city": request.city,
        }).execute()

        # 4. Send invite email via Resend — independently of user creation.
        #    If this fails it is logged but does NOT roll back the created user.
        email_sent = False
        resend_api_key = os.getenv("RESEND_API_KEY")
        if resend_api_key:
            try:
                # Fetch tenant name for the email
                tenant_res = supabase.table("tenants").select("name").eq("id", tenant_id).single().execute()
                tenant_name = tenant_res.data["name"] if tenant_res.data else "your organization"

                # Ensure Sender name is explicitly 'ShelfCast' if DIGEST_FROM_EMAIL is just an email string
                sender_email = os.getenv("DIGEST_FROM_EMAIL", "onboarding@resend.dev")
                if "<" not in sender_email:
                    sender_email = f"ShelfCast <{sender_email}>"

                resend.api_key = resend_api_key
                resend.Emails.send({
                    "from": sender_email,
                    "to": request.email,
                    "subject": f"You have been invited to join {tenant_name} on ShelfCast",
                    "html": f"""
                        <p>You have been invited to join <strong>ShelfCast</strong> as a <em>{request.role}</em> for <strong>{tenant_name}</strong>.</p>
                        <p>Use the credentials below to log in for the first time:</p>
                        <p><strong>Email:</strong> {request.email}<br/>
                        <strong>Temporary Password:</strong> <code>{temp_password}</code></p>
                        <p>Please change your password after logging in.</p>
                    """
                })
                email_sent = True
            except Exception as email_err:
                # Non-fatal: log but continue — admin can share credentials manually
                print(f"[invite] Resend email failed (non-fatal): {email_err}")

        return {
            "message": f"User {request.email} created successfully.",
            "user_id": invited_user_id,
            "email_sent": email_sent,
            # Return temp_password so admin can share it if email is not configured
            "temp_password": temp_password if not email_sent else "[sent via email]",
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to invite user: {str(e)}")

@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(request: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    # 1. Verify current password
    temp_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))
    try:
        temp_client.auth.sign_in_with_password({
            "email": current_user["email"],
            "password": request.current_password
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Incorrect current password")

    # 2. Update to new password
    supabase = get_db()
    try:
        supabase.auth.admin.update_user_by_id(
            current_user["user_id"],
            {"password": request.new_password}
        )
        return {"message": "Password updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update password: {str(e)}")
