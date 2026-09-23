# backend/api/backup.py
"""Backup and restore original Plex posters."""
import json
import os
import re
import shutil
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from ..config import settings, plex_session, plex_headers, logger
from .. import database as db
from ..save_paths import resolve_library_label
from .movies import fetch_and_cache_logo, fetch_and_cache_backdrop, fetch_and_cache_square_art
from .save import normalize_logo_for_plex, normalize_backdrop_for_plex

router = APIRouter()

# Logos/Backdrops/Square Art each get their own subfolder within a library's
# backup dir -- avoids filename collisions with posters (which would otherwise
# share the exact same "Title (Year).ext" naming) and lets each asset type be
# backed up/restored/deleted independently, matching the per-type checkbox UI.
# Posters deliberately stay in the library's own base dir with NO subfolder --
# that's the original, pre-existing layout, and changing it would silently
# strand any backup a user already has on disk from before this feature.
_ASSET_SUBDIRS = {"logo": "logos", "backdrop": "backdrops", "square_art": "square_art"}
_VALID_ASSET_TYPES = {"poster", "logo", "backdrop", "square_art"}

# Plex upload endpoint (relative to /library/metadata/{rating_key}/) + which
# save.py normalize function to run bytes through first, per asset type --
# mirrors plexsend.py's manual per-item send endpoints exactly, since a backup
# restore should be exactly as safe/correct as a normal manual send.
_RESTORE_ENDPOINT = {"poster": "posters", "logo": "clearLogos", "backdrop": "arts", "square_art": "squareArts"}


def _get_backup_root() -> Path:
    """Get backup root directory. Computed at call time so settings.CONFIG_DIR is fully resolved."""
    return Path(settings.CONFIG_DIR) / "backups"


def _get_backup_dir(library_id: str, asset_type: str = "poster") -> Path:
    """Get backup directory for a library, checking both new (library name) and old (library ID) locations."""
    backup_root = _get_backup_root()

    # Try new location (library name)
    library_name = resolve_library_label(library_id)
    new_dir = backup_root / _sanitize_filename(library_name)
    subdir = _ASSET_SUBDIRS.get(asset_type)
    if subdir:
        new_dir = new_dir / subdir
    if new_dir.exists():
        return new_dir

    # Fall back to old location (library ID) for backward compatibility --
    # posters only, since logo/backdrop/square_art never existed under the old
    # ID-keyed layout in the first place (this whole feature is new). Only
    # fall back if the old dir actually has a real prior backup in it --
    # otherwise a library that's never been backed up before would get its
    # very first backup created under the bare ID folder instead of the
    # library-name folder every other asset type already uses.
    if not subdir:
        old_dir = backup_root / str(library_id)
        if old_dir.exists():
            return old_dir
    return new_dir  # Return even if doesn't exist - caller will handle


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename (remove invalid chars, keep readability)."""
    safe = re.sub(r'[<>:"/\\|?*]', '', name)
    safe = safe.strip('. ')
    return safe or 'unknown'


def _normalize_title(title: str) -> str:
    """Normalize a title for fuzzy matching (lowercase, strip punctuation)."""
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _parse_filename(filename: str) -> dict:
    """Parse a backup filename to extract title, year, and optional season_index."""
    stem = Path(filename).stem
    # Try "Title (Year) - Season XX"
    m = re.match(r'^(.+?)\s*\((\d{4})\)\s*-\s*Season\s*(\d+)$', stem)
    if m:
        return {"title": m.group(1).strip(), "year": int(m.group(2)), "season_index": int(m.group(3))}
    # Try "Title - Season XX" (no year)
    m = re.match(r'^(.+?)\s*-\s*Season\s*(\d+)$', stem)
    if m:
        return {"title": m.group(1).strip(), "year": None, "season_index": int(m.group(2))}
    # Try "Title (Year)"
    m = re.match(r'^(.+?)\s*\((\d{4})\)$', stem)
    if m:
        return {"title": m.group(1).strip(), "year": int(m.group(2))}
    # Just a title
    return {"title": stem.strip(), "year": None}


# ---------------------------------------------------------------------------
# Progress tracking (same pattern as batch_status in batch.py)
# ---------------------------------------------------------------------------
backup_status = {
    "state": "idle",
    "total": 0,
    "processed": 0,
    "current_movie": "",
    "current_step": "",
    "started_at": None,
    "finished_at": None,
    "error": None,
}
backup_status_lock = threading.Lock()


def _update_backup_status(updates: dict):
    with backup_status_lock:
        backup_status.update(updates)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class BackupStartRequest(BaseModel):
    library_id: str
    media_type: str = "movie"
    include_seasons: bool = True
    # Which asset type(s) to back up in this run -- any of "poster", "logo",
    # "backdrop", "square_art". Defaults to poster-only so any existing caller
    # that doesn't know about this field keeps its exact original behavior.
    asset_types: List[str] = ["poster"]


class RestorePreviewRequest(BaseModel):
    library_id: str
    media_type: str = "movie"
    asset_type: str = "poster"


class RestoreExecuteItem(BaseModel):
    filename: str
    rating_key: str


class RestoreExecuteRequest(BaseModel):
    library_id: str
    items: List[RestoreExecuteItem]
    asset_type: str = "poster"


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------
def _load_manifest(backup_dir: Path) -> dict:
    """Load the manifest.json from a backup directory."""
    manifest_path = backup_dir / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_manifest(backup_dir: Path, manifest: dict):
    """Save the manifest.json to a backup directory."""
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/backup/progress")
def api_backup_progress():
    with backup_status_lock:
        return dict(backup_status)


@router.get("/backup/status/{library_id}")
def api_backup_status(library_id: str, media_type: str = "movie", asset_type: str = "poster"):
    """Return backup info derived from the filesystem, for one asset type."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id, asset_type)
    logger.debug("[BACKUP] Status check for library %s (%s) asset_type=%s, path: %s", library_id, library_name, asset_type, backup_dir)
    if not backup_dir.exists():
        return {"count": 0, "last_date": None, "total_size": 0, "path": str(backup_dir)}

    files = [f for f in backup_dir.iterdir() if f.is_file() and f.suffix in (".jpg", ".jpeg", ".png", ".webp")]
    if not files:
        return {"count": 0, "last_date": None, "total_size": 0, "path": str(backup_dir)}

    total_size = sum(f.stat().st_size for f in files)
    latest_mtime = max(f.stat().st_mtime for f in files)
    last_date = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()

    return {"count": len(files), "last_date": last_date, "total_size": total_size, "path": str(backup_dir)}


@router.get("/backup/status-all/{library_id}")
def api_backup_status_all(library_id: str, media_type: str = "movie"):
    """Status for all four asset types in one call, so the UI can show all of
    them without four sequential round-trips."""
    return {
        asset_type: api_backup_status(library_id, media_type, asset_type)
        for asset_type in _VALID_ASSET_TYPES
    }


@router.get("/backup/file/{library_id}/{filename:path}")
def api_backup_file(library_id: str, filename: str, media_type: str = "movie", asset_type: str = "poster"):
    """Serve a backup image file for thumbnails in the restore preview."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id, asset_type)
    file_path = backup_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "File not found")
    try:
        file_path.resolve().relative_to(backup_dir.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied")
    return FileResponse(file_path, media_type="image/jpeg")


@router.post("/backup/start")
def api_backup_start(req: BackupStartRequest):
    """Start backing up the selected asset type(s) for a library."""
    with backup_status_lock:
        if backup_status["state"] == "running":
            raise HTTPException(409, "A backup/restore operation is already running")

    asset_types = [a for a in req.asset_types if a in _VALID_ASSET_TYPES] or ["poster"]

    if req.media_type == "tv-show":
        items = db.get_cached_tv_shows(library_id=req.library_id)
    else:
        items = db.get_cached_movies(library_id=req.library_id)

    if not items:
        raise HTTPException(404, "No items found in cache for this library. Run a library scan first.")

    is_tv = req.media_type == "tv-show"
    # Seasons only apply to posters -- logos/backdrops/square art have no
    # per-season variant anywhere else in this app either.
    est_total = 0
    for at in asset_types:
        est_total += len(items)
        if at == "poster" and is_tv and req.include_seasons:
            est_total += len(items)  # rough estimate; refined once seasons are actually fetched

    _update_backup_status({
        "state": "running",
        "total": est_total,
        "processed": 0,
        "current_movie": "",
        "current_step": "Starting backup...",
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
    })

    thread = threading.Thread(
        target=_run_backup,
        args=(req.library_id, items, is_tv, req.include_seasons, asset_types),
        daemon=True,
    )
    thread.start()

    return {"status": "started", "total": est_total, "asset_types": asset_types}


@router.post("/backup/restore/preview")
def api_restore_preview(req: RestorePreviewRequest):
    """Scan backup folder and auto-match files to Plex items. Returns a review list."""
    backup_dir = _get_backup_dir(req.library_id, req.asset_type)
    if not backup_dir.exists():
        raise HTTPException(404, "No backup found for this library")

    files = [f for f in backup_dir.iterdir() if f.is_file() and f.suffix in (".jpg", ".jpeg", ".png", ".webp")]
    if not files:
        raise HTTPException(404, "No backup files found for this library")

    manifest = _load_manifest(backup_dir)

    # Load cached items for name-based matching
    if req.media_type == "tv-show":
        cached_items = db.get_cached_tv_shows(library_id=req.library_id)
    else:
        cached_items = db.get_cached_movies(library_id=req.library_id)

    # Build lookup indexes
    title_year_lookup = {}  # "normalized_title|year" -> item
    title_lookup = {}       # "normalized_title" -> item
    for item in cached_items:
        title = item.get("title", "")
        year = item.get("year")
        norm = _normalize_title(title)
        if norm and year:
            title_year_lookup[f"{norm}|{year}"] = item
        if norm and norm not in title_lookup:
            title_lookup[norm] = item

    results = []
    for f in sorted(files, key=lambda x: x.name.lower()):
        filename = f.name
        file_size = f.stat().st_size
        entry = {
            "filename": filename,
            "file_size": file_size,
            "rating_key": None,
            "plex_title": None,
            "match_type": "unmatched",
            "is_season": False,
        }

        # 1. Try manifest match (most reliable)
        manifest_entry = manifest.get(filename, {})
        if manifest_entry.get("rating_key"):
            entry["rating_key"] = manifest_entry["rating_key"]
            entry["plex_title"] = manifest_entry.get("title", "")
            entry["match_type"] = "manifest"
            entry["is_season"] = manifest_entry.get("type") == "season"
            results.append(entry)
            continue

        # 2. Try filename parsing + matching against cached items
        parsed = _parse_filename(filename)
        parsed_title = parsed.get("title", "")
        parsed_year = parsed.get("year")
        parsed_season = parsed.get("season_index")
        norm_parsed = _normalize_title(parsed_title)

        matched_item = None
        if norm_parsed and parsed_year:
            matched_item = title_year_lookup.get(f"{norm_parsed}|{parsed_year}")
        if not matched_item and norm_parsed:
            matched_item = title_lookup.get(norm_parsed)

        if matched_item:
            if parsed_season is not None:
                # Season poster — find the season's rating_key
                show_key = matched_item.get("rating_key", "")
                season_key = None
                # Try cached seasons first
                seasons = matched_item.get("seasons") or []
                for s in seasons:
                    idx = s.get("index") or s.get("season_index")
                    if idx is not None and int(idx) == parsed_season:
                        season_key = s.get("rating_key") or s.get("key") or s.get("ratingKey")
                        break
                # Fallback: fetch seasons from Plex API
                if not season_key and show_key:
                    plex_seasons = _get_show_seasons(show_key)
                    for s in plex_seasons:
                        if s.get("index") == parsed_season:
                            season_key = s.get("key")
                            break
                if season_key:
                    entry["rating_key"] = season_key
                    entry["plex_title"] = f"{matched_item.get('title', '')} - Season {parsed_season}"
                    entry["match_type"] = "name_match"
                    entry["is_season"] = True
            else:
                entry["rating_key"] = matched_item.get("rating_key", "")
                title_display = matched_item.get("title", "")
                if matched_item.get("year"):
                    title_display += f" ({matched_item['year']})"
                entry["plex_title"] = title_display
                entry["match_type"] = "name_match"

        results.append(entry)

    return {
        "items": results,
        "total": len(results),
        "matched": sum(1 for r in results if r["match_type"] != "unmatched"),
        "unmatched": sum(1 for r in results if r["match_type"] == "unmatched"),
    }


@router.post("/backup/restore/execute")
def api_restore_execute(req: RestoreExecuteRequest):
    """Execute restore for user-confirmed file-to-rating_key pairs."""
    with backup_status_lock:
        if backup_status["state"] == "running":
            raise HTTPException(409, "A backup/restore operation is already running")

    # Determine media type from backup folder or first item
    media_type = "movie"  # default
    # Try to infer from first item's rating_key by checking cache
    if req.items:
        first_key = req.items[0].rating_key
        if db.get_cached_tv_shows(library_id=req.library_id):
            for show in db.get_cached_tv_shows(library_id=req.library_id):
                if show.get("rating_key") == first_key:
                    media_type = "tv-show"
                    break

    asset_type = req.asset_type if req.asset_type in _VALID_ASSET_TYPES else "poster"
    backup_dir = _get_backup_dir(req.library_id, asset_type)
    if not backup_dir.exists():
        raise HTTPException(404, "No backup found for this library")

    if not req.items:
        raise HTTPException(400, "No items to restore")

    valid_items = []
    for item in req.items:
        file_path = backup_dir / item.filename
        if file_path.exists() and file_path.is_file():
            valid_items.append({
                "file_path": file_path,
                "rating_key": item.rating_key,
                "filename": item.filename,
            })

    if not valid_items:
        raise HTTPException(404, "No valid files found to restore")

    _update_backup_status({
        "state": "running",
        "total": len(valid_items),
        "processed": 0,
        "current_movie": "",
        "current_step": "Starting restore...",
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
    })

    thread = threading.Thread(
        target=_restore_selected,
        args=(valid_items, asset_type),
        daemon=True,
    )
    thread.start()

    return {"status": "started", "total": len(valid_items)}


@router.get("/backup/library-items/{library_id}")
def api_library_items(library_id: str, media_type: str = "movie"):
    """Return cached library items for manual match assignment in the restore preview."""
    if media_type == "tv-show":
        cached = db.get_cached_tv_shows(library_id=library_id)
    else:
        cached = db.get_cached_movies(library_id=library_id)

    items = []
    for c in cached:
        title = c.get("title", "")
        year = c.get("year")
        rating_key = c.get("rating_key", "")
        items.append({
            "rating_key": rating_key,
            "title": f"{title} ({year})" if year else title,
            "year": year,
        })
        # For TV shows, include seasons
        if media_type == "tv-show":
            seasons = c.get("seasons") or []
            # If no seasons in cache, fetch from Plex
            if not seasons and rating_key:
                seasons = _get_show_seasons(rating_key)
            for s in seasons:
                sk = s.get("rating_key") or s.get("key") or s.get("ratingKey")
                si = s.get("index") or s.get("season_index")
                if sk and si is not None:
                    items.append({
                        "rating_key": sk,
                        "title": f"{title} - Season {si}",
                        "year": year,
                        "is_season": True,
                    })

    return {"items": items}


@router.delete("/backup/delete/{library_id}")
def api_backup_delete(library_id: str, media_type: str = "movie", asset_type: str = "poster"):
    """Delete all backup files for a library, for one asset type."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id, asset_type)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
        logger.info("[BACKUP] Deleted %s backup folder for library %s", asset_type, library_id)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------
def _download_poster(rating_key: str, out_path: Path) -> bool:
    """Download a poster from Plex by rating_key. Returns True on success."""
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/thumb"
        resp = plex_session.get(url, headers=plex_headers(), timeout=10, stream=True)
        if resp.status_code != 200:
            return False
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        logger.debug("[BACKUP] Download error for key=%s: %s", rating_key, e)
        return False


def _get_show_seasons(show_rating_key: str) -> list:
    """Fetch seasons for a TV show from Plex. Returns list of {key, title, index}."""
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{show_rating_key}/children"
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)

        seasons = []
        for directory in root.findall(".//Directory"):
            season_key = directory.get("ratingKey")
            season_title = directory.get("title", "")
            season_index = directory.get("index")
            if season_key and season_index is not None:
                seasons.append({
                    "key": season_key,
                    "title": season_title,
                    "index": int(season_index),
                })
        seasons.sort(key=lambda s: s["index"])
        return seasons
    except Exception as e:
        logger.debug("[BACKUP] Failed to fetch seasons for show %s: %s", show_rating_key, e)
        return []


def _backup_library(library_id: str, items: list, is_tv: bool, include_seasons: bool, progress_offset: int = 0) -> tuple:
    """Download all posters for a library from Plex using human-readable filenames.
    Returns (succeeded, failed). Does NOT set the final "done" status itself --
    see _run_backup(), which may be running this as one of several selected
    asset types in the same operation."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id, "poster")
    backup_dir.mkdir(parents=True, exist_ok=True)
    logger.info("[BACKUP] Saving %d posters for library '%s' to: %s (tv=%s, seasons=%s)", len(items), library_name, backup_dir, is_tv, include_seasons)

    manifest = {}
    succeeded = 0
    failed = 0
    total_items = len(items)
    _update_backup_status({"total": progress_offset + total_items})

    for idx, item in enumerate(items):
        rating_key = item.get("rating_key") or item.get("key", "")
        title = item.get("title", "Unknown")
        year = item.get("year")

        if year:
            base_name = f"{_sanitize_filename(title)} ({year})"
        else:
            base_name = _sanitize_filename(title)

        filename = f"{base_name}.jpg"

        _update_backup_status({
            "processed": progress_offset + idx,
            "current_movie": title,
            "current_step": f"Downloading poster ({idx + 1}/{total_items})",
        })

        out_path = backup_dir / filename
        if _download_poster(rating_key, out_path):
            manifest[filename] = {
                "rating_key": rating_key,
                "title": title,
                "year": year,
                "type": "tv-show" if is_tv else "movie",
            }
            succeeded += 1
        else:
            failed += 1

        if is_tv and include_seasons:
            seasons = _get_show_seasons(rating_key)
            if seasons:
                total_items += len(seasons)
                _update_backup_status({"total": progress_offset + total_items})

                for season in seasons:
                    season_key = season["key"]
                    season_index = season["index"]
                    season_filename = f"{base_name} - Season {season_index:02d}.jpg"

                    _update_backup_status({
                        "current_movie": f"{title} - Season {season_index}",
                        "current_step": "Downloading season poster",
                    })

                    season_out = backup_dir / season_filename
                    if _download_poster(season_key, season_out):
                        manifest[season_filename] = {
                            "rating_key": season_key,
                            "title": f"{title} - Season {season_index}",
                            "year": year,
                            "type": "season",
                            "parent_key": rating_key,
                            "season_index": season_index,
                        }
                        succeeded += 1
                    else:
                        failed += 1

    _save_manifest(backup_dir, manifest)
    logger.info("[BACKUP] Library %s poster backup complete: %d/%d succeeded (path: %s)", library_id, succeeded, succeeded + failed, backup_dir)
    return succeeded, failed


# Which fetch_and_cache_X function (imported from movies.py, backing the same
# Logo/Backdrop/Square Art disk caches those library-browsing grids use) to
# call for each non-poster asset type. Reused rather than writing a second,
# parallel "download this asset from Plex" implementation -- see art_cache.py's
# make_art_cache() and CLAUDE.md Quirk #42/#49 for why this is the one function
# that already knows how to fetch each of these correctly.
_FETCH_AND_CACHE = {
    "logo": fetch_and_cache_logo,
    "backdrop": fetch_and_cache_backdrop,
    "square_art": fetch_and_cache_square_art,
}


def _backup_art_library(library_id: str, items: list, asset_type: str, progress_offset: int = 0) -> tuple:
    """Back up logo/backdrop/square_art for a library. No season variants for
    these three (unlike posters) -- one file per movie/show. Returns (succeeded, failed)."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id, asset_type)
    backup_dir.mkdir(parents=True, exist_ok=True)
    fetch_and_cache = _FETCH_AND_CACHE[asset_type]
    logger.info("[BACKUP] Saving %d %s files for library '%s' to: %s", len(items), asset_type, library_name, backup_dir)

    manifest = {}
    succeeded = 0
    failed = 0
    total_items = len(items)
    _update_backup_status({"total": progress_offset + total_items})

    for idx, item in enumerate(items):
        rating_key = item.get("rating_key") or item.get("key", "")
        title = item.get("title", "Unknown")
        year = item.get("year")
        base_name = f"{_sanitize_filename(title)} ({year})" if year else _sanitize_filename(title)

        _update_backup_status({
            "processed": progress_offset + idx,
            "current_movie": title,
            "current_step": f"Downloading {asset_type.replace('_', ' ')} ({idx + 1}/{total_items})",
        })

        try:
            # force_refresh=True: a backup should reflect what's CURRENTLY in
            # Plex, not whatever this app's own cache happened to have last --
            # this also has the (desirable, not just tolerated) side effect of
            # refreshing that live cache to match, same as a fresh scan would.
            cached_path = fetch_and_cache(rating_key, force_refresh=True)
        except Exception as e:
            logger.debug("[BACKUP] %s fetch failed for %s: %s", asset_type, rating_key, e)
            cached_path = None

        if cached_path:
            ext = cached_path.suffix  # already includes the leading "."
            filename = f"{base_name}{ext}"
            try:
                shutil.copy2(cached_path, backup_dir / filename)
                manifest[filename] = {"rating_key": rating_key, "title": title, "year": year}
                succeeded += 1
            except Exception as e:
                logger.debug("[BACKUP] Failed to copy %s backup for %s: %s", asset_type, rating_key, e)
                failed += 1
        else:
            failed += 1

    _save_manifest(backup_dir, manifest)
    logger.info("[BACKUP] Library %s %s backup complete: %d/%d succeeded (path: %s)", library_id, asset_type, succeeded, succeeded + failed, backup_dir)
    return succeeded, failed


def _run_backup(library_id: str, items: list, is_tv: bool, include_seasons: bool, asset_types: list):
    """Thread target for /backup/start -- runs each selected asset type in
    turn (sequentially, within the one "running" operation the status lock
    already limits to one at a time) and sets the final "done" status once."""
    total_succeeded = 0
    total_failed = 0
    processed_offset = 0

    for asset_type in asset_types:
        if asset_type == "poster":
            succeeded, failed = _backup_library(library_id, items, is_tv, include_seasons, processed_offset)
        else:
            succeeded, failed = _backup_art_library(library_id, items, asset_type, processed_offset)
        total_succeeded += succeeded
        total_failed += failed
        processed_offset += succeeded + failed

    _update_backup_status({
        "state": "done",
        "processed": processed_offset,
        "total": processed_offset,
        "current_movie": "",
        "current_step": f"Backup complete: {total_succeeded} saved, {total_failed} failed",
        "finished_at": time.time(),
    })


def _restore_selected(items: list, asset_type: str = "poster"):
    """Restore user-confirmed asset files to Plex, for one asset type."""
    succeeded = 0
    failed = 0
    total = len(items)
    endpoint_segment = _RESTORE_ENDPOINT.get(asset_type, "posters")

    for idx, item in enumerate(items):
        file_path = item["file_path"]
        rating_key = item["rating_key"]
        filename = item["filename"]

        _update_backup_status({
            "processed": idx,
            "current_movie": Path(filename).stem,
            "current_step": f"Restoring {asset_type.replace('_', ' ')} ({idx + 1}/{total})",
        })

        try:
            payload = file_path.read_bytes()
            content_type = {".png": "image/png", ".webp": "image/webp"}.get(file_path.suffix.lower(), "image/jpeg")

            # Posters restore exactly as they always have -- these bytes came
            # straight from Plex's own /thumb, a byte-for-byte round trip back
            # to Plex needs no re-encode. Logo/backdrop/square_art go through
            # the same PIL normalize pass plexsend.py's manual sends already
            # use (Quirk #26/#28: never forward raw source bytes unnormalized
            # to a Plex image-upload endpoint).
            if asset_type == "logo":
                payload, content_type = normalize_logo_for_plex(payload, content_type)
            elif asset_type in ("backdrop", "square_art"):
                payload, content_type = normalize_backdrop_for_plex(payload, content_type)

            url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/{endpoint_segment}"
            headers = {
                "X-Plex-Token": settings.PLEX_TOKEN,
                "Content-Type": content_type,
            }
            resp = requests.post(url, headers=headers, data=payload, timeout=20)
            resp.raise_for_status()
            succeeded += 1
        except Exception as e:
            logger.debug("[BACKUP] Error restoring %s (key=%s): %s", filename, rating_key, e)
            failed += 1

    _update_backup_status({
        "state": "done",
        "processed": total,
        "current_movie": "",
        "current_step": f"Restore complete: {succeeded} restored, {failed} failed",
        "finished_at": time.time(),
    })
    logger.info("[BACKUP] Selective restore complete: %d/%d succeeded", succeeded, total)
