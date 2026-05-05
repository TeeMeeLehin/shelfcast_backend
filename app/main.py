import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, intelligence, catalogue, ingest, integrations, dashboard, settings
from app.migrations import run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield


app = FastAPI(
    title="ShelfCast Backend",
    description="Retail Intelligence Engine for FMCG",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS origins from environment
origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "shelfcast-backend"}

# Register Routers with API Versioning (matches documentation)
API_V1 = "/api/v1"

app.include_router(auth.router, prefix=f"{API_V1}/auth", tags=["Authentication"])
app.include_router(intelligence.router, prefix=f"{API_V1}/intelligence", tags=["Intelligence"])
app.include_router(catalogue.router, prefix=f"{API_V1}/catalogue", tags=["Catalogue"])
app.include_router(ingest.router, prefix=f"{API_V1}/ingest", tags=["Ingestion"])
app.include_router(integrations.router, prefix=f"{API_V1}/integrations", tags=["Integrations"])
app.include_router(dashboard.router, prefix=f"{API_V1}/dashboard", tags=["Dashboard"])
app.include_router(settings.router, prefix=f"{API_V1}/settings", tags=["Settings"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
