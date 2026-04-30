import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import supabase

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_tenants():
    # We require real Supabase credentials for this integration test
    if not supabase or os.getenv("SUPABASE_URL") == "https://mock.supabase.co":
        pytest.skip("Skipping real DB tests because Supabase credentials are not configured.")
        
    # Generate unique emails
    email_a = f"admin_a_{os.urandom(4).hex()}@example.com"
    email_b = f"admin_b_{os.urandom(4).hex()}@example.com"
    password = "SecurePassword123!"

    # 1. Sign up Tenant A
    res_a = client.post("/auth/signup", json={
        "tenant_name": "Tenant A Inc",
        "email": email_a,
        "password": password
    })
    assert res_a.status_code == 201, f"Failed to create Tenant A: {res_a.text}"
    tenant_a_data = res_a.json()
    token_a = tenant_a_data["access_token"]
    tenant_id_a = tenant_a_data["tenant_id"]

    # 2. Sign up Tenant B
    res_b = client.post("/auth/signup", json={
        "tenant_name": "Tenant B LLC",
        "email": email_b,
        "password": password
    })
    assert res_b.status_code == 201, f"Failed to create Tenant B: {res_b.text}"
    tenant_b_data = res_b.json()
    token_b = tenant_b_data["access_token"]
    tenant_id_b = tenant_b_data["tenant_id"]

    yield {
        "tenant_a": {"email": email_a, "token": token_a, "id": tenant_id_a},
        "tenant_b": {"email": email_b, "token": token_b, "id": tenant_id_b}
    }
    
    # Cleanup: Delete tenants (cascade deletes users and data)
    supabase.table("tenants").delete().eq("id", tenant_id_a).execute()
    supabase.table("tenants").delete().eq("id", tenant_id_b).execute()
    # Note: deleting from Supabase auth.users requires a specific admin function 
    # but cascade delete on our public tables is enough for this test

def test_rls_isolation(setup_tenants):
    tenant_a = setup_tenants["tenant_a"]
    tenant_b = setup_tenants["tenant_b"]

    # We use the Supabase client directly to test RLS by setting the auth session.
    # To test RLS, the client must use the anon key and the user's JWT.
    # Because we initialized `supabase` with the Service Role Key, it bypasses RLS!
    # We must create a new client with the Anon key for this test.
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY") # You need this in .env
    
    if not supabase_anon_key:
        pytest.skip("SUPABASE_ANON_KEY required to test RLS via the client")
        
    from supabase import create_client
    client_a = create_client(supabase_url, supabase_anon_key)
    client_b = create_client(supabase_url, supabase_anon_key)
    
    # Set the sessions using the JWTs retrieved from signup
    client_a.auth.set_session(tenant_a["token"], "dummy-refresh")
    client_b.auth.set_session(tenant_b["token"], "dummy-refresh")
    
    # Insert a Catalogue item for Tenant A
    # Since we are using client_a, RLS should automatically enforce the tenant_id 
    # if it's set in the policy. But for insertion, we still need to provide it 
    # (or let a trigger handle it, but here we provide it).
    insert_res = client_a.table("catalogue").insert({
        "tenant_id": tenant_a["id"],
        "sku_id": "SKU-001",
        "sku_name": "Identical SKU Name",
        "brand": "Brand X"
    }).execute()
    assert len(insert_res.data) == 1
    
    # Tenant A reads Catalogue: should see 1 row
    read_a = client_a.table("catalogue").select("*").execute()
    assert len(read_a.data) == 1
    assert read_a.data[0]["sku_name"] == "Identical SKU Name"
    
    # Tenant B reads Catalogue: should see 0 rows
    read_b = client_b.table("catalogue").select("*").execute()
    assert len(read_b.data) == 0, "RLS FAILURE: Tenant B can see Tenant A's data!"
