"""PlexClient -- wraps Simposter's existing, already-tested Plex-calling code
behind the MediaServerClient interface. Deliberately a thin delegation layer,
not a rewrite: every method either calls straight into the existing function
in config.py/scheduler.py/webhooks.py that already does this job, or (where no
generic-enough primitive existed -- list_libraries/list_items/upload_image/
download_image/test_connection) is written fresh using the exact same
plex_session/plex_headers/XML-parsing patterns those existing functions use,
since this project's own history (CLAUDE.md Quirk #17/#28) has repeatedly
found new ad-hoc `requests.get/post` calls to be a source of real bugs.

Known, deliberate limitation: this client reads url/token from the global
`settings.PLEX_URL`/`settings.PLEX_TOKEN` (via the functions it delegates to,
which were all written for a single-Plex-server world), not from the
server_id-specific url/token passed to __init__. It therefore only correctly
represents the one globally-configured Plex server -- matching every real
install today, exactly one Plex server. Genuinely supporting a second,
independently-configured Plex server would additionally require threading
url/token through every one of those underlying functions, which is separate,
larger work not yet needed. See CLAUDE.md Quirk #58.
"""
import xml.etree.ElementTree as ET
from typing import Any, List, Optional

from ..config import (
    settings,
    plex_headers,
    plex_session,
    logger,
    get_plex_media_info,
    get_movie_tmdb_id,
    get_media_folder_name,
    plex_remove_label,
    plex_add_label,
    extract_tmdb_id_from_metadata,
)
from .base import ImageType, Library, MediaItem, MediaItemMetadata, MediaServerClient

_UPLOAD_ENDPOINT = {
    ImageType.POSTER: "posters",
    ImageType.BACKDROP: "arts",
    ImageType.SQUARE_ART: "squareArts",
    # LOGO deliberately excluded -- always /library/metadata/{id}/clearLogos,
    # never collection-routed, matching plexsend.py's existing behavior exactly.
}

_DIRECT_DOWNLOAD_ENDPOINT = {
    ImageType.POSTER: "thumb",
    ImageType.BACKDROP: "art",
    ImageType.SQUARE_ART: "squareArt",
    ImageType.LOGO: None,  # no single direct endpoint -- falls through to the Image[] lookup below
}


def _media_segment(is_collection: bool) -> str:
    return "collections" if is_collection else "metadata"


class PlexClient(MediaServerClient):
    def __init__(self, server_id: str, url: Optional[str] = None, token: Optional[str] = None):
        self.server_id = server_id
        # Stored for completeness/future use (e.g. a second Plex server), but
        # not yet what the delegated-to functions actually read from -- see
        # this module's docstring.
        self.url = url or settings.PLEX_URL
        self.token = token or settings.PLEX_TOKEN

    def test_connection(self) -> bool:
        try:
            r = plex_session.get(
                f"{settings.PLEX_URL}/identity",
                headers=plex_headers(),
                timeout=8,
            )
            return r.ok
        except Exception as e:
            logger.debug("[PLEX_CLIENT:%s] test_connection failed: %s", self.server_id, e)
            return False

    def list_libraries(self) -> List[Library]:
        try:
            r = plex_session.get(f"{settings.PLEX_URL}/library/sections", headers=plex_headers(), timeout=8)
            r.raise_for_status()
            root = ET.fromstring(r.text)
        except Exception as e:
            logger.warning("[PLEX_CLIENT:%s] list_libraries failed: %s", self.server_id, e)
            return []

        out: List[Library] = []
        for directory in root.findall(".//Directory"):
            lib_type = directory.get("type")
            # Plex's own XML says "show", but every other MediaServerClient
            # method in this app (list_items, find_item_by_external_id) takes
            # a "movie"|"tv" media_type -- normalize here so Library.media_type
            # matches that same convention instead of leaking Plex's raw value.
            media_type = {"movie": "movie", "show": "tv"}.get(lib_type)
            if not media_type:
                continue
            out.append(Library(id=directory.get("key"), name=directory.get("title") or "", media_type=media_type))
        return out

    def list_items(self, library_id: str, media_type: str) -> List[MediaItem]:
        type_param = "1" if media_type == "movie" else "2"
        try:
            url = f"{settings.PLEX_URL}/library/sections/{library_id}/all?type={type_param}"
            r = plex_session.get(url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.text)
        except Exception as e:
            logger.warning("[PLEX_CLIENT:%s] list_items failed for library=%s: %s", self.server_id, library_id, e)
            return []

        tag = "Video" if media_type == "movie" else "Directory"
        out: List[MediaItem] = []
        for el in root.findall(f".//{tag}"):
            rating_key = el.get("ratingKey")
            if not rating_key:
                continue
            year = el.get("year")
            added_at = el.get("addedAt")
            out.append(MediaItem(
                id=rating_key,
                title=el.get("title") or "",
                year=int(year) if year and year.isdigit() else None,
                added_at=int(added_at) if added_at and added_at.isdigit() else None,
                library_id=library_id,
            ))
        return out

    def get_item_metadata(self, item_id: str) -> MediaItemMetadata:
        info = get_plex_media_info(item_id) or {}
        tmdb_id = get_movie_tmdb_id(item_id)
        return MediaItemMetadata(
            tmdb_id=tmdb_id,
            video_resolution=info.get("video_resolution"),
            video_codec=info.get("video_codec"),
            audio_codec=info.get("audio_codec"),
            audio_channels=info.get("audio_channels"),
            audio_language=info.get("audio_language"),
            edition=info.get("edition"),
        )

    def item_exists(self, item_id: str) -> Optional[bool]:
        try:
            r = plex_session.get(
                f"{settings.PLEX_URL}/library/metadata/{item_id}",
                headers=plex_headers(),
                timeout=6,
            )
            if r.status_code == 404:
                return False
            if r.status_code == 200:
                return True
            return None
        except Exception:
            return None

    def upload_image(self, item_id: str, image_type: ImageType, image_bytes: bytes,
                      content_type: str, is_collection: bool = False) -> None:
        if image_type == ImageType.LOGO:
            url = f"{settings.PLEX_URL}/library/metadata/{item_id}/clearLogos"
        else:
            endpoint = _UPLOAD_ENDPOINT[image_type]
            url = f"{settings.PLEX_URL}/library/{_media_segment(is_collection)}/{item_id}/{endpoint}"

        headers = {"X-Plex-Token": settings.PLEX_TOKEN, "Content-Type": content_type}
        r = plex_session.post(url, headers=headers, data=image_bytes, timeout=20)
        r.raise_for_status()

    def download_image(self, item_id: str, image_type: ImageType) -> Optional[bytes]:
        direct_endpoint = _DIRECT_DOWNLOAD_ENDPOINT.get(image_type)
        if direct_endpoint:
            try:
                r = plex_session.get(
                    f"{settings.PLEX_URL}/library/metadata/{item_id}/{direct_endpoint}",
                    headers=plex_headers(), timeout=10,
                )
                if r.status_code == 200 and r.content:
                    return r.content
            except Exception as e:
                logger.debug("[PLEX_CLIENT:%s] direct download failed for %s/%s: %s", self.server_id, item_id, image_type.value, e)

        # Fall back to hunting the metadata Image[] array for clearLogo (and as a
        # second chance for the others) -- same convention make_art_cache() uses.
        plex_type = {ImageType.LOGO: "clearLogo", ImageType.BACKDROP: "art", ImageType.SQUARE_ART: "backgroundSquare"}.get(image_type)
        if not plex_type:
            return None
        try:
            json_headers = {**plex_headers(), "Accept": "application/json"}
            r = plex_session.get(f"{settings.PLEX_URL}/library/metadata/{item_id}", headers=json_headers, timeout=8)
            if r.status_code != 200:
                return None
            data = r.json()
            images = data.get("MediaContainer", {}).get("Image", [])
            if not images:
                for m in data.get("MediaContainer", {}).get("Metadata", []):
                    images = m.get("Image", [])
                    if images:
                        break
            asset_url = next((img.get("url") for img in images if img.get("type") == plex_type), None)
            if not asset_url:
                return None
            if asset_url.startswith("/"):
                asset_url = f"{settings.PLEX_URL}{asset_url}"
            asset_r = plex_session.get(asset_url, headers=plex_headers(), timeout=10)
            return asset_r.content if asset_r.status_code == 200 else None
        except Exception as e:
            logger.debug("[PLEX_CLIENT:%s] Image[] fallback download failed for %s/%s: %s", self.server_id, item_id, image_type.value, e)
            return None

    def remove_label(self, item_id: str, label: str, content_type: Optional[str] = None) -> bool:
        # plex_remove_label() is fire-and-forget internally (logs, doesn't return
        # a success signal) -- existing call sites already treat it this way, so
        # this wrapper does too rather than fabricating a status this function
        # was never designed to report.
        plex_remove_label(item_id, label, content_type=content_type)
        return True

    def add_label(self, item_id: str, label: str) -> bool:
        plex_add_label(item_id, label)
        return True

    def find_item_by_external_id(self, tmdb_id: Optional[Any], tvdb_id: Optional[Any],
                                  media_type: str) -> Optional[str]:
        try:
            if media_type == "movie" and tmdb_id:
                sections_r = plex_session.get(f"{settings.PLEX_URL}/library/sections", headers=plex_headers(), timeout=10)
                sections_r.raise_for_status()
                sections_root = ET.fromstring(sections_r.content)
                lib_keys = [sec.get("key") for sec in sections_root.findall(".//Directory[@type='movie']")]
                guid_target = f"tmdb://{tmdb_id}"
                item_tag = "Video"
            elif media_type == "tv" and tvdb_id:
                sections_r = plex_session.get(f"{settings.PLEX_URL}/library/sections", headers=plex_headers(), timeout=10)
                sections_r.raise_for_status()
                sections_root = ET.fromstring(sections_r.content)
                lib_keys = [sec.get("key") for sec in sections_root.findall(".//Directory[@type='show']")]
                guid_target = f"tvdb://{tvdb_id}"
                item_tag = "Directory"
            else:
                return None

            for lib_key in lib_keys:
                url = f"{settings.PLEX_URL}/library/sections/{lib_key}/all?includeGuids=1"
                r = plex_session.get(url, headers=plex_headers(), timeout=10)
                r.raise_for_status()
                root = ET.fromstring(r.content)
                for el in root.findall(f".//{item_tag}"):
                    rating_key = el.get("ratingKey")
                    for guid in el.findall("Guid"):
                        if guid.get("id", "") == guid_target:
                            return rating_key
            return None
        except Exception as e:
            logger.error("[PLEX_CLIENT:%s] find_item_by_external_id failed (tmdb=%s tvdb=%s): %s", self.server_id, tmdb_id, tvdb_id, e)
            return None

    def get_folder_name(self, item_id: str, is_tv: bool = False) -> Optional[str]:
        return get_media_folder_name(item_id, is_tv)
