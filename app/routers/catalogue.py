from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_catalogue():
    return {"message": "Catalogue endpoints will be implemented in Phase 2/3"}
