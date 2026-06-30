from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/status")
async def api_status():
    """Simple API status endpoint for frontend connectivity checks."""
    return {"status": "ok"}
