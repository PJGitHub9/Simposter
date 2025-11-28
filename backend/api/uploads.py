import os
import time
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from ..config import settings

router = APIRouter()

@router.post("/upload/background")
async def api_upload_background(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    fname = f"bg_{int(time.time()*1000)}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, fname)

    with open(path, "wb") as f:
        f.write(await file.read())

    return {"url": f"/api/uploaded/{fname}"}

@router.get("/uploaded/{filename}")
def api_uploaded(filename: str):
    path = os.path.join(settings.UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path)
