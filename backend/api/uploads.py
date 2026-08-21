import os
import time
from pathlib import Path
from urllib.parse import quote
import requests
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from ..config import settings, logger

router = APIRouter()

_UPLOAD_PREFIXES = {"background": "bg", "logo": "logo"}

@router.post("/upload/background")
async def api_upload_background(file: UploadFile = File(...), kind: str = Form("background")):
    prefix = _UPLOAD_PREFIXES.get(kind, "bg")
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    fname = f"{prefix}_{int(time.time()*1000)}{ext}"
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


# ---------------------------------------------------------------------------
# Kometa Creator background textures — referenced live from
# Kometa-Team/Defaults-Image-Creation (create_defaults/@base/, MIT licensed)
# rather than vendored, so upstream additions show up without a re-vendor pass.
# The frontend uses the returned raw.githubusercontent.com URL directly as the
# logo URL — the existing render pipeline already fetches arbitrary image URLs
# (rendering.py's _download_image(), with its own LRU cache/retry/SSRF check),
# so no separate serving/proxy endpoint is needed here.
#
# The directory listing itself is cached in-memory (a few hours) because it
# comes from GitHub's Contents API, which is rate-limited to 60 requests/hour
# per IP unauthenticated — the actual texture images are served straight from
# raw.githubusercontent.com (a CDN, not that rate-limited API) and aren't
# affected by this. A hardcoded fallback (the set known at integration time)
# is used if the live listing fetch fails, so a transient GitHub hiccup or a
# hit rate limit degrades to "slightly stale list" rather than an empty one.
# ---------------------------------------------------------------------------
_KOMETA_TEXTURES_API_URL = (
    "https://api.github.com/repos/Kometa-Team/Defaults-Image-Creation/"
    "contents/create_defaults/%40base"
)
_KOMETA_TEXTURES_RAW_BASE = (
    "https://raw.githubusercontent.com/Kometa-Team/Defaults-Image-Creation/"
    "main/create_defaults/%40base/"
)
_KOMETA_TEXTURES_FALLBACK_NAMES = [
    "amethyst", "aqua", "blue", "forest", "fuchsia", "gold", "gray", "green",
    "navy", "ocean", "olive", "orchid", "orig", "pink", "plum", "purple",
    "red", "rust", "salmon", "sand", "stb", "tan",
]
_KOMETA_TEXTURES_CACHE_TTL_SECONDS = 6 * 60 * 60
_kometa_textures_cache: dict = {"names": None, "fetched_at": 0.0}


def _fetch_kometa_texture_names() -> list[str]:
    resp = requests.get(_KOMETA_TEXTURES_API_URL, timeout=10, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    data = resp.json()
    return sorted(
        Path(item["name"]).stem
        for item in data
        if item.get("type") == "file" and item.get("name", "").lower().endswith(".png")
    )


@router.get("/kometa-textures")
def api_list_kometa_textures():
    """List available Kometa Creator background textures as {name, url} pairs,
    refreshing the live GitHub listing at most every few hours."""
    now = time.time()
    if _kometa_textures_cache["names"] is None or (now - _kometa_textures_cache["fetched_at"]) > _KOMETA_TEXTURES_CACHE_TTL_SECONDS:
        try:
            names = _fetch_kometa_texture_names()
            _kometa_textures_cache["names"] = names
            _kometa_textures_cache["fetched_at"] = now
        except Exception as e:
            logger.debug("[KOMETA] Failed to refresh texture listing from GitHub: %s", e)
            if _kometa_textures_cache["names"] is None:
                _kometa_textures_cache["names"] = _KOMETA_TEXTURES_FALLBACK_NAMES

    names = _kometa_textures_cache["names"] or _KOMETA_TEXTURES_FALLBACK_NAMES
    return {"textures": [{"name": n, "url": f"{_KOMETA_TEXTURES_RAW_BASE}{n}.png"} for n in names]}


# ---------------------------------------------------------------------------
# Kometa Creator logo library — same live-reference pattern as the textures
# above, against the same repo's categorized logos_* directories
# (create_defaults/logos_chart/, logos_genre/, etc., MIT licensed). One cache
# entry per category, fetched lazily (only once a category is actually
# selected in the UI) rather than eagerly listing all ~15 directories.
# ---------------------------------------------------------------------------
_KOMETA_LOGO_CATEGORIES = [
    "aspect", "award", "chart", "content_rating", "country", "franchise",
    "genre", "network", "playlist", "resolution", "seasonal", "streaming",
    "studio", "universe", "video_format",
]
_KOMETA_LOGOS_API_URL_TMPL = (
    "https://api.github.com/repos/Kometa-Team/Defaults-Image-Creation/"
    "contents/create_defaults/logos_{category}"
)
_KOMETA_LOGOS_RAW_BASE_TMPL = (
    "https://raw.githubusercontent.com/Kometa-Team/Defaults-Image-Creation/"
    "main/create_defaults/logos_{category}/"
)
_KOMETA_LOGOS_CACHE_TTL_SECONDS = 6 * 60 * 60
_kometa_logos_cache: dict = {}


@router.get("/kometa-logo-categories")
def api_list_kometa_logo_categories():
    return {"categories": _KOMETA_LOGO_CATEGORIES}


def _fetch_kometa_logo_items(category: str) -> list[dict]:
    url = _KOMETA_LOGOS_API_URL_TMPL.format(category=category)
    resp = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    data = resp.json()
    raw_base = _KOMETA_LOGOS_RAW_BASE_TMPL.format(category=category)
    files = sorted(
        (item["name"] for item in data if item.get("type") == "file" and item.get("name", "").lower().endswith((".png", ".webp"))),
        key=str.lower,
    )
    return [{"name": Path(f).stem, "url": f"{raw_base}{quote(f)}"} for f in files]


@router.get("/kometa-logos/{category}")
def api_list_kometa_logos(category: str):
    """List logos in one Kometa default logo category as {name, url} pairs,
    refreshing the live GitHub listing at most every few hours per category."""
    if category not in _KOMETA_LOGO_CATEGORIES:
        raise HTTPException(404, "Unknown logo category")

    now = time.time()
    cached = _kometa_logos_cache.get(category)
    if cached is None or (now - cached["fetched_at"]) > _KOMETA_LOGOS_CACHE_TTL_SECONDS:
        try:
            items = _fetch_kometa_logo_items(category)
            _kometa_logos_cache[category] = {"items": items, "fetched_at": now}
        except Exception as e:
            logger.debug("[KOMETA] Failed to refresh logo listing for '%s': %s", category, e)
            if cached is None:
                _kometa_logos_cache[category] = {"items": [], "fetched_at": now}

    return {"logos": _kometa_logos_cache[category]["items"]}
