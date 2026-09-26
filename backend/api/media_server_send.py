"""Real send-to-Jellyfin/Emby support -- the capability Quirk #68 explicitly
disabled "Send to Plex" for, rather than leaving a confusing failure, with a
note that real support was separate, later work. This is that work.

Deliberately a NEW, separate module rather than threading a server_id branch
through plexsend.py (large, already complex, Plex-only by design -- see that
file's own docstrings). The two files duplicate some structure (bytes
resolution, cache-update-after-upload) rather than sharing it, matching this
project's own established preference for keeping Plex's working code
completely untouched over a shared abstraction that risks it (see Quirk #61's
identical reasoning for upsert_media_server_movies() vs. bulk_refresh_cache()).

Deliberately scoped to poster/logo/backdrop only (no square_art -- Jellyfin's
own client.upload_image() raises NotImplementedError for it, see Quirk #59),
and deliberately does NOT send Discord/Apprise notifications yet (plexsend.py's
sends do) -- a reasonable, explicitly-noted simplification for a first version,
not an oversight.
"""
import base64
from typing import List, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import logger
from ..media_server import get_client, ImageType
from ..save_paths import save_or_cache_render

router = APIRouter(prefix="/media-server", tags=["media-server"])


class MediaServerSendRequest(BaseModel):
    rating_key: str
    image_data: Optional[str] = None   # base64 data URL, e.g. "data:image/png;base64,..."
    image_url: Optional[str] = None    # external URL to download
    is_tv: bool = False
    # When given, `rating_key` is treated as the SERIES item id on this server
    # (not the item to upload to directly) and is resolved to that specific
    # season's own item id via find_season_by_index() before uploading. None
    # (the default) preserves the original behavior exactly -- upload
    # straight to `rating_key` (Quirk #100, see MediaServerClient's own
    # docstring for how season resolution actually works).
    season_index: Optional[int] = None
    # Optional explicit hint, used instead of the db.get_server_id_for_rating_key()
    # lookup in _resolve_non_plex_client(). A season's own item id (whether
    # sent here directly, or resolved above via season_index) is never
    # individually scanned/cached -- only the series-level item gets a
    # server_id row -- so that lookup silently defaults to 'plex-1' for any
    # season rating_key and the send is wrongly rejected with "This item is
    # on Plex". The caller (the TV editor's send picker) already knows which
    # server it's targeting and can pass it straight through.
    server_id: Optional[str] = None


def _resolve_image_bytes(req: MediaServerSendRequest) -> tuple:
    """Mirrors plexsend.py's identical art_data/art_url resolution pattern
    (base64 data URL preferred, external URL as fallback) -- see
    api_plex_send_backdrop() for the pattern this was copied from."""
    if req.image_data:
        try:
            header, data = req.image_data.split(",", 1)
            content_type = "image/png" if "png" in header else "image/jpeg"
            return base64.b64decode(data), content_type
        except Exception as e:
            raise HTTPException(400, f"Invalid image_data: {e}")
    if req.image_url:
        from ..middleware.validation import validate_url
        url = validate_url(req.image_url)
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            return r.content, content_type
        except Exception as e:
            raise HTTPException(500, f"Failed to download image: {e}")
    raise HTTPException(400, "Either image_url or image_data must be provided.")


def _resolve_season_item_id(client, series_item_id: str, season_index: Optional[int], title_hint: str = "?") -> Optional[str]:
    """When season_index is given, resolves the specific season's own item id
    on this server via find_season_by_index() (Quirk #100) -- returns the
    series_item_id unchanged when season_index is None, so every existing
    series-only caller is a strict no-op through this helper. Returns None
    (not the series id) when a season was requested but couldn't be resolved
    -- callers must treat that as "nothing to upload to", never silently
    fall back to the series item."""
    if season_index is None:
        return series_item_id
    resolved = client.find_season_by_index(series_item_id, season_index)
    if not resolved:
        logger.debug("[MEDIA_SERVER_SEND:%s] Could not resolve season %s for series item=%s [%s]",
                     client.server_id, season_index, series_item_id, title_hint)
    return resolved


@router.get("/resolve-season-item")
def api_resolve_season_item(server_id: str, series_item_id: str, season_index: int):
    """Resolves a specific season's own item id on `server_id`, given that
    server's already-known SERIES item id (e.g. from a merged item's
    `other_servers`, Quirk #67/#75) and a season index. Used by the TV
    editor's multi-server preview toggle/send picker (Quirk #100) to build a
    season-scoped linkedServers list -- `other_servers` only ever carries
    series-level rating_keys (Phase 4b's dedup is show-level only), so a
    season target needs this extra resolution step the series case doesn't.
    Read-only, no upload -- a thin wrapper around find_season_by_index()."""
    client = get_client(server_id)
    if not client:
        raise HTTPException(404, f"No configured/enabled media server for server_id={server_id}")
    item_id = client.find_season_by_index(series_item_id, season_index)
    return {"item_id": item_id}


def _resolve_non_plex_client(rating_key: str, server_id_hint: Optional[str] = None):
    """Every caller here only makes sense for a non-Plex item (Plex already
    has its own send flow, plexsend.py) -- resolves and validates the
    server_id the same way fetch_and_cache_poster()/art_cache.py already do
    (Quirk #65), rejecting a Plex or unconfigured server_id with a clear
    error rather than silently no-op'ing.

    server_id_hint: use this instead of the DB lookup when given -- required
    for a season item id, which (unlike a movie/series rating_key) is never
    individually cached with its own server_id row, so the lookup alone
    would always misresolve it to the 'plex-1' default and reject the send."""
    from .. import database as db
    server_id = server_id_hint or db.get_server_id_for_rating_key(rating_key)
    if server_id == "plex-1":
        raise HTTPException(400, "This item is on Plex -- use /api/plex/send instead.")
    client = get_client(server_id)
    if not client:
        raise HTTPException(404, f"No configured/enabled media server for rating_key={rating_key} (server_id={server_id})")
    return server_id, client


def _upload_poster_and_verify(client, server_id: str, item_id: str, image_bytes: bytes, content_type: str) -> None:
    """Core upload+verify-diagnostic logic for a poster, factored out of
    api_send_poster() so batch.py's multi-server sync (which already has a
    resolved (client, item_id) pair from find_item_by_external_id() rather
    than a rating_key to look up via _resolve_non_plex_client()) can reuse
    the exact same upload call and Quirk #77 verification diagnostics
    instead of a third independent copy of this logic. Raises on a genuine
    upload failure (caller's responsibility to catch/report); the
    verification re-fetch is purely diagnostic and never raises."""
    client.upload_image(item_id, ImageType.POSTER, image_bytes, content_type)

    # A 200 from upload_image() only proves the server ACCEPTED the request --
    # not that it actually stored the new image (see CLAUDE.md Quirk #36's
    # plex_add_label() precedent for the identical class of bug: a bare HTTP
    # success status is not proof a field/asset edit actually took effect).
    # Re-fetch immediately and compare size against what was just sent -- a
    # missing image or a size wildly different from what was uploaded is a
    # strong signal the upload didn't really apply, even though nothing
    # raised. Purely diagnostic (logged, not surfaced as a request failure —
    # a verification-fetch problem of its own isn't proof the upload failed
    # either), specifically to give real data the next time this is tried,
    # rather than continuing to guess from a clean-looking log.
    try:
        verify_bytes = client.download_image(item_id, ImageType.POSTER)
        sent_len = len(image_bytes)
        got_len = len(verify_bytes) if verify_bytes is not None else 0
        # A relative threshold, not a fixed byte count -- Jellyfin may
        # legitimately re-encode/re-compress on its end, so an exact or
        # near-exact match isn't guaranteed even on a genuine success; the
        # real signal worth flagging is "way smaller than what was sent"
        # (e.g. still returning an old, unrelated, or placeholder image)
        # rather than any difference at all.
        if verify_bytes is None:
            logger.warning(
                "[MEDIA_SERVER_SEND:%s] Poster upload returned success but re-fetching immediately after found NO image at all for item_id=%s (sent %d bytes) -- the upload likely did not actually apply",
                server_id, item_id, sent_len,
            )
        elif sent_len > 0 and got_len < sent_len * 0.5:
            logger.warning(
                "[MEDIA_SERVER_SEND:%s] Poster upload returned success but re-fetched image (%d bytes) is far smaller than what was sent (%d bytes) for item_id=%s -- may still be showing an old/different image",
                server_id, got_len, sent_len, item_id,
            )
        else:
            logger.info(
                "[MEDIA_SERVER_SEND:%s] Poster upload verified -- re-fetched %d bytes vs. %d bytes sent for item_id=%s",
                server_id, got_len, sent_len, item_id,
            )
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND:%s] Post-upload verification fetch failed (non-fatal): %s", server_id, e)


def _cache_poster_after_upload(item_id: str, image_bytes: bytes, content_type: str) -> Optional[str]:
    """Updates the local poster disk cache + the resend cache after a
    successful non-Plex poster upload -- factored out of api_send_poster()
    for the same reuse reason as _upload_poster_and_verify() above. Never
    raises; returns the new cache URL, or None if either write failed."""
    new_poster_url = None
    try:
        from .movies import _save_poster_cache, _poster_cache_url
        saved = _save_poster_cache(item_id, image_bytes, content_type)
        if saved:
            new_poster_url = _poster_cache_url(item_id, saved)
            from .. import cache as cache_mod
            cache_mod.update_poster(item_id, new_poster_url)
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND] Failed to update poster cache after upload for item_id=%s: %s", item_id, e)

    # Also feeds the SAME resend cache plexsend.py's api_plex_send() writes to
    # (save_or_cache_render()) -- this was missing entirely before, which
    # meant a poster sent to Jellyfin never showed up as resendable: the
    # grid's paper-airplane resend arrow (MovieCard.vue) is gated on whether
    # /api/render-cache/cached-keys knows about this rating_key, and that
    # endpoint only ever finds what save_or_cache_render() has written.
    # User-reported directly: "the arrow to send posters isnt there when
    # its on the jellyfin poster view." Deliberately passes ctx=None (always
    # the hidden internal cache, never the visible asset-folder path) rather
    # than building a real SaveContext -- "save to asset folder on send"
    # resolves {folder} from Plex's own metadata (get_media_folder_name()),
    # which has no Jellyfin equivalent wired up yet; falling back to the
    # hidden cache unconditionally is a safe, correct simplification (the
    # poster is still genuinely resendable), just not asset-folder-aware for
    # a Jellyfin-sourced send specifically.
    try:
        save_or_cache_render(item_id, image_bytes, None)
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND] Failed to update resend cache after upload for item_id=%s: %s", item_id, e)

    return new_poster_url


def _cache_logo_after_upload(item_id: str, image_bytes: bytes, content_type: str, is_tv: bool = False) -> Optional[str]:
    """Updates the local logo disk cache + DB logo_url after a successful
    non-Plex logo upload -- factored out of api_send_logo() for the same
    reuse reason as the poster helpers above. Never raises."""
    new_logo_url = None
    try:
        from .. import database as db
        from .movies import _save_logo_cache, _logo_cache_url
        saved = _save_logo_cache(item_id, image_bytes, content_type)
        if saved:
            new_logo_url = _logo_cache_url(item_id, saved)
            if is_tv:
                db.update_tv_logo_url(item_id, new_logo_url)
            else:
                db.update_movie_logo_url(item_id, new_logo_url)
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND] Failed to update logo cache after upload for item_id=%s: %s", item_id, e)
    return new_logo_url


@router.post("/send-poster")
def api_send_poster(req: MediaServerSendRequest):
    server_id, client = _resolve_non_plex_client(req.rating_key, req.server_id)
    item_id = _resolve_season_item_id(client, req.rating_key, req.season_index)
    if not item_id:
        raise HTTPException(404, f"Could not resolve season {req.season_index} for series {req.rating_key} on {server_id}")
    image_bytes, _content_type = _resolve_image_bytes(req)

    from io import BytesIO
    from PIL import Image
    from .save import encode_poster_for_plex
    # Reused despite the Plex-specific name -- it's a generic RGB-flatten +
    # tiered-PNG-then-JPEG-under-size-limit encode (Quirk #12), not coupled to
    # Plex's own upload beyond the size cap it enforces, which is a reasonable
    # safety net for any destination. Takes a PIL Image, not raw bytes (unlike
    # normalize_logo_for_plex()/normalize_backdrop_for_plex() below) -- decode
    # first.
    img = Image.open(BytesIO(image_bytes))
    image_bytes, content_type = encode_poster_for_plex(img)

    try:
        _upload_poster_and_verify(client, server_id, item_id, image_bytes, content_type)
    except Exception as e:
        logger.error("[MEDIA_SERVER_SEND:%s] Poster upload failed item_id=%s: %s", server_id, item_id, e)
        raise HTTPException(500, f"Failed to upload poster: {e}")

    new_poster_url = _cache_poster_after_upload(item_id, image_bytes, content_type)

    logger.info("[MEDIA_SERVER_SEND:%s] Poster sent for item_id=%s%s", server_id, item_id,
                f" (season {req.season_index} of series {req.rating_key})" if req.season_index is not None else "")
    return {"status": "ok", "poster_url": new_poster_url, "item_id": item_id}


@router.post("/send-logo")
def api_send_logo(req: MediaServerSendRequest):
    server_id, client = _resolve_non_plex_client(req.rating_key, req.server_id)
    item_id = _resolve_season_item_id(client, req.rating_key, req.season_index)
    if not item_id:
        raise HTTPException(404, f"Could not resolve season {req.season_index} for series {req.rating_key} on {server_id}")
    image_bytes, content_type = _resolve_image_bytes(req)

    from .save import normalize_logo_for_plex
    image_bytes, content_type = normalize_logo_for_plex(image_bytes, content_type)

    try:
        client.upload_image(item_id, ImageType.LOGO, image_bytes, content_type)
    except Exception as e:
        logger.error("[MEDIA_SERVER_SEND:%s] Logo upload failed item_id=%s: %s", server_id, item_id, e)
        raise HTTPException(500, f"Failed to upload logo: {e}")

    new_logo_url = _cache_logo_after_upload(item_id, image_bytes, content_type, is_tv=req.is_tv)

    logger.info("[MEDIA_SERVER_SEND:%s] Logo sent for item_id=%s%s", server_id, item_id,
                f" (season {req.season_index} of series {req.rating_key})" if req.season_index is not None else "")
    return {"status": "ok", "logo_url": new_logo_url, "item_id": item_id}


def sync_render_to_linked_servers(
    tmdb_id: Optional[int],
    media_type: str,          # "movie" | "tv" -- matches MediaServerClient.find_item_by_external_id()'s convention
    library_id: Optional[str],
    target_ids: List[str],
    poster_bytes: Optional[bytes] = None,
    poster_content_type: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
    logo_content_type: Optional[str] = None,
    title_hint: str = "?",
    season_index: Optional[int] = None,
) -> List[str]:
    """Sends already-rendered poster/logo bytes (whichever are given -- both
    are optional and independent) to whichever of `target_ids` are BOTH
    requested AND actually linked to `library_id` via a Library Group
    (Quirk #62/#64) -- the same group-scoping fix Quirk #95 applied to
    webhook cross-server sync (_sync_poster_to_other_servers() in
    webhooks.py, a separate, not-yet-unified implementation of a similar
    idea -- see that function's own docstring), applied here so a caller
    (batch.py's multi-server send, Quirk #95's follow-up) can't reach an
    enabled-but-unlinked server just because a requested target happens to
    also have a matching tmdb_id. Returns the list of server_ids actually
    synced to (poster and/or logo -- a partial per-item failure on one
    asset type doesn't exclude a server that succeeded on the other).
    Deliberately Plex-agnostic -- callers should exclude 'plex-1' from
    target_ids themselves (Plex already has its own real send path); any
    'plex-1' present here is silently ignored rather than erroring, since
    intersecting against `allowed` (which never includes 'plex-1') already
    filters it out naturally.

    `season_index` (Quirk #100): when given, `tmdb_id` still identifies the
    SHOW (tmdb_id has no reliable per-season identity), and each linked
    server's SERIES item (resolved via find_item_by_external_id() exactly as
    before) is then further resolved to that specific season via
    find_season_by_index() -- a server where the season can't be resolved is
    skipped for this sync, same as an unmatched series would be, never a hard
    failure for the others."""
    if not tmdb_id or not target_ids:
        return []
    from ..config import get_library_group_members
    linked = get_library_group_members("plex-1", str(library_id or ""), media_type) if library_id else None
    # Keep each linked member's OWN library_id, not just its server_id --
    # a real, live-reported bug (Gran Turismo existing in both a linked
    # "4k-Movies" Jellyfin library and an untracked "Movies" library on the
    # same server) traced to this being discarded here, so
    # find_item_by_external_id() searched the whole server unscoped and
    # could resolve to the wrong same-tmdb_id item nondeterministically.
    allowed = {sid: lid for sid, lid in (linked or []) if sid != "plex-1"}
    requested = {t for t in target_ids if t and t != "plex-1"}
    to_sync = requested & allowed.keys()
    if not to_sync:
        return []

    synced: List[str] = []
    for server_id in to_sync:
        client = get_client(server_id)
        if not client:
            continue
        try:
            series_item_id = client.find_item_by_external_id(tmdb_id, None, media_type, library_id=allowed.get(server_id))
            if not series_item_id:
                logger.debug("[MEDIA_SERVER_SEND:%s] No matching item for tmdb_id=%s [%s] -- skipping", server_id, tmdb_id, title_hint)
                continue
            item_id = _resolve_season_item_id(client, series_item_id, season_index, title_hint)
            if not item_id:
                # Series resolved fine, but this specific season didn't --
                # skip this server for this sync rather than falling back to
                # the series item (which would silently overwrite the show's
                # own poster with a season's).
                continue
            did_something = False
            if poster_bytes:
                _upload_poster_and_verify(client, server_id, item_id, poster_bytes, poster_content_type or "image/png")
                _cache_poster_after_upload(item_id, poster_bytes, poster_content_type or "image/png")
                did_something = True
            if logo_bytes:
                client.upload_image(item_id, ImageType.LOGO, logo_bytes, logo_content_type or "image/png")
                _cache_logo_after_upload(item_id, logo_bytes, logo_content_type or "image/png", is_tv=(media_type == "tv"))
                did_something = True
            if did_something:
                synced.append(server_id)
                logger.info("[MEDIA_SERVER_SEND:%s] Synced poster/logo for tmdb_id=%s [%s] -> item_id=%s", server_id, tmdb_id, title_hint, item_id)
        except Exception as e:
            logger.warning("[MEDIA_SERVER_SEND:%s] Sync failed for tmdb_id=%s [%s]: %s", server_id, tmdb_id, title_hint, e)
    return synced


@router.post("/send-backdrop")
def api_send_backdrop(req: MediaServerSendRequest):
    server_id, client = _resolve_non_plex_client(req.rating_key, req.server_id)
    image_bytes, content_type = _resolve_image_bytes(req)

    from .save import normalize_backdrop_for_plex
    image_bytes, content_type = normalize_backdrop_for_plex(image_bytes, content_type)

    try:
        client.upload_image(req.rating_key, ImageType.BACKDROP, image_bytes, content_type)
    except Exception as e:
        logger.error("[MEDIA_SERVER_SEND:%s] Backdrop upload failed rating_key=%s: %s", server_id, req.rating_key, e)
        raise HTTPException(500, f"Failed to upload backdrop: {e}")

    new_art_url = None
    try:
        from .. import database as db
        from .movies import _save_art_cache, _art_cache_url, _art_thumbnail
        saved = _save_art_cache(req.rating_key, image_bytes, content_type)
        if saved:
            _art_thumbnail(req.rating_key, saved)
            new_art_url = _art_cache_url(req.rating_key, saved)
            if req.is_tv:
                db.update_tv_art_url(req.rating_key, new_art_url)
            else:
                db.update_movie_art_url(req.rating_key, new_art_url)
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND:%s] Failed to update backdrop cache after upload: %s", server_id, e)

    logger.info("[MEDIA_SERVER_SEND:%s] Backdrop sent for rating_key=%s", server_id, req.rating_key)
    return {"status": "ok", "art_url": new_art_url}
