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


def _has_overlays(options: Dict[str, Any], template_id: Optional[str] = None) -> bool:
    """Did this send use any overlay? Its own overlay lists, or the preset's old
    single overlay link. A send with a preset but no overlays isn't tracked:
    a tracked poster only ever has the overlays it was sent with, so it could
    never change."""
    if options.get("overlay_config_ids") or options.get("overlay_config_ids_below"):
        return True
    preset_id = options.get("preset_id")
    if preset_id and template_id:
        try:
            return bool((db.get_preset(template_id, preset_id) or {}).get("overlay_config_id"))
        except Exception:
            return False
    return False


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


def _summary(options: Dict[str, Any], template_id: str, facts: Optional[dict] = None,
             designs: Optional[dict] = None) -> List[dict]:
    from .templates.universal import overlay_summary
    return overlay_summary(options, template_id, facts, designs)


def _drawn_designs(summary: List[dict], designs: Dict[str, Any]) -> Dict[str, Any]:
    """Look settings of the layers the summary draws, keyed by design hash
    (stored with the send so a later check can say what was restyled)."""
    wanted = {e.get("design") for e in summary}
    return {k: v for k, v in designs.items() if k in wanted}


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
        if not _has_overlays(opts, template_id):
            db.delete_overlay_state(server_id, rating_key, season_index)
            return
        if _self_referencing_background(background_url):
            logger.debug("[OVERLAY_REFRESH] Not tracking %s: background is the server's own poster", rating_key)
            return
        facts: Dict[str, Any] = {}
        designs: Dict[str, Any] = {}
        summary = _summary(opts, template_id, facts, designs)
        if not summary:
            # Overlays configured but nothing applied to this item: still track
            # it, so a later change (new resolution, rating) can add one.
            pass
        from .templates.universal import overlay_signature
        meta = opts.get("metadata") or {}
        stored_opts = {k: v for k, v in opts.items() if k != "metadata"}
        stored_opts["_base_metadata"] = {k: v for k, v in meta.items() if k not in _INJECTED_KEYS}
        stored_opts["_facts"] = facts
        stored_opts["_designs"] = _drawn_designs(summary, designs)
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
    opts.pop("_facts", None)
    opts.pop("_designs", None)
    opts["metadata"] = base_meta
    inject_plex_media_metadata(
        opts,
        state.get("meta_rating_key") or state.get("rating_key"),
        tmdb_id=state.get("tmdb_id"),
        is_tv=state.get("media_type") == "tv",
        log_prefix="[OVERLAY_REFRESH] ",
    )
    return opts


def _list_name(key: str) -> str:
    try:
        cached = db.get_list_cache(key) or {}
        if cached.get("title"):
            return str(cached["title"])
    except Exception:
        pass
    return key.rstrip("/").rsplit("/", 1)[-1] or key


def _state_conditions(state: Dict[str, Any]) -> List[dict]:
    """Every condition in the overlays this poster was sent with (layers and
    whole overlays)."""
    conds: List[dict] = []
    for cid in state_overlay_ids(state):
        cfg = db.get_overlay_config(cid) or {}
        conds += [c for c in cfg.get("conditions") or [] if isinstance(c, dict)]
        for el in cfg.get("elements") or []:
            if isinstance(el, dict):
                conds += [c for c in el.get("conditions") or [] if isinstance(c, dict)]
    return conds


def _describe_facts(old: Optional[Dict[str, Any]], new: Dict[str, Any], conditions: List[dict]) -> str:
    """What changed in the data the overlays check, e.g. "now on list Trending;
    Audience rating 8.4 → 8.6", limited to changes that flip one of the
    overlays' rules (a rating moving within a band isn't named). Empty when
    nothing was recorded before (posters sent before this was tracked)."""
    if old is None:
        return ""
    from .overlay_engine import FIELD_LABELS, fields_that_flipped
    flipped = fields_that_flipped(conditions, old, new)
    parts = []
    for field in list(new.keys()) + [f for f in old.keys() if f not in new]:
        before, after = list(old.get(field) or []), list(new.get(field) or [])
        if field not in flipped or before == after:
            continue
        gained = [v for v in after if v not in before]
        lost = [v for v in before if v not in after]
        if field == "list":
            parts += [f"now on list {_list_name(v)}" for v in gained]
            parts += [f"no longer on list {_list_name(v)}" for v in lost]
        elif field == "label":
            parts += [f"label {v} added" for v in gained] + [f"label {v} removed" for v in lost]
        elif field == "filepath":
            parts.append("file changed" + (f" to {after[0]}" if len(after) == 1 else ""))
        else:
            label = FIELD_LABELS.get(field, field.replace("_", " "))
            parts.append(f"{label} {', '.join(before) or '—'} → {', '.join(after) or '—'}")
    return "; ".join(parts)


# What a changed layer setting means to a person, by key (first match wins).
_DESIGN_WORDS = [
    ("position", ("position_x", "position_y", "anchor", "horizontal_align", "vertical_align",
                  "horizontal_offset", "vertical_offset", "queue", "queue_positions")),
    ("size", ("scale", "max_width", "max_height", "font_size", "addon_scale", "width", "height")),
    ("image", ("asset_id", "url", "image", "badge_assets", "full_cover")),
    ("text", ("text",)),
    ("font", ("font_family", "font_path", "font_weight", "font_style")),
    ("outline", ("stroke_width", "stroke_color")),
    ("background box", ("back_",)),
    ("color", ("color", "font_color", "text_color", "opacity")),
]


def _design_change_words(old: Optional[dict], new: Optional[dict]) -> List[str]:
    """Which kinds of settings differ between two layer looks, e.g.
    ["position", "color"]. Empty when either side is unknown."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return []
    words: List[str] = []
    for k in sorted(set(old) | set(new)):
        if old.get(k) == new.get(k):
            continue
        word = "settings"
        for name, keys in _DESIGN_WORDS:
            if any(k == key or (key.endswith("_") and k.startswith(key)) for key in keys):
                word = name
                break
        if word not in words:
            words.append(word)
    return words


def _describe_change(old: List[dict], new: List[dict],
                     old_designs: Optional[Dict[str, Any]] = None,
                     new_designs: Optional[Dict[str, Any]] = None) -> str:
    """What the overlays draw differently, e.g. "now shows bg_mid; no longer
    shows bg_low; Resolution: 1080 → 4k; Trending restyled (position)"."""
    old_designs = old_designs or {}
    new_designs = new_designs or {}
    old_by = {e.get("label"): e for e in old}
    new_by = {e.get("label"): e for e in new}
    parts: List[str] = []
    for label, e in new_by.items():
        before = old_by.get(label)
        if before is None:
            continue
        if before.get("value") != e.get("value"):
            parts.append(f"{label}: {before.get('value') or '—'} → {e.get('value') or '—'}")
        elif before.get("design") != e.get("design"):
            words = _design_change_words(old_designs.get(before.get("design")), new_designs.get(e.get("design")))
            parts.append(f"{label} restyled" + (f" ({', '.join(words)})" if words else ""))
    shown = [str(lbl) for lbl in new_by if lbl not in old_by]
    gone = [str(lbl) for lbl in old_by if lbl not in new_by]
    lead = []
    if shown:
        lead.append("now shows " + ", ".join(shown))
    if gone:
        lead.append("no longer shows " + ", ".join(gone))
    parts = lead + parts
    if not parts:
        parts.append("layer order changed")
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
    facts: Dict[str, Any] = {}
    designs: Dict[str, Any] = {}
    summary = _summary(opts, state["template_id"], facts, designs)
    designs = _drawn_designs(summary, designs)
    sig = overlay_signature(summary)
    stored_opts = state.get("options") or {}
    changed = sig != state.get("signature")
    reason = ""
    if changed and "_designs" not in stored_opts and _same_layers(state.get("summary") or [], summary):
        # Recorded before layer looks were stored (and before show-when rules
        # were left out of the look): the same layers with the same values is
        # treated as unchanged and the record is moved to the new form.
        changed = False
        try:
            db.upsert_overlay_state({**state, "options": {**stored_opts, "_facts": facts, "_designs": designs},
                                     "summary": summary, "signature": sig})
            state["signature"] = sig
        except Exception as e:
            logger.debug("[OVERLAY_REFRESH] could not update record for %s: %s", state.get("rating_key"), e)
    if changed:
        layers = _describe_change(state.get("summary") or [], summary, stored_opts.get("_designs"), designs)
        cause = _describe_facts(stored_opts.get("_facts"), facts, _state_conditions(state))
        reason = f"{cause} → {layers}" if cause else layers
    return {
        "changed": changed,
        "options": opts,
        "summary": summary,
        "signature": sig,
        "facts": facts,
        "designs": designs,
        "reason": reason,
    }


def _same_layers(old: List[dict], new: List[dict]) -> bool:
    def key(e: dict) -> tuple:
        return (e.get("bucket"), e.get("label"), e.get("value"))
    return [key(e) for e in old] == [key(e) for e in new]


def _upload_tracked(client, server_id: str, state: Dict[str, Any], payload: bytes, content_type: str) -> str:
    """Upload a re-rendered poster for a tracked item. If Jellyfin/Emby
    re-imported the item under a new id, find it again by TMDb/TVDB id and
    retry once; the tracked row is moved to the new id (the database's
    re-key does that), so `state` is updated to match. Returns the id the
    poster was uploaded to."""
    from .api.media_server_send import _upload_poster_and_verify, is_not_found_error, refresh_stale_item_id
    rating_key = state["rating_key"]
    is_collection = bool(state.get("is_collection"))
    try:
        _upload_poster_and_verify(client, server_id, rating_key, payload, content_type, is_collection=is_collection)
        return rating_key
    except Exception as e:
        new_key = None
        if is_not_found_error(e) and not is_collection:
            new_key = refresh_stale_item_id(server_id, client, str(rating_key))
        if not new_key:
            raise
    _upload_poster_and_verify(client, server_id, new_key, payload, content_type, is_collection=is_collection)
    state["rating_key"] = new_key
    return new_key


def refresh_state(state: Dict[str, Any], checked: Optional[Dict[str, Any]] = None, source: str = "overlay_refresh") -> Dict[str, Any]:
    """Re-render one tracked poster from its stored source art and upload it.
    Returns {"status": "updated"|"failed", "detail": ...}."""
    from .rendering import render_poster_image
    from .api.save import encode_poster_for_plex
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
    rating_key = _upload_tracked(client, server_id, state, payload, content_type)

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
    stored_opts["_facts"] = checked.get("facts") or {}
    stored_opts["_designs"] = checked.get("designs") or {}
    db.upsert_overlay_state({
        **state,
        "options": stored_opts,
        "summary": checked["summary"],
        "signature": checked["signature"],
    })
    return {"status": "updated", "detail": checked["reason"] or "re-rendered"}


def remove_state(state: Dict[str, Any], source: str = "overlay_refresh") -> Dict[str, Any]:
    """Re-render one tracked poster from its stored source art with no
    overlays at all, upload it, drop the Plex label and stop tracking it (so a
    later refresh doesn't put the overlays back). The poster gets overlays
    again the next time it's sent with a preset that has them."""
    from .rendering import render_poster_image
    from .api.save import encode_poster_for_plex
    from .media_server import get_client
    from .save_paths import save_or_cache_render

    server_id = state["server_id"]
    rating_key = state["rating_key"]
    is_plex = server_id == "plex-1"
    client = get_client(server_id)
    if client is None:
        return {"status": "failed", "detail": f"server {server_id} is not configured"}
    if not state.get("background_url"):
        return {"status": "failed", "detail": "no source image recorded"}

    opts = _fresh_options(state)
    opts["overlay_config_ids"] = []
    opts["overlay_config_ids_below"] = []
    # The preset's legacy single overlay link is read through preset_id.
    opts.pop("preset_id", None)
    img = render_poster_image(state["template_id"], state["background_url"], state.get("logo_url"), opts)
    payload, content_type = encode_poster_for_plex(img, for_plex=is_plex)
    rating_key = _upload_tracked(client, server_id, state, payload, content_type)

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
            action="overlay_removed",
            source=source,
            poster_data=payload,
            server_id=server_id,
        )
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] history write failed for %s: %s", rating_key, e)

    if is_plex:
        label = _refresh_label(_group_for_library(server_id, state.get("library_id"), state.get("media_type") or "movie"))
        if label:
            _apply_plex_label(rating_key, label, False)

    db.delete_overlay_state(server_id, rating_key, state.get("season_index"))
    return {"status": "removed", "detail": "overlays removed"}


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


def prune_without_overlays(pairs: Optional[List[tuple]] = None) -> int:
    """Stop tracking posters that were sent without any overlay (tracked by
    versions before v1.8.17). They can never change, so they only clutter
    Overlay Refresh. pairs limits it to some (server_id, library_id) pairs."""
    removed = 0
    try:
        states = db.get_overlay_states(pairs) if pairs is not None else db.get_all_overlay_states()
        for state in states:
            if not state_overlay_ids(state):
                db.delete_overlay_state(state["server_id"], state["rating_key"], state.get("season_index"))
                removed += 1
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] Prune failed: %s", e)
    if removed:
        logger.info("[OVERLAY_REFRESH] Stopped tracking %d poster(s) that were sent without overlays", removed)
    return removed


def prepare_data(states: List[Dict[str, Any]]) -> Dict[str, int]:
    """Before a run checks posters: fetch the lists and ratings its overlays use
    that are past their refresh time (Overlay Manager > Scheduler), so the run
    sees them. Everything still fresh comes from the cache with no API call."""
    out = {"lists": 0, "ratings": 0}
    try:
        from . import list_sources, overlay_engine
        elements: List[Dict[str, Any]] = []
        seen = set()
        for state in states:
            for cid in state_overlay_ids(state):
                if cid in seen:
                    continue
                seen.add(cid)
                cfg = db.get_overlay_config(cid) or {}
                elements.extend(e for e in cfg.get("elements") or [] if isinstance(e, dict))
                if cfg.get("conditions"):
                    elements.append({"conditions": cfg["conditions"]})
        if not elements:
            return out
        needs = overlay_engine.needed_data(elements)
        if needs["lists"]:
            out["lists"] = list_sources.refresh_due(needs["lists"])
        if needs["ratings"]:
            from . import mdblist_client as mdb
            if mdb.has_key():
                for kind, media in (("movie", "movie"), ("show", "tv")):
                    ids = [s.get("tmdb_id") for s in states if s.get("media_type") == media and s.get("tmdb_id")]
                    if ids:
                        out["ratings"] += mdb.prefetch_ratings(kind, ids)
    except Exception as e:
        logger.info("[OVERLAY_REFRESH] Updating lists/ratings before the run failed: %s", e)
    if out["lists"] or out["ratings"]:
        logger.info("[OVERLAY_REFRESH] Updated %d list(s) and %d rating(s) before checking", out["lists"], out["ratings"])
    return out


data_refresh_status: Dict[str, Any] = {"state": "idle"}


def refresh_all_data() -> Dict[str, Any]:
    """Overlays → Scheduler → "Refresh now": fetch every list any overlay uses
    and the ratings of every tracked poster whose overlays use a rating,
    regardless of their age. Doesn't re-render anything."""
    from . import list_sources, overlay_engine
    out: Dict[str, Any] = {"lists": 0, "ratings": 0}
    data_refresh_status.update({"state": "running", "lists": 0, "ratings": 0, "error": None,
                                "started_at": datetime.now().isoformat(timespec="seconds")})
    try:
        elements: List[Dict[str, Any]] = []
        for cfg in db.get_all_overlay_configs():
            elements.extend(e for e in cfg.get("elements") or [] if isinstance(e, dict))
            if cfg.get("conditions"):
                elements.append({"conditions": cfg["conditions"]})
        needs = overlay_engine.needed_data(elements)
        if needs["lists"]:
            out["lists"] = list_sources.refresh_due(needs["lists"], force=True)
            data_refresh_status["lists"] = out["lists"]
        from . import mdblist_client as mdb
        if mdb.has_key():
            states = db.get_all_overlay_states()
            by_config: Dict[str, bool] = {}
            for kind, media in (("movie", "movie"), ("show", "tv")):
                ids = []
                for s in states:
                    if s.get("media_type") != media or not s.get("tmdb_id"):
                        continue
                    for cid in state_overlay_ids(s):
                        if cid not in by_config:
                            cfg = db.get_overlay_config(cid) or {}
                            els = [e for e in cfg.get("elements") or [] if isinstance(e, dict)]
                            if cfg.get("conditions"):
                                els.append({"conditions": cfg["conditions"]})
                            by_config[cid] = bool(overlay_engine.needed_data(els)["ratings"])
                        if by_config[cid]:
                            ids.append(s["tmdb_id"])
                            break
                if ids:
                    out["ratings"] += mdb.prefetch_ratings(kind, ids, force=True)
                    data_refresh_status["ratings"] = out["ratings"]
        logger.info("[OVERLAY_REFRESH] Refreshed %d list(s) and %d rating(s) on request", out["lists"], out["ratings"])
        data_refresh_status.update({"state": "done", **out, "finished_at": datetime.now().isoformat(timespec="seconds")})
    except Exception as e:
        logger.warning("[OVERLAY_REFRESH] Refreshing lists/ratings failed: %s", e)
        data_refresh_status.update({"state": "error", "error": str(e)})
    return out


def start_data_refresh() -> bool:
    """refresh_all_data() in a background thread. False if one is already running."""
    with run_status_lock:
        if data_refresh_status.get("state") == "running":
            return False
        data_refresh_status["state"] = "running"
    threading.Thread(target=refresh_all_data, daemon=True).start()
    return True


def run_group(group_id: str, apply: bool, only_keys: Optional[List[str]] = None,
              force: bool = False, scheduled: bool = False, remove: bool = False) -> Dict[str, Any]:
    """Check (apply=False) or check-and-refresh (apply=True) every tracked
    poster in one group, or with remove=True re-send them without overlays.
    Progress goes to run_status[group_id]."""
    run_id = uuid.uuid4().hex[:12]
    apply = apply or remove
    mode = "remove" if remove else ("apply" if apply else "check")
    _update_status(group_id, {
        "state": "running", "mode": mode, "run_id": run_id, "total": 0, "processed": 0,
        "current": "", "changed": 0, "updated": 0, "unchanged": 0, "failed": 0, "removed": 0,
        "error": None, "items": [], "started_at": datetime.now().isoformat(timespec="seconds"),
    })
    group = None
    log_entries: List[Dict[str, Any]] = []
    try:
        group = find_group(group_id)
        if not group:
            raise ValueError("Library group not found")
        prune_without_overlays(group_pairs(group))
        states = db.get_overlay_states(group_pairs(group))
        if only_keys is not None:
            wanted = set(only_keys)
            states = [s for s in states if state_key(s) in wanted]
        if not remove:
            _update_status(group_id, {"current": "Updating lists and ratings"})
            prepare_data(states)
        _update_status(group_id, {"total": len(states)})
        items: List[Dict[str, Any]] = []
        counts = {"changed": 0, "updated": 0, "unchanged": 0, "failed": 0, "removed": 0}
        for i, state in enumerate(states):
            title = _display_title(state)
            _update_status(group_id, {"processed": i, "current": title})
            entry = {
                "key": state_key(state), "server_id": state["server_id"], "rating_key": state["rating_key"],
                "season_index": state.get("season_index"), "title": title,
            }
            try:
                if remove:
                    result = remove_state(state, source="overlay_refresh")
                    entry["status"] = result["status"]
                    entry["reason"] = result["detail"]
                    if result["status"] == "removed":
                        counts["removed"] += 1
                    else:
                        counts["failed"] += 1
                    items.append(entry)
                    log_entries.append({
                        "server_id": entry["server_id"], "rating_key": entry["rating_key"],
                        "season_index": entry["season_index"], "title": title,
                        "status": entry["status"], "detail": entry["reason"],
                    })
                    _update_status(group_id, {**counts, "items": items[-500:]})
                    continue
                checked = check_state(state)
                if not checked["changed"] and not force:
                    counts["unchanged"] += 1
                    # Posters tracked before the checked values were recorded:
                    # record them now, so the next change can say what changed.
                    if "_facts" not in (state.get("options") or {}) or "_designs" not in (state.get("options") or {}):
                        try:
                            db.upsert_overlay_state({
                                **state,
                                "options": {**(state.get("options") or {}), "_facts": checked["facts"], "_designs": checked["designs"]},
                                "summary": checked["summary"],
                                "signature": checked["signature"],
                            })
                        except Exception as e:
                            logger.debug("[OVERLAY_REFRESH] recording checked values for %s failed: %s", title, e)
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
              force: bool = False, scheduled: bool = False, remove: bool = False) -> bool:
    """Start run_group() in a background thread. False if one is already running."""
    with run_status_lock:
        if (run_status.get(group_id) or {}).get("state") == "running":
            return False
        run_status.setdefault(group_id, {})["state"] = "running"
    threading.Thread(target=run_group, args=(group_id, apply, only_keys, force, scheduled, remove), daemon=True).start()
    return True


def _notify(group: dict, stats: Dict[str, int], items: List[Dict[str, Any]], scheduled: bool) -> None:
    """Summary notification; a scheduled run that changed nothing stays quiet."""
    if scheduled and not stats.get("updated") and not stats.get("failed") and not stats.get("removed"):
        return
    try:
        from .api.notifications import send_overlay_refresh_notification
        send_overlay_refresh_notification(group, stats, items, scheduled)
    except Exception as e:
        logger.debug("[OVERLAY_REFRESH] notification failed: %s", e)
