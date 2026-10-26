# backend/live_kometa.py
"""Live Kometa files: overlay YAMLs on disk that another tool rewrites (e.g. UMTK
regenerating its upcoming/trending lists daily). Each one is re-read on a
schedule; when its contents change it is re-imported into the same overlay
config, and optionally Overlay Refresh re-renders the posters whose overlay
now comes out differently. Overlay Manager → Advanced → Live Kometa files.
"""
import hashlib
import threading
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from . import database as db
from . import kometa_import as ki
from .config import logger

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_FONT_EXT = {".ttf", ".otf"}
_lock = threading.Lock()  # one sync at a time (they share assets and configs)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_network_path(path: str) -> bool:
    """UNC/network paths (\\host\share, //host/share). Touching one makes
    Windows connect to that host and send the account's credentials, so the
    live-file picker and validate_path() never open them."""
    p = (path or "").strip().replace("\\", "/")
    return p.startswith("//")


def validate_path(path: str) -> Path:
    """The file must exist and be a .yml/.yaml file."""
    raw = str(path or "").strip()
    if is_network_path(raw):
        raise ValueError("Network paths aren't allowed; mount the share on the server and use its local path")
    p = Path(raw).expanduser()
    if p.suffix.lower() not in (".yml", ".yaml"):
        raise ValueError("Pick a .yml or .yaml file")
    if not p.is_file():
        raise ValueError(f"File not found on the Simposter server: {p}")
    return p


def _disk_finder(base: Path, allowed_ext: set):
    """find(wanted) for images/fonts a YAML refers to by path: tried as given,
    next to the YAML, and in the folders above it (Kometa paths are usually
    relative to its config folder)."""
    roots = [base, *list(base.parents)[:3]]

    def find(wanted: str) -> Optional[Tuple[str, bytes]]:
        rel = str(wanted).replace("\\", "/").lstrip("/")
        candidates = [Path(str(wanted))] + [r / rel for r in roots] + [base / PurePosixPath(rel).name]
        for c in candidates:
            try:
                if c.suffix.lower() in allowed_ext and c.is_file():
                    return c.name, c.read_bytes()
            except OSError:
                continue
        return None
    return find


def _image_finder(base: Path):
    """Images on disk (see _disk_finder), then the image library by file name."""
    from .api.kometa_import import chain_finders, library_image_finder
    return chain_finders(_disk_finder(base, _IMAGE_EXT), library_image_finder())


def _matching_groups(library_type: str) -> List[dict]:
    groups = (db.get_ui_settings() or {}).get("libraryGroups") or []
    groups = [g for g in groups if isinstance(g, dict) and g.get("id")]
    if library_type == "both":
        return groups
    media = "tv" if library_type == "show" else "movie"
    return [g for g in groups if (g.get("mediaType") or "movie") == media]


def sync_file(file_id: str, force: bool = False, scheduled: bool = False) -> Dict[str, Any]:
    """Re-read one live file. Re-imports when its contents changed (or force)."""
    live = db.get_live_kometa_file(file_id)
    if not live:
        return {"status": "error", "message": "Not found"}
    with _lock:
        return _sync(live, force, scheduled)


def _sync(live: Dict[str, Any], force: bool, scheduled: bool) -> Dict[str, Any]:
    fid = live["id"]

    def done(status: str, message: str, **extra: Any) -> Dict[str, Any]:
        db.update_live_kometa_status(fid, last_checked_at=_now(), last_status=status, last_message=message, **extra)
        (logger.warning if status == "error" else logger.info)("[LIVE KOMETA] %s: %s", live.get("path"), message)
        return {"status": status, "message": message}

    try:
        path = validate_path(live["path"])
        raw = path.read_bytes()
    except (ValueError, OSError) as e:
        return done("error", str(e))

    digest = hashlib.sha256(raw).hexdigest()
    if not force and digest == live.get("last_hash") and live.get("config_id") and db.get_overlay_config(live["config_id"]):
        return done("unchanged", "No changes since the last check")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    library_type = live.get("library_type") if live.get("library_type") in ("show", "both") else "movie"
    try:
        if library_type == "both":
            elements, report, file_messages = ki.expand_file_both(text, {str(path): text})
        else:
            elements, report, file_messages = ki.expand_file(text, library_type, {str(path): text})
    except ki.ImportError_ as e:
        return done("error", f"Couldn't read the file: {e}")

    from .api.kometa_import import _AssetSaver, finalize_elements, _remote_cache
    _remote_cache.clear()
    from .api.overlay_config import api_list_fonts
    saver = _AssetSaver(dry_run=False)
    available_fonts = {f.lower() for f in api_list_fonts().get("fonts", [])}
    missing: Dict[str, List[str]] = {}
    final_elements, _fonts = finalize_elements(
        elements, report, _image_finder(path.parent), _disk_finder(path.parent, _FONT_EXT),
        saver, False, available_fonts, {}, missing,
    )

    name = (live.get("name") or "").strip() or path.stem
    config_id = live.get("config_id") if live.get("config_id") and db.get_overlay_config(live["config_id"]) else None
    config_id = config_id or f"overlay-live-{uuid.uuid4().hex[:10]}"
    old = db.get_overlay_config(config_id)
    changed_layers = old is None or old.get("elements") != final_elements
    # conditions=None keeps any whole-overlay conditions set in the editor.
    db.save_overlay_config(config_id, name, final_elements, (old or {}).get("streaming_region") or "US")

    counts = {s: sum(1 for r in report if r.get("status") == s) for s in ("ok", "warning", "hidden", "skipped")}
    parts = [f"{len(final_elements)} layers"]
    if counts["hidden"]:
        parts.append(f"{counts['hidden']} hidden")
    if counts["skipped"]:
        # Group skipped overlays by reason so the status says why, not just how many.
        reasons: Dict[str, List[str]] = {}
        for r in report:
            if r.get("status") == "skipped":
                why = (r.get("messages") or ["no reason given"])[0]
                reasons.setdefault(why, []).append(str(r.get("name") or "?"))
        detail = "; ".join(
            f"{why}: {', '.join(names[:3])}{f' +{len(names) - 3} more' if len(names) > 3 else ''}"
            for why, names in reasons.items()
        )
        parts.append(f"{counts['skipped']} skipped ({detail})")
    if missing:
        parts.append(f"{len(missing)} image(s) not found")
    message = "Re-imported: " + ", ".join(parts)

    refreshed: List[str] = []
    if changed_layers and live.get("refresh_posters"):
        from . import overlay_refresh
        for group in _matching_groups(library_type):
            if overlay_refresh.start_run(group["id"], apply=True, scheduled=scheduled):
                refreshed.append(group.get("name") or group["id"])
        if refreshed:
            message += f"; refreshing posters in {', '.join(refreshed)}"
    elif not changed_layers:
        message += " (layers unchanged)"

    result = done("updated", message, config_id=config_id, last_hash=digest, last_changed_at=_now())
    result.update(config_id=config_id, refreshed_groups=refreshed, file_messages=file_messages)
    return result
