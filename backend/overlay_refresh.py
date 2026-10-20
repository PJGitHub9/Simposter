"""Overlay refresh (Quirk #166).

Every time Simposter sends a poster that has overlays, it records what went
into that render (source art, template/preset, options) and a summary of what
the overlays drew (which elements, with which values). A per-library-group
check then rebuilds that summary from the item's current data (scan cache,
MDBList, current overlay configs) and, when it differs, re-renders the poster
from the same source art and uploads it again -- the same idea as Kometa
re-applying overlays, without needing the poster Plex currently has.

Plex items additionally get a label (default "Simposter-Overlay") so they can
be found in Plex; Jellyfin/Emby have no labels here, so every change is also
written to the overlay refresh log.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .config import logger
from . import database as db

DEFAULT_LABEL = "Simposter-Overlay"

# Metadata keys inject_plex_media_metadata() (re)computes -- a stored send's
# metadata keeps everything else (season text etc.) and refreshes these.
_INJECTED_KEYS = {
    "rating_key", "video_resolution", "video_codec", "audio_codec", "audio_channels",
    "audio_language", "edition", "tmdb_id", "media_type", "streaming_platform",
    "streaming_platform_logo_url", "studio", "studio_company_id", "file_paths", "lists",
}

_INTERNAL_POSTER_MARKERS = ("/api/movie/", "/api/tv-show/")


def _has_overlays(options: Dict[str, Any]) -> bool:
    return bool(options.get("overlay_config_ids")) or bool(options.get("preset_id"))


def _self_referencing_background(url: Optional[str]) -> bool:
    """A background that is the server's own current poster already carries
    the old overlay (Quirk #43) -- re-rendering on top of it would stack them."""
    u = (url or "").lower()
    return any(m in u for m in _INTERNAL_POSTER_MARKERS) and "/poster" in u


def _group_for_library(server_id: str, library_id: Optional[str], media_type: str) -> Optional[dict]:
    if not library_id:
        return None
    try:
        from .config import get_library_group_for
        return get_library_group_for(server_id, str(library_id), media_type)
    except Exception:
        return None


def library_in_group(source_server_id: str, library_id: Optional[str], media_type: str,
                     target_server_id: str) -> Optional[str]:
    """The library id `target_server_id` has in the same group as
    (source_server_id, library_id) -- for recording a poster synced to
    another server under that server's own library."""
    if target_server_id == source_server_id:
        return str(library_id) if library_id is not None else None
    group = _group_for_library(source_server_id, library_id, media_type)
    for m in (group or {}).get("members") or []:
        if m.get("serverId") == target_server_id:
            return str(m.get("libraryId"))
    return None


def _refresh_label(group: Optional[dict]) -> str:
    cfg = (group or {}).get("overlayRefresh") or {}
    if not cfg.get("enabled"):
        return ""
    label = cfg.get("plexLabel")
    return DEFAULT_LABEL if label is None else str(label).strip()


def _summary(options: Dict[str, Any], template_id: str) -> List[dict]:
    from .templates.universal import overlay_summary
    return overlay_summary(options, template_id)


def record_send(
    server_id: str,
    rating_key: str,
    *,
    template_id: Optional[str],
    options: Optional[Dict[str, Any]],
    background_url: Optional[str],
    logo_url: Optional[str],
    media_type: str = "movie",
    library_id: Optional[str] = None,
    season_index: Optional[int] = None,
    tmdb_id: Optional[Any] = None,
    title: Optional[str] = None,
    year: Optional[Any] = None,
    is_collection: bool = False,
    add_label: bool = True,
) -> None:
    """Remember the inputs of a poster just sent to `server_id`. Never raises."""
    try:
        if not rating_key or not template_id:
            return
        opts = dict(options or {})
        if not _has_overlays(opts):
            db.delete_overlay_state(server_id, rating_key, season_index)
            return
        if _self_referencing_background(background_url):
            logger.debug("[OVERLAY_REFRESH] Not tracking %s: background is the server's own poster", rating_key)
            return
        summary = _summary(opts, template_id)
        if not summary:
            # Overlays configured but nothing applied to this item: still track
            # it, so a later change (new resolution, rating) can add one.
            pass
        from .templates.universal import overlay_signature
        meta = opts.get("metadata") or {}
        stored_opts = {k: v for k, v in opts.items() if k != "metadata"}
        stored_opts["_base_metadata"] = {k: v for k, v in meta.items() if k not in _INJECTED_KEYS}
        try:
            tmdb_val = int(tmdb_id) if tmdb_id not in (None, "") else (int(meta["tmdb_id"]) if meta.get("tmdb_id") else None)
        except (TypeError, ValueError):
            tmdb_val = None
        try:
            year_val = int(year) if year not in (None, "") else None
        except (TypeError, ValueError):
            year_val = None
        db.upsert_overlay_state({
            "server_id": server_id,
            "rating_key": str(rating_key),
            "season_index": season_index,
            "media_type": "tv" if media_type in ("tv", "tv-show", "show") else "movie",
            "library_id": library_id,
            "tmdb_id": tmdb_val,
            "title": title,
            "year": year_val,
            "meta_rating_key": meta.get("rating_key") or rating_key,
            "template_id": template_id,
            "preset_id": opts.get("preset_id"),
            "background_url": background_url,
            "logo_url": logo_url,
            "options": stored_opts,
            "summary": summary,
            "signature": overlay_signature(summary),
            "is_collection": is_collection,
        })
        if add_label and server_id == "plex-1" and summary:
            label = _refresh_label(_group_for_library(server_id, library_id, "tv" if media_type in ("tv", "tv-show", "show") else "movie"))
            if label:
                _apply_plex_label(str(rating_key), label, True)
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] record_send failed for %s/%s: %s", server_id, rating_key, e)


def _apply_plex_label(rating_key: str, label: str, present: bool) -> None:
    try:
        from .config import plex_add_label, plex_remove_label
        if present:
            plex_add_label(rating_key, label)
        else:
            plex_remove_label(rating_key, label)
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] Plex label %s on %s failed: %s", "add" if present else "remove", rating_key, e)


def _fresh_options(state: Dict[str, Any]) -> Dict[str, Any]:
    """The stored render options with metadata rebuilt from the item's current
    cached data, the same way a send builds it."""
    from .config import inject_plex_media_metadata
    opts = dict(state.get("options") or {})
    base_meta = dict(opts.pop("_base_metadata", None) or {})
    opts["metadata"] = base_meta
    inject_plex_media_metadata(
        opts,
        state.get("meta_rating_key") or state.get("rating_key"),
        tmdb_id=state.get("tmdb_id"),
        is_tv=state.get("media_type") == "tv",
        log_prefix="[OVERLAY_REFRESH] ",
    )
    return opts


def _describe_change(old: List[dict], new: List[dict]) -> str:
    def key(e: dict) -> str:
        return f"{e.get('label')}" + (f" = {e.get('value')}" if e.get("value") else "")

    old_keys = [key(e) for e in old]
    new_keys = [key(e) for e in new]
    added = [k for k in new_keys if k not in old_keys]
    removed = [k for k in old_keys if k not in new_keys]
    parts = []
    # Same element, different value: "Resolution: 1080 → 4k".
    old_by_label = {e.get("label"): e.get("value") for e in old}
    new_by_label = {e.get("label"): e.get("value") for e in new}
    for label, value in new_by_label.items():
        if label in old_by_label and old_by_label[label] != value:
            parts.append(f"{label}: {old_by_label[label] or '—'} → {value or '—'}")
            added = [k for k in added if not (k == label or k.startswith(f"{label} = "))]
            removed = [k for k in removed if not (k == label or k.startswith(f"{label} = "))]
    if added:
        parts.append("added " + ", ".join(added))
    if removed:
        parts.append("removed " + ", ".join(removed))
    if not parts:
        parts.append("overlay design changed")
    return "; ".join(parts)


def _display_title(state: Dict[str, Any]) -> str:
    title = state.get("title") or state.get("rating_key") or "?"
    if state.get("season_index") is not None:
        si = state["season_index"]
        title = f"{title} - {'Specials' if si == 0 else f'Season {si}'}"
    if state.get("year"):
        title = f"{title} ({state['year']})"
    return title


def check_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Compare a tracked poster's recorded overlay with what it would get now."""
    from .templates.universal import overlay_signature
    opts = _fresh_options(state)
    summary = _summary(opts, state["template_id"])
    sig = overlay_signature(summary)
    changed = sig != state.get("signature")
    return {
        "changed": changed,
        "options": opts,
        "summary": summary,
        "signature": sig,
        "reason": _describe_change(state.get("summary") or [], summary) if changed else "",
    }


def refresh_state(state: Dict[str, Any], checked: Optional[Dict[str, Any]] = None, source: str = "overlay_refresh") -> Dict[str, Any]:
    """Re-render one tracked poster from its stored source art and upload it.
    Returns {"status": "updated"|"failed", "detail": ...}."""
    from .rendering import render_poster_image
    from .api.save import encode_poster_for_plex
    from .api.media_server_send import _upload_poster_and_verify
    from .media_server import get_client
    from .save_paths import save_or_cache_render

    checked = checked or check_state(state)
    server_id = state["server_id"]
    rating_key = state["rating_key"]
    is_plex = server_id == "plex-1"
    client = get_client(server_id)
    if client is None:
        return {"status": "failed", "detail": f"server {server_id} is not configured"}
    if not state.get("background_url"):
        return {"status": "failed", "detail": "no source image recorded"}

    opts = checked["options"]
    img = render_poster_image(state["template_id"], state["background_url"], state.get("logo_url"), opts)
    payload, content_type = encode_poster_for_plex(img, for_plex=is_plex)
    _upload_poster_and_verify(client, server_id, rating_key, payload, content_type,
                              is_collection=bool(state.get("is_collection")))

    try:
        save_or_cache_render(rating_key, payload, None)
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] resend cache update failed for %s: %s", rating_key, e)

    try:
        db.record_poster_history(
            rating_key=rating_key,
            library_id=state.get("library_id"),
            title=_display_title({**state, "year": None}),
            year=state.get("year"),
            template_id=state["template_id"],
            preset_id=state.get("preset_id"),
            action="overlay_refresh",
            source=source,
            poster_data=payload,
            server_id=server_id,
        )
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] history write failed for %s: %s", rating_key, e)

    if is_plex:
        label = _refresh_label(_group_for_library(server_id, state.get("library_id"), state.get("media_type") or "movie"))
        if label:
            _apply_plex_label(rating_key, label, bool(checked["summary"]))

    stored_opts = dict(state.get("options") or {})
    db.upsert_overlay_state({
        **state,
        "options": stored_opts,
        "summary": checked["summary"],
        "signature": checked["signature"],
    })
    return {"status": "updated", "detail": checked["reason"] or "re-rendered"}


# ---------------------------------------------------------------------------
# Group runs
# ---------------------------------------------------------------------------

run_status: Dict[str, Dict[str, Any]] = {}
run_status_lock = threading.Lock()


def _update_status(group_id: str, updates: dict) -> None:
    with run_status_lock:
        run_status.setdefault(group_id, {}).update(updates)


def get_status(group_id: str) -> Dict[str, Any]:
    with run_status_lock:
        return dict(run_status.get(group_id) or {"state": "idle"})


def find_group(group_id: str) -> Optional[dict]:
    for g in (db.get_ui_settings() or {}).get("libraryGroups") or []:
        if g.get("id") == group_id:
            return g
    return None


def group_pairs(group: dict) -> List[tuple]:
    return [(m.get("serverId"), str(m.get("libraryId"))) for m in (group.get("members") or [])
            if m.get("serverId") and m.get("libraryId") is not None]


def state_overlay_ids(state: Dict[str, Any]) -> List[str]:
    """Overlay config ids a tracked poster was sent with (above and below the
    logo, plus a preset's legacy single link), in order, without repeats."""
    opts = state.get("options") or {}
    ids: List[str] = []
    for value in (opts.get("overlay_config_ids") or [], opts.get("overlay_config_ids_below") or []):
        for cid in value if isinstance(value, list) else [value]:
            if cid and str(cid) not in ids:
                ids.append(str(cid))
    if state.get("preset_id") and state.get("template_id"):
        try:
            preset = db.get_preset(state["template_id"], state["preset_id"])
            linked = (preset or {}).get("overlay_config_id")
            if linked and str(linked) not in ids:
                ids.append(str(linked))
        except Exception:
            pass
    return ids


def state_key(state: Dict[str, Any]) -> str:
    si = state.get("season_index")
    return f"{state['server_id']}:{state['rating_key']}:{-1 if si is None else si}"


def run_group(group_id: str, apply: bool, only_keys: Optional[List[str]] = None,
              force: bool = False, scheduled: bool = False) -> Dict[str, Any]:
    """Check (apply=False) or check-and-refresh (apply=True) every tracked
    poster in one group. Progress goes to run_status[group_id]."""
    run_id = uuid.uuid4().hex[:12]
    mode = "apply" if apply else "check"
    _update_status(group_id, {
        "state": "running", "mode": mode, "run_id": run_id, "total": 0, "processed": 0,
        "current": "", "changed": 0, "updated": 0, "unchanged": 0, "failed": 0,
        "error": None, "items": [], "started_at": datetime.now().isoformat(timespec="seconds"),
    })
    group = None
    log_entries: List[Dict[str, Any]] = []
    try:
        group = find_group(group_id)
        if not group:
            raise ValueError("Library group not found")
        states = db.get_overlay_states(group_pairs(group))
        if only_keys is not None:
            wanted = set(only_keys)
            states = [s for s in states if state_key(s) in wanted]
        _update_status(group_id, {"total": len(states)})
        items: List[Dict[str, Any]] = []
        counts = {"changed": 0, "updated": 0, "unchanged": 0, "failed": 0}
        for i, state in enumerate(states):
            title = _display_title(state)
            _update_status(group_id, {"processed": i, "current": title})
            entry = {
                "key": state_key(state), "server_id": state["server_id"], "rating_key": state["rating_key"],
                "season_index": state.get("season_index"), "title": title,
            }
            try:
                checked = check_state(state)
                if not checked["changed"] and not force:
                    counts["unchanged"] += 1
                    continue
                counts["changed"] += 1
                entry["reason"] = checked["reason"] or "forced"
                entry["overlay"] = [e.get("label") + (f" = {e['value']}" if e.get("value") else "") for e in checked["summary"]]
                if apply:
                    result = refresh_state(state, checked, source="scheduled" if scheduled else "overlay_refresh")
                    entry["status"] = result["status"]
                    if result["status"] == "updated":
                        counts["updated"] += 1
                    else:
                        counts["failed"] += 1
                        entry["reason"] = result["detail"]
                else:
                    entry["status"] = "changed"
            except Exception as e:
                counts["failed"] += 1
                entry["status"] = "failed"
                entry["reason"] = str(e)
                logger.warning("[OVERLAY_REFRESH] %s failed: %s", title, e)
            items.append(entry)
            if apply:
                log_entries.append({
                    "server_id": entry["server_id"], "rating_key": entry["rating_key"],
                    "season_index": entry["season_index"], "title": title,
                    "status": entry.get("status"), "detail": entry.get("reason"),
                })
            _update_status(group_id, {**counts, "items": items[-500:]})

        stats = {"checked": len(states), **counts}
        _update_status(group_id, {"state": "done", "processed": len(states), "current": "", **counts,
                                  "items": items[-500:], "finished_at": datetime.now().isoformat(timespec="seconds")})
        if apply:
            db.add_overlay_refresh_log(run_id, group_id, log_entries)
            cfg = dict(group.get("overlayRefresh") or {})
            cfg["lastRunAt"] = datetime.now().isoformat(timespec="seconds")
            cfg["lastRunStats"] = stats
            db.set_library_group_overlay_refresh(group_id, cfg)
            _notify(group, stats, items, scheduled)
        logger.info("[OVERLAY_REFRESH] %s run for group %s: %s", mode, group.get("name") or group_id, stats)
        return stats
    except Exception as e:
        logger.error("[OVERLAY_REFRESH] Run failed for group %s: %s", group_id, e)
        _update_status(group_id, {"state": "error", "error": str(e)})
        if apply and log_entries:
            db.add_overlay_refresh_log(run_id, group_id, log_entries)
        return {"error": str(e)}


def start_run(group_id: str, apply: bool, only_keys: Optional[List[str]] = None,
              force: bool = False, scheduled: bool = False) -> bool:
    """Start run_group() in a background thread. False if one is already running."""
    with run_status_lock:
        if (run_status.get(group_id) or {}).get("state") == "running":
            return False
        run_status.setdefault(group_id, {})["state"] = "running"
    threading.Thread(target=run_group, args=(group_id, apply, only_keys, force, scheduled), daemon=True).start()
    return True


def _notify(group: dict, stats: Dict[str, int], items: List[Dict[str, Any]], scheduled: bool) -> None:
    """Summary notification; a scheduled run that changed nothing stays quiet."""
    if scheduled and not stats.get("updated") and not stats.get("failed"):
        return
    try:
        from .api.notifications import send_overlay_refresh_notification
        send_overlay_refresh_notification(group, stats, items, scheduled)
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] notification failed: %s", e)
