"""JellyfinClient -- also serves Emby via the is_emby flag (they share ~95% of
the same API, see the plan doc sec5.3/sec2.4).

Everything cited below to a confidence level is from
ai_repo/simposter/jellyfin-upgrade-plan.md sec5/sec6, based on this project's
own research into Jellyfin/Emby's real API behavior. Where that research
never exercised something (a case this app hits that the research didn't
cover -- see the plan doc), this file says so explicitly rather than
presenting a guess as confirmed. See CLAUDE.md Quirk #59.
"""
import os
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

import requests

from ..config import logger
from .base import ImageType, Library, MediaItem, MediaItemMetadata, MediaServerClient


def _parse_jellyfin_datetime(value: Optional[str]) -> Optional[int]:
    """Jellyfin's `DateCreated` is an ISO 8601 string with .NET-style
    variable-precision fractional seconds and a trailing 'Z'
    (e.g. "2026-06-29T22:27:37.1150226Z", sometimes 6 digits, sometimes 7)
    -- Python's datetime.fromisoformat() doesn't accept more than 6 fractional
    digits, so it's truncated/padded to microseconds first. `MediaItem.added_at`
    is meant to hold Unix epoch seconds throughout this app (matching Plex's
    own `addedAt` XML attribute, and schemas.py's Movie.addedAt: Optional[int])
    -- converted here so every downstream consumer (DB storage, the API
    response model) never has to know Jellyfin's date format exists. Never
    raises -- an unparseable value returns None. A second, independent
    defensive coercion also exists at the DB-read side (database.py's
    _coerce_added_at()) for any row written before this fix, or by any future
    server type that isn't as careful."""
    if not value:
        return None
    try:
        s = value.rstrip("Z")
        if "." in s:
            main, frac = s.split(".", 1)
            s = f"{main}.{(frac + '000000')[:6]}"
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None

# Confirmed: Primary/Backdrop are both real, working image types. Logo is
# NOT independently confirmed by this research (no prior source ever sent
# one to Jellyfin, always compositing logos locally instead) -- included
# because Jellyfin's API is documented to support a Logo image type and
# this app has a genuine standalone clearlogo pipeline that needs it, but
# this specific mapping needs real-instance verification (plan doc sec13 Q6).
_UPLOAD_IMAGE_TYPE = {
    ImageType.POSTER: "Primary",
    ImageType.BACKDROP: "Backdrop",
    ImageType.LOGO: "Logo",
    # SQUARE_ART deliberately absent -- no confirmed Jellyfin/Emby equivalent
    # exists (plan doc sec13 Q1). upload_image() raises explicitly rather than
    # guessing at an image type name.
}


class JellyfinClient(MediaServerClient):
    def __init__(self, server_id: str, url: str, api_key: str, is_emby: bool = False):
        self.server_id = server_id
        self.is_emby = is_emby
        self.api_key = api_key
        self.url = self._normalize_url(url, is_emby)

    @staticmethod
    def _normalize_url(url: str, is_emby: bool) -> str:
        url = (url or "").rstrip("/")
        if is_emby and url and not url.endswith("/emby"):
            # Auto-corrects a bare Emby host missing the required /emby
            # suffix (plan doc sec5.3) -- a simplified version of the more
            # specific bare-IP/localhost regex this was reasoned from, since
            # this is a convenience default, not a hard
            # requirement (a reverse-proxied Emby URL that legitimately
            # doesn't want /emby appended can just be entered with a
            # trailing path already, since this only appends when missing).
            if re.match(r"^https?://[^/]+$", url):
                url = f"{url}/emby"
                logger.info("[JELLYFIN_CLIENT] Auto-appended /emby to a bare Emby host URL: %s", url)
        return url

    def _headers(self) -> dict:
        # Confirmed identical for Jellyfin and Emby (plan doc sec5.1).
        return {"Authorization": f'MediaBrowser Token="{self.api_key}"'}

    def test_connection(self) -> bool:
        # GET /System/Info, success = non-empty version field, 401 = bad key.
        # Confirmed against real behavior for both Jellyfin and Emby.
        try:
            r = requests.get(f"{self.url}/System/Info", headers=self._headers(), timeout=8)
            if r.status_code == 401:
                return False
            data = r.json()
            return bool(data.get("Version") or data.get("version"))
        except Exception as e:
            logger.debug("[JELLYFIN_CLIENT:%s] test_connection failed: %s", self.server_id, e)
            return False

    def list_libraries(self) -> List[Library]:
        # GET /Library/VirtualFolders. Confirmed.
        try:
            r = requests.get(f"{self.url}/Library/VirtualFolders", headers=self._headers(), timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("[JELLYFIN_CLIENT:%s] list_libraries failed: %s", self.server_id, e)
            return []

        out: List[Library] = []
        for entry in data:
            media_type = {"movies": "movie", "tvshows": "tv"}.get(entry.get("CollectionType"))
            if not media_type:
                continue
            item_id = entry.get("ItemId")
            if not item_id:
                continue
            out.append(Library(id=item_id, name=entry.get("Name") or "", media_type=media_type))
        return out

    def list_items(self, library_id: str, media_type: str) -> List[MediaItem]:
        # Bulk GET /Items?ParentId=...&Recursive=true&Fields=...&IncludeItemTypes=...
        # Confirmed -- the primary listing mechanism, with no per-item detail
        # fetch needed; everything (including ProviderIds) comes from this
        # one bulk response.
        item_type = "Movie" if media_type == "movie" else "Series"
        params = {
            "ParentId": library_id,
            "Recursive": "true",
            "IncludeItemTypes": item_type,
            "Fields": "ProviderIds,Path,ProductionYear,DateCreated",
            "CollapseBoxSetItems": "false",
        }
        try:
            r = requests.get(f"{self.url}/Items", headers=self._headers(), params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("[JELLYFIN_CLIENT:%s] list_items failed for library=%s: %s", self.server_id, library_id, e)
            return []

        out: List[MediaItem] = []
        for item in data.get("Items", []):
            item_id = item.get("Id")
            if not item_id:
                continue
            provider_ids = item.get("ProviderIds") or {}
            out.append(MediaItem(
                id=item_id,
                title=item.get("Name") or "",
                year=item.get("ProductionYear"),
                tmdb_id=provider_ids.get("Tmdb"),
                tvdb_id=provider_ids.get("Tvdb"),
                added_at=_parse_jellyfin_datetime(item.get("DateCreated")),
                library_id=library_id,
                file_path=item.get("Path"),
            ))
        return out

    def _fetch_items_by_ids(self, item_ids: List[str], fields: str = "ProviderIds,Path,MediaStreams,Tags") -> List[dict]:
        """Shared helper for get_item_metadata()/item_exists() -- deliberately
        reuses the *confirmed* bulk /Items endpoint (via the Ids filter)
        rather than a singular GET /Items/{id}, which this project's own
        research never exercised (see this file's module docstring). Not yet
        verified against a real Jellyfin instance -- this is the first thing
        worth checking."""
        if not item_ids:
            return []
        try:
            params = {"Ids": ",".join(item_ids), "Fields": fields}
            r = requests.get(f"{self.url}/Items", headers=self._headers(), params=params, timeout=10)
            r.raise_for_status()
            return r.json().get("Items", [])
        except Exception as e:
            logger.debug("[JELLYFIN_CLIENT:%s] _fetch_items_by_ids failed for %s: %s", self.server_id, item_ids, e)
            return []

    def get_item_metadata(self, item_id: str) -> MediaItemMetadata:
        items = self._fetch_items_by_ids([item_id])
        if not items:
            return MediaItemMetadata()
        item = items[0]
        provider_ids = item.get("ProviderIds") or {}

        # Resolution/HDR: confirmed field names differ between Jellyfin and
        # Emby (plan doc sec5.3) -- Width/Height always present; HDR type is
        # VideoRangeType (Jellyfin) vs. ExtendedVideoSubTypeDescription/
        # ExtendedVideoType (Emby).
        video_resolution = None
        video_codec = None
        # Audio codec/channels/language: not independently confirmed by this
        # project's research (plan doc sec8/sec13 Q2) -- reasoned instead
        # from Jellyfin's own documented MediaStream schema (Codec/
        # Channels/Language are standard, stable field names on any Audio-type
        # stream entry, part of the public Jellyfin OpenAPI spec, not a guess
        # in the same category as an unconfirmed REST endpoint). Worth
        # confirming against a real scan's results, same as every other
        # not-yet-live-verified piece of this client. `edition`/`studio` are
        # still left None -- Jellyfin has no equivalent concept to Plex's
        # editionTitle at all, not just an unconfirmed field name.
        audio_codec = None
        audio_channels = None
        audio_language = None
        for stream in item.get("MediaStreams") or []:
            stream_type = stream.get("Type")
            if stream_type == "Video" and video_resolution is None:
                w = item.get("Width")
                video_resolution = self._classify_resolution(w) if w else None
                video_codec = (stream.get("Codec") or "").lower() or None
            elif stream_type == "Audio" and audio_codec is None:
                audio_codec = (stream.get("Codec") or "").lower() or None
                channels = stream.get("Channels")
                audio_channels = str(channels) if channels else None
                audio_language = stream.get("Language") or None

        return MediaItemMetadata(
            tmdb_id=provider_ids.get("Tmdb"),
            tvdb_id=provider_ids.get("Tvdb"),
            video_resolution=video_resolution,
            video_codec=video_codec,
            audio_codec=audio_codec,
            audio_channels=audio_channels,
            audio_language=audio_language,
            labels=list(item.get("Tags") or []),
        )

    @staticmethod
    def _classify_resolution(width: Optional[int]) -> Optional[str]:
        # Width-threshold classification (plan doc sec8) -- not a
        # Jellyfin-specific fact, just a reasonable, already-precedented
        # bucketing.
        if not width:
            return None
        if width >= 7000:
            return "8k"
        if width >= 3800:
            return "4k"
        if width >= 2500:
            return "1440p"
        if width >= 1800:
            return "1080p"
        if width >= 1200:
            return "720p"
        return "sd"

    def item_exists(self, item_id: str) -> Optional[bool]:
        # Same not-directly-confirmed caveat as get_item_metadata.
        try:
            items = self._fetch_items_by_ids([item_id], fields="")
            return len(items) > 0
        except Exception:
            return None

    def upload_image(self, item_id: str, image_type: ImageType, image_bytes: bytes,
                      content_type: str, is_collection: bool = False) -> None:
        # is_collection is accepted for interface parity with PlexClient but
        # unused here -- Jellyfin BoxSet (collection) support is out of scope
        # for this phase entirely (plan doc sec9, no confirmed pattern exists).
        if image_type == ImageType.SQUARE_ART:
            raise NotImplementedError(
                "Jellyfin/Emby has no confirmed Square Art image type -- see "
                "jellyfin-upgrade-plan.md sec13 Q1. Verify against a real "
                "instance before implementing this."
            )
        jellyfin_image_type = _UPLOAD_IMAGE_TYPE[image_type]

        if image_type == ImageType.BACKDROP:
            # Confirmed: Backdrop is multi-valued/indexed, unlike Plex's
            # single-slot /arts. Delete-then-post is the established
            # full-replace pattern for this (plan doc sec5.2) -- without the
            # delete, repeated backdrop sends would accumulate duplicates.
            try:
                requests.delete(f"{self.url}/items/{item_id}/images/Backdrop/0", headers=self._headers(), timeout=10)
            except Exception as e:
                logger.debug("[JELLYFIN_CLIENT:%s] Backdrop delete-before-replace failed (continuing anyway): %s", self.server_id, e)

        import base64
        payload = base64.b64encode(image_bytes)
        headers = {**self._headers(), "Content-Type": content_type}
        # Confirmed: base64 body, NOT multipart/binary, NOT a JSON wrapper.
        # Note the lowercase "items" here -- this is the exact casing
        # confirmed to work for the upload endpoint specifically (unlike the
        # capitalized "/Items" used for listing/search above); reproduced
        # as-is rather than "cleaned up", since API routing can be
        # case-sensitive.
        url = f"{self.url}/items/{item_id}/images/{jellyfin_image_type}/"
        r = requests.post(url, headers=headers, data=payload, timeout=20)
        r.raise_for_status()
        # A 2xx here only proves Jellyfin ACCEPTED the request -- it's never
        # been confirmed (against a real server) that this also proves the
        # image was actually stored. Logged at info level specifically so a
        # real "200 but nothing actually changed" case (as opposed to a
        # genuine upload failure, which raise_for_status() above already
        # catches) has something to compare against in the logs -- payload
        # size in particular, since a large poster upload silently not
        # applying while a small logo upload does is the first real report
        # of this class of bug.
        logger.info(
            "[JELLYFIN_CLIENT:%s] Upload response for %s item=%s: status=%s body_len=%d payload_bytes=%d",
            self.server_id, jellyfin_image_type, item_id, r.status_code, len(r.content or b""), len(payload),
        )

    def download_image(self, item_id: str, image_type: ImageType) -> Optional[bytes]:
        if image_type == ImageType.SQUARE_ART:
            return None
        jellyfin_image_type = _UPLOAD_IMAGE_TYPE.get(image_type)
        if not jellyfin_image_type:
            return None
        try:
            # Confirmed pattern for fetching the currently-set image.
            r = requests.get(
                f"{self.url}/items/{item_id}/images/{jellyfin_image_type}/",
                headers=self._headers(), timeout=15,
            )
            return r.content if r.status_code == 200 else None
        except Exception as e:
            logger.debug("[JELLYFIN_CLIENT:%s] download_image failed for %s/%s: %s", self.server_id, item_id, image_type.value, e)
            return None

    def remove_label(self, item_id: str, label: str, content_type: Optional[str] = None) -> bool:
        # Deliberately a no-op -- no Jellyfin/Emby tag-write mechanism is
        # confirmed to exist in practice. Simposter's own dedup doesn't need
        # this either (it's DB-based). See plan doc sec10's explicit
        # "skip write-back" call.
        logger.debug("[JELLYFIN_CLIENT:%s] remove_label is a no-op for Jellyfin/Emby (no confirmed write mechanism) -- see plan doc sec10", self.server_id)
        return False

    def add_label(self, item_id: str, label: str) -> bool:
        logger.debug("[JELLYFIN_CLIENT:%s] add_label is a no-op for Jellyfin/Emby (no confirmed write mechanism) -- see plan doc sec10", self.server_id)
        return False

    def find_item_by_external_id(self, tmdb_id: Optional[Any], tvdb_id: Optional[Any],
                                  media_type: str, library_id: Optional[str] = None) -> Optional[str]:
        # Deliberately does NOT use title+year+path matching (a known-fragile
        # approach, per plan doc sec10) or a guessed server-side ProviderIds
        # filter parameter (unconfirmed against Jellyfin's real API). Instead
        # reuses the confirmed bulk /Items
        # endpoint and filters client-side on an exact ProviderIds match --
        # slower for a very large library than a real server-side filter would
        # be, but correct without relying on unverified API surface. Revisit
        # with a server-side filter once Jellyfin's own OpenAPI spec is
        # checked (plan doc sec13's closing recommendation).
        if media_type == "movie" and tmdb_id:
            item_type, target_key, target_val = "Movie", "Tmdb", str(tmdb_id)
        elif media_type == "tv" and tvdb_id:
            item_type, target_key, target_val = "Series", "Tvdb", str(tvdb_id)
        else:
            return None

        try:
            params = {
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "Fields": "ProviderIds",
            }
            if library_id:
                # Real bug fix, not defensive: without this, a tmdb_id present
                # in more than one library on the same server (a duplicate/4K
                # copy, or an untracked library sharing the server) resolves
                # nondeterministically to whichever match Jellyfin lists
                # first -- see this method's docstring in base.py.
                params["ParentId"] = library_id
            r = requests.get(f"{self.url}/Items", headers=self._headers(), params=params, timeout=30)
            r.raise_for_status()
            for item in r.json().get("Items", []):
                if str((item.get("ProviderIds") or {}).get(target_key, "")) == target_val:
                    return item.get("Id")
            return None
        except Exception as e:
            logger.error("[JELLYFIN_CLIENT:%s] find_item_by_external_id failed (tmdb=%s tvdb=%s): %s", self.server_id, tmdb_id, tvdb_id, e)
            return None

    def get_folder_name(self, item_id: str, is_tv: bool = False) -> Optional[str]:
        # Confirmed: Path is directly on the item (no need for Plex's
        # first-episode workaround, since Fields=Path is requested straight
        # off the movie/series item itself). NOT independently verified
        # here that a Jellyfin Series-level item's Path is its own show
        # folder rather than empty/an episode path -- worth confirming
        # against a real TV library specifically.
        items = self._fetch_items_by_ids([item_id], fields="Path")
        if not items:
            return None
        path = items[0].get("Path")
        if not path:
            return None
        # A movie's Path is a file; a show's Path is normally already its own
        # folder. Treat anything with a file extension as a file and take its
        # parent; otherwise assume it's already a directory.
        if os.path.splitext(path)[1]:
            return os.path.basename(os.path.dirname(path))
        return os.path.basename(path.rstrip("/\\"))

    def list_seasons(self, series_item_id: str) -> List[dict]:
        # Same confirmed /Items?ParentId=...&IncludeItemTypes=Season query as
        # find_season_by_index() (Quirk #100), just returning every season
        # instead of filtering to one index. Shape matches exactly what
        # api_tv_show_seasons() already returns for Plex ({key, title, index,
        # thumb}), so the frontend needed zero changes to consume this.
        # `thumb` is deliberately left None -- Jellyfin's own thumb path isn't
        # in the same format the frontend's toPlexPosterUrl() expects, and
        # nothing in this app currently needs a season-list thumbnail for a
        # Jellyfin-sourced show badly enough to build that translation yet.
        try:
            params = {
                "ParentId": series_item_id,
                "IncludeItemTypes": "Season",
                "Recursive": "true",
                "Fields": "IndexNumber",
            }
            r = requests.get(f"{self.url}/Items", headers=self._headers(), params=params, timeout=15)
            r.raise_for_status()
            out: List[dict] = []
            for item in r.json().get("Items", []):
                index = item.get("IndexNumber")
                item_id = item.get("Id")
                if index is None or not item_id:
                    continue
                out.append({"key": item_id, "title": item.get("Name") or f"Season {index}", "index": index, "thumb": None})
            out.sort(key=lambda s: s["index"])
            return out
        except Exception as e:
            logger.error("[JELLYFIN_CLIENT:%s] list_seasons failed (series=%s): %s", self.server_id, series_item_id, e)
            return []

    def find_season_by_index(self, series_item_id: str, season_index: int) -> Optional[str]:
        # Confirmed live against a real server (CLAUDE.md Quirk #100) -- the
        # same /Items?ParentId=...&IncludeItemTypes=... shape list_items()
        # already uses, just scoped to a series with IncludeItemTypes=Season.
        # A real response: {Id: '...', Name: 'Season 2', IndexNumber: 2,
        # ProviderIds: {Tvdb: '...'}} -- IndexNumber is Jellyfin's own season
        # number field, matching Simposter's season_index convention
        # (0 = Specials) directly, no translation needed.
        try:
            params = {
                "ParentId": series_item_id,
                "IncludeItemTypes": "Season",
                "Recursive": "true",
                "Fields": "IndexNumber",
            }
            r = requests.get(f"{self.url}/Items", headers=self._headers(), params=params, timeout=15)
            r.raise_for_status()
            for item in r.json().get("Items", []):
                if item.get("IndexNumber") == season_index:
                    return item.get("Id")
            return None
        except Exception as e:
            logger.error("[JELLYFIN_CLIENT:%s] find_season_by_index failed (series=%s season=%s): %s",
                         self.server_id, series_item_id, season_index, e)
            return None
