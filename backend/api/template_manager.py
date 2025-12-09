from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any

from .. import database as db
from ..config import logger

router = APIRouter()

FALLBACK_KEYS = {
    "fallback.poster_filter": "all",
    "fallback.logo_mode": "first",
    "pref.language": "en",
}


def _get_fallback_settings() -> Dict[str, Any]:
    data = {}
    for key, default in FALLBACK_KEYS.items():
        val = db.get_setting(key)
        data[key] = val if val is not None else default
    return {
        "poster_filter": data["fallback.poster_filter"],
        "logo_mode": data["fallback.logo_mode"],
        "language_preference": data["pref.language"],
    }


@router.get("/template-fallback")
def api_get_template_fallback():
    """Return fallback settings for template rendering (poster/logo defaults)."""
    try:
        return _get_fallback_settings()
    except Exception as e:
        logger.error(f"[TEMPLATE_FALLBACK] Failed to read: {e}")
        raise HTTPException(status_code=500, detail="Failed to read fallback settings")


@router.post("/template-fallback")
def api_set_template_fallback(payload: Dict[str, Any]):
    """Save fallback settings for template rendering."""
    try:
        poster_filter = str(payload.get("poster_filter") or FALLBACK_KEYS["fallback.poster_filter"])
        logo_mode = str(payload.get("logo_mode") or FALLBACK_KEYS["fallback.logo_mode"])
        language_preference = str(payload.get("language_preference") or FALLBACK_KEYS["pref.language"])
        db.set_setting("fallback.poster_filter", poster_filter)
        db.set_setting("fallback.logo_mode", logo_mode)
        db.set_setting("pref.language", language_preference)
        return _get_fallback_settings()
    except Exception as e:
        logger.error(f"[TEMPLATE_FALLBACK] Failed to save: {e}")
        raise HTTPException(status_code=500, detail="Failed to save fallback settings")
