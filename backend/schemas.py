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
    tmdb_id: Optional[int] = None
    labels: Optional[List[str]] = None
    updated_at: Optional[str] = None


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
    options: Dict[str, Any]
    season_options: Optional[Dict[str, Any]] = None


class PresetDeleteRequest(BaseModel):
    template_id: str = "uniformlogo"
    preset_id: str


class PlexSettings(BaseModel):
    url: str = ""
    token: str = ""
    movieLibraryName: str = ""
    movieLibraryNames: List[str] = Field(default_factory=list)
    libraryMappings: List[Dict[str, Any]] = Field(default_factory=list)
    tvShowLibraryName: str = ""
    tvShowLibraryNames: List[str] = Field(default_factory=list)
    tvShowLibraryMappings: List[Dict[str, Any]] = Field(default_factory=list)


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


class SchedulerSettings(BaseModel):
    enabled: bool = False
    cronExpression: str = "0 1 * * *"
    libraryId: Optional[Union[str, int]] = None
    libraryIds: List[str] = Field(default_factory=list)


class AutomationSettings(BaseModel):
    """Settings for automatic poster generation via webhooks"""
    webhookAutoSend: bool = True  # Automatically send generated posters to Plex
    webhookAutoLabels: str = "Simposter"  # Comma-separated labels to apply to webhook-generated posters
    webhookAlwaysRegenerateSeason: bool = False  # Always regenerate season poster on new episode webhook


class NotificationSettings(BaseModel):
    """Settings for Discord and other notifications"""
    discordEnabled: bool = False
    discordWebhookUrl: str = ""
    discordNotifyLibraries: List[str] = Field(default_factory=list)  # Library IDs to notify for
    discordNotifyBatch: bool = True  # Notify on batch completion
    discordNotifyManual: bool = True  # Notify on manual send
    discordNotifyWebhook: bool = True  # Notify on webhook sends
    discordNotifyAutoGenerate: bool = True  # Notify on auto-generate


class UISettings(BaseModel):
    theme: str = "neon"
    posterDensity: int = 20
    deduplicateMovies: bool = False
    defaultSort: str = "added-desc"
    timezone: str = "UTC"
    saveLocation: str = "/config/output/{library}/{title}.jpg"  # Legacy field for backwards compatibility
    movieSaveLocation: str = "/config/output/{library}/{title}.jpg"
    tvShowSaveLocation: str = "/config/output/{library}/{title} ({year}).jpg"
    saveBatchInSubfolder: bool = False
    tvShowSaveMode: str = "flat"  # "flat" (all in one folder with prefixes) or "nested" (each show in its own folder)
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

class PlexSendRequest(BaseModel):
    template_id: str
    preset_id: str  # ADD THIS
    rating_key: str
    background_url: str  # Keep for extracting tmdb_id
    logo_url: Optional[str] = None  # Can be removed
    options: Optional[Dict[str, Any]] = None  # Can be removed
    labels: Optional[List[str]] = None
    library_id: Optional[str] = None  # For history tracking


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


# Overlay Configuration schemas
class OverlayElement(BaseModel):
    type: str  # "video_badge" | "audio_badge" | "edition_badge" | "streaming_platform_badge" | "studio_badge" | "custom_image" | "text_label"
               # Legacy aliases (still render, hidden from UI): "resolution_badge" | "codec_badge" | "label_badge"
    position_x: float = 0.5  # 0.0 to 1.0 (left to right)
    position_y: float = 0.5  # 0.0 to 1.0 (top to bottom)
    width: Optional[float] = None  # Width as percentage of poster width (0.0 to 1.0)
    height: Optional[float] = None  # Height as percentage of poster height (0.0 to 1.0)
    max_width: Optional[int] = None  # Max width in pixels
    max_height: Optional[int] = None  # Max height in pixels
    scale: Optional[float] = None  # Scale multiplier for images (0.1 to 2.0), applied before width/height
    anchor: Optional[str] = None  # Image anchor: "top-left"|"top-center"|"top-right"|"center-left"|"center"|"center-right"|"bottom-left"|"bottom-center"|"bottom-right" (default: "center")
    asset_id: Optional[str] = None  # For custom_image: reference to overlay_assets
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
