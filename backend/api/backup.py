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
from .save import resolve_library_label

router = APIRouter()


def _get_backup_root() -> Path:
    """Get backup root directory. Computed at call time so settings.CONFIG_DIR is fully resolved."""
    return Path(settings.CONFIG_DIR) / "backups"


def _get_backup_dir(library_id: str) -> Path:
    """Get backup directory for a library, checking both new (library name) and old (library ID) locations."""
    backup_root = _get_backup_root()

    # Try new location (library name)
    library_name = resolve_library_label(library_id)
    new_dir = backup_root / _sanitize_filename(library_name)
    if new_dir.exists():
        return new_dir

    # Fall back to old location (library ID) for backward compatibility
    old_dir = backup_root / str(library_id)
    return old_dir  # Return even if doesn't exist - caller will handle


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


class RestorePreviewRequest(BaseModel):
    library_id: str
    media_type: str = "movie"


class RestoreExecuteItem(BaseModel):
    filename: str
    rating_key: str


class RestoreExecuteRequest(BaseModel):
    library_id: str
    items: List[RestoreExecuteItem]


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
def api_backup_status(library_id: str, media_type: str = "movie"):
    """Return backup info derived from the filesystem."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id)
    logger.debug("[BACKUP] Status check for library %s (%s), path: %s", library_id, library_name, backup_dir)
    if not backup_dir.exists():
        return {"count": 0, "last_date": None, "total_size": 0, "path": str(backup_dir)}

    files = [f for f in backup_dir.iterdir() if f.is_file() and f.suffix in (".jpg", ".jpeg", ".png", ".webp")]
    if not files:
        return {"count": 0, "last_date": None, "total_size": 0, "path": str(backup_dir)}

    total_size = sum(f.stat().st_size for f in files)
    latest_mtime = max(f.stat().st_mtime for f in files)
    last_date = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()

    return {"count": len(files), "last_date": last_date, "total_size": total_size, "path": str(backup_dir)}


@router.get("/backup/file/{library_id}/{filename:path}")
def api_backup_file(library_id: str, filename: str, media_type: str = "movie"):
    """Serve a backup image file for thumbnails in the restore preview."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id)
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
    """Start backing up all posters for a library."""
    with backup_status_lock:
        if backup_status["state"] == "running":
            raise HTTPException(409, "A backup/restore operation is already running")

    if req.media_type == "tv-show":
        items = db.get_cached_tv_shows(library_id=req.library_id)
    else:
        items = db.get_cached_movies(library_id=req.library_id)

    if not items:
        raise HTTPException(404, "No items found in cache for this library. Run a library scan first.")

    _update_backup_status({
        "state": "running",
        "total": len(items),
        "processed": 0,
        "current_movie": "",
        "current_step": "Starting backup...",
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
    })

    is_tv = req.media_type == "tv-show"
    thread = threading.Thread(
        target=_backup_library,
        args=(req.library_id, items, is_tv, req.include_seasons),
        daemon=True,
    )
    thread.start()

    return {"status": "started", "total": len(items)}


@router.post("/backup/restore/preview")
def api_restore_preview(req: RestorePreviewRequest):
    """Scan backup folder and auto-match files to Plex items. Returns a review list."""
    backup_dir = _get_backup_dir(req.library_id)
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

    backup_dir = _get_backup_dir(req.library_id)
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
        args=(valid_items,),
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
def api_backup_delete(library_id: str, media_type: str = "movie"):
    """Delete all backup files for a library."""
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
        logger.info("[BACKUP] Deleted backup folder for library %s", library_id)
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


def _backup_library(library_id: str, items: list, is_tv: bool, include_seasons: bool):
    """Download all posters for a library from Plex using human-readable filenames."""
    media_type = "tv-show" if is_tv else "movie"
    library_name = resolve_library_label(library_id)
    backup_dir = _get_backup_dir(library_id)
    backup_dir.mkdir(parents=True, exist_ok=True)
    logger.info("[BACKUP] Saving %d items for library '%s' to: %s (tv=%s, seasons=%s)", len(items), library_name, backup_dir, is_tv, include_seasons)

    manifest = {}
    succeeded = 0
    failed = 0
    total_items = len(items)
    _update_backup_status({"total": total_items})

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
            "processed": idx,
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
                _update_backup_status({"total": total_items})

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

    _update_backup_status({
        "state": "done",
        "processed": total_items,
        "current_movie": "",
        "current_step": f"Backup complete: {succeeded} saved, {failed} failed",
        "finished_at": time.time(),
    })
    logger.info("[BACKUP] Library %s backup complete: %d/%d succeeded (path: %s)", library_id, succeeded, succeeded + failed, backup_dir)


def _restore_selected(items: list):
    """Restore user-confirmed poster files to Plex."""
    succeeded = 0
    failed = 0
    total = len(items)

    for idx, item in enumerate(items):
        file_path = item["file_path"]
        rating_key = item["rating_key"]
        filename = item["filename"]

        _update_backup_status({
            "processed": idx,
            "current_movie": Path(filename).stem,
            "current_step": f"Restoring poster ({idx + 1}/{total})",
        })

        try:
            payload = file_path.read_bytes()
            url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
            headers = {
                "X-Plex-Token": settings.PLEX_TOKEN,
                "Content-Type": "image/jpeg",
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
