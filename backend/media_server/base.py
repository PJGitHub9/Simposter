"""The MediaServerClient interface -- one implementation per configured server
type (PlexClient today; JellyfinClient, covering Emby too via a flag, is
Phase 3). See ai_repo/simposter/jellyfin-upgrade-plan.md sec4 for the design
this was drafted from, and CLAUDE.md Quirk #58 for what actually shipped.

Nothing in the running app calls into this package yet -- wiring existing
code (movies.py/tv_shows.py/batch.py/webhooks.py/scheduler.py/plexsend.py)
through it is Phase 4, deliberately separate from building the abstraction
itself, so this phase carries no regression risk to the app as it runs today.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


class ImageType(str, Enum):
    POSTER = "poster"
    BACKDROP = "backdrop"
    LOGO = "logo"
    SQUARE_ART = "square_art"  # no confirmed Jellyfin/Emby target yet -- plan doc sec13 Q1


@dataclass
class Library:
    id: str          # opaque per-server identifier (Plex section key / Jellyfin ItemId)
    name: str
    media_type: str  # "movie" | "tv" -- normalized here even though Plex's own XML
                      # says "show"; every MediaServerClient method that takes a
                      # media_type (list_items, find_item_by_external_id) expects
                      # "movie"|"tv", so implementations must normalize at the source
                      # rather than leak a server-specific raw value (a real bug found
                      # via live testing -- see CLAUDE.md's Library Groups Quirk).


@dataclass
class MediaItem:
    id: str           # opaque per-server identifier (Plex rating_key / Jellyfin GUID)
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    added_at: Optional[int] = None  # Unix epoch seconds, matching Plex's own `addedAt`
                                     # XML attribute convention -- schemas.py's Movie.addedAt
                                     # is typed the same way. A non-Plex client whose native
                                     # date format differs (e.g. Jellyfin's ISO 8601
                                     # `DateCreated`) must convert to epoch seconds itself
                                     # before constructing a MediaItem -- see
                                     # jellyfin_client.py's _parse_jellyfin_datetime() and the
                                     # real bug it fixes, documented in CLAUDE.md.
    library_id: Optional[str] = None
    file_path: Optional[str] = None


@dataclass
class MediaItemMetadata:
    tmdb_id: Optional[Any] = None
    tvdb_id: Optional[Any] = None
    video_resolution: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    audio_channels: Optional[str] = None
    audio_language: Optional[str] = None
    edition: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    folder_name: Optional[str] = None


class MediaServerClient(ABC):
    """One instance per configured+enabled entry in the `mediaServers` setting
    (see database.py's Phase 1 seed, CLAUDE.md Quirk #57). A server_id
    identifies which entry a given instance represents -- e.g. two separately
    configured Plex servers each get their own PlexClient instance."""

    server_id: str

    @abstractmethod
    def test_connection(self) -> bool: ...

    @abstractmethod
    def list_libraries(self) -> List[Library]: ...

    @abstractmethod
    def list_items(self, library_id: str, media_type: str) -> List[MediaItem]:
        """media_type: 'movie' | 'tv'."""

    @abstractmethod
    def get_item_metadata(self, item_id: str) -> MediaItemMetadata: ...

    @abstractmethod
    def item_exists(self, item_id: str) -> Optional[bool]:
        """True/False on a definitive answer, None if ambiguous (network error,
        timeout) -- callers must never treat None as "gone", only an explicit
        False. Mirrors the existing safety rule from Simposter's own
        _plex_item_exists() (CLAUDE.md Quirk #24)."""

    @abstractmethod
    def upload_image(self, item_id: str, image_type: ImageType, image_bytes: bytes,
                      content_type: str, is_collection: bool = False) -> None: ...

    @abstractmethod
    def download_image(self, item_id: str, image_type: ImageType) -> Optional[bytes]:
        """Fetch whatever's currently set on the server for this item/image type."""

    @abstractmethod
    def remove_label(self, item_id: str, label: str, content_type: Optional[str] = None) -> bool: ...

    @abstractmethod
    def add_label(self, item_id: str, label: str) -> bool: ...

    @abstractmethod
    def find_item_by_external_id(self, tmdb_id: Optional[Any], tvdb_id: Optional[Any],
                                  media_type: str, library_id: Optional[str] = None) -> Optional[str]:
        """Resolve an external-tool-supplied TMDb/TVDb ID (from a Radarr/Sonarr
        webhook, or a cross-server sync) to this server's own item id. Returns
        None if not found.

        `library_id` is optional but should always be passed when the caller
        knows which specific library on THIS server the item is expected to
        be in (e.g. a Library Group's linked member) -- without it, a title
        present in more than one library on the same server (a duplicate/4K
        copy, an untracked library sharing the server) can resolve to the
        WRONG item nondeterministically, since nothing else disambiguates
        between same-tmdb_id matches. A real, live-reported bug found this
        exact scenario: Gran Turismo existed in both a linked "4k-Movies"
        Jellyfin library and an untracked "Movies" library on the same
        server -- unscoped lookups kept silently updating the untracked
        copy instead of the one actually linked via the Library Group."""

    @abstractmethod
    def get_folder_name(self, item_id: str, is_tv: bool = False) -> Optional[str]:
        """The real on-disk folder name for this item, for {folder} save-path
        resolution (see CLAUDE.md Quirk #14)."""

    @abstractmethod
    def find_season_by_index(self, series_item_id: str, season_index: int) -> Optional[str]:
        """Resolve a specific season's own item id, given the series' own
        already-resolved item id (e.g. from find_item_by_external_id()) and a
        season index using Simposter's own convention (0 = Specials, matching
        Plex's numbering and this codebase's existing season_index usage
        throughout backend/api/batch.py). Returns None if not found.

        This was, until CLAUDE.md Quirk #100, wrongly believed to be
        impossible for Jellyfin -- every prior TV multi-server Quirk
        (#69/#71/#75/#96/#99) deferred season-level sync/send on that
        assumption. It was never actually checked against a real server:
        Jellyfin's season items are real, individually-addressable Items
        with their own Id, reachable via the exact same
        `/Items?ParentId=...&IncludeItemTypes=...` shape list_items() already
        uses, just scoped to the series' item id with IncludeItemTypes=Season
        and matched by IndexNumber. See Quirk #100 for the live verification
        that established this."""
