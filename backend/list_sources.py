# backend/list_sources.py
"""List membership for overlay "On a list" rules, across every list service.

A list is identified by one canonical key string, which is what overlay
conditions store and what list_cache is keyed by:

  MDBList   https://mdblist.com/lists/<user>/<slug>     (backend/mdblist_client.py)
  WeTrakr   https://wetrakr.com/lists/<id>              custom list (public, or yours when signed in)
            wetrakr:<status>                            your tracking list (planning = watchlist)
  SIMKL     simkl:<status>                              your watchlist bucket (plantowatch, ...)
            https://simkl.com/lists/<id>                custom list (SIMKL PRO/VIP only)
  Floppy    floppy:list:<id>                            a list on your Floppy server

The service is read from the key itself, so one condition field ("list") works
for all of them. Contents (TMDb ids of the movies and shows on the list) are
cached in list_cache for the "re-check lists" hours (Overlay Manager >
Scheduler, get_refresh_settings()). A stale list is served from the
cache while a background thread refreshes it; only a list never fetched before
is fetched during a render. Any error means "not on the list": a render never
fails over a list.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Iterable, List, Optional

from .config import logger


class ListSourceError(Exception):
    pass


def _providers():
    from . import floppy_client, simkl_client, wetrakr_client
    return {"wetrakr": wetrakr_client, "simkl": simkl_client, "floppy": floppy_client}


PROVIDER_LABELS = {"mdblist": "MDBList", "wetrakr": "WeTrakr", "simkl": "SIMKL", "floppy": "Floppy"}


def ui_settings(section: str) -> Dict[str, Any]:
    try:
        from . import database as db
        return (db.get_ui_settings() or {}).get(section) or {}
    except Exception:
        return {}


# --------------------------------------------------------------------------
# How often ratings and lists are re-fetched (Overlay Manager > Scheduler).
# Kept in its own one-row table, not the settings table, which every Settings
# save rebuilds from the page's copy. Ratings default to the old
# mdblist.cacheDays value the first time it's read.
# --------------------------------------------------------------------------

_DEFAULT_LISTS_HOURS = 24.0
_refresh_cache: Dict[str, Any] = {"at": 0.0, "data": None}


def _refresh_conn():
    import sqlite3
    from . import database as db
    conn = sqlite3.connect(str(db.DB_PATH), timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS overlay_data_refresh ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), ratings_days REAL NOT NULL, lists_hours REAL NOT NULL)"
    )
    return conn


def get_refresh_settings() -> Dict[str, float]:
    """{"ratingsDays", "listsHours"}, cached for 30 seconds."""
    if _refresh_cache["data"] is not None and time.time() - _refresh_cache["at"] < 30:
        return _refresh_cache["data"]
    try:
        conn = _refresh_conn()
        try:
            row = conn.execute("SELECT ratings_days, lists_hours FROM overlay_data_refresh WHERE id = 1").fetchone()
            if not row:
                try:
                    old = float(ui_settings("mdblist").get("cacheDays") or 7)
                except (TypeError, ValueError):
                    old = 7.0
                row = (old, _DEFAULT_LISTS_HOURS)
                conn.execute("INSERT INTO overlay_data_refresh (id, ratings_days, lists_hours) VALUES (1, ?, ?)", row)
                conn.commit()
        finally:
            conn.close()
        data = {"ratingsDays": float(row[0]), "listsHours": float(row[1])}
    except Exception:
        data = {"ratingsDays": 7.0, "listsHours": _DEFAULT_LISTS_HOURS}
    _refresh_cache.update(at=time.time(), data=data)
    return data


def save_refresh_settings(ratings_days: float, lists_hours: float) -> Dict[str, float]:
    ratings_days = min(max(float(ratings_days), 1.0), 90.0)
    lists_hours = min(max(float(lists_hours), 1.0), 720.0)
    conn = _refresh_conn()
    try:
        conn.execute(
            "INSERT INTO overlay_data_refresh (id, ratings_days, lists_hours) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET ratings_days = excluded.ratings_days, lists_hours = excluded.lists_hours",
            (ratings_days, lists_hours),
        )
        conn.commit()
    finally:
        conn.close()
    _refresh_cache.update(at=0.0, data=None)
    return get_refresh_settings()


def ratings_max_age() -> float:
    return get_refresh_settings()["ratingsDays"] * 86400


def lists_max_age() -> float:
    return get_refresh_settings()["listsHours"] * 3600


def cache_seconds() -> float:
    """How long a list's contents are reused (all services)."""
    return lists_max_age()


def app_version() -> str:
    try:
        from .api.version_info import get_current_version
        return str(get_current_version() or "1.8").lstrip("v")
    except Exception:
        return "1.8"


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------

def normalize_list_key(value: Any) -> Optional[str]:
    """Canonical key for a pasted link or a stored key, or None if no service
    recognizes it. MDBList is tried last because it also accepts "user/slug"."""
    raw = str(value or "").strip()
    if not raw:
        return None
    for module in _providers().values():
        key = module.normalize(raw)
        if key:
            return key
    if raw.lower().startswith(("wetrakr:", "simkl:", "floppy:")):
        return None  # a malformed key for one of these, never an MDBList "user/slug"
    from .mdblist_client import normalize_list_url
    return normalize_list_url(raw)


def provider_of(key: str) -> Optional[str]:
    k = str(key or "")
    for name, module in _providers().items():
        if module.owns(k):
            return name
    if k.startswith("https://mdblist.com/lists/"):
        return "mdblist"
    return None


def missing_setup(key: str) -> Optional[str]:
    """Why this list can't be read right now (no key, not signed in), or None."""
    provider = provider_of(key)
    if provider == "mdblist":
        from .mdblist_client import has_key
        return None if has_key() else "no MDBList API key in Settings > General"
    module = _providers().get(provider or "")
    if not module:
        return "not a list link Simposter recognizes"
    return module.missing_setup(key)


# --------------------------------------------------------------------------
# Contents
# --------------------------------------------------------------------------

_refreshing: set = set()
_refresh_lock = threading.Lock()


def _fetch_and_store(key: str) -> Optional[Dict[str, Any]]:
    from . import database as db
    module = _providers()[provider_of(key)]
    data = module.fetch_list(key)
    now = time.time()
    movies = sorted({int(i) for i in data.get("movie_ids") or []})
    shows = sorted({int(i) for i in data.get("show_ids") or []})
    db.save_list_cache(key, data.get("title"), movies, shows, now)
    logger.info("[LISTS] %s: %d movies, %d shows", key, len(movies), len(shows))
    return {"title": data.get("title"), "movie_ids": movies, "show_ids": shows, "fetched_at": now}


def _refresh_in_background(key: str) -> None:
    with _refresh_lock:
        if key in _refreshing:
            return
        _refreshing.add(key)

    def run():
        try:
            _fetch_and_store(key)
        except Exception as e:
            from .config import redact_secrets
            logger.info("[LISTS] Refreshing %s failed, keeping the cached copy: %s", key, redact_secrets(e))
        finally:
            with _refresh_lock:
                _refreshing.discard(key)

    threading.Thread(target=run, name=f"list-refresh-{key[:40]}", daemon=True).start()


def get_list(value: Any, fetch: bool = True, force: bool = False, wait: bool = False) -> Optional[Dict[str, Any]]:
    """Cached contents {"title", "movie_ids", "show_ids", "fetched_at"} of any list.
    An out-of-date list is returned as is and re-fetched in the background,
    unless wait=True (Overlay Refresh), which fetches it before returning."""
    key = normalize_list_key(value)
    if not key:
        return None
    provider = provider_of(key)
    if provider == "mdblist":
        from .mdblist_client import get_list as mdb_get_list
        return mdb_get_list(key, fetch=fetch, force=force)
    from . import database as db
    cached = db.get_list_cache(key)
    fresh = cached and time.time() - cached["fetched_at"] < cache_seconds()
    if (fresh and not force) or not fetch or missing_setup(key):
        return cached
    if cached and not force and not wait:
        _refresh_in_background(key)
        return cached
    try:
        return _fetch_and_store(key)
    except Exception as e:
        from .config import redact_secrets
        logger.info("[LISTS] %s: %s", key, redact_secrets(e))
        if force:
            raise ListSourceError(redact_secrets(e))
        return cached


def lists_containing(values: Iterable[Any], media_type: str, tmdb_id: Any) -> List[str]:
    """Which of these lists contain the item (canonical keys). media_type is
    "movie" or "show"."""
    try:
        tid = int(tmdb_id)
    except (TypeError, ValueError):
        return []
    out = []
    for value in values:
        key = normalize_list_key(value)
        if not key:
            continue
        data = get_list(key)
        if not data:
            continue
        ids = data["show_ids"] if media_type == "show" else data["movie_ids"]
        if tid in ids:
            out.append(key)
    return out


def refresh_due(values: Iterable[Any]) -> int:
    """Fetch every one of these lists that is out of date, now (not in the
    background). Returns how many were fetched. Used before an Overlay Refresh
    run, so the run already sees lists past their refresh time."""
    from . import database as db
    fetched = 0
    seen = set()
    for value in values:
        key = normalize_list_key(value)
        if not key or key in seen or missing_setup(key):
            continue
        seen.add(key)
        cached = db.get_list_cache(key)
        if cached and time.time() - cached["fetched_at"] < cache_seconds():
            continue
        if get_list(key, wait=True) is not None:
            fetched += 1
    return fetched


def setup_notes(values: Iterable[Any]) -> List[str]:
    """Plain reasons some of these lists can't be read (for the render log)."""
    notes = []
    for value in values:
        key = normalize_list_key(value)
        reason = missing_setup(key) if key else "not a list link Simposter recognizes"
        if reason and reason not in notes:
            notes.append(reason)
    return notes


# --------------------------------------------------------------------------
# Your lists (for the overlay editor's list picker)
# --------------------------------------------------------------------------

_my_lists_cache: Dict[str, Any] = {"at": 0.0, "data": None}


def my_lists(force: bool = False) -> Dict[str, Any]:
    """{"lists": [{"key", "title", "provider", "items"}], "errors": {provider: msg}}
    from every connected service. Kept 10 minutes in memory."""
    if not force and _my_lists_cache["data"] is not None and time.time() - _my_lists_cache["at"] < 600:
        return _my_lists_cache["data"]
    from .config import redact_secrets
    lists: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    for name, module in _providers().items():
        if not module.can_list_own():
            continue
        try:
            for item in module.my_lists():
                lists.append({**item, "provider": name})
        except Exception as e:
            errors[name] = redact_secrets(e)
    data = {"lists": lists, "errors": errors}
    _my_lists_cache.update(at=time.time(), data=data)
    return data


def forget_my_lists() -> None:
    _my_lists_cache.update(at=0.0, data=None)


def status() -> Dict[str, Any]:
    out = {}
    for name, module in _providers().items():
        out[name] = module.status()
    return out


# --------------------------------------------------------------------------
# Sign-in (device code) flows shared by WeTrakr and SIMKL
# --------------------------------------------------------------------------

_pending: Dict[str, Dict[str, Any]] = {}


def start_connect(provider: str) -> Dict[str, Any]:
    module = _providers().get(provider)
    if not module or not hasattr(module, "start_device"):
        raise ListSourceError("This service doesn't use a sign-in")
    info = module.start_device()
    _pending[provider] = {**info, "expires_at": time.time() + float(info.get("expires_in") or 600)}
    return {
        "user_code": info.get("user_code"),
        "verification_url": info.get("verification_url"),
        "verification_url_complete": info.get("verification_url_complete"),
        "interval": info.get("interval") or 5,
        "expires_in": info.get("expires_in") or 600,
    }


def poll_connect(provider: str) -> Dict[str, Any]:
    """{"status": "pending" | "connected" | "expired" | "error", ...}. One token
    request per call; the page calls this at the interval the service gave."""
    module = _providers().get(provider)
    pending = _pending.get(provider)
    if not module or not pending:
        return {"status": "error", "error": "No sign-in in progress. Start again."}
    if time.time() > pending["expires_at"]:
        _pending.pop(provider, None)
        return {"status": "expired", "error": "The code expired. Start again."}
    result = module.poll_device(pending["device_code"])
    if result.get("status") == "connected":
        _pending.pop(provider, None)
        forget_my_lists()
    elif result.get("status") in ("error", "expired"):
        _pending.pop(provider, None)
    return result


def disconnect(provider: str) -> None:
    from . import database as db
    _pending.pop(provider, None)
    db.delete_list_source_auth(provider)
    forget_my_lists()


def save_tokens(provider: str, token_response: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Store an OAuth token response (access/refresh/expiry) plus extra fields."""
    from . import database as db
    current = db.get_list_source_auth(provider)
    data = {
        **current,
        "access_token": token_response.get("access_token"),
        "refresh_token": token_response.get("refresh_token") or token_response.get("new_refresh_token") or current.get("refresh_token"),
        "expires_at": time.time() + float(token_response.get("expires_in") or 604800),
        **(extra or {}),
    }
    db.save_list_source_auth(provider, data)
    return data
