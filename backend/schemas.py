# backend/schemas.py
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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


class SaveRequest(PreviewRequest):
    movie_title: str
    movie_year: Optional[int] = None
    filename: Optional[str] = "poster.jpg"


class PresetSaveRequest(BaseModel):
    template_id: str = "default"
    preset_id: str
    options: Dict[str, Any]


class PresetDeleteRequest(BaseModel):
    template_id: str = "default"
    preset_id: str


class UISettings(BaseModel):
    theme: str = "neon"
    showBoundingBoxes: bool = True
    autoSave: bool = False
    posterDensity: int = 20
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
    labels: List[str] = []



class RadarrWebhookMovie(BaseModel):
    title: str
    year: Optional[int] = None
    tmdbId: Optional[int] = None


class RadarrWebhook(BaseModel):
    eventType: str
    movie: RadarrWebhookMovie
