from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, intelligence, catalogue, ingest, integrations

app = FastAPI(
    title="ShelfCast Backend",
    description="Retail Intelligence Engine for FMCG",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update with frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "shelfcast-backend"}

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(intelligence.router, prefix="/intelligence", tags=["Intelligence"])
app.include_router(catalogue.router, prefix="/catalogue", tags=["Catalogue"])
app.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])
app.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
