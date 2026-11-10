"""Poster API: settings routes (public image routes are added in later tasks)."""
import hmac
import re
import secrets
import base64
import io
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from .. import database as db
from .. import poster_api_store as store
from ..config import SECRET_MASK, load_presets, logger
from ..schemas import (PosterApiBulkRequest, PosterApiClearRequest, PosterApiPinRequest, PosterApiSettings,
                       PosterApiTarget)

router = APIRouter()


@router.get("/poster-api/settings")
def get_poster_api_settings():
    data = store.get_settings().model_dump()
    if data.get("key"):
        data["key"] = SECRET_MASK
    return data


@router.put("/poster-api/settings")
def put_poster_api_settings(body: PosterApiSettings):
    current = store.get_settings()
    from .. import poster_api
    uniform = poster_api._uniformlogo_preset_ids()
    for field in ("defaultMoviePreset", "defaultTvPreset"):
        pid = getattr(body, field)
        if pid and pid not in uniform:
            raise HTTPException(status_code=400, detail=f"Unknown uniformlogo preset '{pid}' for {field}")
    for field, media_type in (("movieGroup", "movie"), ("tvGroup", "tv")):
        gid = (getattr(body, field) or "").strip()
        if gid and not store.resolve_group(media_type, gid):
            raise HTTPException(status_code=400, detail=f"Unknown library group '{gid}' for {field}")
    if body.key == SECRET_MASK:
        body.key = current.key
    body.waitSeconds = store.clamp_wait_seconds(body.waitSeconds)
    body.retentionDays = max(1, body.retentionDays)
    # Write only the posterApi rows: db.save_ui_settings() deletes every setting first.
    for name, value in body.model_dump().items():
        text = ("true" if value else "false") if isinstance(value, bool) else str(value)
        db.set_setting(f"posterApi.{name}", text, "posterApi")
    out = store.get_settings().model_dump()
    if out.get("key"):
        out["key"] = SECRET_MASK
    return out


@router.post("/poster-api/generate-key")
def generate_poster_api_key():
    # Returned once; not stored until the settings are saved with it.
    return {"key": secrets.token_urlsafe(24)}


# ---------------------------------------------------------------------------
# Public image routes
# ---------------------------------------------------------------------------

_TYPE_MAP = {"movie": "movie", "tv": "tv", "series": "tv", "show": "tv", "tv-show": "tv"}
_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


def _sniff_media_type(path) -> str:
    """Library files hold the Plex-upload payload (usually PNG despite a .jpg name)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return "image/jpeg"
    return "image/png" if head == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _request_title(media_type: str, tmdb_id: int, season: Optional[int], served=None) -> Optional[str]:
    """Best title for the request history: the served cache row's title, else the library's."""
    try:
        if served is not None and served.source in ("rendered", "pinned") and served.path:
            with db.get_db() as conn:
                row = conn.execute("SELECT title FROM poster_api_cache WHERE file_path = ? AND title IS NOT NULL "
                                   "AND title != '' LIMIT 1", (str(served.path),)).fetchone()
            if row:
                return row["title"]
        return db.get_title_for_tmdb_id(media_type, tmdb_id)
    except Exception:
        return None


def _log_request(media_type, tmdb_id, season, preset, group_id, result, title, started) -> None:
    try:
        db.poster_api_queue_request(media_type, tmdb_id, season, preset or "", group_id or "", result, title,
                                  int((time.monotonic() - started) * 1000))
    except Exception:
        logger.debug("[POSTER API] Could not record the request", exc_info=True)


def handle_poster_request(request: Request, tmdb_id: Optional[int], type_: Optional[str],
                          season: Optional[int], preset: Optional[str],
                          group: Optional[str] = None) -> Response:
    """Shared by GET /api/poster, GET /api/poster/{type}/{id} and the root GET /poster.
    Every request that reaches a lookup (and every rejected key) goes into the
    request history shown on the Poster API page."""
    from .. import poster_api

    started = time.monotonic()
    cfg = store.get_settings()
    if not cfg.enabled:
        raise HTTPException(status_code=404, detail="Not found")

    if cfg.key:
        supplied = request.query_params.get("key") or ""
        if not hmac.compare_digest(supplied.encode("utf-8"), cfg.key.encode("utf-8")):
            logger.warning("[POSTER API] Rejected %s: missing or invalid key (key=***)", request.url.path)
            _log_request(_TYPE_MAP.get((type_ or "").strip().lower()), tmdb_id if (tmdb_id or 0) > 0 else None,
                         season, preset, "", "bad_key", None, started)
            raise HTTPException(status_code=401, detail="Invalid or missing key")

    media_type = _TYPE_MAP.get((type_ or "").strip().lower())
    if media_type is None:
        raise HTTPException(status_code=400, detail="type must be movie or tv")
    if tmdb_id is None or tmdb_id <= 0:
        raise HTTPException(status_code=400, detail="tmdb_id must be a positive integer")
    if media_type == "movie":
        season = None
    elif season is not None and season < 0:
        raise HTTPException(status_code=400, detail="season must be >= 0")
    preset = (preset or "").strip() or None
    if preset and not re.fullmatch(r"[a-zA-Z0-9_-]+", preset):
        raise HTTPException(status_code=400, detail="invalid preset")

    # group: a library group id or name (e.g. a 4K group vs a regular one); decides
    # which library copy's poster is served and whose media info feeds the badges.
    group = (group or "").strip()[:200] or None
    group_id = poster_api.resolve_request_group(media_type, group)
    if group_id is None:
        _log_request(media_type, tmdb_id, season, preset, group or "", "not_found",
                     _request_title(media_type, tmdb_id, season), started)
        raise HTTPException(status_code=404, detail="Unknown library group")
    served = poster_api.serve(media_type, tmdb_id, season, preset, group_id or None)
    if served.kind == "file" and served.path:
        result = "generated" if served.generated else (served.source or "rendered")
    else:
        result = "redirect" if served.kind == "redirect" else ("not_found" if served.kind == "not_found" else "rendered")
    _log_request(media_type, tmdb_id, season, preset, group_id, result,
                 _request_title(media_type, tmdb_id, season, served), started)
    if served.kind == "redirect" and served.url:
        return RedirectResponse(served.url, status_code=302)
    if served.kind == "file" and served.path:
        try:
            store.touch_served(store.CacheKey(media_type, tmdb_id, season, preset or "", group_id),
                               served.source or "rendered")
        except Exception:
            logger.exception("[POSTER API] touch_served failed")
        return FileResponse(str(served.path), media_type=_sniff_media_type(served.path), headers=_CACHE_HEADERS)
    if served.kind == "bytes" and served.data:
        return Response(content=served.data, media_type="image/jpeg", headers=_CACHE_HEADERS)
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/poster")
def api_poster(request: Request, tmdb_id: Optional[int] = None, type: Optional[str] = None,
               season: Optional[int] = None, preset: Optional[str] = None, group: Optional[str] = None):
    return handle_poster_request(request, tmdb_id, type, season, preset, group)


@router.get("/poster/{media_type}/{tmdb_id}")
def api_poster_path(request: Request, media_type: str, tmdb_id: int,
                    season: Optional[int] = None, preset: Optional[str] = None, group: Optional[str] = None):
    return handle_poster_request(request, tmdb_id, media_type, season, preset, group)


# ---------------------------------------------------------------------------
# Admin routes (Poster API page)
# ---------------------------------------------------------------------------

MAX_PIN_BYTES = 20 * 1024 * 1024
MAX_BULK_ITEMS = 500  # bulk regenerate/clear per request
_SOURCES = ("rendered", "pinned")


def _norm_type(type_: Optional[str]) -> str:
    media_type = _TYPE_MAP.get((type_ or "").strip().lower())
    if media_type is None:
        raise HTTPException(status_code=400, detail="type must be movie or tv")
    return media_type


def _admin_key(body, allow_preset: bool = True) -> "store.CacheKey":
    media_type = _norm_type(body.type)
    if body.tmdb_id is None or body.tmdb_id <= 0:
        raise HTTPException(status_code=400, detail="tmdb_id must be a positive integer")
    season = body.season
    if season is not None:
        if media_type != "tv":
            raise HTTPException(status_code=400, detail="season is only valid for tv")
        if season < 0:
            raise HTTPException(status_code=400, detail="season must be >= 0")
    preset = (getattr(body, "preset", None) or "").strip() if allow_preset else ""
    if preset and not re.fullmatch(r"[a-zA-Z0-9_-]+", preset):
        raise HTTPException(status_code=400, detail="invalid preset")
    group = (getattr(body, "group", None) or "").strip() if allow_preset else ""
    return store.CacheKey(media_type, int(body.tmdb_id), season, preset, group)


@router.get("/poster-api/status")
def poster_api_status(request: Request):
    from .. import poster_api

    cfg = store.get_settings()
    base = str(request.base_url).rstrip("/")
    def _templates(key_text: str) -> dict:
        # Only the /poster form is shown: it's the one a reverse proxy can pass on
        # its own. /api/poster and /api/poster/{type}/{id} still work for old links.
        q = f"&key={key_text}" if cfg.key else ""
        return {
            "movie": f"{base}/poster?tmdb_id={{tmdb_id}}&type=movie{q}",
            "tv": f"{base}/poster?tmdb_id={{tmdb_id}}&type=tv{q}",
        }

    ids = poster_api._uniformlogo_preset_ids()
    missing = any(p and p not in ids for p in (cfg.defaultMoviePreset, cfg.defaultTvPreset))
    counts = db.poster_api_cache_counts()
    return {
        "enabled": cfg.enabled,
        "key_set": bool(cfg.key),
        "default_movie_preset": cfg.defaultMoviePreset,
        "default_tv_preset": cfg.defaultTvPreset,
        "default_preset_missing": missing,
        # Shown on the page (key hidden) ...
        "url_templates": _templates("YOUR_KEY"),
        # ... and what the Copy buttons copy, so the URL works as pasted. Same
        # trust model as the rest of the admin API (trusted network, Quirk #11).
        "url_templates_with_key": _templates(quote(cfg.key, safe="")),
        "counts": {"pinned": counts.get("pinned", 0), "rendered": counts.get("rendered", 0)},
    }


def _item_json(r: dict) -> dict:
    season = r.get("season_index")
    return {
        "id": r["id"],
        "type": r["media_type"],
        "tmdb_id": r["tmdb_id"],
        "season": None if season is None or season < 0 else season,
        "preset": store.split_dbkey(r.get("preset_key") or "")[0],
        "group": store.split_dbkey(r.get("preset_key") or "")[1],
        "source": r["source"],
        "title": r.get("title") or "",
        "hits": r.get("hits") or 0,
        "created_at": r.get("created_at"),
        "last_served_at": r.get("last_served_at"),
        "thumb_url": f"/api/poster-api/thumb/{r['id']}",
    }


_REQUEST_RESULTS = ("library", "pinned", "rendered", "generated", "redirect", "not_found", "bad_key")


@router.get("/poster-api/requests")
def poster_api_requests(result: Optional[str] = None, search: str = "", offset: int = 0, limit: int = 50):
    if result and result not in _REQUEST_RESULTS:
        raise HTTPException(status_code=400, detail="invalid result")
    rows, total, counts = db.poster_api_requests_list(result or None, search, max(0, offset), max(1, min(200, limit)))
    return {
        "items": [{
            "id": r["id"],
            "requested_at": r["requested_at"],
            "type": r["media_type"],
            "tmdb_id": r["tmdb_id"],
            "season": r["season_index"],
            "preset": r["preset"] or "",
            "group": r["group_id"] or "",
            "result": r["result"],
            "title": r["title"] or "",
            "duration_ms": r["duration_ms"],
        } for r in rows],
        "total": total,
        "counts": counts,
    }


@router.delete("/poster-api/requests")
def poster_api_requests_clear():
    return {"deleted": db.poster_api_requests_clear()}


@router.get("/poster-api/items")
def poster_api_items(search: str = "", type: Optional[str] = None, source: Optional[str] = None,
                     offset: int = 0, limit: int = 50):
    media_type = _norm_type(type) if type else None
    if source and source not in _SOURCES:
        raise HTTPException(status_code=400, detail="invalid source")
    offset = max(0, offset)
    limit = max(1, min(200, limit))
    rows, total = store.list_entries(search, media_type, source or None, offset, limit)
    return {"items": [_item_json(r) for r in rows], "total": total}


def _thumb_path(row_id: int) -> Path:
    return store.cache_dir() / "thumbs" / f"{int(row_id)}.jpg"


@router.get("/poster-api/thumb/{row_id}")
def poster_api_thumb(row_id: int):
    row = db.poster_api_cache_get_by_id(row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    src = Path(row["file_path"])
    if not src.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    thumb = _thumb_path(row_id)
    try:
        if not (thumb.is_file() and thumb.stat().st_mtime >= src.stat().st_mtime):
            from PIL import Image
            thumb.parent.mkdir(parents=True, exist_ok=True)
            tmp = thumb.with_name(f".{thumb.name}.{os.getpid()}.tmp")
            try:
                img = Image.open(src).convert("RGB")
                img.thumbnail((480, 480))
                img.save(tmp, "JPEG", quality=80)
                os.replace(tmp, thumb)
            finally:
                if tmp.exists():
                    tmp.unlink()
    except Exception:
        logger.exception("[POSTER API] thumbnail failed for row %s", row_id)
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(thumb), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.post("/poster-api/regenerate")
def poster_api_regenerate(body: PosterApiTarget):
    from .. import poster_api

    key = _admin_key(body)
    if key.preset_key and key.preset_key not in poster_api._uniformlogo_preset_ids():
        raise HTTPException(status_code=400, detail="Unknown uniformlogo preset")
    poster_api.regenerate(key)
    return JSONResponse({"queued": True}, status_code=202)


def _clear_key(key: "store.CacheKey", source: Optional[str]) -> int:
    """Delete rows (and their files and thumbnails) for one key; source None = all."""
    season_index = -1 if key.season is None else key.season
    rows = db.poster_api_cache_rows_for_key(key.media_type, key.tmdb_id, season_index, store._dbkey(key), source)
    deleted = store.delete_entry(key, source)
    for r in rows:
        try:
            _thumb_path(r["id"]).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("[POSTER API] could not remove thumbnail for row %s", r["id"])
    return deleted


@router.post("/poster-api/clear")
def poster_api_clear(body: PosterApiClearRequest):
    key = _admin_key(body)
    if body.source and body.source not in _SOURCES:
        raise HTTPException(status_code=400, detail="invalid source")
    return {"deleted": _clear_key(key, body.source)}


@router.post("/poster-api/bulk")
def poster_api_bulk(body: PosterApiBulkRequest):
    """Regenerate or clear many tiles at once. Regenerate only applies to
    rendered rows (pinned and library posters aren't rendered by the API);
    clear removes exactly the source each tile is. Invalid items are counted
    as skipped rather than failing the whole request."""
    from .. import poster_api

    if body.action not in ("regenerate", "clear"):
        raise HTTPException(status_code=400, detail="action must be regenerate or clear")
    if len(body.items) > MAX_BULK_ITEMS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_BULK_ITEMS} items at a time")
    preset_ids = set(poster_api._uniformlogo_preset_ids())
    done = skipped = 0
    for item in body.items:
        try:
            key = _admin_key(item)
        except HTTPException:
            skipped += 1
            continue
        if item.source and item.source not in _SOURCES:
            skipped += 1
            continue
        if body.action == "regenerate":
            if item.source not in (None, "rendered") or (key.preset_key and key.preset_key not in preset_ids):
                skipped += 1
                continue
            poster_api.regenerate(key)
            done += 1
        else:
            done += 1 if _clear_key(key, item.source) else 0
    return {"action": body.action, "done": done, "skipped": skipped}


@router.post("/poster-api/pin")
def poster_api_pin(body: PosterApiPinRequest):
    from PIL import Image
    from .. import poster_api

    key = _admin_key(body, allow_preset=False)
    m = re.match(r"^data:image/[a-zA-Z0-9.+-]+;base64,(.*)$", body.image_data or "", re.DOTALL)
    if not m:
        raise HTTPException(status_code=400, detail="image_data must be a base64 image data URL")
    b64 = m.group(1)
    if len(b64) > MAX_PIN_BYTES * 4 // 3 + 8:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    if len(raw) > MAX_PIN_BYTES:
        raise HTTPException(status_code=413, detail="Image too large")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = img.convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Not a valid image")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=95, subsampling=0)
    poster_api.pin(key, out.getvalue(), (body.title or "").strip() or None)
    # The pinned poster replaces the default render for this title, which is
    # never served while a pin exists -- remove it rather than keep a dead copy.
    # Renders for an explicit ?preset= are still served, so they stay.
    # The default slot exists once per library group (plus "any library").
    group_ids = [""] + [str(g.get("id")) for g in store._library_groups(key.media_type) if g.get("id")]
    removed = sum(_clear_key(store.CacheKey(key.media_type, key.tmdb_id, key.season, "", gid), "rendered")
                  for gid in group_ids)
    return {"ok": True, "removed_rendered": removed}


# ---------------------------------------------------------------------------
# TMDb title search / trending (Poster API page picker). Exact 2-segment paths:
# no existing /tmdb/... route is 2-segment, so nothing shadows these.
# ---------------------------------------------------------------------------

@router.get("/tmdb/search")
def tmdb_search(q: str = "", type: str = "movie"):
    from .. import tmdb_client

    media_type = _norm_type(type)
    if not (q or "").strip():
        return []
    try:
        return tmdb_client.search_titles(q, media_type)
    except Exception as exc:
        logger.warning("[POSTER API] TMDb search failed: %s", exc)
        raise HTTPException(status_code=502, detail="TMDb search failed")


@router.get("/tmdb/tv/{tmdb_id}/seasons")
def tmdb_tv_seasons(tmdb_id: int):
    """Season list for the editor's API mode (no media-server season list to use).

    /api/tmdb/tv/{id}/details only returns number_of_seasons, not the list itself.
    """
    from .. import tmdb_client

    try:
        return tmdb_client.get_tv_seasons(tmdb_id)
    except Exception as exc:
        logger.warning("[POSTER API] TMDb season list failed for tmdb_id=%s: %s", tmdb_id, exc)
        raise HTTPException(status_code=502, detail="TMDb season list failed")


@router.get("/tmdb/trending")
def tmdb_trending(type: str = "movie"):
    from .. import tmdb_client

    media_type = _norm_type(type)
    try:
        return tmdb_client.get_trending(media_type)
    except Exception as exc:
        logger.warning("[POSTER API] TMDb trending failed: %s", exc)
        raise HTTPException(status_code=502, detail="TMDb trending failed")
