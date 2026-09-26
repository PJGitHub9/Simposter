# backend/schemas.py
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class Movie(BaseModel):
    key: str
    title: str
    year: Optional[int] = None
    addedAt: Optional[int] = None
    library_id: Optional[str] = None
    poster: Optional[str] = None
    logo_url: Optional[str] = None
    art_url: Optional[str] = None
    square_art_url: Optional[str] = None
    tmdb_id: Optional[int] = None
    labels: Optional[List[str]] = None
    updated_at: Optional[str] = None
    edition: Optional[str] = None
    server_id: Optional[str] = None  # which configured media server this item came from
                                      # (Quirk #57) -- 'plex-1' for every pre-multi-server
                                      # row, a real value once a scan/Library Group union
                                      # (Quirk #62/#64) includes non-Plex rows.
    also_on: Optional[List[str]] = None  # other server_ids this same title (by tmdb_id) was
                                          # also found on within a merged Library Group,
                                          # collapsed into this one card by _dedupe_by_tmdb_id()
                                          # (Quirk #65/#67) -- empty/None for every non-merged item.
    other_servers: Optional[List[Dict[str, str]]] = None  # {server_id, rating_key} for each
                                          # dropped duplicate above -- lets the manual editor
                                          # fetch/send against a linked title's OTHER servers
                                          # directly, without a second API round-trip to
                                          # resolve which rating_key belongs to which server.


class MovieTMDbResponse(BaseModel):
    tmdb_id: Optional[int]



class PreviewRequest(BaseModel):
    template_id: str
    background_url: Optional[str] = None  # Optional to allow backend to fetch from TMDb using tv_show_rating_key
    logo_url: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    preset_id: Optional[str] = None
    movie_title: Optional[str] = None
    movie_year: Optional[int] = None
    rating_key: Optional[str] = None  # Plex rating key for media info lookup (overlay badges)
    tv_show_rating_key: Optional[str] = None  # For TV show logo fetching and poster fallback
    season_index: Optional[int] = None  # For TV show season poster fetching (1, 2, 3, etc.)
    fallbackPosterAction: Optional[str] = None
    fallbackPosterTemplate: Optional[str] = None
    fallbackPosterPreset: Optional[str] = None
    fallbackLogoAction: Optional[str] = None
    fallbackLogoTemplate: Optional[str] = None
    fallbackLogoPreset: Optional[str] = None
    logoSource: Optional[str] = None
    disableOverlayCache: Optional[bool] = None
    skip_fallback: Optional[bool] = None  # When True, never apply poster/logo fallback (for manual editor preview)
    is_collection: Optional[bool] = False  # True for Plex collection posters (Kometa Creator or Simposter Creator on a collection)
    # Explicit TV-show flag -- SaveRequest/api_plex_send() already have this
    # (render.ts's save()/send() both send it), but /api/preview never did,
    # leaving it to guess via background_url string-pattern-matching
    # (does it look like "/api/tv-show/{key}/poster"?). That guess silently
    # fails whenever the background is a raw external TMDb/Fanart/TVDB
    # candidate URL instead of Simposter's own internal poster-cache URL --
    # i.e. the common case of picking a specific candidate poster, not just
    # a Jellyfin-specific issue. None (the default) preserves the exact
    # original guessing behavior for any caller that doesn't send this.
    is_tv: Optional[bool] = None


class SaveRequest(PreviewRequest):
    movie_title: str
    movie_year: Optional[int] = None
    rating_key: Optional[str] = None
    filename: Optional[str] = "poster.jpg"
    library_id: Optional[str] = None
    season_index: Optional[int] = None  # For TV show seasons (e.g., 1, 2, 3)
    is_tv: Optional[bool] = False  # True for TV shows, False for movies


class PresetSaveRequest(BaseModel):
    template_id: str = "uniformlogo"
    preset_id: str
    name: Optional[str] = None
    options: Dict[str, Any]
    season_options: Optional[Dict[str, Any]] = None


class PresetDeleteRequest(BaseModel):
    template_id: str = "uniformlogo"
    preset_id: str


class MediaServerEntry(BaseModel):
    id: str
    type: str  # "plex" | "jellyfin" | "emby"
    name: Optional[str] = None  # user-supplied display label (e.g. "pj-jellyfin") so
                                 # multiple same-type servers can be told apart in the UI --
                                 # falls back to a generic type label ("Jellyfin"/"Emby")
                                 # everywhere it's displayed when unset/blank.
    url: str = ""
    token: Optional[str] = None    # Plex
    apiKey: Optional[str] = None   # Jellyfin/Emby
    enabled: bool = True


class PlexSettings(BaseModel):
    url: str = ""
    token: str = ""
    movieLibraryName: str = ""
    movieLibraryNames: List[str] = Field(default_factory=list)
    libraryMappings: List[Dict[str, Any]] = Field(default_factory=list)
    tvShowLibraryName: str = ""
    tvShowLibraryNames: List[str] = Field(default_factory=list)
    tvShowLibraryMappings: List[Dict[str, Any]] = Field(default_factory=list)
    sendLogosToPlex: bool = False


class TMDBSettings(BaseModel):
    apiKey: str = ""


class TVDBSettings(BaseModel):
    apiKey: str = ""
    comingSoon: bool = True


class FanartSettings(BaseModel):
    apiKey: str = ""


class ImageQualitySettings(BaseModel):
    outputFormat: str = "jpg"  # jpg, png, webp
    jpgQuality: int = 95
    pngCompression: int = 6
    webpQuality: int = 90


class PerformanceSettings(BaseModel):
    concurrentRenders: int = 2
    tmdbRateLimit: int = 40  # requests per 10 seconds
    tvdbRateLimit: int = 20
    memoryLimit: int = 2048  # MB
    useOverlayCache: bool = True  # Pre-generate overlay effects for faster batch rendering


_DEFAULT_CLEANUP_CATEGORIES = [
    "poster_cache", "logo_cache", "backdrop_cache", "square_art_cache",
    "overlay_effect_cache", "uploaded_files", "overlay_assets", "poster_history",
]


class SchedulerSettings(BaseModel):
    enabled: bool = False
    cronExpression: str = "0 1 * * *"
    libraryId: Optional[Union[str, int]] = None
    libraryIds: List[str] = Field(default_factory=list)
    # Scheduled cleanup (backend/api/cleanup.py) -- off by default like every other
    # automated/destructive-adjacent feature in this app, even though it's fully
    # reversible via the cleanup trash. Cron rather than a simple interval to match
    # the existing library-scan schedule's own UX/mechanism above.
    cleanupEnabled: bool = False
    cleanupCronExpression: str = "0 3 * * 0"  # weekly, Sunday 3 AM
    cleanupCategories: List[str] = Field(default_factory=lambda: list(_DEFAULT_CLEANUP_CATEGORIES))
    cleanupHistoryDays: int = 180


class AutomationSettings(BaseModel):
    """Settings for automatic poster generation via webhooks"""
    webhookAutoSend: bool = True
    webhookAutoLabels: str = "Simposter"
    labelToAdd: str = ""  # Optional label applied to a Plex item after a poster is sent
                           # successfully — the opposite direction from webhookAutoLabels
                           # (which strips a pre-existing label), see plex_add_label().
    webhookAlwaysRegenerateSeason: bool = False
    webhookSecret: str = ""
    existingContentMode: str = "regenerate"  # "regenerate" or "resend"
    retryUntilTemplateMet: bool = False
    retryIntervalHours: int = 24
    retryMaxAttempts: int = 0
    kometaCompatibility: bool = False  # When true, any newly-added library automatically
                                        # gets "Overlay" added to its Default Labels to
                                        # Remove — see SettingsView.vue's saveSettings()
    reuseCachedPosterDays: float = 0  # 0 = disabled. When > 0, an item that looks "new" to
                                       # Simposter (never-before-seen rating_key) but has a
                                       # recently-sent poster on file for the same TMDb ID
                                       # gets that cached poster resent instead of a fresh
                                       # render/send — protects against a Radarr/Sonarr
                                       # re-grab (or e.g. UMTK re-downloading a trailer)
                                       # causing Plex to re-match an item under a new
                                       # rating_key, which otherwise looks identical to a
                                       # genuinely new library addition. See
                                       # get_reuse_cached_poster_days() in config.py.
    preferredPosterServer: str = "plex-1"  # DEPRECATED, no longer read by anything -- superseded
                                             # by the per-group LibraryGroup.preferredServerId
                                             # field (a single global choice applied to every
                                             # merged group at once wasn't granular enough once
                                             # a real install had more than one linked group).
                                             # Field kept only so an existing stored value on an
                                             # already-upgraded install round-trips harmlessly
                                             # through GET/POST /api/ui-settings; no UI edits it
                                             # anymore.


class NotificationSettings(BaseModel):
    """Settings for Discord and other notifications"""
    discordEnabled: bool = False
    discordWebhookUrl: str = ""
    discordNotifyLibraries: List[str] = Field(default_factory=list)
    discordNotifyBatch: bool = True
    discordNotifyManual: bool = True
    discordNotifyWebhook: bool = True
    discordNotifyAutoGenerate: bool = True
    appriseEnabled: bool = False
    appriseUrls: List[str] = Field(default_factory=list)
    appriseNotifyLibraries: List[str] = Field(default_factory=list)
    appriseNotifyBatch: bool = True
    appriseNotifyManual: bool = True
    appriseNotifyWebhook: bool = True
    appriseNotifyAutoGenerate: bool = True


class LibraryGroupMember(BaseModel):
    """One (server, library) pair inside a LibraryGroup -- e.g. Plex's
    'Movies' library, or Jellyfin's 'Movies-HD' library."""
    serverId: str
    libraryId: str
    libraryName: str = ""  # Display-only snapshot from the last time this member was
                            # added/refreshed -- never used for matching, only so the
                            # UI can show a name without a live per-server lookup.


class LibraryGroup(BaseModel):
    """A user-defined set of libraries across different media servers that
    represent 'the same logical library' -- e.g. Plex 'Movies' + Jellyfin
    'Movies-HD' both feeding one merged 'Movies' view. Settings (auto-generate,
    labels) are unified across the whole group, not kept per-member -- the
    user explicitly chose this over independent per-server-library settings.
    See CLAUDE.md's Jellyfin-integration Quirks for the full design rationale."""
    id: str
    name: str
    mediaType: str  # "movie" | "tv"
    members: List[LibraryGroupMember] = Field(default_factory=list)
    autoGenerateEnabled: bool = False
    autoGeneratePresetId: Optional[str] = None
    autoGenerateTemplateId: Optional[str] = None
    labelsToRemove: List[str] = Field(default_factory=list)
    preferredServerId: Optional[str] = None  # Which member's row wins when this group's
                                              # merged grid finds the same tmdb_id on more
                                              # than one server (database.py's
                                              # _dedupe_by_tmdb_id()). None = the function's
                                              # own default ('plex-1' if a Plex member
                                              # exists, else most-recently-updated) --
                                              # replaces the old global
                                              # automation.preferredPosterServer setting,
                                              # which applied the same choice to every
                                              # group at once; this is scoped per-group
                                              # instead, edited from that group's own
                                              # Linked Libraries section in Settings.


class UISettings(BaseModel):
    theme: str = "neon"
    posterDensity: int = 20
    deduplicateMovies: bool = False
    defaultSort: str = "added-desc"
    timezone: str = "UTC"
    saveLocation: str = "/config/output/{library}/{title}.jpg"  # Legacy field for backwards compatibility
    movieSaveLocation: str = "/config/output/{library}/{title}.jpg"
    tvShowSaveLocation: str = "/config/output/{library}/{title} ({year}).jpg"
    collectionSaveLocation: str = "/config/output/{library}/Collections/{title}.jpg"
    saveBatchInSubfolder: bool = False
    tvShowSaveMode: str = "flat"  # "flat" (all in one folder with prefixes) or "nested" (each show in its own folder)
    saveToAssetFolderOnSend: bool = False  # When true, "Send to Plex" also writes the render to the
    # configured local asset folder (via the same template as "Save to Disk") instead of the hidden
    # internal resend cache — the asset-folder file becomes the resend source.
    defaultLabelsToRemove: Union[List[str], Dict[str, List[str]]] = Field(default_factory=list)
    defaultTvLabelsToRemove: Union[List[str], Dict[str, List[str]]] = Field(default_factory=list)
    plex: PlexSettings = Field(default_factory=PlexSettings)
    tmdb: TMDBSettings = Field(default_factory=TMDBSettings)
    tvdb: TVDBSettings = Field(default_factory=TVDBSettings)
    fanart: FanartSettings = Field(default_factory=FanartSettings)
    imageQuality: ImageQualitySettings = Field(default_factory=ImageQualitySettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    automation: AutomationSettings = Field(default_factory=AutomationSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    apiOrder: List[str] = Field(default_factory=lambda: ["tmdb", "fanart", "tvdb"])
    onboarding_completed: bool = False
    mediaServers: List[MediaServerEntry] = Field(default_factory=list)
    libraryGroups: List[LibraryGroup] = Field(default_factory=list)

class PlexLogoSendRequest(BaseModel):
    rating_key: str
    logo_url: Optional[str] = None   # external URL to download
    logo_data: Optional[str] = None  # base64 data URL (for uploads)
    is_tv: bool = False
    library_id: Optional[str] = None


class PlexBackdropSendRequest(BaseModel):
    rating_key: str
    art_url: Optional[str] = None   # external URL to download
    art_data: Optional[str] = None  # base64 data URL (for uploads)
    is_tv: bool = False
    is_collection: bool = False
    library_id: Optional[str] = None


class PlexSquareArtSendRequest(BaseModel):
    # Plex's squareArts endpoint is a genuinely separate slot from posters/arts,
    # confirmed against python-plexapi's SquareArtMixin source (not a guess) --
    # POST /library/metadata/{ratingKey}/squareArts, image type "backgroundSquare".
    rating_key: str
    art_url: Optional[str] = None   # external URL to download
    art_data: Optional[str] = None  # base64 data URL (for uploads)
    is_tv: bool = False
    is_collection: bool = False
    library_id: Optional[str] = None


class PlexSendRequest(BaseModel):
    template_id: str
    preset_id: str  # ADD THIS
    rating_key: str
    background_url: Optional[str] = None  # Keep for extracting tmdb_id; empty for collections (no photo background)
    logo_url: Optional[str] = None  # Can be removed
    options: Optional[Dict[str, Any]] = None  # Can be removed
    labels: Optional[List[str]] = None
    library_id: Optional[str] = None  # For history tracking
    is_tv: bool = False  # Needed for the "save to asset folder on send" template resolution
    is_collection: bool = False  # True when sending a Plex collection poster (uses /library/collections/ instead of /library/metadata/)
    season_index: Optional[int] = None  # Set when sending a specific season's poster


class LabelsResponse(BaseModel):
    labels: List[str]


class LabelsRemoveRequest(BaseModel):
    labels: List[str]


class MovieBatchRequest(BaseModel):
    rating_keys: List[str]
    template_id: str
    preset_id: Optional[str] = None
    background_url: Optional[str] = None
    logo_url: Optional[str] = None
    options: dict
    send_to_plex: bool = False
    save_locally: bool = False
    labels: List[str] = []
    library_id: Optional[str] = None
    fallbackPosterAction: Optional[str] = None
    fallbackPosterTemplate: Optional[str] = None
    fallbackPosterPreset: Optional[str] = None
    fallbackLogoAction: Optional[str] = None
    fallbackLogoTemplate: Optional[str] = None
    fallbackLogoPreset: Optional[str] = None
    send_logos_to_plex: bool = False
    send_only_if_ideal: bool = False  # Skip Plex upload if the render still needs_retry (used by the retry queue)
    require_textless_poster: bool = False  # Forces needs_retry=True until the selected poster is genuinely
    # textless, regardless of fallbackPosterAction -- set only when resolving a manually-queued
    # RETRY_REASON_MANUAL_TEXTLESS retry item (database.py), since the ordinary needs_retry check
    # doesn't catch a missing textless poster when fallbackPosterAction is "continue" (the default).
    batch_subfolder: Optional[str] = None  # Server-computed once per batch run; any client value is overwritten
    targets: List[str] = []  # Non-Plex server_ids to ALSO sync the rendered poster/logo to, in
    # addition to whatever send_to_plex already does (or doesn't) -- purely additive, does not
    # replace send_to_plex (unlike ResendTarget/ResendCachedRequest's single-list model, since
    # send_to_plex already gates a large block of Plex-only side effects -- label add/remove,
    # retry-queue resolution, "sent_to_plex" history -- that shouldn't change shape here). Each
    # requested target is further scoped server-side to only the servers actually linked to this
    # batch's library via a Library Group (see CLAUDE.md Quirk #95's identical webhook-sync fix)
    # -- a target that isn't linked is silently skipped, never blindly synced to. 'plex-1' in this
    # list is a no-op (Plex already has its own real send path via send_to_plex).


class TVShowBatchRequest(BaseModel):
    rating_keys: List[str]
    template_id: str
    preset_id: Optional[str] = None
    background_url: Optional[str] = None
    logo_url: Optional[str] = None
    options: dict
    send_to_plex: bool = False
    save_locally: bool = False
    labels: List[str] = []
    library_id: Optional[str] = None
    include_series: bool = True   # Render the series-level poster
    include_seasons: bool = True  # Render individual season posters
    fallbackPosterAction: Optional[str] = None
    fallbackPosterTemplate: Optional[str] = None
    fallbackPosterPreset: Optional[str] = None
    send_logos_to_plex: bool = False
    send_only_if_ideal: bool = False  # Skip Plex upload if the render still needs_retry (used by the retry queue)
    require_textless_poster: bool = False  # See MovieBatchRequest's field of the same name.
    batch_subfolder: Optional[str] = None  # Server-computed once per batch run; any client value is overwritten
    targets: List[str] = []  # See MovieBatchRequest.targets -- series-level poster/logo only, never
    # season-level (JellyfinClient has no season-level item resolution yet, same reason Quirk #69/#71
    # deferred TV sends elsewhere).


# Legacy batch request - kept for backward compatibility
class BatchRequest(BaseModel):
    rating_keys: List[str]
    template_id: str
    preset_id: Optional[str] = None
    background_url: Optional[str] = None
    logo_url: Optional[str] = None
    options: dict
    send_to_plex: bool = False
    save_locally: bool = False
    labels: List[str] = []
    library_id: Optional[str] = None
    include_seasons: bool = False  # TV shows: render all seasons instead of series poster
    batch_subfolder: Optional[str] = None  # Server-computed once per batch run; any client value is overwritten


# Overlay Configuration schemas
class OverlayElement(BaseModel):
    type: str  # "video_badge" | "audio_badge" | "edition_badge" | "streaming_platform_badge" | "studio_badge" | "custom_image" | "full_cover_image" | "text_label"
               # Legacy aliases (still render, hidden from UI): "resolution_badge" | "codec_badge" | "label_badge"
    position_x: float = 0.5  # 0.0 to 1.0 (left to right)
    position_y: float = 0.5  # 0.0 to 1.0 (top to bottom)
    width: Optional[float] = None  # Width as percentage of poster width (0.0 to 1.0)
    height: Optional[float] = None  # Height as percentage of poster height (0.0 to 1.0)
    max_width: Optional[int] = None  # Max width in pixels
    max_height: Optional[int] = None  # Max height in pixels
    scale: Optional[float] = None  # Scale multiplier for images (0.1 to 2.0), applied before width/height
    anchor: Optional[str] = None  # Image anchor: "top-left"|"top-center"|"top-right"|"center-left"|"center"|"center-right"|"bottom-left"|"bottom-center"|"bottom-right" (default: "center")
    asset_id: Optional[str] = None  # For custom_image/full_cover_image: reference to overlay_assets. full_cover_image ignores position/width/height/scale/anchor — always stretches to the full canvas.
    text: Optional[str] = None  # For text_label: the text to display
    font_family: Optional[str] = None  # For text_label
    font_size: Optional[int] = None  # For text_label
    font_color: Optional[str] = None  # For text_label
    label_name: Optional[str] = None  # For label_badge: Plex label to check
    show_if_label: Optional[str] = None  # Show only if this Plex label is present
    hide_if_label: Optional[str] = None  # Hide if this Plex label is present
    metadata_field: Optional[str] = None  # Metadata field to check (e.g., "video_resolution", "audio_codec")
    badge_modes: Optional[Dict[str, str]] = None  # Maps metadata value -> "none" | "text" | "image" | "url"
    badge_assets: Optional[Dict[str, str]] = None  # Maps metadata value -> asset_id (e.g., {"4k": "asset-123"})
    badge_texts: Optional[Dict[str, str]] = None  # Maps metadata value -> custom display text (e.g., {"1080": "HD"})
    badge_scales: Optional[Dict[str, float]] = None  # Maps metadata value -> scale multiplier (image/url mode only)
    badge_anchors: Optional[Dict[str, str]] = None  # Maps metadata value -> anchor point (image/url mode only)
    badge_urls: Optional[Dict[str, str]] = None  # Maps metadata value -> image URL (url mode only)
    slug_aliases: Optional[Dict[str, str]] = None  # Maps TMDb slug -> canonical asset slug (e.g., {"cj-enm-studios": "cj-entertainment-studios"})
    text_align: Optional[str] = None  # "left" | "center" | "right" (default: "center")


class OverlayConfigSaveRequest(BaseModel):
    id: str
    name: str
    elements: List[OverlayElement]
    streaming_region: str = "US"  # ISO 3166-1 alpha-2 region for TMDb watch provider lookups


class OverlayConfigDeleteRequest(BaseModel):
    id: str


class OverlayAssetUploadRequest(BaseModel):
    id: str
    name: str
    file_type: str
    width: int
    height: int


class OverlayAssetDeleteRequest(BaseModel):
    id: str


class PresetOverlayLinkRequest(BaseModel):
    template_id: str
    preset_id: str
    overlay_config_id: Optional[str] = None


# Radarr webhook schemas removed
