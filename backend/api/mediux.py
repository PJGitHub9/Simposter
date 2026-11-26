# backend/api/mediux.py
"""MediUX key test (Settings -> Ratings & Lists)."""

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import SECRET_MASK, redact_secrets

router = APIRouter()


@router.post("/test-mediux")
def api_test_mediux(payload: dict):
    from .. import mediux_client
    key = str((payload or {}).get("api_key") or "").strip()
    if not key or key == SECRET_MASK:
        key = mediux_client.get_mediux_key()
    if not key:
        return {"ok": False, "message": "Enter a MediUX API key first."}
    try:
        ok, message = mediux_client.check_key(key)
    except Exception as e:
        return {"ok": False, "message": redact_secrets(str(e)) or "MediUX test failed."}
    return {"ok": bool(ok), "message": redact_secrets(message)}


_ASSET_RE = re.compile(r"^[A-Za-z0-9-]+$")
_V_RE = re.compile(r"^[0-9]{1,20}$")
_SIZE_KEY = {"thumb": "thumb", "jpg": "jpg", "original": None}
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/avif": "avif"}
_MAX_BYTES = 15 * 1024 * 1024
_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


def _cache_dir() -> Path:
    from ..config import settings
    d = Path(settings.CONFIG_DIR) / "cache" / "mediux"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/mediux/image")
def api_mediux_image(asset: str = Query(...), v: str = Query(""), size: str = Query("jpg")):
    """Browser access to MediUX images (they need the key, which stays server-side)."""
    from .. import mediux_client
    from ..middleware.validation import safe_get
    from ..config import EXTERNAL_IMAGE_FETCH_HEADERS
    if not _ASSET_RE.match(asset or ""):
        raise HTTPException(status_code=400, detail="Invalid asset id")
    if v and not _V_RE.match(v):
        raise HTTPException(status_code=400, detail="Invalid version")
    if size not in _SIZE_KEY:
        raise HTTPException(status_code=400, detail="Invalid size")
    stem = "%s_%s_%s" % (asset, v or "0", size)
    d = _cache_dir()
    for f in d.glob(stem + ".*"):
        if f.suffix != ".tmp":
            return FileResponse(str(f), headers=_HEADERS)
    key = mediux_client.get_mediux_key()
    if not key:
        raise HTTPException(status_code=404, detail="No MediUX key")
    url = "%s/assets/%s" % (mediux_client.BASE, asset)
    params = []
    if v:
        params.append("v=" + v)
    if _SIZE_KEY[size]:
        params.append("key=" + _SIZE_KEY[size])
    if params:
        url += "?" + "&".join(params)

    def _auth(u):
        return {"Authorization": "Bearer " + key} if mediux_client.is_mediux_image_url(u) else {}

    try:
        r = safe_get(url, strict=True, timeout=30, headers=EXTERNAL_IMAGE_FETCH_HEADERS, headers_for=_auth, stream=True)
    except Exception:
        raise HTTPException(status_code=502, detail="Could not fetch the MediUX image")
    try:
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Not found")
        if r.status_code >= 300:
            raise HTTPException(status_code=502, detail="MediUX returned HTTP %d" % r.status_code)
        ctype = str(r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        ext = _EXT.get(ctype)
        if not ext:
            raise HTTPException(status_code=502, detail="MediUX did not return an image")
        data = bytearray()
        for chunk in r.iter_content(65536):
            data.extend(chunk)
            if len(data) > _MAX_BYTES:
                raise HTTPException(status_code=502, detail="MediUX image is too large")
    finally:
        try:
            r.close()
        except Exception:
            pass
    path = d / ("%s.%s" % (stem, ext))
    tmp = d / ("%s.%s.tmp" % (stem, uuid.uuid4().hex))
    try:
        tmp.write_bytes(bytes(data))
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return FileResponse(str(path), headers=_HEADERS)
