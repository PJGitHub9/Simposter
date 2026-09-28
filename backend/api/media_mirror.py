"""Media Mirror (Quirk #123) -- designates one Library Group member as "the
truth" and copies its posters/logos/backdrops/square art to one or more
other linked members. Requested directly by the user: "i want to set plex as
the main, and jf as the mirrored... an initial run to copy all posters to
jellyfin, then a scheduler option which checks if plex has updated any
posters since the last check."

Deliberately reuses everything already built rather than inventing new
image-handling code:
  - MediaServerClient.download_image()/upload_image() (Phase 2/3) for the
    actual per-item copy.
  - save.py's encode_poster_for_plex()/normalize_logo_for_plex()/
    normalize_backdrop_for_plex() (the same normalize-before-upload
    functions plexsend.py/media_server_send.py already use, Quirk #69) --
    a mirror upload gets exactly the same safety treatment a manual send
    already does, not a second, less-careful code path.
  - database.py's get_movie_mirror_mapping()/get_tv_mirror_mapping() for
    the source->target item resolution (built on the same raw union query
    get_cached_movies_multi()/_tv_shows_multi() already use, Quirk #121).

This first slice covers config + the mapping-confirmation view + a manual
"Run Now" full sync. The scheduled incremental sync (only re-copying items
whose source image actually changed since last run) is deliberately NOT
part of this slice -- it needs a verified, cheap per-item "has this image
changed" signal (Plex's thumb/art path suffix, Jellyfin's ImageTags hash)
that hasn't been checked against a real server yet, matching this project's
own "verify, don't guess" discipline (Quirk #100's explicit lesson) rather
than shipping unverified drift-detection logic. Tracked as a fast follow-up,
not a cut corner.
"""
import threading
from io import BytesIO
from typing import Any, Dict, List, Optional

from PIL import Image
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import logger, get_library_group_for
from .. import database as db
from ..media_server import get_client, ImageType

router = APIRouter(prefix="/media-mirror", tags=["media-mirror"])

_ASSET_TYPE_MAP = {
    "poster": ImageType.POSTER,
    "logo": ImageType.LOGO,
    "backdrop": ImageType.BACKDROP,
    "square_art": ImageType.SQUARE_ART,
}

# ---------------------------------------------------------------------------
# Progress tracking -- same shape as backup.py's backup_status (Quirk #55),
# keyed per group since more than one group could theoretically run a mirror
# at once (unlike backup, which is a single global operation).
# ---------------------------------------------------------------------------
mirror_status: Dict[str, Dict[str, Any]] = {}
mirror_status_lock = threading.Lock()


def _status_key(server_id: str, library_id: str, media_type: str) -> str:
    return f"{server_id}:{library_id}:{media_type}"


def _update_status(key: str, updates: dict):
    with mirror_status_lock:
        mirror_status.setdefault(key, {}).update(updates)


class MirrorConfigRequest(BaseModel):
    server_id: str = "plex-1"
    library_id: str
    media_type: str
    mirror: dict


@router.post("/config")
def api_save_mirror_config(req: MirrorConfigRequest):
    updated = db.set_library_group_mirror_config(req.server_id, req.library_id, req.media_type, req.mirror)
    if updated is None:
        raise HTTPException(404, "No Library Group found for this library")
    return {"group": updated}


def _resolve_mapping(group: dict, media_type: str, source_server_id: str, target_server_ids: List[str]) -> List[dict]:
    pairs = [(m.get("serverId"), m.get("libraryId")) for m in (group.get("members") or [])]
    if not pairs:
        return []
    fn = db.get_movie_mirror_mapping if media_type == "movie" else db.get_tv_mirror_mapping
    return fn(pairs, source_server_id, target_server_ids)


@router.get("/mapping")
def api_get_mirror_mapping(
    server_id: str = "plex-1",
    library_id: str = "",
    media_type: str = "movie",
    source_server_id: Optional[str] = None,
    target_server_ids: Optional[str] = None,
):
    """Returns the source->target item mapping for this group -- the
    "confirm mappings" section the user directly asked for. Defaults to the
    group's own SAVED mirror config's source/targets, but accepts explicit
    overrides so the UI can preview a mapping before the config is saved."""
    group = get_library_group_for(server_id, library_id, media_type)
    if not group:
        raise HTTPException(404, "No Library Group found for this library")

    mirror = group.get("mirror") or {}
    src = source_server_id or mirror.get("sourceServerId")
    targets = target_server_ids.split(",") if target_server_ids else (mirror.get("targetServerIds") or [])
    targets = [t for t in targets if t]

    if not src or not targets:
        return {"mapping": [], "source_server_id": src, "target_server_ids": targets}

    mapping = _resolve_mapping(group, media_type, src, targets)
    return {"mapping": mapping, "source_server_id": src, "target_server_ids": targets}


def _download_and_normalize(source_client, source_rating_key: str, asset_type: str) -> Optional[tuple]:
    """Downloads the source server's CURRENT image of this type and
    normalizes it through the same PIL functions every other send path in
    this app already uses (Quirk #69). Returns (bytes, content_type), or
    None if the source has no image of this type set."""
    image_type = _ASSET_TYPE_MAP[asset_type]
    raw = source_client.download_image(source_rating_key, image_type)
    if not raw:
        return None
    from .save import encode_poster_for_plex, normalize_logo_for_plex, normalize_backdrop_for_plex
    if asset_type == "poster":
        try:
            img = Image.open(BytesIO(raw))
            img.load()
        except Exception as e:
            logger.warning("[MIRROR] Could not decode source poster bytes for %s: %s", source_rating_key, e)
            return None
        return encode_poster_for_plex(img)
    if asset_type == "logo":
        return normalize_logo_for_plex(raw)
    # backdrop and square_art both get the same treatment -- Quirk #44's own
    # established reasoning ("the same kind of large photographic image").
    return normalize_backdrop_for_plex(raw)


def _run_mirror(server_id: str, library_id: str, media_type: str):
    key = _status_key(server_id, library_id, media_type)
    _update_status(key, {
        "state": "running", "total": 0, "processed": 0, "current": "",
        "updated": 0, "skipped": 0, "unmapped": 0, "failed": 0, "error": None,
    })
    try:
        group = get_library_group_for(server_id, library_id, media_type)
        if not group:
            raise ValueError("No Library Group found for this library")
        mirror = group.get("mirror") or {}
        if not mirror.get("enabled"):
            raise ValueError("Media Mirror is not enabled for this group")
        source_server_id = mirror.get("sourceServerId")
        target_server_ids = [t for t in (mirror.get("targetServerIds") or []) if t]
        asset_types = [a for a in (mirror.get("assetTypes") or []) if a in _ASSET_TYPE_MAP]
        if not source_server_id or not target_server_ids or not asset_types:
            raise ValueError("Media Mirror is missing a source server, target server(s), or asset type(s)")

        source_client = get_client(source_server_id)
        if not source_client:
            raise ValueError(f"Source server '{source_server_id}' is not configured/enabled")
        target_clients = {}
        for target_id in target_server_ids:
            client = get_client(target_id)
            if client:
                target_clients[target_id] = client
            else:
                logger.warning("[MIRROR] Target server '%s' is not configured/enabled -- skipping it this run", target_id)

        mapping = _resolve_mapping(group, media_type, source_server_id, target_server_ids)
        unmapped_titles: List[str] = []

        updated = skipped = unmapped = failed = 0
        total = len(mapping)
        _update_status(key, {"total": total})

        for idx, entry in enumerate(mapping, start=1):
            title = entry.get("title") or entry.get("source_rating_key") or ""
            _update_status(key, {"processed": idx - 1, "current": title})

            real_targets = {t: rk for t, rk in entry.get("targets", {}).items() if rk and t in target_clients}
            if not real_targets:
                unmapped += 1
                unmapped_titles.append(title)
                continue

            source_rating_key = entry.get("source_rating_key")
            item_touched = False
            item_failed = False
            for asset_type in asset_types:
                try:
                    result = _download_and_normalize(source_client, source_rating_key, asset_type)
                except Exception as e:
                    logger.warning("[MIRROR] Failed to fetch/normalize %s for '%s': %s", asset_type, title, e)
                    item_failed = True
                    continue
                if result is None:
                    continue  # source has no image of this type -- nothing to mirror
                image_bytes, content_type = result
                for target_id, target_rating_key in real_targets.items():
                    try:
                        target_clients[target_id].upload_image(
                            target_rating_key, _ASSET_TYPE_MAP[asset_type], image_bytes, content_type,
                        )
                        item_touched = True
                    except NotImplementedError:
                        # e.g. square_art has no Jellyfin/Emby equivalent (Quirk #59) -- a
                        # routine, expected skip for this one target, not a real failure.
                        logger.info(
                            "[MIRROR] %s not supported on %s, skipping for '%s'", asset_type, target_id, title,
                        )
                    except Exception as e:
                        logger.warning("[MIRROR] Failed to upload %s for '%s' to %s: %s", asset_type, title, target_id, e)
                        item_failed = True

            if item_failed:
                failed += 1
            elif item_touched:
                updated += 1
            else:
                skipped += 1

        _update_status(key, {
            "processed": total, "state": "done",
            "updated": updated, "skipped": skipped, "unmapped": unmapped, "failed": failed,
        })

        from datetime import datetime, timezone
        mirror["lastRunAt"] = datetime.now(timezone.utc).isoformat()
        # unmapped_titles capped at 25 for storage -- the full accurate count is
        # in "unmapped" above; the mapping endpoint itself (which the UI already
        # calls) is the real source of truth for exactly which items are
        # unmapped, this is just a quick-glance sample for the run summary.
        mirror["lastRunStats"] = {
            "checked": total, "updated": updated, "skipped": skipped,
            "unmapped": unmapped, "failed": failed,
            "unmappedSample": unmapped_titles[:25],
        }
        db.set_library_group_mirror_config(server_id, library_id, media_type, mirror)

        # Deliberately NOT sending a notification for unmapped items on a manual
        # run -- the user is already looking at this run's results in the UI, and
        # the mapping-confirmation view surfaces the exact same information. A
        # real notification (matching the user's explicit "skip and notify"
        # choice) belongs on the SCHEDULED run instead, where nobody's watching --
        # that's part of the scheduler follow-up, not this manual-run slice, so
        # it can be built against the real notification-settings shape
        # (ui_settings["notifications"], not guessed) rather than rushed here.
        if unmapped_titles:
            logger.info("[MIRROR] %d unmapped item(s) in group '%s': %s%s",
                        unmapped, group.get("name") or library_id, ", ".join(unmapped_titles[:5]),
                        f" (+{len(unmapped_titles) - 5} more)" if len(unmapped_titles) > 5 else "")

        logger.info("[MIRROR] Run complete for group '%s': %d updated, %d skipped, %d unmapped, %d failed",
                    group.get("name") or library_id, updated, skipped, unmapped, failed)
    except Exception as e:
        logger.error("[MIRROR] Run failed for %s: %s", key, e)
        _update_status(key, {"state": "error", "error": str(e)})


class MirrorRunRequest(BaseModel):
    server_id: str = "plex-1"
    library_id: str
    media_type: str


@router.post("/run")
def api_run_mirror(req: MirrorRunRequest):
    key = _status_key(req.server_id, req.library_id, req.media_type)
    with mirror_status_lock:
        if mirror_status.get(key, {}).get("state") == "running":
            raise HTTPException(409, "A mirror run is already in progress for this group")
    thread = threading.Thread(target=_run_mirror, args=(req.server_id, req.library_id, req.media_type), daemon=True)
    thread.start()
    return {"status": "started"}


@router.get("/run-status")
def api_mirror_run_status(server_id: str = "plex-1", library_id: str = "", media_type: str = "movie"):
    key = _status_key(server_id, library_id, media_type)
    with mirror_status_lock:
        return mirror_status.get(key, {"state": "idle"})
