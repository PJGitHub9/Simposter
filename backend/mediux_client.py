# backend/mediux_client.py
"""MediUX (mediux.io community poster sets) client.

One GraphQL request per title, cached 24 h in `mediux_sets`. The key is only
sent to images.mediux.io, never follows a redirect, and is never logged.
No key = no request.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from . import config
from . import database as db

logger = logging.getLogger("simposter")

BASE = "https://images.mediux.io"
GRAPHQL_URL = BASE + "/graphql"
ME_URL = BASE + "/users/me"
CACHE_SECONDS = 24 * 3600
_RETRY_WAITS = (2, 5)
_RETRY_AFTER_CAP = 15
_TIMEOUT = 20

_FIELDS = "id modified_on language{iso_639_1}"
_SET_FIELDS = "id set_title user_created{username} date_updated popularity"

_MOVIE_QUERY = (
    "query($tmdb_id: ID!) { movies_by_id(id: $tmdb_id) { movie_sets { "
    + _SET_FIELDS + " movie_poster{" + _FIELDS + "} movie_backdrop{" + _FIELDS + "} } } }"
)
_SHOW_QUERY = (
    "query($tmdb_id: ID!) { shows_by_id(id: $tmdb_id) { show_sets { "
    + _SET_FIELDS + " show_poster{" + _FIELDS + "} show_backdrop{" + _FIELDS + "} "
    "season_posters{season{season_number} " + _FIELDS + "} } } }"
)

_locks: Dict[Tuple[str, int], threading.Lock] = {}
_locks_guard = threading.Lock()
_session = requests.Session()


def get_mediux_key() -> str:
    try:
        s = db.get_ui_settings() or {}
        return str((s.get("mediux") or {}).get("apiKey") or "").strip()
    except Exception:
        return ""


def _headers(key: str) -> Dict[str, str]:
    return {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "User-Agent": config.api_user_agent(),
    }


def _stamp(modified_on: Any) -> str:
    return "".join(c for c in str(modified_on or "")[:19] if c.isdigit())


def is_mediux_image_url(url: str) -> bool:
    """True only for https URLs whose host is exactly images.mediux.io."""
    from urllib.parse import urlparse
    try:
        u = urlparse(url)
        return u.scheme == "https" and (u.hostname or "").lower() == "images.mediux.io"
    except ValueError:
        return False


def auth_headers_for(url: str) -> Dict[str, str]:
    """Bearer header for images.mediux.io hops only (use as safe_get headers_for)."""
    if not is_mediux_image_url(url):
        return {}
    key = get_mediux_key()
    return {"Authorization": "Bearer " + key} if key else {}


def asset_url(asset_id: str, modified_on: str, size: Optional[str] = None) -> str:
    url = "%s/assets/%s?v=%s" % (BASE, asset_id, _stamp(modified_on))
    return url + "&key=" + size if size else url


def _entry(raw: Any, set_id: str, creator: str) -> Optional[Dict[str, Any]]:
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    url = asset_url(raw["id"], raw.get("modified_on"))
    lang = (raw.get("language") or {}).get("iso_639_1") if isinstance(raw.get("language"), dict) else None
    return {"url": url, "thumb": url + "&key=thumb", "source": "mediux", "has_text": True,
            "language": lang or None, "mediux_set_id": set_id, "mediux_creator": creator}


def _normalize(raw_sets: List[Dict[str, Any]], poster_key: str, backdrop_key: str) -> List[Dict[str, Any]]:
    out = []
    for s in raw_sets or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "")
        creator = str((s.get("user_created") or {}).get("username") or "")
        poster = _entry(s.get(poster_key), sid, creator)
        if not poster:
            continue
        seasons = {}
        for sp in s.get("season_posters") or []:
            try:
                n = int((sp.get("season") or {}).get("season_number"))
            except (TypeError, ValueError, AttributeError):
                continue
            e = _entry(sp, sid, creator)
            if e:
                seasons[n] = e
        try:
            pop = float(s.get("popularity") or 0)
        except (TypeError, ValueError):
            pop = 0.0
        out.append({"set_id": sid, "title": str(s.get("set_title") or ""), "creator": creator,
                    "popularity": pop, "date_updated": str(s.get("date_updated") or ""),
                    "poster": poster, "backdrop": _entry(s.get(backdrop_key), sid, creator),
                    "season_posters": seasons})
    out.sort(key=lambda x: x["date_updated"], reverse=True)
    out.sort(key=lambda x: x["popularity"], reverse=True)
    return out




def _read_cache(media_type: str, tmdb_id: int) -> Optional[List[Dict[str, Any]]]:
    try:
        with db.get_db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS mediux_sets (media_type TEXT, tmdb_id INTEGER, "
                         "sets_json TEXT, fetched_at REAL, PRIMARY KEY(media_type, tmdb_id))")
            row = conn.execute("SELECT sets_json, fetched_at FROM mediux_sets WHERE media_type=? AND tmdb_id=?",
                               (media_type, tmdb_id)).fetchone()
        if row and time.time() - float(row[1]) < CACHE_SECONDS:
            sets = json.loads(row[0])
            # JSON turns int season keys into strings
            for s in sets:
                s["season_posters"] = {int(k): v for k, v in (s.get("season_posters") or {}).items()}
            return sets
    except Exception as e:
        logger.debug("[MEDIUX] cache read failed: %s", config.redact_secrets(str(e)))
    return None


def _write_cache(media_type: str, tmdb_id: int, sets: List[Dict[str, Any]]) -> None:
    try:
        with db.get_db() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS mediux_sets (media_type TEXT, tmdb_id INTEGER, "
                         "sets_json TEXT, fetched_at REAL, PRIMARY KEY(media_type, tmdb_id))")
            conn.execute("INSERT OR REPLACE INTO mediux_sets VALUES (?,?,?,?)",
                         (media_type, tmdb_id, json.dumps(sets), time.time()))
    except Exception as e:
        logger.debug("[MEDIUX] cache write failed: %s", config.redact_secrets(str(e)))


class _Failed(Exception):
    pass


def _post(key: str, query: str, tmdb_id: int) -> Dict[str, Any]:
    """POST with 429 retries. Raises _Failed on any error."""
    waits = list(_RETRY_WAITS)
    while True:
        try:
            r = _session.post(GRAPHQL_URL, headers=_headers(key), timeout=_TIMEOUT, allow_redirects=False,
                              json={"query": query, "variables": {"tmdb_id": str(tmdb_id)}})
        except requests.RequestException as e:
            raise _Failed(config.redact_secrets(str(e)))
        if r.status_code == 429:
            if not waits:
                raise _Failed("MediUX rate limit")
            wait = waits.pop(0)
            try:
                ra = float(r.headers.get("Retry-After"))
                wait = min(ra, _RETRY_AFTER_CAP)
                wait = int(wait) if wait == int(wait) else wait
            except (TypeError, ValueError):
                pass
            time.sleep(wait)
            continue
        if r.status_code in (401, 403):
            raise _Failed("MediUX rejected the key")
        if r.status_code >= 300:
            raise _Failed("MediUX returned HTTP %d" % r.status_code)
        try:
            body = r.json()
        except ValueError:
            raise _Failed("MediUX returned an unreadable response")
        if not isinstance(body, dict) or (body.get("errors") and not body.get("data")):
            raise _Failed("MediUX returned an error")
        return body


def _get_sets(media_type: str, tmdb_id: int) -> List[Dict[str, Any]]:
    key = get_mediux_key()
    if not key:
        return []
    try:
        tmdb_id = int(tmdb_id)
    except (TypeError, ValueError):
        return []
    cached = _read_cache(media_type, tmdb_id)
    if cached is not None:
        return cached
    with _locks_guard:
        lock = _locks.setdefault((media_type, tmdb_id), threading.Lock())
    with lock:
        cached = _read_cache(media_type, tmdb_id)
        if cached is not None:
            return cached
        movie = media_type == "movie"
        try:
            body = _post(key, _MOVIE_QUERY if movie else _SHOW_QUERY, tmdb_id)
        except _Failed as e:
            logger.warning("[MEDIUX] %s %s: %s; skipping MediUX for this title", media_type, tmdb_id, e)
            return []
        data = body.get("data") or {}
        node = data.get("movies_by_id" if movie else "shows_by_id") or {}
        raw_sets = node.get("movie_sets" if movie else "show_sets") or []
        sets = _normalize(raw_sets, "movie_poster" if movie else "show_poster",
                          "movie_backdrop" if movie else "show_backdrop")
        _write_cache(media_type, tmdb_id, sets)
        return sets


def get_movie_sets(tmdb_id: int) -> List[Dict[str, Any]]:
    return _get_sets("movie", tmdb_id)


def get_show_sets(tmdb_id: int) -> List[Dict[str, Any]]:
    return _get_sets("show", tmdb_id)


def check_key(key: str) -> Tuple[bool, str]:
    try:
        r = _session.get(ME_URL, headers=_headers(key), timeout=_TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        return False, config.redact_secrets(str(e)) or "Could not reach MediUX"
    if r.status_code in (401, 403):
        return False, "MediUX rejected the key"
    if r.status_code >= 300:
        return False, "MediUX returned HTTP %d" % r.status_code
    name = ""
    try:
        body = r.json()
        d = body.get("data", body) if isinstance(body, dict) else {}
        if isinstance(d, dict):
            name = str(d.get("username") or d.get("first_name") or "").strip()
    except ValueError:
        pass
    return True, ("Connected as " + name) if name else "Connected"
