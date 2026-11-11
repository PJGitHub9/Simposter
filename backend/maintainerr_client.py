# backend/maintainerr_client.py
"""Maintainerr (https://github.com/Maintainerr/Maintainerr) — when items leave.

  GET {url}/api/collections/overlay-data?typeId=movie|show|season
returns every collection with its full member list (Maintainerr 3.20+). A
collection has deleteAfterDays/isActive/title; each member has mediaServerId,
tmdbId, tvdbId and addDate. Maintainerr acts once addDate + deleteAfterDays
days has passed. Its API doesn't check an API key, but the key is sent as
X-Api-Key when set, for a proxy in front of it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .config import SECRET_MASK, redact_secrets

OVERLAY_DATA_PATH = "/api/collections/overlay-data"


class MaintainerrError(Exception):
    pass


def _settings() -> Dict[str, Any]:
    try:
        from . import database as db
        return (db.get_ui_settings() or {}).get("maintainerr") or {}
    except Exception:
        return {}


def _base(override: Optional[str] = None) -> str:
    return str(override if override is not None else (_settings().get("url") or "")).strip().rstrip("/")


def _origin(url: str):
    p = urlparse(str(url or "").strip())
    return (p.scheme.lower(), p.netloc.lower())


def _blocked_host(url: str) -> bool:
    """Maintainerr runs on your LAN, so private addresses are fine; never
    link-local / cloud metadata addresses."""
    try:
        from .middleware.validation import _host_is_always_blocked
        return _host_is_always_blocked(urlparse(url).hostname or "")
    except Exception:
        return False


def is_configured() -> bool:
    return bool(_base())


def _user_agent() -> str:
    try:
        from .config import api_user_agent
        return api_user_agent()
    except Exception:
        return "Simposter"


def fetch_overlay_data(type_id: str, url: Optional[str] = None,
                       api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Collections (with their members) of one media type. Raises
    MaintainerrError with a log-safe message on any failure."""
    base = _base(url)
    key = str(_settings().get("apiKey") or "") if api_key is None else str(api_key or "")
    if not base:
        raise MaintainerrError("Maintainerr isn't set up")
    if not base.lower().startswith(("http://", "https://")):
        raise MaintainerrError("The address must start with http:// or https://")
    if _blocked_host(base):
        raise MaintainerrError("That address isn't allowed (link-local / cloud metadata)")
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    if key:
        headers["X-Api-Key"] = key
    try:
        r = requests.get(f"{base}{OVERLAY_DATA_PATH}", params={"typeId": type_id}, headers=headers,
                         timeout=20, allow_redirects=False)
    except requests.Timeout:
        raise MaintainerrError(f"Maintainerr at {base} didn't answer in time")
    except requests.ConnectionError:
        raise MaintainerrError(f"Couldn't connect to Maintainerr at {base} (is it running, and is the address right?)")
    except requests.RequestException as e:
        raise MaintainerrError(f"Couldn't reach Maintainerr: {redact_secrets(e)}")
    if r.status_code == 404:
        raise MaintainerrError("Maintainerr didn't recognise the request; it needs Maintainerr 3.20 or newer")
    if r.status_code in (401, 403):
        raise MaintainerrError("Maintainerr (or a proxy in front of it) refused the request; check the API key")
    if 300 <= r.status_code < 400:
        raise MaintainerrError("Maintainerr answered with a redirect; use the address it redirects to")
    if not 200 <= r.status_code < 300:
        raise MaintainerrError(f"Maintainerr returned HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise MaintainerrError("Maintainerr didn't answer with JSON (check the address)")
    if not isinstance(data, list):
        raise MaintainerrError("Maintainerr returned something unexpected (check the address)")
    return [c for c in data if isinstance(c, dict)]


def test(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Settings → Test. The masked key means "the saved key", which is only
    ever sent to the saved server."""
    saved = _base()
    base = str(payload.get("url") or "").strip().rstrip("/") or saved
    raw_key = str(payload.get("apiKey") or "")
    if raw_key == SECRET_MASK:
        key = str(_settings().get("apiKey") or "") if _origin(base) == _origin(saved) else ""
    else:
        key = raw_key
    if not base:
        return {"ok": False, "message": "Enter Maintainerr's address", "collections": 0, "items": 0}
    collections = items = 0
    try:
        for type_id in ("movie", "show"):
            for c in fetch_overlay_data(type_id, url=base, api_key=key):
                collections += 1
                items += len(c.get("media") or [])
    except MaintainerrError as e:
        return {"ok": False, "message": str(e), "collections": 0, "items": 0}
    return {"ok": True, "message": f"Connected: {collections} collections, {items} items",
            "collections": collections, "items": items}
