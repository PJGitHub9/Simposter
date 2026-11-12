"""Overlay-only posters (poster modes, mode "overlay_only").

Another app (e.g. Aura) owns the poster; Simposter only draws its overlays on
top of it. The other app's poster is kept as a "clean copy" in
config/cache/clean_base/ ({server}__{key}[__s{season}].{ext}), downloaded at
full size from the server. A clean copy is never a poster Simposter sent
itself (Quirk #43): when the server's poster matches the fingerprint of what
Simposter last sent, the art Simposter last rendered from (overlay_state's
background_url) is used as the base instead, without saving it as a clean copy.

After an upload: drift fingerprint (so the next scan doesn't see our own
poster as a change), resend cache, History (action "overlay_only_sent"), and
an overlay_state row marked "clean_base" so Overlay Refresh re-renders from
the clean copy (overlay_refresh.refresh_state()).
"""
from __future__ import annotations

import io
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from . import database as db
from .config import logger

CANVAS = (2000, 3000)
WAITING = "waiting for the other app's poster"
_FORMAT_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp", "TIFF": "tif"}

_waiting_logged: set = set()
_waiting_lock = threading.Lock()


# --------------------------------------------------------------------------
# Clean copies
# --------------------------------------------------------------------------

def _clean_dir() -> Path:
    # Always from settings at call time (tests and installs override CONFIG_DIR).
    from .config import settings
    d = Path(settings.CONFIG_DIR) / "cache" / "clean_base"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(part: Any) -> str:
    from .poster_drift import _safe as drift_safe
    return drift_safe(str(part))


def _stem(server_id: str, rating_key: str, season_index: Optional[int] = None) -> str:
    stem = f"{_safe(server_id or 'plex-1')}__{_safe(rating_key)}"
    if season_index is not None:
        stem += f"__s{int(season_index)}"
    return stem


_KNOWN_EXTS = tuple(sorted(set(_FORMAT_EXT.values())))


def _files_for(stem: str) -> List[Path]:
    """Existing files for one item: checks the known extensions directly
    instead of listing the folder (called once per item in a refresh run)."""
    d = _clean_dir()
    out = []
    for ext in _KNOWN_EXTS:
        p = d / f"{stem}.{ext}"
        try:
            if p.is_file():
                out.append(p)
        except OSError:
            pass
    return out


def clean_base_path(server_id: str, rating_key: str, season_index: Optional[int] = None) -> Optional[Path]:
    """The existing clean copy for this item (any extension), or None."""
    if not rating_key:
        return None
    files = _files_for(_stem(server_id, rating_key, season_index))
    return files[0] if files else None


def _ext_for(data: bytes) -> str:
    try:
        fmt = Image.open(io.BytesIO(data)).format
        return _FORMAT_EXT.get(fmt or "", "jpg")
    except Exception:
        return "jpg"


def save_clean_base(server_id: str, rating_key: str, season_index: Optional[int], data: bytes) -> Path:
    """Write (replace) the clean copy for this item and return its path."""
    stem = _stem(server_id, rating_key, season_index)
    path = _clean_dir() / f"{stem}.{_ext_for(data)}"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(bytes(data))
    os.replace(tmp, path)
    for old in _files_for(stem):
        if old != path:
            try:
                old.unlink()
            except OSError:
                pass
    return path


def remove_server_clean_bases(server_id: str) -> int:
    """Delete every clean copy of a removed media server. Returns the count."""
    removed = 0
    prefix = f"{_safe(server_id)}__"
    try:
        for f in _clean_dir().iterdir():
            if f.is_file() and f.name.startswith(prefix):
                f.unlink(missing_ok=True)
                removed += 1
    except OSError:
        pass
    return removed


def rekey_clean_base(server_id: str, old_key: str, new_key: str, season_index: Optional[int] = None) -> bool:
    """Move a clean copy to an item's new id (Jellyfin/Emby re-import, Plex
    re-add). If one already exists under the new id, the old one is dropped."""
    old = clean_base_path(server_id, old_key, season_index)
    if old is None or str(old_key) == str(new_key):
        return False
    new_stem = _stem(server_id, new_key, season_index)
    if _files_for(new_stem):
        old.unlink(missing_ok=True)
    else:
        os.replace(old, old.with_name(new_stem + old.suffix))
    return True


def clean_base_orphans() -> List[Path]:
    """Clean copies whose rating key is in no cache table (the item left the
    library), for Settings -> Cleanup's "Clean base posters" category."""
    known = set(db.get_all_known_rating_keys())
    try:
        with db.get_db() as conn:
            for table in ("collection_cache", "season_media_info", "overlay_state"):
                try:
                    known.update(r[0] for r in conn.execute(f"SELECT rating_key FROM {table}").fetchall() if r[0])
                except Exception:
                    pass
    except Exception:
        pass
    known_safe = {_safe(k) for k in known}
    orphans: List[Path] = []
    try:
        for f in _clean_dir().iterdir():
            if not f.is_file() or f.name.endswith(".tmp"):
                continue
            parts = f.stem.split("__")
            if len(parts) < 2 or parts[1] not in known_safe:
                orphans.append(f)
    except OSError:
        pass
    return orphans


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_overlay_only(base: bytes, options: Dict[str, Any], template_id: str = "uniformlogo") -> Image.Image:
    """The base poster cover-resized to 2000x3000 with only the overlays drawn
    on it: the below list, then the above list (plus the preset's legacy
    single overlay link), the same split uniformlogo uses. No logo, text,
    matte, fade, vignette, grain or border."""
    from .templates.universal import _resize_cover, apply_overlay_config

    canvas = _resize_cover(Image.open(io.BytesIO(base)).convert("RGB"), *CANVAS)
    metadata = options.get("metadata") or {}
    preset_id = options.get("preset_id")
    ids = list(options.get("overlay_config_ids") or [])
    below = [cid for cid in (options.get("overlay_config_ids_below") or []) if cid in ids]
    if below:
        canvas = apply_overlay_config(canvas, None, template_id, metadata, below)
    above = [cid for cid in ids if cid not in below]
    if preset_id or above:
        canvas = apply_overlay_config(canvas, preset_id, template_id, metadata, above)
    return canvas.convert("RGB") if canvas.mode != "RGB" else canvas


# --------------------------------------------------------------------------
# Base resolution
# --------------------------------------------------------------------------

def _fetch_url(url: str) -> Optional[bytes]:
    """Download the stored source art (a TMDb/Fanart URL). None on failure."""
    try:
        from .middleware.validation import assert_fetch_url_safe, safe_get
        from .config import EXTERNAL_IMAGE_FETCH_HEADERS
        assert_fetch_url_safe(url)
        resp = safe_get(url, timeout=60, headers=EXTERNAL_IMAGE_FETCH_HEADERS)
        resp.raise_for_status()
        return resp.content or None
    except Exception as e:
        logger.debug("[OVERLAY_ONLY] Couldn't fetch %s: %s", url, e)
        return None


def _log_waiting(server_id: str, rating_key: str, season_index: Optional[int]) -> None:
    key = (server_id, str(rating_key), season_index)
    with _waiting_lock:
        if key in _waiting_logged:
            return
        _waiting_logged.add(key)
    logger.info("[OVERLAY_ONLY] %s on %s: the poster there is Simposter's own and no source art is "
                "recorded; waiting for the other app's poster", _title_for_log(rating_key, season_index), server_id)


def _usable_background(state: Optional[Dict[str, Any]]) -> Optional[str]:
    from .overlay_refresh import _self_referencing_background
    bg = (state or {}).get("background_url")
    return bg if bg and not _self_referencing_background(bg) else None


def resolve_base(server_id: str, rating_key: str, season_index: Optional[int], is_tv: bool) -> Tuple[Optional[bytes], str]:
    """The image to draw overlays on. The server's poster is looked at first
    (the other app may have changed it since the clean copy was saved): when it
    isn't what Simposter last sent, it replaces the clean copy and is used.
    When it IS Simposter's own (or can't be downloaded), the stored clean copy
    is used; else the art Simposter last rendered from. (None, WAITING) when
    there's nothing usable."""
    existing = clean_base_path(server_id, rating_key, season_index)

    from . import media_server, poster_drift
    from .media_server import ImageType
    client = media_server.get_client(server_id)
    data = None
    if client is not None:
        try:
            data = client.download_image(rating_key, ImageType.POSTER)
        except Exception as e:
            logger.debug("[OVERLAY_ONLY] Couldn't download the poster of %s from %s: %s", rating_key, server_id, e)
    if data:
        matches = poster_drift.matches_sent(server_id, rating_key, data)
        # No fingerprint but History has a send: Simposter's own poster from
        # before fingerprints existed (v1.8.11) -- never keep that as the clean copy.
        if matches is None and db.poster_already_sent(server_id, rating_key):
            matches = True
        if matches is not True and season_index is not None:
            # A season with no poster of its own is served the show's poster,
            # which may be Simposter's fresh overlay-only one (Quirk #43).
            show_key = _show_key_for_season(rating_key)
            if show_key and poster_drift.matches_sent(server_id, show_key, data) is True:
                matches = True
        if matches is not True:
            save_clean_base(server_id, rating_key, season_index, data)
            return data, "the server's poster"

    if existing is not None:
        try:
            return existing.read_bytes(), "clean copy"
        except OSError as e:
            logger.debug("[OVERLAY_ONLY] Couldn't read %s: %s", existing, e)

    bg = _usable_background(db.get_overlay_state(server_id, rating_key, season_index))
    if bg:
        fetched = _fetch_url(bg)
        if fetched:
            return fetched, "the art Simposter last used"

    _log_waiting(server_id, rating_key, season_index)
    return None, WAITING


# --------------------------------------------------------------------------
# Item identity
# --------------------------------------------------------------------------

def _cached_row(rating_key: str) -> Optional[Dict[str, Any]]:
    with db.get_db() as conn:
        for table in ("movie_cache", "tv_cache"):
            row = conn.execute(
                f"SELECT title, year, tmdb_id, library_id FROM {table} WHERE rating_key = ? LIMIT 1",
                (str(rating_key),),
            ).fetchone()
            if row:
                return dict(row)
    return None


def _show_key_for_season(season_key: str) -> Optional[str]:
    try:
        with db.get_db() as conn:
            row = conn.execute("SELECT show_rating_key FROM season_media_info WHERE rating_key = ?",
                               (str(season_key),)).fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def _identity(server_id: str, rating_key: str, season_index: Optional[int]) -> Dict[str, Any]:
    """title, year, tmdb_id, library_id of the item (a season: of its show)."""
    row = None
    if season_index is not None:
        show_key = _show_key_for_season(rating_key)
        if show_key:
            row = _cached_row(show_key)
    else:
        row = _cached_row(rating_key)
    out = dict(row or {})
    if not out.get("title") or not out.get("tmdb_id"):
        state = db.get_overlay_state(server_id, rating_key, season_index) or {}
        for k in ("title", "year", "tmdb_id", "library_id"):
            if not out.get(k) and state.get(k):
                out[k] = state[k]
    return out


def _title_for_log(rating_key: str, season_index: Optional[int]) -> str:
    try:
        row = _cached_row(_show_key_for_season(rating_key) or rating_key) if season_index is not None else _cached_row(rating_key)
        title = (row or {}).get("title") or f"item {rating_key}"
    except Exception:
        title = f"item {rating_key}"
    if season_index is not None:
        title = f"{title} - {'Specials' if season_index == 0 else f'Season {season_index}'}"
    return title


# --------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------

def _overlay_lists(template_id: str, preset_id: Optional[str], season_index: Optional[int],
                   overlay_lists: Optional[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    if overlay_lists is not None:
        ids = overlay_lists.get("ids", overlay_lists.get("overlay_config_ids")) or []
        below = overlay_lists.get("below", overlay_lists.get("overlay_config_ids_below")) or []
    elif preset_id:
        from .overlay_refresh import preset_overlay_lists
        lists = preset_overlay_lists(template_id, preset_id)["season" if season_index is not None else "series"]
        ids, below = lists.get("ids") or [], lists.get("below") or []
    else:
        ids, below = [], []
    ids = [str(c) for c in ids if c]
    below = [str(c) for c in below if c and str(c) in ids]
    return ids, below


def _legacy_overlay(template_id: str, preset_id: Optional[str]) -> Optional[str]:
    if not preset_id:
        return None
    try:
        return (db.get_preset(template_id, preset_id) or {}).get("overlay_config_id")
    except Exception:
        return None


def _notify(source: str, server_id: str, library_id: Optional[str], title: str, year: Any,
            template_id: str, preset_id: Optional[str], payload: bytes) -> None:
    """The same per-send Discord/Apprise notification other sends use, with
    action "overlay_only_sent" ("Overlays applied"). Batch runs notify once for
    the whole batch, so a batch item doesn't. Never raises."""
    if source == "batch":
        return
    try:
        from .api.notifications import send_discord_notification, send_apprise_notification
        kwargs = dict(title=title, year=year, template_id=template_id or "", preset_id=preset_id or "",
                      library_id=library_id, source=source, action="overlay_only_sent",
                      poster_data=payload, server_id=server_id)
        send_discord_notification(**kwargs)
        send_apprise_notification(**kwargs)
    except Exception as e:
        logger.debug("[OVERLAY_ONLY] Notification failed: %s", e)


def apply_for_item(server_id: str, rating_key: str, library_id: Optional[str], is_tv: bool,
                   template_id: str, preset_id: Optional[str], source: str,
                   season_index: Optional[int] = None,
                   overlay_lists: Optional[Dict[str, Any]] = None,
                   upload: bool = True, title_hint: Optional[str] = None,
                   year_hint: Any = None) -> Dict[str, Any]:
    """Draw the preset's overlays (or `overlay_lists`) on this item's clean
    copy and upload the result. Returns {"status": "ok"|"skipped"|"error", ...};
    an ok result carries "image_bytes"/"content_type" (the encoded poster).
    upload=False only renders (nothing is sent, recorded or notified), for a
    caller that just wants the image (Batch Edit's local save)."""
    template_id = template_id or "uniformlogo"
    ids, below = _overlay_lists(template_id, preset_id, season_index, overlay_lists)
    if not ids and not _legacy_overlay(template_id, preset_id):
        return {"status": "skipped", "reason": "preset has no overlays"}

    log_title = _title_for_log(rating_key, season_index)
    base, base_from = resolve_base(server_id, rating_key, season_index, is_tv)
    if base is None:
        return {"status": "skipped", "reason": base_from}

    from . import media_server, overlay_refresh, poster_drift
    from .config import inject_plex_media_metadata
    from .api.save import encode_poster_for_plex
    from .api.media_server_send import (_cache_poster_after_upload, _upload_poster_and_verify,
                                        upload_with_stale_retry)

    client = media_server.get_client(server_id) if upload else None
    if upload and client is None:
        return {"status": "error", "reason": f"server {server_id} is not configured"}

    ident = _identity(server_id, rating_key, season_index)
    tmdb_id = ident.get("tmdb_id")
    library_id = library_id if library_id is not None else ident.get("library_id")
    title = ident.get("title") or title_hint or f"item {rating_key}"
    year = ident.get("year") or year_hint

    opts: Dict[str, Any] = {"overlay_config_ids": ids, "overlay_config_ids_below": below,
                            "preset_id": preset_id, "metadata": {}}
    try:
        inject_plex_media_metadata(opts, rating_key, tmdb_id=tmdb_id, is_tv=is_tv, log_prefix="[OVERLAY_ONLY] ")
    except Exception as e:
        logger.debug("[OVERLAY_ONLY] Metadata for %s failed: %s", log_title, e)

    try:
        img = render_overlay_only(base, opts, template_id=template_id)
        payload, content_type = encode_poster_for_plex(img, for_plex=server_id == "plex-1")
    except Exception as e:
        logger.error("[OVERLAY_ONLY] Rendering %s failed: %s", log_title, e)
        return {"status": "error", "reason": f"render failed: {e}"}

    if not upload:
        return {"status": "ok", "uploaded": False, "item_id": str(rating_key), "rating_key": str(rating_key),
                "base": base_from, "image_bytes": payload, "content_type": content_type}
    try:
        if server_id == "plex-1":
            _upload_poster_and_verify(client, server_id, rating_key, payload, content_type)
            item_id, current_key = str(rating_key), str(rating_key)
        else:
            item_id, current_key = upload_with_stale_retry(
                server_id, client, str(rating_key), None,
                lambda iid: _upload_poster_and_verify(client, server_id, iid, payload, content_type),
            )
    except Exception as e:
        detail = getattr(e, "detail", None) or str(e)
        logger.error("[OVERLAY_ONLY] Upload of %s to %s failed: %s", log_title, server_id, detail)
        return {"status": "error", "reason": f"upload failed: {detail}"}
    item_id = str(item_id)
    if item_id != str(rating_key):
        rekey_clean_base(server_id, rating_key, item_id, season_index)

    # Our own upload is never "the other app changed it" on the next scan.
    poster_drift.record_sent(server_id, item_id, payload)
    _cache_poster_after_upload(item_id, payload, content_type, is_tv=bool(is_tv))  # display + resend cache

    display = title
    if season_index is not None:
        display = f"{title} - {'Specials' if season_index == 0 else f'Season {season_index}'}"
    try:
        db.record_poster_history(
            rating_key=item_id, library_id=library_id, title=display, year=year,
            template_id=template_id, preset_id=preset_id, action="overlay_only_sent",
            source=source, poster_data=payload, server_id=server_id,
        )
    except Exception as e:
        logger.debug("[OVERLAY_ONLY] History write failed for %s: %s", log_title, e)

    prev_bg = _usable_background(db.get_overlay_state(server_id, item_id, season_index))
    overlay_refresh.record_send(
        server_id, item_id, template_id=template_id, options=opts, background_url=prev_bg, logo_url=None,
        media_type="tv" if is_tv else "movie", library_id=library_id, season_index=season_index,
        tmdb_id=tmdb_id, title=title, year=year, source_kind=overlay_refresh.CLEAN_BASE,
    )

    _notify(source, server_id, library_id, display, year, template_id, preset_id, payload)
    logger.info("[OVERLAY_ONLY] %s: overlays applied on %s (base: %s)", log_title, server_id, base_from)
    return {"status": "ok", "item_id": item_id, "rating_key": current_key, "base": base_from,
            "image_bytes": payload, "content_type": content_type}


def apply_for_title(server_id: str, rating_key: str, library_id: Optional[str], is_tv: bool,
                    template_id: str, preset_id: Optional[str], source: str,
                    include_series: bool = True, include_seasons: bool = False,
                    affected_seasons: Optional[List[int]] = None, other_copies: bool = True,
                    servers: Optional[List[str]] = None, tmdb_id=None, tvdb_id=None,
                    render_unsent_own: bool = False, title_hint: Optional[str] = None,
                    year_hint: Any = None) -> Dict[str, Any]:
    """Overlay-only for a whole title (poster modes): this copy and,
    with `other_copies`, every other copy in its library group (found by
    TMDb/TVDB id). For a show: the show poster (include_series) and its seasons
    (include_seasons, filtered to `affected_seasons` when given). `servers`
    limits which servers get it (Batch Edit's send choices); with `render_unsent_own`, this copy is still
    rendered (not uploaded) when it isn't in `servers`, so the caller can save it.
    title_hint/year_hint: the caller's title/year for an item not in the cache yet.
    Never raises.
    Returns {"status": "ok"|"skipped"|"error", "results": [...]}."""
    from . import poster_mode
    server_id = server_id or "plex-1"
    media_type = "tv" if is_tv else "movie"
    copies: List[Tuple[str, str, Optional[str]]] = [(server_id, str(rating_key), library_id)]
    if other_copies and library_id:
        try:
            db_tmdb, db_tvdb = db.get_ids_for_rating_key(str(rating_key))
            key = poster_mode.item_key(media_type, db_tmdb or tmdb_id, db_tvdb or tvdb_id)
            if key:
                gid = poster_mode.group_id_for(server_id, str(library_id), media_type)
                for sid, rk, _tmdb, lib in poster_mode._member_copies(gid, media_type, key[0], key[1]):
                    if (sid, rk) not in {(c[0], c[1]) for c in copies}:
                        copies.append((sid, rk, lib))
        except Exception as e:
            logger.debug("[OVERLAY_ONLY] Couldn't find other copies of %s: %s", rating_key, e)

    hints: Dict[str, Any] = {}
    if title_hint:
        hints["title_hint"] = title_hint
    if year_hint:
        hints["year_hint"] = year_hint
    results: List[Dict[str, Any]] = []
    for ci, (sid, rk, lib) in enumerate(copies):
        up = servers is None or sid in servers
        if not up and not (render_unsent_own and ci == 0):
            continue
        if not is_tv or include_series:
            r = apply_for_item(sid, rk, lib, is_tv, template_id, preset_id, source, upload=up, **hints)
            results.append({**r, "server_id": sid, "season_index": None})
        if is_tv and include_seasons:
            try:
                from .api.batch import _list_show_seasons
                seasons = _list_show_seasons(rk, sid)
            except Exception as e:
                logger.warning("[OVERLAY_ONLY] Couldn't list the seasons of %s on %s: %s",
                               _title_for_log(rk, None), sid, e)
                results.append({"status": "error", "reason": f"season list failed: {e}", "server_id": sid})
                continue
            for s in seasons:
                if affected_seasons and s["index"] not in affected_seasons:
                    continue
                r = apply_for_item(sid, s["key"], lib, True, template_id, preset_id, source,
                                   season_index=s["index"], upload=up, **hints)
                results.append({**r, "server_id": sid, "season_index": s["index"]})
    statuses = [r.get("status") for r in results]
    status = "ok" if "ok" in statuses else ("error" if "error" in statuses else "skipped")
    return {"status": status, "results": results}


def on_external_poster(server_id: str, rating_key: str, season_index: Optional[int] = None) -> Dict[str, Any]:
    """Drift found a new poster from the other app on an overlay-only title:
    keep it as the clean copy and put the overlays back on it, with the
    title's last-used template/preset."""
    from . import media_server
    from .media_server import ImageType
    title = _title_for_log(rating_key, season_index)
    client = media_server.get_client(server_id)
    data = None
    if client is not None:
        try:
            data = client.download_image(rating_key, ImageType.POSTER)
        except Exception as e:
            logger.debug("[OVERLAY_ONLY] Couldn't download the poster of %s from %s: %s", title, server_id, e)
    if not data:
        logger.info("[OVERLAY_ONLY] %s: couldn't download the new poster from %s", title, server_id)
        return {"status": "error", "reason": "download failed"}
    save_clean_base(server_id, rating_key, season_index, data)

    state = db.get_overlay_state(server_id, rating_key, season_index) or {}
    ident = _identity(server_id, rating_key, season_index)
    is_tv = state.get("media_type") == "tv" if state else (season_index is not None or _is_tv(rating_key))
    media_type = "tv" if is_tv else "movie"
    library_id = state.get("library_id") or ident.get("library_id")
    if library_id is None:
        try:
            library_id = db.get_library_id_for_rating_key(str(rating_key))
        except Exception:
            library_id = None

    template_id, preset_id = state.get("template_id"), state.get("preset_id")
    if not preset_id:
        last = db.get_last_plex_send_preset(media_type, ident.get("tmdb_id")) or {}
        template_id, preset_id = last.get("template_id"), last.get("preset_id")
    if not preset_id:
        cfg = _group_auto_generate(server_id, library_id, media_type)
        if cfg:
            template_id, preset_id = cfg.get("template_id"), cfg.get("preset_id")
    if not preset_id:
        logger.info("[OVERLAY_ONLY] %s: new poster kept as the clean copy, but no preset is known "
                    "for it (no earlier send, no auto-generate preset); overlays not applied", title)
        return {"status": "skipped", "reason": "no preset"}
    return apply_for_item(server_id, rating_key, library_id, is_tv, template_id or "uniformlogo", preset_id,
                          source="auto_generate", season_index=season_index)


def _is_tv(rating_key: str) -> bool:
    try:
        return db.get_cached_tv_show(str(rating_key)) is not None
    except Exception:
        return False


def _group_auto_generate(server_id: str, library_id: Optional[str], media_type: str) -> Optional[Dict[str, Any]]:
    if not library_id:
        return None
    try:
        from .config import get_library_group_for
        from .auto_generate import _resolve_auto_generate_config
        group = get_library_group_for(server_id, str(library_id), media_type)
        if not group:
            return None
        return _resolve_auto_generate_config(group, media_type, db.get_ui_settings() or {})
    except Exception as e:
        logger.debug("[OVERLAY_ONLY] Auto-generate preset lookup failed: %s", e)
        return None
