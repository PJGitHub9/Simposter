# backend/schemas.py
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Movie(BaseModel):
    key: str
    title: str
    year: Optional[int] = None
    addedAt: Optional[int] = None


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


class SaveRequest(PreviewRequest):
    movie_title: str
    movie_year: Optional[int] = None
    rating_key: Optional[str] = None
    filename: Optional[str] = "poster.jpg"


class PresetSaveRequest(BaseModel):
    template_id: str = "default"
    preset_id: str
    options: Dict[str, Any]


class PresetDeleteRequest(BaseModel):
    template_id: str = "default"
    preset_id: str


class PlexSettings(BaseModel):
    url: str = ""
    token: str = ""
    movieLibraryName: str = ""


class TMDBSettings(BaseModel):
    apiKey: str = ""


class TVDBSettings(BaseModel):
    apiKey: str = ""
    comingSoon: bool = True


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


class UISettings(BaseModel):
    theme: str = "neon"
    posterDensity: int = 20
    saveLocation: str = "/output"
    saveBatchInSubfolder: bool = False
    defaultLabelsToRemove: List[str] = Field(default_factory=list)
    plex: PlexSettings = Field(default_factory=PlexSettings)
    tmdb: TMDBSettings = Field(default_factory=TMDBSettings)
    tvdb: TVDBSettings = Field(default_factory=TVDBSettings)
    imageQuality: ImageQualitySettings = Field(default_factory=ImageQualitySettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)

class PlexSendRequest(BaseModel):
    template_id: str
    preset_id: str  # ADD THIS
    rating_key: str
    background_url: str  # Keep for extracting tmdb_id
    logo_url: Optional[str] = None  # Can be removed
    options: Optional[Dict[str, Any]] = None  # Can be removed
    labels: Optional[List[str]] = None


class LabelsResponse(BaseModel):
    labels: List[str]


class LabelsRemoveRequest(BaseModel):
    labels: List[str]


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



class RadarrWebhookMovie(BaseModel):
    title: str
    year: Optional[int] = None
    tmdbId: Optional[int] = None


class RadarrWebhook(BaseModel):
    eventType: str
    movie: RadarrWebhookMovie
