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
    background_url: str
    logo_url: Optional[str] = None
    options: Optional[Dict[str, Any]] = None
    preset_id: Optional[str] = None   # <-- MAKE OPTIONAL
    movie_title: Optional[str] = None
    movie_year: Optional[int] = None
    tv_show_rating_key: Optional[str] = None  # For TV show logo fetching
    season_index: Optional[int] = None  # For TV show season poster fetching (1, 2, 3, etc.)
    fallbackPosterAction: Optional[str] = None
    fallbackPosterTemplate: Optional[str] = None
    fallbackPosterPreset: Optional[str] = None
    fallbackLogoAction: Optional[str] = None
    fallbackLogoTemplate: Optional[str] = None
    fallbackLogoPreset: Optional[str] = None
    logoSource: Optional[str] = None
    disableOverlayCache: Optional[bool] = None


class SaveRequest(PreviewRequest):
    movie_title: str
    movie_year: Optional[int] = None
    rating_key: Optional[str] = None
    filename: Optional[str] = "poster.jpg"
    library_id: Optional[str] = None
    season_index: Optional[int] = None  # For TV show seasons (e.g., 1, 2, 3)
    is_tv: Optional[bool] = False  # True for TV shows, False for movies


class PresetSaveRequest(BaseModel):
    template_id: str = "default"
    preset_id: str
    options: Dict[str, Any]
    season_options: Optional[Dict[str, Any]] = None


class PresetDeleteRequest(BaseModel):
    template_id: str = "default"
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
    webhookAutoLabels: str = "Overlay"  # Comma-separated labels to apply to webhook-generated posters


class UISettings(BaseModel):
    theme: str = "neon"
    posterDensity: int = 20
    timezone: str = "UTC"
    saveLocation: str = "/config/output/{library}/{title}.jpg"  # Legacy field for backwards compatibility
    movieSaveLocation: str = "/config/output/{library}/{title}.jpg"
    tvShowSaveLocation: str = "/config/output/{library}/{title}.jpg"
    saveBatchInSubfolder: bool = False
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
    include_seasons: bool = True  # Always true for TV shows: render all seasons instead of series poster


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



# Radarr webhook schemas removed
