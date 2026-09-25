import base64
import time
import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from io import BytesIO
from pathlib import Path
from PIL import Image
from pydantic import BaseModel
from typing import List, Optional

from ..config import settings, plex_headers, plex_session, plex_remove_label, plex_add_label, get_label_to_add, logger, get_media_folder_name
from ..rendering import render_poster_image
from ..schemas import PlexSendRequest, PlexLogoSendRequest, PlexBackdropSendRequest, PlexSquareArtSendRequest
from ..save_paths import SaveContext, resolve_library_label, save_or_cache_render, load_cached_render, save_to_asset_folder_on_send_enabled
from .save import encode_poster_for_plex, normalize_logo_for_plex, normalize_backdrop_for_plex, _PLEX_UPLOAD_SIZE_LIMIT
from .movies import fetch_and_cache_poster, fetch_and_cache_logo, _logo_cache_url, _read_image_metadata, _find_asset_under_roots
from .notifications import send_discord_notification, send_apprise_notification

router = APIRouter()


def _plex_media_segment(is_collection: bool) -> str:
    """Plex's poster/logo upload path segment: /library/collections/ for a
    collection, /library/metadata/ for everything else (movies, shows, seasons)."""
    return "collections" if is_collection else "metadata"


@router.post("/plex/send")
def api_plex_send(req: PlexSendRequest):
    _send_start = time.time()

    # Validate Plex settings
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set.")

    # Allow ANY URL (TMDB, uploaded, custom) — collections have no photo background
    # (kometa synthesizes one), so background_url is legitimately empty there.
    if req.background_url and not (
        req.background_url.startswith("http://")
        or req.background_url.startswith("https://")
        or req.background_url.startswith("/api/uploaded/")
    ):
        raise HTTPException(400, "Invalid background_url")

    # Load preset options if preset_id is provided
    options = req.options or {}
    if req.preset_id:
        from ..config import load_presets
        presets_data = load_presets()
        template_presets = presets_data.get(req.template_id, {}).get("presets", [])
        preset = next((p for p in template_presets if p.get("id") == req.preset_id), None)
        if preset:
            # Use preset options, but allow req.options to override
            preset_options = preset.get("options", {})
            options = {**preset_options, **options}
            logger.debug("[PLEX] Using preset '%s' options for template '%s'", req.preset_id, req.template_id)
        else:
            logger.warning("[PLEX] Preset '%s' not found for template '%s', using provided options", req.preset_id, req.template_id)

    # Fetch movie details BEFORE rendering so {title} and {year} can be substituted
    import xml.etree.ElementTree as ET
    movie_details = {}
    plex_xml_text = None
    is_tv = False
    try:
        metadata_url = f"{settings.PLEX_URL}/library/metadata/{req.rating_key}"
        resp = plex_session.get(metadata_url, headers=plex_headers(), timeout=5)
        if resp.ok:
            plex_xml_text = resp.text
            root = ET.fromstring(resp.text)
            is_tv = root.find('.//Directory') is not None
            item = root.find('.//Video') or root.find('.//Directory')
            if item is not None:
                title = item.get('title', '')
                year = item.get('year')
                movie_details = {
                    'title': title,
                    'year': int(year) if year and year.isdigit() else None,
                    'library_id': req.library_id
                }
    except Exception as plex_err:
        logger.debug("[PLEX] Failed to get metadata from Plex for template vars: %s", plex_err)
        # Fallback to cache
        try:
            from .. import database as db
            cached_movies = db.get_cached_movies()
            for m in cached_movies:
                if m.get("rating_key") == req.rating_key:
                    movie_details = m
                    break
            if not movie_details:
                cached_tv = db.get_cached_tv_shows()
                for s in cached_tv:
                    if s.get("rating_key") == req.rating_key:
                        movie_details = s
                        break
        except Exception as cache_err:
            logger.debug("[PLEX] Failed to get details from cache: %s", cache_err)

    # Collections aren't movies or shows — Plex's metadata XML represents a
    # collection as a <Directory> too (same as shows/seasons), which would
    # otherwise misdetect it as a TV show above.
    if req.is_collection:
        is_tv = False

    # Add movie details to options for template variable substitution
    options["movie_title"] = movie_details.get("title", "")
    options["movie_year"] = movie_details.get("year", "")

    # Pass preset_id so the template renderer can look up linked overlay configs
    if req.preset_id:
        options["preset_id"] = req.preset_id

    # Inject Plex media metadata / tmdb_id for overlay badge rendering — collections
    # have no resolution/codec/edition metadata and no TMDb entry, so skip entirely.
    if not req.is_collection:
        try:
            from ..config import inject_plex_media_metadata
            inject_plex_media_metadata(
                options, req.rating_key,
                is_tv=is_tv, plex_xml_text=plex_xml_text,
                log_prefix="[PLEX] ",
            )
        except Exception as e:
            logger.debug("[PLEX] Failed to inject media info: %s", e)

    # Render poster using template + preset options
    img = render_poster_image(
        req.template_id,
        req.background_url,
        req.logo_url,
        options,
    )

    # Encode for Plex — PNG when the user's output format is PNG (lossless, matches a
    # manual Plex upload of their saved file), otherwise a high-quality JPEG.
    payload, content_type = encode_poster_for_plex(img)

    plex_url = f"{settings.PLEX_URL}/library/{_plex_media_segment(req.is_collection)}/{req.rating_key}/posters"
    headers = {
        "X-Plex-Token": settings.PLEX_TOKEN,
        "Content-Type": content_type,
    }

    logger.info("[PLEX] Uploading poster rating_key=%s [%s] template=%s preset=%s", req.rating_key, movie_details.get("title") or "?", req.template_id, req.preset_id)
    try:
        r = plex_session.post(plex_url, headers=headers, data=payload, timeout=20)
        r.raise_for_status()
    except Exception as e:
        logger.error("[PLEX] Upload failed rating_key=%s [%s] err=%s", req.rating_key, movie_details.get("title") or "?", e)
        raise

    try:
        library_label = resolve_library_label(req.library_id or movie_details.get("library_id"))
        # {folder} template variable: resolve the real on-disk folder name from Plex
        # (movies only — TV shows/seasons have no single <Part> file to derive it from,
        # apply_save_location_variables() falls back to {title} automatically). This was
        # previously never resolved on the send-to-Plex path at all (only save-to-disk
        # had it), so {folder} silently fell back to the plain — possibly Plex-localized —
        # title with no year whenever "save to asset folder on send" was enabled. Only
        # worth the extra Plex metadata fetch when that setting is actually on — it's off
        # by default, and save_or_cache_render() ignores folder_name entirely otherwise.
        folder_name = None
        if not req.is_collection and save_to_asset_folder_on_send_enabled():
            folder_name = get_media_folder_name(req.rating_key, is_tv)
        media_type = "collection" if req.is_collection else ("tv-show" if is_tv else "movie")
        cache_ctx = SaveContext(
            media_type=media_type,
            title=movie_details.get("title") or "",
            year=movie_details.get("year"),
            rating_key=req.rating_key,
            library_label=library_label,
            season=req.season_index if is_tv else None,
            folder_name=folder_name,
        )
    except Exception:
        cache_ctx = None
    save_or_cache_render(req.rating_key, payload, cache_ctx)

    # Manual send always resolves any pending retry — the user chose this poster
    try:
        from .. import database as _db_retry
        _db_retry.remove_from_retry_queue(req.rating_key)
    except Exception:
        pass

    # Remove labels if requested. content_type is derived here from the metadata XML
    # already fetched above (for {title}/{year} substitution) when available, using the
    # identical detection plex_remove_label() would otherwise do itself — skips it
    # re-fetching the exact same /library/metadata/{rating_key} a second time per label.
    # Falls back to None (plex_remove_label's own detection) if that fetch failed/is unavailable.
    label_content_type = None
    try:
        if plex_xml_text and 'root' in locals():
            if root.find(".//Directory[@type='show']") is not None:
                label_content_type = "2"
            elif root.find(".//Directory[@type='season']") is not None:
                label_content_type = "3"
            elif root.find(".//Video[@type='episode']") is not None:
                label_content_type = "4"
            else:
                label_content_type = "1"
    except Exception:
        label_content_type = None

    for label in req.labels or []:
        plex_remove_label(req.rating_key, label, content_type=label_content_type)

    # Add tracking label if configured (opposite direction from the removal above — see
    # get_label_to_add()'s docstring)
    try:
        label_to_add = get_label_to_add()
        if label_to_add:
            plex_add_label(req.rating_key, label_to_add, content_type=label_content_type)
    except Exception as e:
        logger.warning("[PLEX] Label add failed for %s: %s", req.rating_key, e)

    # Refresh cached poster so future calls use the updated image
    try:
        fetch_and_cache_poster(req.rating_key, force_refresh=True)
    except Exception as e:
        logger.debug("[CACHE] poster refresh after send failed for %s: %s", req.rating_key, e)

    # Record history entry for manual send (movie_details already fetched above)
    try:
        from .. import database as db
        db.record_poster_history(
            rating_key=req.rating_key,
            library_id=req.library_id or movie_details.get("library_id"),
            title=movie_details.get("title"),
            year=movie_details.get("year"),
            template_id=req.template_id,
            preset_id=req.preset_id,
            action="sent_to_plex",
            save_path=None,
            source='manual',
            poster_data=payload,  # Save thumbnail for history preview
        )
    except Exception as history_err:
        logger.debug("[HISTORY] Failed to record manual send: %s", history_err)

    # Send notifications for manual send
    _notif_kwargs = dict(
        title=movie_details.get("title", "Unknown"),
        year=movie_details.get("year"),
        template_id=req.template_id,
        preset_id=req.preset_id or "",
        library_id=req.library_id or movie_details.get("library_id"),
        source="manual",
        action="sent_to_plex",
    )
    try:
        send_discord_notification(**_notif_kwargs, poster_data=payload)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Discord notification: %s", notif_err)
    try:
        send_apprise_notification(**_notif_kwargs, poster_data=payload)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Apprise notification: %s", notif_err)

    elapsed = time.time() - _send_start
    display_title = movie_details.get("title") or f"rating key {req.rating_key}"
    logger.info("[PLEX] Poster for '%s' sent in %.1fs (rating_key=%s)", display_title, elapsed, req.rating_key)
    return {"status": "ok"}


@router.post("/plex/send-logo")
def api_plex_send_logo(req: PlexLogoSendRequest):
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set.")

    # Best-effort display title for log readability — cheap local DB cache lookup,
    # never a network call (this endpoint doesn't otherwise fetch movie/show details).
    # Also feeds the send-notification below, so kept as separate title/year rather
    # than only the combined display string.
    _logo_title = "?"
    _t, _y = None, None
    try:
        from .. import database as _db_title
        _t, _y = _db_title.get_title_for_rating_key(req.rating_key)
        if _t:
            _logo_title = f"{_t} ({_y})" if _y else _t
    except Exception:
        pass

    # Resolve logo bytes
    logo_bytes = None
    content_type = "image/png"

    if req.logo_data:
        try:
            header, data = req.logo_data.split(",", 1)
            if "jpeg" in header or "jpg" in header:
                content_type = "image/jpeg"
            logo_bytes = base64.b64decode(data)
        except Exception as e:
            raise HTTPException(400, f"Invalid logo_data: {e}")
    elif req.logo_url:
        from ..middleware.validation import validate_url
        req.logo_url = validate_url(req.logo_url)
        try:
            r = requests.get(req.logo_url, timeout=15)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "image/png").split(";")[0].strip()
            logo_bytes = r.content
        except Exception as e:
            raise HTTPException(500, f"Failed to download logo: {e}")
    else:
        raise HTTPException(400, "Either logo_url or logo_data must be provided.")

    logo_bytes, content_type = normalize_logo_for_plex(logo_bytes, content_type)

    # Upload to Plex clearLogos endpoint
    plex_url = f"{settings.PLEX_URL}/library/metadata/{req.rating_key}/clearLogos"
    upload_headers = {
        "X-Plex-Token": settings.PLEX_TOKEN,
        "Content-Type": content_type,
    }
    logger.info("[PLEX] Uploading clearlogo rating_key=%s [%s] is_tv=%s", req.rating_key, _logo_title, req.is_tv)
    try:
        r = plex_session.post(plex_url, headers=upload_headers, data=logo_bytes, timeout=20)
        r.raise_for_status()
    except Exception as e:
        logger.error("[PLEX] Logo upload failed rating_key=%s [%s] err=%s", req.rating_key, _logo_title, e)
        raise HTTPException(500, f"Failed to upload logo to Plex: {e}")

    # Save uploaded bytes directly to cache — no need to re-fetch from Plex
    # (Plex may not have processed the upload yet, so re-fetching would return the old logo)
    new_logo_url = None
    try:
        from .. import database as db_mod
        from .movies import _save_logo_cache, _logo_cache_url
        logo_path = _save_logo_cache(req.rating_key, logo_bytes, content_type)
        if logo_path:
            new_logo_url = _logo_cache_url(req.rating_key, logo_path)
            if req.is_tv:
                db_mod.update_tv_logo_url(req.rating_key, new_logo_url)
            else:
                db_mod.update_movie_logo_url(req.rating_key, new_logo_url)
    except Exception as e:
        logger.debug("[PLEX] Failed to update logo cache after upload: %s", e)

    logger.info("[PLEX] Clearlogo sent for ratingKey=%s [%s]", req.rating_key, _logo_title)

    _notif_kwargs = dict(
        title=_t or "Unknown", year=_y, template_id="", preset_id="",
        library_id=req.library_id, source="manual", action="sent_to_plex",
        asset_type="logo",
    )
    try:
        send_discord_notification(**_notif_kwargs, poster_data=logo_bytes)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Discord notification: %s", notif_err)
    try:
        send_apprise_notification(**_notif_kwargs, poster_data=logo_bytes)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Apprise notification: %s", notif_err)

    return {"status": "ok", "logo_url": new_logo_url}


@router.post("/plex/send-backdrop")
def api_plex_send_backdrop(req: PlexBackdropSendRequest):
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set.")

    _art_title = "?"
    _t, _y = None, None
    try:
        from .. import database as _db_title
        _t, _y = _db_title.get_title_for_rating_key(req.rating_key)
        if _t:
            _art_title = f"{_t} ({_y})" if _y else _t
    except Exception:
        pass

    # Resolve backdrop bytes
    art_bytes = None
    content_type = "image/jpeg"

    if req.art_data:
        try:
            header, data = req.art_data.split(",", 1)
            if "png" in header:
                content_type = "image/png"
            art_bytes = base64.b64decode(data)
        except Exception as e:
            raise HTTPException(400, f"Invalid art_data: {e}")
    elif req.art_url:
        from ..middleware.validation import validate_url
        req.art_url = validate_url(req.art_url)
        try:
            r = requests.get(req.art_url, timeout=15)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            art_bytes = r.content
        except Exception as e:
            raise HTTPException(500, f"Failed to download backdrop: {e}")
    else:
        raise HTTPException(400, "Either art_url or art_data must be provided.")

    art_bytes, content_type = normalize_backdrop_for_plex(art_bytes, content_type)

    # Upload to Plex's /arts endpoint (plural) -- confirmed against python-plexapi's
    # actual ArtMixin.uploadArt() source (not a guess): it only ever POSTs to
    # /library/metadata/{ratingKey}/arts, there is no singular /art write path. An
    # earlier version of this endpoint tried a singular /art fallback based on an
    # incorrect assumption (mirroring the read-side GET convenience path, which IS
    # singular) -- that was the actual cause of a dropped-SSL-connection failure in
    # production, now removed. See CLAUDE.md Quirk #44.
    segment = _plex_media_segment(req.is_collection)
    upload_headers = {
        "X-Plex-Token": settings.PLEX_TOKEN,
        "Content-Type": content_type,
    }
    plex_url = f"{settings.PLEX_URL}/library/{segment}/{req.rating_key}/arts"
    logger.info("[PLEX] Uploading backdrop rating_key=%s [%s] is_tv=%s is_collection=%s", req.rating_key, _art_title, req.is_tv, req.is_collection)
    try:
        r = plex_session.post(plex_url, headers=upload_headers, data=art_bytes, timeout=20)
        r.raise_for_status()
    except Exception as e:
        logger.error("[PLEX] Backdrop upload failed rating_key=%s [%s] err=%s", req.rating_key, _art_title, e)
        raise HTTPException(500, f"Failed to upload backdrop to Plex: {e}")

    # Save uploaded bytes directly to cache — no need to re-fetch from Plex
    # (Plex may not have processed the upload yet, so re-fetching would return the old art)
    new_art_url = None
    try:
        from .. import database as db_mod
        from .movies import _save_art_cache, _art_cache_url, _art_thumbnail
        art_path = _save_art_cache(req.rating_key, art_bytes, content_type)
        if art_path:
            # Pre-warm the grid thumbnail immediately, same as scan does -- without
            # this, the grid's next paint would regenerate it cold on first view.
            _art_thumbnail(req.rating_key, art_path)
            new_art_url = _art_cache_url(req.rating_key, art_path)
            if req.is_tv:
                db_mod.update_tv_art_url(req.rating_key, new_art_url)
            else:
                db_mod.update_movie_art_url(req.rating_key, new_art_url)
    except Exception as e:
        logger.debug("[PLEX] Failed to update backdrop cache after upload: %s", e)

    logger.info("[PLEX] Backdrop sent for ratingKey=%s [%s]", req.rating_key, _art_title)

    _notif_kwargs = dict(
        title=_t or "Unknown", year=_y, template_id="", preset_id="",
        library_id=req.library_id, source="manual", action="sent_to_plex",
        asset_type="backdrop",
    )
    try:
        send_discord_notification(**_notif_kwargs, poster_data=art_bytes)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Discord notification: %s", notif_err)
    try:
        send_apprise_notification(**_notif_kwargs, poster_data=art_bytes)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Apprise notification: %s", notif_err)

    return {"status": "ok", "art_url": new_art_url}


@router.post("/plex/send-square-art")
def api_plex_send_square_art(req: PlexSquareArtSendRequest):
    """Upload square (1:1) art to Plex's dedicated squareArts slot -- a genuinely
    separate slot from posters/arts, confirmed against python-plexapi's
    SquareArtMixin source: POST /library/metadata/{ratingKey}/squareArts, image
    type "backgroundSquare". No overwrite risk to the item's regular poster or
    background art, unlike sending through either of those existing slots."""
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set.")

    _sq_title = "?"
    _t, _y = None, None
    try:
        from .. import database as _db_title
        _t, _y = _db_title.get_title_for_rating_key(req.rating_key)
        if _t:
            _sq_title = f"{_t} ({_y})" if _y else _t
    except Exception:
        pass

    art_bytes = None
    content_type = "image/jpeg"

    if req.art_data:
        try:
            header, data = req.art_data.split(",", 1)
            if "png" in header:
                content_type = "image/png"
            art_bytes = base64.b64decode(data)
        except Exception as e:
            raise HTTPException(400, f"Invalid art_data: {e}")
    elif req.art_url:
        from ..middleware.validation import validate_url
        req.art_url = validate_url(req.art_url)
        try:
            r = requests.get(req.art_url, timeout=15)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            art_bytes = r.content
        except Exception as e:
            raise HTTPException(500, f"Failed to download square art: {e}")
    else:
        raise HTTPException(400, "Either art_url or art_data must be provided.")

    # Square art is the same kind of large photographic image as a backdrop --
    # reuse the identical RGB-flatten + tiered-PNG-then-JPEG-fallback normalize.
    art_bytes, content_type = normalize_backdrop_for_plex(art_bytes, content_type)

    segment = _plex_media_segment(req.is_collection)
    upload_headers = {
        "X-Plex-Token": settings.PLEX_TOKEN,
        "Content-Type": content_type,
    }
    plex_url = f"{settings.PLEX_URL}/library/{segment}/{req.rating_key}/squareArts"
    logger.info("[PLEX] Uploading square art rating_key=%s [%s] is_tv=%s is_collection=%s", req.rating_key, _sq_title, req.is_tv, req.is_collection)
    try:
        r = plex_session.post(plex_url, headers=upload_headers, data=art_bytes, timeout=20)
        r.raise_for_status()
    except Exception as e:
        logger.error("[PLEX] Square art upload failed rating_key=%s [%s] err=%s", req.rating_key, _sq_title, e)
        raise HTTPException(500, f"Failed to upload square art to Plex: {e}")

    # Save uploaded bytes directly to cache — no need to re-fetch from Plex (same
    # reasoning as backdrop's post-upload caching: Plex may not have processed the
    # upload yet). This is what lets the manual editor immediately show "Current
    # Square Art" matching what was just sent, instead of nothing at all -- there's
    # no scan-time population for this niche, manually-triggered asset type, so the
    # send action itself is the primary way this cache ever gets populated.
    new_square_art_url = None
    try:
        from .. import database as db_mod
        from .movies import _save_square_art_cache, _square_art_cache_url, _square_art_thumbnail
        sq_path = _save_square_art_cache(req.rating_key, art_bytes, content_type)
        if sq_path:
            # Pre-warm the grid thumbnail immediately -- especially worth it here,
            # since the cached file is the full 2000x2000 render (see Quirk #49).
            _square_art_thumbnail(req.rating_key, sq_path)
            new_square_art_url = _square_art_cache_url(req.rating_key, sq_path)
            if req.is_tv:
                db_mod.update_tv_square_art_url(req.rating_key, new_square_art_url)
            else:
                db_mod.update_movie_square_art_url(req.rating_key, new_square_art_url)
    except Exception as e:
        logger.debug("[PLEX] Failed to update square art cache after upload: %s", e)

    logger.info("[PLEX] Square art sent for ratingKey=%s [%s]", req.rating_key, _sq_title)

    _notif_kwargs = dict(
        title=_t or "Unknown", year=_y, template_id="", preset_id="",
        library_id=req.library_id, source="manual", action="sent_to_plex",
        asset_type="square_art",
    )
    try:
        send_discord_notification(**_notif_kwargs, poster_data=art_bytes)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Discord notification: %s", notif_err)
    try:
        send_apprise_notification(**_notif_kwargs, poster_data=art_bytes)
    except Exception as notif_err:
        logger.debug("[PLEX] Failed to send Apprise notification: %s", notif_err)

    return {"status": "ok", "square_art_url": new_square_art_url}


# ---------------------------------------------------------------------------
# Render-cache resend endpoints
# ---------------------------------------------------------------------------

class ResendTarget(BaseModel):
    server_id: str
    rating_key: str  # this server's OWN rating_key for the same logical item --
                      # not necessarily equal to the path rating_key (e.g. resending
                      # a Plex-sourced grid card's cached bytes to a linked Jellyfin
                      # server needs Jellyfin's own item id, not Plex's)


class ResendCachedRequest(BaseModel):
    include_seasons: bool = False
    is_tv: bool = False
    # Explicit list of servers to resend to, added for the grid's per-card
    # "send to..." picker (movies only for now -- see CLAUDE.md's Quirk).
    # None/empty preserves this endpoint's exact original behavior: resend to
    # whichever single server the path rating_key actually belongs to
    # (db.get_server_id_for_rating_key(), 'plex-1' for every pre-multi-server
    # install).
    targets: Optional[List[ResendTarget]] = None


@router.get("/render-cache/cached-keys")
def api_render_cache_cached_keys():
    """Return the set of rating_keys that have a saved poster available to resend."""
    from ..save_paths import save_to_asset_folder_on_send_enabled, resolve_save_path, get_save_template

    # The hidden internal cache (poster_renders/) is always a valid resend source,
    # regardless of the "save to asset folder on send" setting -- save_or_cache_render()
    # falls back to writing here whenever a caller has no SaveContext to resolve an
    # asset-folder path with (ctx=None). media_server_send.py's Jellyfin/Emby sends
    # always pass ctx=None (no Plex-metadata-derived {folder}/{title} substitution
    # exists for a non-Plex item yet -- see CLAUDE.md Quirk #89), so a Jellyfin-sent
    # poster's bytes only ever land here, never at a resolved asset-folder path. The
    # asset-folder branch below used to be the ONLY check performed once that setting
    # was on, silently missing anything that landed in the hidden cache instead --
    # user-reported directly ("i still dont see the send arrow ... when on jellyfin
    # view") even after Quirk #89's write-side fix, because this read side never
    # looked at what that fix actually wrote. Always include this set now, unioned
    # with whatever the asset-folder check below finds -- a strict no-op for any
    # existing Plex-only install (nothing else writes a hidden-cache entry while
    # this setting is on, since every Plex send path passes a real ctx).
    cache_dir = Path(settings.CONFIG_DIR) / "cache" / "poster_renders"
    hidden_keys = set(p.stem for p in cache_dir.glob("*.jpg")) if cache_dir.exists() else set()

    if not save_to_asset_folder_on_send_enabled():
        return {"cached_keys": sorted(hidden_keys)}

    # Asset-folder mode: also check the resolved path for every known movie/show
    # (top-level posters only — matches what the library grid's resend button checks).
    #
    # Only resolve {folder} (one live Plex metadata fetch per movie) if the movie
    # save template actually uses it — checked once, not per item, so libraries that
    # don't use {folder} don't pay for a Plex round-trip per movie in this loop.
    movie_template_uses_folder = "{folder}" in get_save_template("movie")

    from .. import database as db
    keys = set(hidden_keys)
    for m in db.get_cached_movies():
        try:
            ctx = SaveContext(
                media_type="movie",
                title=m.get("title") or "",
                year=m.get("year"),
                rating_key=m.get("rating_key"),
                library_label=resolve_library_label(m.get("library_id")),
                folder_name=get_media_folder_name(m.get("rating_key"), False) if movie_template_uses_folder else None,
            )
            if resolve_save_path(ctx, ".jpg").exists():
                keys.add(m["rating_key"])
        except Exception:
            continue
    tv_template_uses_folder = "{folder}" in get_save_template("tv-show")
    for s in db.get_cached_tv_shows():
        try:
            ctx = SaveContext(
                media_type="tv-show",
                title=s.get("title") or "",
                year=s.get("year"),
                rating_key=s.get("rating_key"),
                library_label=resolve_library_label(s.get("library_id")),
                folder_name=get_media_folder_name(s.get("rating_key"), True) if tv_template_uses_folder else None,
            )
            if resolve_save_path(ctx, ".jpg").exists():
                keys.add(s["rating_key"])
        except Exception:
            continue
    return {"cached_keys": sorted(keys)}


@router.get("/render-cache/{rating_key}/preview")
def api_render_cache_preview(
    rating_key: str,
    is_tv: bool = Query(False),
    season_index: Optional[int] = Query(None),
):
    """Return the saved/cached poster image bytes for the resend confirmation preview
    (the "before" side, compared against the current live Plex poster)."""
    from .. import database as db

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT library_id FROM movie_cache WHERE rating_key = ? "
            "UNION SELECT library_id FROM tv_cache WHERE rating_key = ? LIMIT 1",
            (rating_key, rating_key)
        ).fetchone()
    library_id: Optional[str] = row["library_id"] if row else None

    title, year = db.get_title_for_rating_key(rating_key)
    try:
        folder_name = None
        if save_to_asset_folder_on_send_enabled():
            folder_name = get_media_folder_name(rating_key, is_tv)
        ctx = SaveContext(
            media_type="tv-show" if is_tv else "movie",
            title=title or "",
            year=year,
            rating_key=rating_key,
            library_label=resolve_library_label(library_id),
            season=season_index if is_tv else None,
            folder_name=folder_name,
        )
    except Exception:
        ctx = None

    cached = load_cached_render(rating_key, ctx)
    if not cached:
        raise HTTPException(404, f"No saved poster for {rating_key}")
    return Response(content=cached, media_type="image/jpeg")


def _remove_labels_for_key(rating_key: str, is_tv: bool, library_id: Optional[str], db) -> None:
    """Remove configured auto-labels from Plex and sync the label cache."""
    try:
        from .webhooks import _get_default_remove_labels
        ui = db.get_ui_settings() or {}
        auto_labels_raw = ui.get("automation", {}).get("webhookAutoLabels", "Simposter")
        labels = [l.strip() for l in auto_labels_raw.split(",") if l.strip()]
        if library_id:
            lib_default = _get_default_remove_labels(library_id)
            if lib_default:
                labels = list({*labels, *lib_default})
        if not labels:
            return
        logger.info("[PLEXSEND] Removing labels %s from %s (resend)", labels, rating_key)
        removed = []
        for lbl in labels:
            try:
                plex_remove_label(rating_key, lbl)
                logger.info("[PLEXSEND] Removed label '%s' from %s", lbl, rating_key)
                removed.append(lbl.lower())
            except Exception as le:
                logger.warning("[PLEXSEND] Failed to remove label '%s' from %s: %s", lbl, rating_key, le)
        if removed:
            if is_tv:
                current = db.get_tv_labels(rating_key)
                db.update_tv_labels(rating_key, [l for l in current if l.lower() not in removed],
                                    library_id=library_id or "default")
            else:
                current = db.get_movie_labels(rating_key)
                db.update_movie_labels(rating_key, [l for l in current if l.lower() not in removed])
    except Exception as e:
        logger.warning("[PLEXSEND] Label removal failed for %s: %s", rating_key, e)


def _add_label_for_key(rating_key: str, is_tv: bool, library_id: Optional[str], db) -> None:
    """Add the configured tracking label to Plex and sync the label cache — the opposite
    direction from _remove_labels_for_key() above, see get_label_to_add()'s docstring."""
    try:
        label_to_add = get_label_to_add()
        if not label_to_add:
            return
        plex_add_label(rating_key, label_to_add)
        logger.info("[PLEXSEND] Added label '%s' to %s (resend)", label_to_add, rating_key)
        if is_tv:
            current = db.get_tv_labels(rating_key)
            if label_to_add.lower() not in [l.lower() for l in current]:
                db.update_tv_labels(rating_key, current + [label_to_add], library_id=library_id or "default")
        else:
            current = db.get_movie_labels(rating_key)
            if label_to_add.lower() not in [l.lower() for l in current]:
                db.update_movie_labels(rating_key, current + [label_to_add])
    except Exception as e:
        logger.warning("[PLEXSEND] Label add failed for %s: %s", rating_key, e)


@router.post("/render-cache/{rating_key}/resend")
def api_render_cache_resend(rating_key: str, req: ResendCachedRequest):
    """Resend a previously cached rendered poster (no re-render) to one or
    more servers. Defaults to whichever single server the path rating_key
    actually belongs to (db.get_server_id_for_rating_key()) -- 'plex-1' for
    every pre-multi-server install, reproducing this endpoint's exact
    original behavior byte-for-byte. `req.targets` (added for the grid's
    per-card "send to..." picker, movies only for now) can name any linked
    server explicitly, including more than one -- every target reuses the
    SAME already-loaded cached bytes, resent as-is, matching every other
    multi-server send path in this app that reuses already-rendered bytes
    rather than re-rendering per destination.
    """
    from .. import database as db

    if req.targets:
        targets = req.targets
    else:
        default_server = db.get_server_id_for_rating_key(rating_key) or "plex-1"
        targets = [ResendTarget(server_id=default_server, rating_key=rating_key)]

    has_plex_target = any(t.server_id == "plex-1" for t in targets)
    # Only require Plex to be configured when a Plex target is actually
    # involved -- a Jellyfin-only resend (a pure Jellyfin browsing session
    # with no Plex configured at all) must not be blocked by a Plex-only
    # precondition that has nothing to do with where this resend is going.
    if has_plex_target and (not settings.PLEX_URL or not settings.PLEX_TOKEN):
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set")

    # Look up library_id from cache
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT library_id FROM movie_cache WHERE rating_key = ? "
            "UNION SELECT library_id FROM tv_cache WHERE rating_key = ? LIMIT 1",
            (rating_key, rating_key)
        ).fetchone()
    library_id: Optional[str] = row["library_id"] if row else None

    _title_for_ctx, _year_for_ctx = db.get_title_for_rating_key(rating_key)
    try:
        _folder_name_for_ctx = None
        if save_to_asset_folder_on_send_enabled():
            _folder_name_for_ctx = get_media_folder_name(rating_key, req.is_tv)
        top_ctx = SaveContext(
            media_type="tv-show" if req.is_tv else "movie",
            title=_title_for_ctx or "",
            year=_year_for_ctx,
            rating_key=rating_key,
            library_label=resolve_library_label(library_id),
            folder_name=_folder_name_for_ctx,
        )
    except Exception:
        top_ctx = None
    # The rating_key-keyed cache is looked up against the PATH rating_key
    # (there's only ever one cached render per item, regardless of how many
    # servers it then gets resent to) -- every target below reuses these
    # same bytes rather than each needing its own cached copy.
    cached = load_cached_render(rating_key, top_ctx)
    if not cached:
        raise HTTPException(404, f"No cached poster for {rating_key}")

    sent_to: List[str] = []
    failed: List[str] = []
    for target in targets:
        if target.server_id == "plex-1":
            try:
                plex_url = f"{settings.PLEX_URL}/library/metadata/{target.rating_key}/posters"
                plex_session.post(
                    plex_url,
                    headers={**plex_headers(), "Content-Type": "image/jpeg"},
                    data=cached,
                    timeout=20,
                ).raise_for_status()
                logger.info("[PLEXSEND] Resent cached poster for %s (%s)", target.rating_key, _title_for_ctx)
                _remove_labels_for_key(target.rating_key, req.is_tv, library_id, db)
                _add_label_for_key(target.rating_key, req.is_tv, library_id, db)
                sent_to.append(target.server_id)
            except Exception as e:
                logger.warning("[PLEXSEND] Failed to resend cached poster to Plex (%s): %s", target.rating_key, e)
                failed.append(target.server_id)
        else:
            try:
                import base64
                from .media_server_send import api_send_poster, MediaServerSendRequest
                data_url = f"data:image/jpeg;base64,{base64.b64encode(cached).decode()}"
                api_send_poster(MediaServerSendRequest(rating_key=target.rating_key, image_data=data_url, is_tv=req.is_tv))
                logger.info("[PLEXSEND] Resent cached poster to %s (%s)", target.server_id, target.rating_key)
                sent_to.append(target.server_id)
            except Exception as e:
                logger.warning("[PLEXSEND] Failed to resend cached poster to %s (%s): %s", target.server_id, target.rating_key, e)
                failed.append(target.server_id)

    if not sent_to:
        raise HTTPException(502, f"Failed to resend poster to: {', '.join(failed) or 'unknown'}")

    resent_seasons = 0
    # Season resend stays Plex-only -- season rating_keys in the cache below
    # are always Plex's own (no Jellyfin season-item resolution exists yet,
    # see Quirk #71's identical TV/season deferral), so this only runs at all
    # when a Plex target was actually part of this resend.
    if req.include_seasons and has_plex_target:
        show = db.get_cached_tv_show(rating_key)
        if show:
            library_label = resolve_library_label(library_id)
            for season in show.get("seasons", []):
                season_key = season.get("key")
                if not season_key:
                    continue
                season_ctx = SaveContext(
                    media_type="tv-show",
                    title=_title_for_ctx or "",
                    year=_year_for_ctx,
                    rating_key=season_key,
                    library_label=library_label,
                    season=season.get("index"),
                )
                season_cached = load_cached_render(season_key, season_ctx)
                if not season_cached:
                    continue
                try:
                    season_url = f"{settings.PLEX_URL}/library/metadata/{season_key}/posters"
                    plex_session.post(
                        season_url,
                        headers={**plex_headers(), "Content-Type": "image/jpeg"},
                        data=season_cached,
                        timeout=20,
                    ).raise_for_status()
                    resent_seasons += 1
                    logger.info("[PLEXSEND] Resent cached season poster for %s", season_key)
                    _remove_labels_for_key(season_key, True, library_id, db)
                    _add_label_for_key(season_key, True, library_id, db)
                except Exception as se:
                    logger.warning("[PLEXSEND] Failed to resend season %s: %s", season_key, se)

    return {"status": "ok", "rating_key": rating_key, "title": _title_for_ctx, "resent_seasons": resent_seasons, "sent_to": sent_to, "failed": failed}


class LocalAssetResendRequest(BaseModel):
    paths: List[str]  # relative asset paths, as returned by GET /local-assets


@router.post("/local-assets/resend")
def api_local_assets_resend(req: LocalAssetResendRequest):
    """
    Bulk-resend one or more saved local asset files straight to Plex (no re-render).

    Each file's Plex rating_key is read from its own embedded metadata (added when
    it was saved) — files saved before that metadata existed have no rating_key and
    are reported back as skipped rather than guessed at.
    """
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set")

    from .. import database as db

    results = []
    for rel_path in req.paths:
        entry: dict = {"path": rel_path}
        try:
            file_path = _find_asset_under_roots(rel_path)
        except HTTPException:
            entry.update(status="error", reason="File not found")
            results.append(entry)
            continue

        metadata = _read_image_metadata(file_path)
        rating_key = metadata.get("rating_key")
        if not rating_key:
            entry.update(status="skipped", reason="No Plex rating key saved with this file (saved before resend support was added)")
            results.append(entry)
            continue

        entry["rating_key"] = rating_key
        entry["title"] = metadata.get("movie_title")
        is_tv = bool(metadata.get("is_tv"))

        try:
            # Resending an already-saved file: upload it as-is (PNG stays PNG, JPEG
            # stays JPEG) rather than re-encoding, so there's zero extra generation
            # loss beyond what was already baked in when it was saved. WEBP has no
            # native Plex poster support, so that one case still gets converted.
            #
            # Plex's /posters endpoint rejects payloads over ~10MB (a 500, not a
            # helpful error) — a saved PNG that's too large falls back to a
            # high-quality JPEG re-encode instead of failing the resend outright.
            ext = file_path.suffix.lower()
            if ext == ".png" and file_path.stat().st_size <= _PLEX_UPLOAD_SIZE_LIMIT:
                payload, content_type = file_path.read_bytes(), "image/png"
            elif ext in (".jpg", ".jpeg"):
                payload, content_type = file_path.read_bytes(), "image/jpeg"
            else:
                img = Image.open(file_path).convert("RGB")
                buf = BytesIO()
                img.save(buf, "JPEG", quality=98, subsampling=0)
                payload, content_type = buf.getvalue(), "image/jpeg"

            plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
            plex_session.post(
                plex_url,
                headers={**plex_headers(), "Content-Type": content_type},
                data=payload,
                timeout=20,
            ).raise_for_status()
        except Exception as e:
            entry.update(status="error", reason=str(e))
            results.append(entry)
            continue

        logger.info("[LOCAL_ASSETS] Resent %s (rating_key=%s) to Plex", rel_path, rating_key)
        _remove_labels_for_key(rating_key, is_tv, metadata.get("library_id"), db)
        _add_label_for_key(rating_key, is_tv, metadata.get("library_id"), db)
        entry["status"] = "ok"
        results.append(entry)

    succeeded = sum(1 for r in results if r["status"] == "ok")
    return {"status": "ok", "succeeded": succeeded, "total": len(results), "results": results}
