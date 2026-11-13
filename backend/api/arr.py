"""Radarr/Sonarr connections: test one, and list an instance's tags.

Read only (see backend/arr_client.py). The connections themselves are saved
with the rest of the settings (UISettings.arrInstances).
"""
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import arr_client
from ..config import SECRET_MASK

router = APIRouter()


class ArrTestRequest(BaseModel):
    type: str
    url: str = ""
    apiKey: str = ""
    instance_id: Optional[str] = None


def _origin(url) -> tuple:
    p = urlparse(str(url or "").strip())
    return (p.scheme.lower(), p.netloc.lower())


@router.post("/arr/test")
def api_arr_test(req: ArrTestRequest):
    if req.type not in arr_client.TYPES:
        raise HTTPException(status_code=400, detail="type must be 'radarr' or 'sonarr'")
    key = req.apiKey
    if key in (SECRET_MASK, ""):
        # The page never sees the real key. Use the stored one, but only for
        # the stored address, so it is never sent to another host.
        stored = arr_client.get_instance(req.instance_id) or {}
        if not stored.get("apiKey"):
            return {"ok": False, "app": "", "version": "", "error": "Enter the API key"}
        if _origin(req.url) != _origin(stored.get("url")):
            return {"ok": False, "app": "", "version": "",
                    "error": "The address changed, so enter the API key again"}
        key = stored["apiKey"]
    return arr_client.test_connection(req.type, req.url, key)


@router.get("/arr/{instance_id}/tags")
def api_arr_tags(instance_id: str):
    if not arr_client.get_instance(instance_id):
        raise HTTPException(status_code=404, detail="Unknown Radarr/Sonarr instance")
    synced = arr_client.refresh(instance_id, 300)
    return {"tags": arr_client.known_tags(instance_id), "synced": synced,
            "error": "" if synced else arr_client.last_error(instance_id)}
