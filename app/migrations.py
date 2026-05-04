"""
Auto-migration runner — executes on FastAPI startup.
Each entry in MIGRATIONS is idempotent (IF NOT EXISTS / IF EXISTS guards).
Add new migrations to the list in order; never remove or reorder existing ones.
"""

import os
import psycopg2
from psycopg2 import sql

MIGRATIONS = [
    # 015 — onboarding progress tracking
    """
    ALTER TABLE tenants
        ADD COLUMN IF NOT EXISTS onboarding_step SMALLINT NOT NULL DEFAULT 1,
        ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;
    """,
]


def _get_conn():
    """
    Prefer an explicit DATABASE_URL. If absent, build the Supabase
    direct-connection URL from SUPABASE_URL + DB_PASSWORD.
    Supabase direct URLs follow the pattern:
        postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg2.connect(url)

    supabase_url = os.getenv("SUPABASE_URL", "")
    db_password = os.getenv("SUPABASE_DB_PASSWORD") or os.getenv("DB_PASSWORD")

    if supabase_url and db_password:
        # Extract project ref from https://<ref>.supabase.co
        ref = supabase_url.replace("https://", "").split(".")[0]
        direct_url = f"postgresql://postgres:{db_password}@db.{ref}.supabase.co:5432/postgres"
        return psycopg2.connect(direct_url)

    raise RuntimeError(
        "No database connection available for migrations. "
        "Set DATABASE_URL or SUPABASE_DB_PASSWORD in your environment."
    )


def run_migrations():
    """Run all pending migrations. Called once at app startup."""
    try:
        conn = _get_conn()
    except Exception as e:
        # Non-fatal on connection failure — app still starts, log clearly
        print(f"[migrations] WARNING: could not connect for migrations: {e}")
        print("[migrations] Skipping auto-migration. Run migrations manually if needed.")
        return

    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            for i, migration in enumerate(MIGRATIONS, start=1):
                try:
                    cur.execute(migration)
                    print(f"[migrations] migration {i} applied OK")
                except Exception as e:
                    print(f"[migrations] migration {i} failed (may already be applied): {e}")
    finally:
        conn.close()
