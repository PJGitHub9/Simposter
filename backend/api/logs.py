from fastapi import APIRouter
from ..config import settings

router = APIRouter()

@router.get("/logs")
def api_logs():
    try:
        with open(settings.LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except:
        return {"text": ""}

    return {"text": "".join(lines[-500:])}
