# backend/mdblist_client.py
"""MDBList client: ratings and list membership for overlays.

Endpoints (the same ones Kometa uses, modules/mdblist.py):
  GET  https://api.mdblist.com/user?apikey=...                  key check + daily limits
  GET  https://api.mdblist.com/{tmdb|imdb|tvdb}/{movie|show}/{id}/?apikey=...
       -> {"score", "score_average", "ratings": [{"source", "value", ...}], ...}
  POST https://api.mdblist.com/{provider}/{movie|show}/?apikey=...  {"ids": [...]}  (<=100, batch)
  GET  https://api.mdblist.com/lists/{user}/{slug}/items/?apikey=...&limit=1000&offset=N&unified=true
       -> {"movies": [...], "shows": [...]} or a list; X-Has-More header pages
  GET  https://api.mdblist.com/lists/{user}/{slug}                 list title / item count

Everything is cached in the DB (item_ratings, list_cache) for
settings.mdblist.cacheDays, and requests are spaced out (MDBList's free tier
is a daily quota, so a render must never refetch what it already knows).
A missing key or any API error returns "no data": an overlay that needs a
rating or a list simply stays hidden, the render never fails.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

import requests

from .config import logger, settings
from .config import SECRET_MASK, redact_secrets

API_URL = "https://api.mdblist.com/"
LIST_URL_PREFIX = "https://mdblist.com/lists/"

# Overlay rating fields filled from MDBList. Raw values keep MDBList's own scale
# (Kometa's mdb_*_rating names); audience_rating/critic_rating are on 0-10.
RATING_SOURCES = (
    "imdb", "tmdb", "trakt", "tomatoes", "tomatoesaudience", "metacritic",
    "metacriticuser", "letterboxd", "myanimelist",
)
# Maximum of each source's value, used to bring it to 0-10.
_SOURCE_MAX = {
    "imdb": 10, "tmdb": 100, "trakt": 100, "tomatoes": 100, "tomatoesaudience": 100,
    "metacritic": 100, "metacriticuser": 10, "letterboxd": 5, "myanimelist": 10,
    "score": 100, "average": 100,
}
RATING_FIELDS = (
    ["audience_rating", "critic_rating", "mdb_rating", "mdb_average_rating"]
    + [f"mdb_{s}_rating" for s in RATING_SOURCES]
)

_lock = threading.Lock()
_last_request = 0.0
_MIN_INTERVAL = 1.0  # seconds between requests (free tier friendly)
_limit_hit_until = 0.0  # back off after a 429 / daily-limit response


class MDBListError(Exception):
    pass


class MDBListNotFound(MDBListError):
    """MDBList has no entry for this id (cached as "no ratings")."""


def _mdblist_settings() -> Dict[str, Any]:
    try:
        from . import database as db
        data = db.get_ui_settings() or {}
        return data.get("mdblist") or {}
    except Exception:
        return {}


def _cache_seconds() -> float:
    try:
        days = float(_mdblist_settings().get("cacheDays") or 7)
    except (TypeError, ValueError):
        days = 7
    return max(days, 0.04) * 86400


def has_key() -> bool:
    return bool(getattr(settings, "MDBLIST_API_KEY", ""))


def _request(path_or_url: str, params: Optional[Dict[str, Any]] = None, json_data: Any = None,
             api_key: Optional[str] = None) -> Tuple[Any, Dict[str, str]]:
    """One API call, spaced out and with the key added. Raises MDBListError."""
    global _last_request, _limit_hit_until
    key = api_key or getattr(settings, "MDBLIST_API_KEY", "")
    if not key:
        raise MDBListError("No MDBList API key")
    if time.time() < _limit_hit_until:
        raise MDBListError("MDBList rate limit reached; waiting before retrying")
    url = path_or_url if path_or_url.startswith("http") else API_URL + path_or_url
    query = {"apikey": key, **(params or {})}
    with _lock:
        wait = _MIN_INTERVAL - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            if json_data is not None:
                sep = "&" if "?" in url else "?"
                r = requests.post(f"{url}{sep}{urlencode(query)}", json=json_data, timeout=20)
            else:
                r = requests.get(url, params=query, timeout=20)
        except requests.RequestException as e:
            raise MDBListError(f"MDBList request failed: {redact_secrets(e)}")
        finally:
            _last_request = time.time()
    if r.status_code == 429:
        _limit_hit_until = time.time() + (3600 if "daily" in r.text.lower() else 60)
        raise MDBListError("MDBList API limit reached")
    if r.status_code in (401, 403):
        raise MDBListError("MDBList rejected the API key")
    if r.status_code == 404:
        raise MDBListNotFound("MDBList has no entry for this item")
    if not 200 <= r.status_code < 300:
        raise MDBListError(f"MDBList returned HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise MDBListError("MDBList returned invalid JSON")
    if isinstance(data, dict) and data.get("response") is False:
        err = str(data.get("error") or "unknown error")
        if "limit" in err.lower():
            _limit_hit_until = time.time() + 3600
        if "not found" in err.lower():
            raise MDBListNotFound(err)
        raise MDBListError(f"MDBList error: {err}")
    return data, dict(r.headers)


# --------------------------------------------------------------------------
# Key test
# --------------------------------------------------------------------------

def test_key(api_key: str) -> Dict[str, Any]:
    if api_key == SECRET_MASK:
        api_key = getattr(settings, "MDBLIST_API_KEY", "")
    if not api_key:
        return {"status": "error", "error": "API key required"}
    try:
        data, _ = _request("user", api_key=api_key)
    except MDBListError as e:
        return {"status": "error", "error": redact_secrets(e)}
    data = data if isinstance(data, dict) else {}
    limit = data.get("api_requests")
    used = data.get("api_requests_count")
    msg = "API key valid"
    if limit is not None:
        msg += f" ({used or 0}/{limit} requests used today)"
    return {
        "status": "ok",
        "message": msg,
        "supporter": bool(data.get("is_supporter")),
        "api_requests": limit,
        "api_requests_count": used,
    }


# --------------------------------------------------------------------------
# Ratings
# --------------------------------------------------------------------------

def _num(value: Any) -> Optional[float]:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None  # MDBList uses 0/null for "no rating"


def normalize(data: Dict[str, Any], batch: bool = False) -> Dict[str, Any]:
    """MDBList item -> {"raw": {source: value}, ...} with the overlay fields."""
    raw: Dict[str, float] = {}
    for rating in data.get("ratings") or []:
        if not isinstance(rating, dict):
            continue
        source = str(rating.get("source") or "").lower()
        if source == "popcorn":
            source = "tomatoesaudience"
        value = _num(rating.get("value"))
        if source not in RATING_SOURCES or value is None:
            continue
        if source == "letterboxd" and batch and value > 5:
            value = value / 2  # batch responses give letterboxd on 0-10 (Kometa does the same)
        raw[source] = value
    for key, field in (("score", "score"), ("average", "score_average")):
        value = _num(data.get(field))
        if value is not None:
            raw[key] = value
    return {
        "raw": raw,
        "imdb_id": data.get("imdbid") or data.get("imdb_id") or (data.get("ids") or {}).get("imdb"),
        "certification": data.get("certification"),
    }


def _to_ten(source: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    maximum = _SOURCE_MAX.get(source, 10)
    return round(value * 10.0 / maximum, 1) if maximum != 10 else round(value, 1)


def rating_fields(normalized: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay context fields from a normalized MDBList item."""
    raw = (normalized or {}).get("raw") or {}
    out: Dict[str, Any] = {}
    for source in RATING_SOURCES:
        if source in raw:
            out[f"mdb_{source}_rating"] = raw[source]
    if "score" in raw:
        out["mdb_rating"] = raw["score"]
    if "average" in raw:
        out["mdb_average_rating"] = raw["average"]
    cfg = _mdblist_settings()
    for field, setting, default in (
        ("audience_rating", "audienceRatingSource", "imdb"),
        ("critic_rating", "criticRatingSource", "tomatoes"),
    ):
        source = str(cfg.get(setting) or default).lower()
        value = _to_ten(source, raw.get(source))
        if value is not None:
            out[field] = value
    return out


def _item_key(media_type: str, provider: str, item_id: Any) -> str:
    return f"{media_type}:{provider}:{item_id}"


def get_ratings(media_type: str, tmdb_id: Any = None, tvdb_id: Any = None, imdb_id: Any = None,
                fetch: bool = True) -> Optional[Dict[str, Any]]:
    """Normalized MDBList data for one item, from the cache when fresh.
    media_type is "movie" or "show". Returns None when unknown/unavailable."""
    from . import database as db

    candidates: List[Tuple[str, Any]] = []
    if tmdb_id:
        candidates.append(("tmdb", tmdb_id))
    if imdb_id:
        candidates.append(("imdb", imdb_id))
    if tvdb_id and media_type == "show":
        candidates.append(("tvdb", tvdb_id))
    if not candidates:
        return None

    max_age = _cache_seconds()
    now = time.time()
    stale: Optional[Dict[str, Any]] = None
    for provider, item_id in candidates:
        cached = db.get_item_ratings(_item_key(media_type, provider, item_id))
        if cached:
            data, fetched_at = cached
            if now - fetched_at < max_age:
                return data or None
            stale = stale or data

    if not fetch or not has_key():
        return stale or None
    provider, item_id = candidates[0]
    try:
        payload, _ = _request(f"{provider}/{media_type}/{item_id}/")
    except MDBListNotFound:
        db.save_item_ratings(_item_key(media_type, provider, item_id), {}, time.time())
        return None
    except MDBListError as e:
        logger.info("[MDBLIST] %s %s %s: %s", provider, media_type, item_id, e)
        return stale or None
    data = normalize(payload) if isinstance(payload, dict) else {}
    db.save_item_ratings(_item_key(media_type, provider, item_id), data, time.time())
    logger.info("[MDBLIST] Ratings for %s %s %s: %s", media_type, provider, item_id, data.get("raw"))
    return data or None


def prefetch_ratings(media_type: str, tmdb_ids: Iterable[Any]) -> int:
    """Fetch ratings for many items with batch requests (100 per call), only for
    ids not already cached. Returns how many were fetched."""
    from . import database as db

    if not has_key():
        return 0
    max_age = _cache_seconds()
    now = time.time()
    pending = []
    for tid in dict.fromkeys(t for t in tmdb_ids if t):
        cached = db.get_item_ratings(_item_key(media_type, "tmdb", tid))
        if not cached or now - cached[1] >= max_age:
            pending.append(tid)
    fetched = 0
    for start in range(0, len(pending), 100):
        batch = pending[start:start + 100]
        try:
            payload, _ = _request(f"tmdb/{media_type}/", json_data={"ids": [int(t) for t in batch]})
        except (MDBListError, ValueError) as e:
            logger.info("[MDBLIST] Batch ratings stopped: %s", e)
            break
        seen = set()
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            tid = item.get("tmdbid") or item.get("tmdb_id") or (item.get("ids") or {}).get("tmdb") or item.get("id")
            if tid is None:
                continue
            seen.add(str(tid))
            db.save_item_ratings(_item_key(media_type, "tmdb", tid), normalize(item, batch=True), time.time())
            fetched += 1
        for tid in batch:  # remember misses so they aren't requested again until the cache expires
            if str(tid) not in seen:
                db.save_item_ratings(_item_key(media_type, "tmdb", tid), {}, time.time())
    return fetched


# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------

def normalize_list_url(url: str) -> Optional[str]:
    """"https://mdblist.com/lists/user/slug/" -> "https://mdblist.com/lists/user/slug".
    Also accepts "user/slug". None if it isn't an MDBList list."""
    u = str(url or "").strip().split("?")[0].rstrip("/")
    if not u:
        return None
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    if u.startswith("https://www.mdblist.com/"):
        u = "https://mdblist.com/" + u[len("https://www.mdblist.com/"):]
    if not u.startswith("http"):
        u = LIST_URL_PREFIX + u.lstrip("/")
    if not u.startswith(LIST_URL_PREFIX) or len(u) <= len(LIST_URL_PREFIX):
        return None
    return u


def _fetch_list(url: str) -> Optional[Dict[str, Any]]:
    path = url[len(LIST_URL_PREFIX):]
    title = None
    try:
        meta, _ = _request(f"lists/{path}")
        if isinstance(meta, list) and meta:
            meta = meta[0]
        if isinstance(meta, dict):
            title = meta.get("name") or meta.get("title")
    except MDBListError:
        pass
    movies: List[int] = []
    shows: List[int] = []
    offset = 0
    for _page in range(50):  # 50k items max
        data, headers = _request(f"lists/{path}/items/", params={"limit": 1000, "offset": offset, "unified": "true"})
        if isinstance(data, dict):
            items = list(data.get("movies") or []) + list(data.get("shows") or []) + list(data.get("items") or [])
        elif isinstance(data, list):
            items = data
        else:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            tid = item.get("id") or item.get("tmdbid") or item.get("tmdb_id") or (item.get("ids") or {}).get("tmdb")
            try:
                tid = int(tid)
            except (TypeError, ValueError):
                continue
            kind = str(item.get("mediatype") or item.get("type") or "movie").lower()
            (shows if kind in ("show", "tv", "series") else movies).append(tid)
        offset += len(items)
        more = str({k.lower(): v for k, v in headers.items()}.get("x-has-more", "false")).lower() == "true"
        if not items or not more:
            break
    return {"title": title, "movie_ids": sorted(set(movies)), "show_ids": sorted(set(shows))}


def get_list(url: str, fetch: bool = True, force: bool = False) -> Optional[Dict[str, Any]]:
    """Cached list contents {"title", "movie_ids", "show_ids", "fetched_at"}."""
    from . import database as db

    norm = normalize_list_url(url)
    if not norm:
        return None
    cached = db.get_list_cache(norm)
    if cached and not force and time.time() - cached["fetched_at"] < _cache_seconds():
        return cached
    if not fetch or not has_key():
        return cached
    try:
        data = _fetch_list(norm)
    except MDBListError as e:
        logger.info("[MDBLIST] List %s: %s", norm, e)
        return cached
    if data is None:
        return cached
    now = time.time()
    db.save_list_cache(norm, data["title"], data["movie_ids"], data["show_ids"], now)
    logger.info("[MDBLIST] List %s: %d movies, %d shows", norm, len(data["movie_ids"]), len(data["show_ids"]))
    return {**data, "fetched_at": now}


def lists_containing(urls: Iterable[str], media_type: str, tmdb_id: Any) -> List[str]:
    """Which of these MDBList list URLs contain the item (normalized URLs)."""
    try:
        tid = int(tmdb_id)
    except (TypeError, ValueError):
        return []
    out = []
    for url in urls:
        data = get_list(url)
        if not data:
            continue
        ids = data["show_ids"] if media_type == "show" else data["movie_ids"]
        if tid in ids:
            out.append(normalize_list_url(url))
    return out
