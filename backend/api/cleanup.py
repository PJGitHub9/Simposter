"""Manual, on-demand cleanup for Simposter's own disk cache and DB bloat.

Conceptually modeled on Kometa-Team's ImageMaid (github.com/Kometa-Team/ImageMaid),
which does the equivalent job for Plex's own image cache -- but scoped entirely to
files/rows Simposter itself already owns and writes, so (unlike ImageMaid) this
never needs a second filesystem mount into Plex's own server data directory.

Every destructive action goes through a reversible "trash" step first (files moved,
DB rows exported to JSON), mirroring ImageMaid's own move/restore/clear split --
nothing is ever permanently deleted except via the explicit, separately-confirmed
"Empty Trash" action. See CLAUDE.md's Cleanup Tool quirk if this file is touched
again.
"""
import shutil
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import database as db
from ..config import (
    settings,
    plex_headers,
    plex_session,
    logger,
    POSTER_CACHE_DIR,
    LOGO_CACHE_DIR,
    ART_CACHE_DIR,
    SQUARE_ART_CACHE_DIR,
)

router = APIRouter()

TRASH_DIR = Path(settings.CONFIG_DIR) / "cache" / "_cleanup_trash"
OVERLAY_CACHE_DIR = Path(settings.CONFIG_DIR) / "overlays"
OVERLAY_ASSETS_DIR = Path(settings.CONFIG_DIR) / "assets"

# A scan's results are only trusted for this long -- past it, "Clean Selected"
# requires a fresh scan rather than acting on what could be a stale world-view
# (files may have changed, a library may have been rescanned, etc.).
_SCAN_TTL_SECONDS = 600

# Populated by /scan, consumed by /clean. Category id -> list of absolute file
# paths (for file-backed categories) or asset ids (for "overlay_assets").
# poster_history isn't cached here -- its candidate set is just "rows older than
# N days," recomputed identically and safely at clean time.
_last_scan: Dict[str, List[str]] = {}
_last_scan_at: Optional[float] = None
_last_scan_history_days: int = 180


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def _scan_dir_orphans(cache_dir: Path, known_keys: set) -> List[Path]:
    """Files directly inside `cache_dir` whose filename (minus extension) isn't
    a rating_key Simposter currently has a movie_cache/tv_cache row for."""
    orphans: List[Path] = []
    if not cache_dir.exists():
        return orphans
    for f in cache_dir.iterdir():
        if f.is_file() and f.stem not in known_keys:
            orphans.append(f)
    return orphans


def _dir_size(paths: List[Path]) -> int:
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


class CleanRequest(BaseModel):
    categories: List[str]
    history_days: int = 180


class TrashActionRequest(BaseModel):
    batch_id: str


@router.get("/cleanup/schedule")
def api_cleanup_schedule_status():
    """Next-run info for the scheduled cleanup job, if one is currently active --
    enabled/cron/categories themselves live in the regular settings (Settings ->
    Cleanup applies/cancels the actual job as a side effect of saving, same as
    the poster-retry scheduler), this just exposes what the live APScheduler job
    computed so the UI can show "Next run: ..."."""
    from ..scheduler import get_cleanup_schedule
    info = get_cleanup_schedule()
    return {"active": info is not None, "next_run_time": info.get("next_run_time") if info else None}


@router.get("/cleanup/scan")
def api_cleanup_scan(history_days: int = 180):
    """Dry-run report only -- never modifies or deletes anything. Computes every
    category's orphan candidates fresh and caches them (see _last_scan above) so
    the follow-up /cleanup/clean call acts on exactly what was shown, not a
    possibly-different recomputation."""
    global _last_scan, _last_scan_at, _last_scan_history_days

    known_keys = db.get_all_known_rating_keys()
    preset_blob = db.get_all_preset_reference_blob()
    overlay_elements_blob = db.get_all_overlay_elements_blob()
    known_template_preset_pairs = db.get_all_preset_template_pairs()

    categories = []
    scan: Dict[str, List[str]] = {}

    # --- Disk cache: poster / logo / backdrop / square art -------------------
    def add_file_category(cid: str, label: str, description: str, cache_dir: Path, include_thumbs: bool = False):
        orphans = _scan_dir_orphans(cache_dir, known_keys)
        if include_thumbs:
            orphans += _scan_dir_orphans(cache_dir / "thumbs", known_keys)
        scan[cid] = [str(p) for p in orphans]
        categories.append({
            "id": cid,
            "label": label,
            "description": description,
            "kind": "files",
            "count": len(orphans),
            "bytes": _dir_size(orphans),
        })

    add_file_category(
        "poster_cache", "Orphaned poster cache",
        "Cached posters for items no longer in your library, as of the last scan.",
        Path(POSTER_CACHE_DIR),
    )
    add_file_category(
        "logo_cache", "Orphaned logo cache",
        "Cached clearlogos for items no longer in your library, as of the last scan.",
        Path(LOGO_CACHE_DIR),
    )
    add_file_category(
        "backdrop_cache", "Orphaned backdrop cache",
        "Cached backdrops (and their generated thumbnails) for items no longer in your library.",
        Path(ART_CACHE_DIR), include_thumbs=True,
    )
    add_file_category(
        "square_art_cache", "Orphaned square art cache",
        "Cached square art (and its generated thumbnails) for items no longer in your library.",
        Path(SQUARE_ART_CACHE_DIR), include_thumbs=True,
    )

    # --- Overlay effect cache (config/overlays/{template_id}/{preset_id}.png) -
    overlay_cache_orphans: List[Path] = []
    if OVERLAY_CACHE_DIR.exists():
        for template_dir in OVERLAY_CACHE_DIR.iterdir():
            if not template_dir.is_dir():
                continue
            for f in template_dir.iterdir():
                if f.is_file() and (template_dir.name, f.stem) not in known_template_preset_pairs:
                    overlay_cache_orphans.append(f)
    scan["overlay_effect_cache"] = [str(p) for p in overlay_cache_orphans]
    categories.append({
        "id": "overlay_effect_cache",
        "label": "Orphaned overlay effect cache",
        "description": "Pre-rendered matte/fade/vignette layers for presets that have since been deleted or renamed.",
        "kind": "files",
        "count": len(overlay_cache_orphans),
        "bytes": _dir_size(overlay_cache_orphans),
    })

    # --- Uploaded files never referenced by any saved preset -----------------
    uploaded_orphans: List[Path] = []
    upload_dir = Path(settings.UPLOAD_DIR)
    if upload_dir.exists():
        for f in upload_dir.iterdir():
            if f.is_file() and f"/api/uploaded/{f.name}" not in preset_blob:
                uploaded_orphans.append(f)
    scan["uploaded_files"] = [str(p) for p in uploaded_orphans]
    categories.append({
        "id": "uploaded_files",
        "label": "Unused uploaded images",
        "description": "Custom posters/logos uploaded in the editor that were never saved into a preset. "
                        "Note: a file you just uploaded but haven't saved yet will show here too.",
        "kind": "files",
        "count": len(uploaded_orphans),
        "bytes": _dir_size(uploaded_orphans),
    })

    # --- Overlay Manager assets never referenced by any overlay config -------
    all_assets = db.get_all_overlay_assets()
    orphan_asset_ids = [a["id"] for a in all_assets if a["id"] not in overlay_elements_blob]
    orphan_asset_paths = [OVERLAY_ASSETS_DIR / a["file_path"] for a in all_assets if a["id"] in orphan_asset_ids]
    scan["overlay_assets"] = orphan_asset_ids
    categories.append({
        "id": "overlay_assets",
        "label": "Unused overlay badge assets",
        "description": "Badge/custom images uploaded in Overlay Manager that no overlay config currently uses.",
        "kind": "files",
        "count": len(orphan_asset_ids),
        "bytes": _dir_size([p for p in orphan_asset_paths if p.exists()]),
    })

    # --- Old History entries (retention trim, not an orphan) ------------------
    history_count = db.get_poster_history_count_older_than(history_days)
    categories.append({
        "id": "poster_history",
        "label": "Old History entries",
        "description": f"History entries older than {history_days} days.",
        "kind": "rows",
        "count": history_count,
        "bytes": 0,
    })

    _last_scan = scan
    _last_scan_at = time.time()
    _last_scan_history_days = history_days

    total_bytes = sum(c["bytes"] for c in categories)

    # Flag if the reference data itself might be stale -- a library nobody's
    # rescanned in a while makes "orphaned" less trustworthy, not less true.
    stale_cache_warning = None
    try:
        newest = db.get_movie_cache_stats().get("max_updated")
        if newest:
            from datetime import datetime, timezone
            last = datetime.fromisoformat(newest)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            if age_hours > 24:
                stale_cache_warning = f"Your library cache is {int(age_hours)} hours old -- consider running a fresh scan before cleaning for the most accurate results."
    except Exception:
        pass

    return {
        "scanned_at": _last_scan_at,
        "history_days": history_days,
        "categories": categories,
        "total_bytes": total_bytes,
        "total_bytes_human": _human_bytes(total_bytes),
        "stale_cache_warning": stale_cache_warning,
    }


def _require_fresh_scan():
    if _last_scan_at is None or (time.time() - _last_scan_at) > _SCAN_TTL_SECONDS:
        raise HTTPException(400, "Scan results are missing or stale -- run a new scan first.")


@router.post("/cleanup/clean")
def api_cleanup_clean(req: CleanRequest):
    """Moves every selected category's scanned candidates into a new trash batch
    instead of deleting them outright -- see the module docstring. Requires a
    /cleanup/scan to have run recently (_SCAN_TTL_SECONDS) so this only ever acts
    on candidates the user actually saw in a report."""
    _require_fresh_scan()

    unknown = [c for c in req.categories if c not in _last_scan and c != "poster_history"]
    if unknown:
        raise HTTPException(400, f"Unknown or unscanned categories: {unknown}")

    batch_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    batch_dir = TRASH_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict = {"batch_id": batch_id, "created_at": time.time(), "categories": {}}
    moved_files = 0
    deleted_rows = 0

    for cid in req.categories:
        if cid == "poster_history":
            rows = db.export_and_delete_poster_history_older_than(req.history_days)
            if rows:
                import json
                (batch_dir / "poster_history.json").write_text(json.dumps(rows, default=str))
                manifest["categories"]["poster_history"] = {"kind": "rows", "count": len(rows)}
                deleted_rows += len(rows)
            continue

        if cid == "overlay_assets":
            asset_ids = _last_scan.get("overlay_assets", [])
            if asset_ids:
                import json
                exported = []
                cat_dir = batch_dir / "overlay_assets"
                cat_dir.mkdir(exist_ok=True)
                for asset_id in asset_ids:
                    asset = db.get_overlay_asset(asset_id)
                    if not asset:
                        continue
                    src = OVERLAY_ASSETS_DIR / asset["file_path"]
                    if src.exists():
                        dest = cat_dir / src.name
                        shutil.move(str(src), str(dest))
                    exported.append(asset)
                    db.delete_overlay_asset(asset_id)
                    moved_files += 1
                (batch_dir / "overlay_assets.json").write_text(json.dumps(exported, default=str))
                manifest["categories"]["overlay_assets"] = {"kind": "asset_rows", "count": len(exported)}
            continue

        # Plain file categories: preserve the original absolute path in the
        # manifest so Restore can put each file back exactly where it came from.
        paths = _last_scan.get(cid, [])
        if not paths:
            continue
        cat_dir = batch_dir / cid
        cat_dir.mkdir(exist_ok=True)
        moved = []
        for original in paths:
            src = Path(original)
            if not src.exists():
                continue
            # Namespace by a short hash of the original path to avoid collisions
            # between e.g. the top-level cache file and its thumbs/ counterpart,
            # which otherwise share the same filename.
            dest = cat_dir / f"{abs(hash(str(src))) % 100000}_{src.name}"
            shutil.move(str(src), str(dest))
            moved.append({"original_path": str(src), "trashed_path": str(dest)})
            moved_files += 1
        manifest["categories"][cid] = {"kind": "files", "files": moved}

    import json
    (batch_dir / "manifest.json").write_text(json.dumps(manifest, default=str))

    logger.info("[CLEANUP] Batch %s: moved %d files, deleted %d rows", batch_id, moved_files, deleted_rows)

    # Force a fresh scan before any further clean -- the files just moved are
    # gone from their original locations now, so the cached candidate lists for
    # any category not included in this request are still valid, but it's not
    # worth the complexity of partial invalidation for a manually-triggered,
    # infrequent action.
    global _last_scan_at
    _last_scan_at = None

    return {"batch_id": batch_id, "moved_files": moved_files, "deleted_rows": deleted_rows}


def _read_manifest(batch_id: str) -> Dict:
    manifest_path = TRASH_DIR / batch_id / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"Trash batch {batch_id} not found")
    import json
    return json.loads(manifest_path.read_text())


@router.get("/cleanup/trash")
def api_cleanup_list_trash():
    if not TRASH_DIR.exists():
        return {"batches": []}
    batches = []
    for batch_dir in sorted(TRASH_DIR.iterdir(), reverse=True):
        manifest_path = batch_dir / "manifest.json"
        if not batch_dir.is_dir() or not manifest_path.exists():
            continue
        import json
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            continue
        total_bytes = sum(f.stat().st_size for f in batch_dir.rglob("*") if f.is_file())
        batches.append({
            "batch_id": manifest.get("batch_id", batch_dir.name),
            "created_at": manifest.get("created_at"),
            "categories": list(manifest.get("categories", {}).keys()),
            "bytes": total_bytes,
            "bytes_human": _human_bytes(total_bytes),
        })
    return {"batches": batches}


@router.post("/cleanup/trash/restore")
def api_cleanup_restore(req: TrashActionRequest):
    manifest = _read_manifest(req.batch_id)
    batch_dir = TRASH_DIR / req.batch_id

    restored_files = 0
    restored_rows = 0

    for cid, info in manifest.get("categories", {}).items():
        if info.get("kind") == "files":
            for entry in info.get("files", []):
                src = Path(entry["trashed_path"])
                dest = Path(entry["original_path"])
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
                    restored_files += 1
        elif info.get("kind") == "rows" and cid == "poster_history":
            import json
            rows_path = batch_dir / "poster_history.json"
            if rows_path.exists():
                rows = json.loads(rows_path.read_text())
                db.restore_poster_history_rows(rows)
                restored_rows += len(rows)
        elif info.get("kind") == "asset_rows" and cid == "overlay_assets":
            import json
            rows_path = batch_dir / "overlay_assets.json"
            cat_dir = batch_dir / "overlay_assets"
            if rows_path.exists():
                assets = json.loads(rows_path.read_text())
                for asset in assets:
                    src = cat_dir / Path(asset["file_path"]).name
                    dest = OVERLAY_ASSETS_DIR / asset["file_path"]
                    if src.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(src), str(dest))
                    db.save_overlay_asset(
                        asset["id"], asset["name"], asset["file_path"],
                        asset["file_type"], asset["width"], asset["height"],
                    )
                    restored_rows += 1

    shutil.rmtree(batch_dir, ignore_errors=True)
    logger.info("[CLEANUP] Restored batch %s: %d files, %d rows", req.batch_id, restored_files, restored_rows)
    return {"restored_files": restored_files, "restored_rows": restored_rows}


@router.post("/cleanup/trash/empty")
def api_cleanup_empty_batch(req: TrashActionRequest):
    batch_dir = TRASH_DIR / req.batch_id
    if not batch_dir.exists():
        raise HTTPException(404, f"Trash batch {req.batch_id} not found")
    freed = sum(f.stat().st_size for f in batch_dir.rglob("*") if f.is_file())
    shutil.rmtree(batch_dir, ignore_errors=True)
    logger.info("[CLEANUP] Permanently emptied trash batch %s (%s)", req.batch_id, _human_bytes(freed))
    return {"bytes_freed": freed}


@router.post("/cleanup/trash/empty-all")
def api_cleanup_empty_all_trash():
    if not TRASH_DIR.exists():
        return {"bytes_freed": 0}
    freed = sum(f.stat().st_size for f in TRASH_DIR.rglob("*") if f.is_file())
    shutil.rmtree(TRASH_DIR, ignore_errors=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[CLEANUP] Permanently emptied all cleanup trash (%s)", _human_bytes(freed))
    return {"bytes_freed": freed}


# ---------------------------------------------------------------------------
# Plex server maintenance -- plain Plex API calls, no filesystem access to the
# Plex server needed at all. Verified against python-plexapi's real source
# (Library.emptyTrash/cleanBundles/optimize in plexapi/library.py) rather than
# guessed, matching this project's established "pull real source, don't guess
# at Plex API behavior" lesson.
# ---------------------------------------------------------------------------

def _require_plex():
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set.")


@router.post("/cleanup/plex/empty-trash")
def api_cleanup_plex_empty_trash():
    """PUT /library/sections/{key}/emptyTrash for every library section -- Plex
    has no single server-wide emptyTrash call, only a per-section one."""
    _require_plex()
    try:
        r = plex_session.get(f"{settings.PLEX_URL}/library/sections", headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        section_keys = [d.get("key") for d in root.findall(".//Directory") if d.get("key")]
    except Exception as e:
        raise HTTPException(500, f"Failed to list Plex library sections: {e}")

    emptied = []
    for key in section_keys:
        try:
            plex_session.put(f"{settings.PLEX_URL}/library/sections/{key}/emptyTrash", headers=plex_headers(), timeout=30)
            emptied.append(key)
        except Exception as e:
            logger.warning("[CLEANUP] Empty Trash failed for section %s: %s", key, e)
    logger.info("[CLEANUP] Plex Empty Trash run for %d/%d sections", len(emptied), len(section_keys))
    return {"sections_emptied": len(emptied), "sections_total": len(section_keys)}


@router.post("/cleanup/plex/clean-bundles")
def api_cleanup_plex_clean_bundles():
    _require_plex()
    try:
        plex_session.put(f"{settings.PLEX_URL}/library/clean/bundles?async=1", headers=plex_headers(), timeout=30)
    except Exception as e:
        raise HTTPException(500, f"Failed to start Clean Bundles: {e}")
    logger.info("[CLEANUP] Plex Clean Bundles started")
    return {"status": "started"}


@router.post("/cleanup/plex/optimize-db")
def api_cleanup_plex_optimize_db():
    _require_plex()
    try:
        plex_session.put(f"{settings.PLEX_URL}/library/optimize?async=1", headers=plex_headers(), timeout=30)
    except Exception as e:
        raise HTTPException(500, f"Failed to start Optimize DB: {e}")
    logger.info("[CLEANUP] Plex Optimize DB started")
    return {"status": "started"}
