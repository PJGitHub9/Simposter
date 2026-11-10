"""Storage layer for the Poster API cache: JPEG files in config/cache/poster_api/
plus the `poster_api_cache` index table (SQL lives in backend/database.py).

media_type is "movie" or "tv". source is "rendered" | "pinned" | "library"
(library rows point at the existing library cache file and are never unlinked here).
"""
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import database as db
from .config import logger, settings


@dataclass
class CacheKey:
    media_type: str
    tmdb_id: int
    season: Optional[int]
    preset_key: str  # "" = default
    # Library group id ("" = any library). Part of the key because the group decides
    # which library copy's poster is served and whose media info feeds the badges.
    group: str = ""


def _season(key: CacheKey) -> int:
    return -1 if key.season is None else int(key.season)


GROUP_SEP = "@"


def _dbkey(key: CacheKey) -> str:
    """The poster_api_cache.preset_key column value: the preset, plus "@group" when a
    group is set (keeps one table/primary key for every group)."""
    return f"{key.preset_key}{GROUP_SEP}{key.group}" if key.group else key.preset_key


def split_dbkey(value: str) -> Tuple[str, str]:
    """Inverse of _dbkey(): (preset, group)."""
    value = value or ""
    if GROUP_SEP in value:
        preset, group = value.split(GROUP_SEP, 1)
        return preset, group
    return value, ""


def _library_groups(media_type: str) -> List[Dict[str, Any]]:
    want = "tv" if media_type == "tv" else "movie"
    groups = (db.get_ui_settings() or {}).get("libraryGroups") or []
    return [g for g in groups if isinstance(g, dict) and g.get("mediaType") == want]


def resolve_group(media_type: str, value: Optional[str]) -> Optional[Dict[str, Any]]:
    """A library group of this media type matched by id, else by name (case-insensitive)."""
    value = (value or "").strip()
    if not value:
        return None
    groups = _library_groups(media_type)
    for g in groups:
        if str(g.get("id")) == value:
            return g
    for g in groups:
        if str(g.get("name") or "").strip().lower() == value.lower():
            return g
    return None


def group_members(media_type: str, group_id: str) -> Optional[List[Tuple[str, str]]]:
    """(server_id, library_id) pairs of the group, or None for "any library"."""
    g = resolve_group(media_type, group_id) if group_id else None
    if not g:
        return None
    return [(str(m.get("serverId")), str(m.get("libraryId"))) for m in (g.get("members") or [])
            if isinstance(m, dict)]


def cache_dir() -> Path:
    return Path(settings.CONFIG_DIR) / "cache" / "poster_api"


def file_name_for(key: CacheKey, source: str) -> str:
    season = f"_s{key.season}" if key.season is not None else ""
    # Explicit-preset files carry a "p_" prefix so a preset literally named
    # "pinned" or "default" can never collide with the pinned/default-slot files.
    if source == "pinned":
        suffix = "pinned"
    elif key.preset_key:
        suffix = f"p_{key.preset_key}"
    else:
        suffix = "default"
    if key.group and source != "pinned":
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key.group)
        suffix = f"{suffix}__g_{safe}"
    return f"{key.media_type}_{key.tmdb_id}{season}__{suffix}.jpg"


def _inside_cache_dir(path: Path) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(cache_dir()))
        return True
    except ValueError:
        return False


def _row_to_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row)
    row["path"] = row["file_path"]
    return row


def get_entry(key: CacheKey, source: str) -> Optional[Dict[str, Any]]:
    """Row + `path`. A row whose file is gone is deleted and None returned."""
    row = db.poster_api_cache_get(key.media_type, key.tmdb_id, _season(key), _dbkey(key), source)
    if not row:
        return None
    if not Path(row["file_path"]).is_file():
        db.poster_api_cache_delete(key.media_type, key.tmdb_id, _season(key), _dbkey(key), source)
        return None
    return _row_to_entry(row)


def put_entry(key: CacheKey, source: str, image_bytes: bytes, title: Optional[str], preset_hash: Optional[str]) -> None:
    """Atomic write (temp file + os.replace) of the JPEG, then upsert the row."""
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / file_name_for(key, source)
    tmp = d / f".{dest.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_bytes(image_bytes)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()
    db.poster_api_cache_put(key.media_type, key.tmdb_id, _season(key), _dbkey(key), source,
                            str(dest), title, preset_hash)


def delete_entry(key: CacheKey, source: Optional[str] = None) -> int:
    """Delete rows (and their files, only if inside cache_dir()) for the key;
    all sources when `source` is None. Returns rows deleted."""
    n = 0
    for row in db.poster_api_cache_rows_for_key(key.media_type, key.tmdb_id, _season(key), _dbkey(key), source):
        p = Path(row["file_path"])
        if _inside_cache_dir(p):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        n += db.poster_api_cache_delete(key.media_type, key.tmdb_id, _season(key), _dbkey(key), row["source"])
    return n


def touch_served(key: CacheKey, source: str) -> None:
    if source == "library":
        # The file belongs to the library, not the API: no tile, only the request
        # history (poster_api_requests) records it.
        return
    db.poster_api_queue_touch(key.media_type, key.tmdb_id, _season(key), _dbkey(key), source)


def list_entries(search: str, media_type: Optional[str], source: Optional[str],
                 offset: int, limit: int) -> Tuple[List[Dict[str, Any]], int]:
    """Rows with files present (missing-file rows are pruned). Ordered by last_served_at
    desc (never-served last), then created_at desc. Numeric search also matches tmdb id."""
    rows, total = db.poster_api_cache_list(search, media_type, source, offset, limit)
    out = []
    for r in rows:
        if Path(r["file_path"]).is_file():
            out.append(_row_to_entry(r))
        else:
            db.poster_api_cache_delete(r["media_type"], r["tmdb_id"], r["season_index"], r["preset_key"], r["source"])
            total -= 1
    return out, total


def list_stale_rendered(days: int) -> List[Dict[str, Any]]:
    """Rendered rows not served for more than `days` (never-served: measured from created_at)."""
    return [_row_to_entry(r) for r in db.poster_api_cache_stale_rendered(days)]


def preset_hash(template_id: str, preset_id: str) -> str:
    """sha256 over the preset's options + season_options + the updated_at of each linked
    overlay config. An unknown preset hashes as an empty preset (stable, never raises)."""
    from .config import load_presets
    preset: Dict[str, Any] = {}
    for p in (load_presets().get(template_id) or {}).get("presets", []):
        if p.get("id") == preset_id:
            preset = p
            break
    options = preset.get("options") or {}
    ids: List[str] = []
    for field in ("overlay_config_ids", "overlay_config_ids_below"):
        ids += [i for i in (options.get(field) or []) if isinstance(i, str)]
    stamps = {}
    for oid in sorted(set(ids)):
        cfg = db.get_overlay_config(oid)
        stamps[oid] = (cfg or {}).get("updated_at")
    payload = json.dumps({"o": options, "s": preset.get("season_options") or {}, "ov": stamps},
                         sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def library_poster_path(media_type: str, tmdb_id: int, season: Optional[int],
                        members: Optional[List[Tuple[str, str]]] = None) -> Optional[Path]:
    """A poster this install already has on disk for the title, so the API can serve
    it instead of rendering. Checked in order:

    1. The last poster Simposter sent for this TMDb id (``poster_renders_by_tmdb/``).
    2. The last poster Simposter sent to any library copy of the title (the resend
       cache, ``poster_renders/{rating_key}.jpg``, full size).
    3. The poster currently on the media server, as cached by library scans
       (``posters/{rating_key}.*``, or ``tv_{rating_key}.*`` for shows; up to
       1000px tall since v1.8.32).

    Plex copies are tried before Jellyfin/Emby ones. Steps 2 and 3 are for movies and
    whole shows only: the cache tables don't record a season's number.

    ``members`` (a library group's (server_id, library_id) pairs) limits the lookup to
    those libraries and skips step 1, which isn't tied to any library.
    """
    from .config import POSTER_CACHE_DIR, _render_cache_path, _render_cache_path_by_tmdb
    if members is None:
        p = _render_cache_path_by_tmdb("tv-show" if media_type == "tv" else media_type, tmdb_id, season)
        if p.is_file():
            return p
    if season is not None:
        return None

    table = "tv_cache" if media_type == "tv" else "movie_cache"
    try:
        with db.get_db() as conn:
            rows = conn.execute(
                f"SELECT rating_key, server_id, library_id FROM {table} WHERE tmdb_id = ? AND rating_key IS NOT NULL "
                "ORDER BY (server_id = 'plex-1') DESC, updated_at DESC",
                (int(tmdb_id),),
            ).fetchall()
    except Exception as e:
        logger.debug("[POSTER API] Library lookup failed for %s %s: %s", media_type, tmdb_id, e)
        return None
    allowed = set(members) if members is not None else None
    keys = [str(r[0]) for r in rows if allowed is None or (str(r[1]), str(r[2])) in allowed]

    for key in keys:
        sent = _render_cache_path(key)
        if sent.is_file():
            return sent

    prefix = "tv_" if media_type == "tv" else ""
    cache_dir = Path(POSTER_CACHE_DIR)
    for key in keys:
        for ext in ("jpg", "jpeg", "png", "webp"):
            cached = cache_dir / f"{prefix}{key}.{ext}"
            if cached.is_file():
                return cached
    return None


def clamp_wait_seconds(value: Any) -> int:
    try:
        return max(2, min(30, int(value)))
    except (TypeError, ValueError):
        return 10


def get_settings():
    """Poster API settings, read fresh from the DB (never the runtime `settings.*` copy,
    Quirk #36), defaults filled in, waitSeconds clamped 2-30, retentionDays >= 1."""
    from .schemas import PosterApiSettings

    raw = (db.get_ui_settings() or {}).get("posterApi")
    data: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    fields = PosterApiSettings.model_fields
    data = {k: v for k, v in data.items() if k in fields}
    for k in ("key", "defaultMoviePreset", "defaultTvPreset"):
        if k in data:
            data[k] = "" if data[k] is None else str(data[k])
    try:
        p = PosterApiSettings(**data)
    except Exception:
        p = PosterApiSettings()
    p.waitSeconds = clamp_wait_seconds(p.waitSeconds)
    p.retentionDays = max(1, int(p.retentionDays))
    return p
