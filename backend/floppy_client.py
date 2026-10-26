# backend/floppy_client.py
"""Floppy lists (self-hosted, https://github.com/dannyvfilms/Floppy).

Connected by the server's address plus an app token (Floppy: Settings >
Integrations > App tokens, scope lists:read), sent as Authorization: Bearer.
  GET {url}/api/v1/lists/                     your lists (id, name, items_count)
  GET {url}/api/v1/lists/{id}/items/?limit=200&offset=N   follow pagination.next
Each result carries an item with media_type, source, media_id and ids; movies
and shows are always addressable by TMDb id. Seasons on a list are skipped.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .config import SECRET_MASK, redact_secrets
from .list_sources import ListSourceError, app_version, ui_settings

KEY_PREFIX = "floppy:list:"
_LIST_PATH_RE = re.compile(r"/lists?/(\d+)(?:/|$)")


def _settings() -> Dict[str, Any]:
    return ui_settings("floppy")


def _base(override: Optional[str] = None) -> str:
    return str(override or _settings().get("url") or "").strip().rstrip("/")


def _token(override: Optional[str] = None) -> str:
    if override and override != SECRET_MASK:
        return override
    return str(_settings().get("token") or "")


def normalize(raw: str) -> Optional[str]:
    s = raw.strip()
    if s.lower().startswith(KEY_PREFIX):
        rest = s[len(KEY_PREFIX):]
        return KEY_PREFIX + rest if rest.isdigit() else None
    base = _base()
    if not base or not s.lower().startswith(("http://", "https://")):
        return None
    if urlparse(s).netloc.lower() != urlparse(base).netloc.lower():
        return None
    m = _LIST_PATH_RE.search(urlparse(s).path)
    return KEY_PREFIX + m.group(1) if m else None


def owns(key: str) -> bool:
    return key.startswith(KEY_PREFIX)


def missing_setup(key: str) -> Optional[str]:
    if not _base() or not _token():
        return "Floppy isn't set up (server address and app token in Settings > General)"
    return None


def _get(path_or_url: str, params: Optional[Dict[str, Any]] = None,
         base: Optional[str] = None, token: Optional[str] = None) -> Any:
    root = _base(base)
    tok = _token(token)
    if not root or not tok:
        raise ListSourceError("Floppy isn't set up")
    url = path_or_url if path_or_url.startswith("http") else f"{root}{path_or_url}"
    # The token only ever goes to the Floppy server itself: a pagination "next"
    # link pointing elsewhere is refused, and redirects aren't followed.
    if urlparse(url).netloc.lower() != urlparse(root).netloc.lower():
        raise ListSourceError("Floppy pointed to a different server; refusing to send the token there")
    try:
        r = requests.get(url, params=params, timeout=20, allow_redirects=False,
                         headers={"Authorization": f"Bearer {tok}", "User-Agent": f"Simposter/{app_version()}"})
    except requests.RequestException as e:
        raise ListSourceError(f"Couldn't reach Floppy: {redact_secrets(e)}")
    if r.status_code in (401, 403):
        raise ListSourceError("Floppy rejected the app token (it needs the lists:read scope)")
    if r.status_code == 404:
        raise ListSourceError("Floppy has no such list")
    if 300 <= r.status_code < 400:
        raise ListSourceError("Floppy answered with a redirect; use the address it redirects to")
    if not 200 <= r.status_code < 300:
        raise ListSourceError(f"Floppy returned HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise ListSourceError("Floppy didn't answer with JSON (check the server address)")


def _pages(path: str, base: Optional[str] = None, token: Optional[str] = None, limit: int = 200):
    data = _get(path, {"limit": limit, "offset": 0}, base, token)
    for _ in range(500):
        results = data.get("results") if isinstance(data, dict) else data
        for row in results or []:
            if isinstance(row, dict):
                yield row
        nxt = ((data.get("pagination") or {}).get("next")) if isinstance(data, dict) else None
        if not nxt:
            return
        if not nxt.startswith("http"):
            nxt = f"{_base(base)}{nxt if nxt.startswith('/') else '/' + nxt}"
        data = _get(nxt, None, base, token)


def fetch_list(key: str) -> Dict[str, Any]:
    list_id = key[len(KEY_PREFIX):]
    title = None
    try:
        meta = _get(f"/api/v1/lists/{list_id}/")
        if isinstance(meta, dict):
            title = meta.get("name")
    except ListSourceError:
        pass
    movies: List[int] = []
    shows: List[int] = []
    for row in _pages(f"/api/v1/lists/{list_id}/items/"):
        item = row.get("item") if isinstance(row.get("item"), dict) else row
        kind = str(item.get("media_type") or "").lower()
        if kind not in ("movie", "tv", "anime", "show"):
            continue  # seasons, episodes, games, books...
        ids = item.get("ids") or {}
        tid = ids.get("tmdb") if isinstance(ids, dict) else None
        if tid is None and str(item.get("source") or "").lower() == "tmdb":
            tid = item.get("media_id")
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            continue
        (movies if kind == "movie" else shows).append(tid)
    return {"title": title or f"Floppy list {list_id}", "movie_ids": movies, "show_ids": shows}


def can_list_own() -> bool:
    return bool(_base() and _token())


def my_lists() -> List[Dict[str, Any]]:
    out = []
    for lst in _pages("/api/v1/lists/", limit=100):
        if lst.get("id") is None:
            continue
        out.append({"key": f"{KEY_PREFIX}{lst['id']}", "title": lst.get("name") or f"List {lst['id']}",
                    "items": lst.get("items_count")})
    return out


def status() -> Dict[str, Any]:
    configured = bool(_base() and _token())
    return {"configured": configured, "connected": configured, "username": None}


def test(payload: Dict[str, Any]) -> Dict[str, Any]:
    saved_base = _base()
    base = str(payload.get("url") or "").strip().rstrip("/") or saved_base
    raw_token = str(payload.get("token") or "")
    # The masked placeholder means "the saved token", which may only be sent to
    # the saved server: otherwise anyone could point the test at their own host.
    # A blank token falls back to the saved one too, so treat both the same.
    uses_saved = not raw_token or raw_token == SECRET_MASK
    if uses_saved and urlparse(base).netloc.lower() != urlparse(saved_base).netloc.lower():
        return {"status": "error", "error": "Enter the token again when changing the server address"}
    token = _token() if uses_saved else raw_token
    if not base or not token:
        return {"status": "error", "error": "Server address and app token required"}
    if not base.lower().startswith(("http://", "https://")):
        return {"status": "error", "error": "The address must start with http:// or https://"}
    try:
        data = _get("/api/v1/lists/", {"limit": 1}, base, token)
    except ListSourceError as e:
        return {"status": "error", "error": str(e)}
    total = ((data.get("pagination") or {}).get("total")) if isinstance(data, dict) else None
    msg = "Connected" + (f" ({total} list{'s' if total != 1 else ''})" if total is not None else "")
    return {"status": "ok", "message": msg}
