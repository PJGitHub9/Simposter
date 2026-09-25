"""Generic disk cache for a single-image-per-item Plex asset synced via the
metadata Image[] array (clearLogo, art, ...). Factored out of what used to be
movies.py's logo-only cache helpers so a second asset type (backdrop/"art")
doesn't have to duplicate the same four functions a second time -- see
CLAUDE.md's Backdrop feature note if this file is touched again."""
from pathlib import Path
from typing import Optional

import requests

from ..config import settings, plex_headers, plex_session, logger

# Maps this app's Plex-XML-derived `plex_image_type` string (what make_art_cache()
# was originally built around) to the server-agnostic ImageType enum
# (backend/media_server/base.py) -- used only for the non-Plex fetch branch below,
# so a Jellyfin/Emby item routes through MediaServerClient.download_image() with
# the right image type instead of always assuming Plex.
_PLEX_TYPE_TO_IMAGE_TYPE = {
    "clearLogo": "logo",
    "art": "backdrop",
    "backgroundSquare": "square_art",
}


def make_art_cache(cache_dir: str, route_prefix: str, plex_image_type: str, direct_endpoint: Optional[str] = None):
    """Returns (cache_path, cache_url, save_cache, fetch_and_cache, get_or_create_thumbnail) for one asset type.

    cache_dir: on-disk directory (e.g. LOGO_CACHE_DIR, ART_CACHE_DIR)
    route_prefix: the serving route's path segment (e.g. "logo", "backdrop") -- used
        only to build cache-busting URLs, not to register the route itself.
    plex_image_type: the `type` value Plex's metadata Image[] array uses for this
        asset ("clearLogo") -- used as a fallback if direct_endpoint isn't set or fails.
    direct_endpoint: when set (e.g. "art"), tries GET
        {PLEX_URL}/library/metadata/{rating_key}/{direct_endpoint} FIRST -- Plex serves
        the item's current asset directly at this path (the same convention
        fetch_and_cache_poster() already relies on via /thumb, and the same path
        plexsend.py's uploads POST to), which is more reliable than hunting the
        Image[] array for a matching `type` (that array doesn't reliably include a
        background-art entry at all, which is what left backdrops never caching
        despite a scan reporting it fetched them -- see CLAUDE.md's Backdrop quirk).
    """
    _cache_dir = Path(cache_dir)

    def cache_path(rating_key: str) -> Optional[Path]:
        for ext in ("png", "jpg", "jpeg", "webp"):
            candidate = _cache_dir / f"{rating_key}.{ext}"
            if candidate.exists():
                return candidate
        return None

    def cache_url(rating_key: str, cached: Path) -> str:
        ts = int(cached.stat().st_mtime)
        return f"/api/{route_prefix}/{rating_key}?raw=1&v={ts}"

    def save_cache(rating_key: str, content: bytes, content_type: str) -> Optional[Path]:
        ext = (content_type.split("/")[-1] if "/" in content_type else "png").lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "png"
        target = _cache_dir / f"{rating_key}.{ext}"
        try:
            target.write_bytes(content)
            return target
        except Exception as e:
            logger.debug("[ART_CACHE:%s] Failed to write cache for %s: %s", plex_image_type, rating_key, e)
            return None

    def fetch_and_cache(rating_key: str, force_refresh: bool = False) -> Optional[Path]:
        """Fetch this asset type from Plex and cache locally. Returns cached file path or None."""
        if not force_refresh:
            cached = cache_path(rating_key)
            if cached:
                return cached

        from .. import database as db
        server_id = db.get_server_id_for_rating_key(rating_key)
        if server_id != "plex-1":
            image_type_value = _PLEX_TYPE_TO_IMAGE_TYPE.get(plex_image_type)
            if not image_type_value:
                return None
            try:
                from ..media_server import get_client, ImageType
                client = get_client(server_id)
                if not client:
                    return None
                data = client.download_image(rating_key, ImageType(image_type_value))
                if not data:
                    return None
                # Jellyfin's download_image() returns raw bytes with no content-type
                # header of its own -- Primary/Backdrop/Logo images are virtually
                # always JPEG or PNG in practice, and save_cache()'s extension
                # detection falls back to "png" for anything it doesn't recognize
                # anyway, so a fixed guess here is a cosmetic detail, not a
                # correctness one (the bytes themselves are never re-encoded).
                return save_cache(rating_key, data, "image/jpeg")
            except Exception as e:
                logger.debug("[ART_CACHE:%s] Non-Plex fetch failed for %s (server=%s): %s", plex_image_type, rating_key, server_id, e)
                return None

        if direct_endpoint:
            try:
                import time as _time
                cache_buster = f"?X-Plex-Token={settings.PLEX_TOKEN}&t={int(_time.time())}" if force_refresh else ""
                direct_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/{direct_endpoint}{cache_buster}"
                r = plex_session.get(direct_url, headers=plex_headers(), timeout=10)
                if r.status_code == 200 and r.content:
                    content_type = r.headers.get("content-type", "image/jpeg")
                    saved = save_cache(rating_key, r.content, content_type)
                    if saved:
                        return saved
            except Exception as e:
                logger.debug("[ART_CACHE:%s] Direct /%s fetch failed for %s, falling back to Image[] lookup: %s", plex_image_type, direct_endpoint, rating_key, e)

        try:
            metadata_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
            json_headers = {**plex_headers(), "Accept": "application/json"}
            r = plex_session.get(metadata_url, headers=json_headers, timeout=5)
            if r.status_code != 200:
                return None

            asset_url = None
            try:
                data = r.json()
                container = data.get("MediaContainer", {})
                images = container.get("Image", [])
                if not images:
                    for item in container.get("Metadata", []):
                        images = item.get("Image", [])
                        if images:
                            break
                for img in images:
                    if img.get("type") == plex_image_type:
                        asset_url = img.get("url")
                        break
            except Exception:
                pass

            if not asset_url:
                return None

            if asset_url.startswith("/"):
                asset_url = f"{settings.PLEX_URL}{asset_url}"
                asset_r = plex_session.get(asset_url, headers=plex_headers(), timeout=10)
            else:
                asset_r = requests.get(asset_url, timeout=10)
            if asset_r.status_code != 200:
                logger.debug("[ART_CACHE:%s] Failed to download for %s: HTTP %s", plex_image_type, rating_key, asset_r.status_code)
                return None
            content_type = asset_r.headers.get("content-type", "image/png")
            return save_cache(rating_key, asset_r.content, content_type)
        except Exception as e:
            logger.debug("[ART_CACHE:%s] Failed to fetch Plex asset for %s: %s", plex_image_type, rating_key, e)
            return None

    def get_or_create_thumbnail(rating_key: str, source: Path, max_dim: int = 480, quality: int = 80) -> Optional[Path]:
        """Downscaled JPEG derivative of an already-cached full-size asset, purely
        for fast grid browsing -- the source file itself is untouched and is still
        what the editor modal's "Current X" preview and any Plex re-send actually
        use. Backdrops (photographic) and especially Square Art (a freshly
        Simposter-rendered 2000x2000 PNG once an item has been sent) can be several
        MB; Poster grid tiles don't have this problem because Plex's own /thumb
        convenience path (which posters fetch through) already serves a
        pre-downscaled preview -- there's no equivalent for /art or /squareArt, so
        without this every grid tile downloaded the full original.
        Regenerated automatically whenever the source is newer than the last
        thumbnail (e.g. after a fresh send overwrites the cached file)."""
        thumb_dir = _cache_dir / "thumbs"
        thumb_path = thumb_dir / f"{rating_key}.jpg"
        try:
            if thumb_path.exists() and thumb_path.stat().st_mtime >= source.stat().st_mtime:
                return thumb_path
            from PIL import Image
            thumb_dir.mkdir(parents=True, exist_ok=True)
            img = Image.open(source).convert("RGB")
            img.thumbnail((max_dim, max_dim))
            img.save(thumb_path, "JPEG", quality=quality)
            return thumb_path
        except Exception as e:
            logger.debug("[ART_CACHE:%s] Failed to generate thumbnail for %s: %s", plex_image_type, rating_key, e)
            return None

    return cache_path, cache_url, save_cache, fetch_and_cache, get_or_create_thumbnail
