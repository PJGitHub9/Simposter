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
from typing import Optional

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


def _resolve_non_plex_client(rating_key: str):
    """Every caller here only makes sense for a non-Plex item (Plex already
    has its own send flow, plexsend.py) -- resolves and validates the
    server_id the same way fetch_and_cache_poster()/art_cache.py already do
    (Quirk #65), rejecting a Plex or unconfigured server_id with a clear
    error rather than silently no-op'ing."""
    from .. import database as db
    server_id = db.get_server_id_for_rating_key(rating_key)
    if server_id == "plex-1":
        raise HTTPException(400, "This item is on Plex -- use /api/plex/send instead.")
    client = get_client(server_id)
    if not client:
        raise HTTPException(404, f"No configured/enabled media server for rating_key={rating_key} (server_id={server_id})")
    return server_id, client


@router.post("/send-poster")
def api_send_poster(req: MediaServerSendRequest):
    server_id, client = _resolve_non_plex_client(req.rating_key)
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
        client.upload_image(req.rating_key, ImageType.POSTER, image_bytes, content_type)
    except Exception as e:
        logger.error("[MEDIA_SERVER_SEND:%s] Poster upload failed rating_key=%s: %s", server_id, req.rating_key, e)
        raise HTTPException(500, f"Failed to upload poster: {e}")

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
        verify_bytes = client.download_image(req.rating_key, ImageType.POSTER)
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
                "[MEDIA_SERVER_SEND:%s] Poster upload returned success but re-fetching immediately after found NO image at all for rating_key=%s (sent %d bytes) -- the upload likely did not actually apply",
                server_id, req.rating_key, sent_len,
            )
        elif sent_len > 0 and got_len < sent_len * 0.5:
            logger.warning(
                "[MEDIA_SERVER_SEND:%s] Poster upload returned success but re-fetched image (%d bytes) is far smaller than what was sent (%d bytes) for rating_key=%s -- may still be showing an old/different image",
                server_id, got_len, sent_len, req.rating_key,
            )
        else:
            logger.info(
                "[MEDIA_SERVER_SEND:%s] Poster upload verified -- re-fetched %d bytes vs. %d bytes sent for rating_key=%s",
                server_id, got_len, sent_len, req.rating_key,
            )
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND:%s] Post-upload verification fetch failed (non-fatal): %s", server_id, e)

    new_poster_url = None
    try:
        from .. import database as db
        from .movies import _save_poster_cache, _poster_cache_url
        saved = _save_poster_cache(req.rating_key, image_bytes, content_type)
        if saved:
            new_poster_url = _poster_cache_url(req.rating_key, saved)
            from .. import cache as cache_mod
            cache_mod.update_poster(req.rating_key, new_poster_url)
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND:%s] Failed to update poster cache after upload: %s", server_id, e)

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
        save_or_cache_render(req.rating_key, image_bytes, None)
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND:%s] Failed to update resend cache after upload: %s", server_id, e)

    logger.info("[MEDIA_SERVER_SEND:%s] Poster sent for rating_key=%s", server_id, req.rating_key)
    return {"status": "ok", "poster_url": new_poster_url}


@router.post("/send-logo")
def api_send_logo(req: MediaServerSendRequest):
    server_id, client = _resolve_non_plex_client(req.rating_key)
    image_bytes, content_type = _resolve_image_bytes(req)

    from .save import normalize_logo_for_plex
    image_bytes, content_type = normalize_logo_for_plex(image_bytes, content_type)

    try:
        client.upload_image(req.rating_key, ImageType.LOGO, image_bytes, content_type)
    except Exception as e:
        logger.error("[MEDIA_SERVER_SEND:%s] Logo upload failed rating_key=%s: %s", server_id, req.rating_key, e)
        raise HTTPException(500, f"Failed to upload logo: {e}")

    new_logo_url = None
    try:
        from .. import database as db
        from .movies import _save_logo_cache, _logo_cache_url
        saved = _save_logo_cache(req.rating_key, image_bytes, content_type)
        if saved:
            new_logo_url = _logo_cache_url(req.rating_key, saved)
            if req.is_tv:
                db.update_tv_logo_url(req.rating_key, new_logo_url)
            else:
                db.update_movie_logo_url(req.rating_key, new_logo_url)
    except Exception as e:
        logger.debug("[MEDIA_SERVER_SEND:%s] Failed to update logo cache after upload: %s", server_id, e)

    logger.info("[MEDIA_SERVER_SEND:%s] Logo sent for rating_key=%s", server_id, req.rating_key)
    return {"status": "ok", "logo_url": new_logo_url}


@router.post("/send-backdrop")
def api_send_backdrop(req: MediaServerSendRequest):
    server_id, client = _resolve_non_plex_client(req.rating_key)
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
