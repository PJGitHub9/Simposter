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
from .config import settings


@dataclass
class CacheKey:
    media_type: str
    tmdb_id: int
    season: Optional[int]
    preset_key: str  # "" = default


def _season(key: CacheKey) -> int:
    return -1 if key.season is None else int(key.season)


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
    row = db.poster_api_cache_get(key.media_type, key.tmdb_id, _season(key), key.preset_key, source)
    if not row:
        return None
    if not Path(row["file_path"]).is_file():
        db.poster_api_cache_delete(key.media_type, key.tmdb_id, _season(key), key.preset_key, source)
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
    db.poster_api_cache_put(key.media_type, key.tmdb_id, _season(key), key.preset_key, source,
                            str(dest), title, preset_hash)


def delete_entry(key: CacheKey, source: Optional[str] = None) -> int:
    """Delete rows (and their files, only if inside cache_dir()) for the key;
    all sources when `source` is None. Returns rows deleted."""
    n = 0
    for row in db.poster_api_cache_rows_for_key(key.media_type, key.tmdb_id, _season(key), key.preset_key, source):
        p = Path(row["file_path"])
        if _inside_cache_dir(p):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        n += db.poster_api_cache_delete(key.media_type, key.tmdb_id, _season(key), key.preset_key, row["source"])
    return n


def touch_served(key: CacheKey, source: str) -> None:
    if source == "library":
        # Library files have no file of their own here: record a row pointing at the
        # library path so the Poster API page can list it. Never put_entry (no copy,
        # and delete_entry never unlinks outside cache_dir()).
        p = library_poster_path(key.media_type, key.tmdb_id, key.season)
        if p is not None:
            title = db.get_title_for_tmdb_id(key.media_type, key.tmdb_id) or ""
            existing = db.poster_api_cache_get(key.media_type, key.tmdb_id, _season(key), key.preset_key, "library")
            if not existing or existing["file_path"] != str(p):
                db.poster_api_cache_put(key.media_type, key.tmdb_id, _season(key), key.preset_key,
                                        "library", str(p), title, "")
    db.poster_api_cache_touch(key.media_type, key.tmdb_id, _season(key), key.preset_key, source)


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


def library_poster_path(media_type: str, tmdb_id: int, season: Optional[int]) -> Optional[Path]:
    """Existing library cache file for this title, if present. "tv" maps to the
    library cache's "tv-show" naming."""
    from .config import _render_cache_path_by_tmdb
    p = _render_cache_path_by_tmdb("tv-show" if media_type == "tv" else media_type, tmdb_id, season)
    return p if p.is_file() else None


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
