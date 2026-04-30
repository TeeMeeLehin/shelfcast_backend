from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_intelligence():
    return {"message": "Intelligence endpoints will be implemented in Phase 4"}
