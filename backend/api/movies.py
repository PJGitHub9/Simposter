import xml.etree.ElementTree as ET
from typing import List

import requests
from fastapi import APIRouter, HTTPException

from ..config import settings, plex_headers, logger, get_plex_movies, get_movie_tmdb_id
from ..schemas import Movie, MovieTMDbResponse, LabelsResponse, LabelsRemoveRequest
from ..tmdb_client import get_images_for_movie, TMDBError

router = APIRouter()


@router.get("/movies", response_model=List[Movie])
def api_movies():
    return get_plex_movies()


@router.get("/movie/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_movie_tmdb(rating_key: str):
    tmdb_id = get_movie_tmdb_id(rating_key)
    return MovieTMDbResponse(tmdb_id=tmdb_id)


@router.get("/movie/{rating_key}/labels", response_model=LabelsResponse)
def api_movie_labels(rating_key: str):
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    r = requests.get(url, headers=plex_headers(), timeout=10)
    r.raise_for_status()

    try:
        root = ET.fromstring(r.text)
    except Exception:
        return LabelsResponse(labels=[])

    labels = set()

    # Modern Plex: <Tag tagType="label">
    for tag in root.findall(".//Tag"):
        tag_type = (tag.get("tagType") or tag.get("type") or "").lower()
        if tag_type == "label":
            name = tag.get("tag")
            if name:
                labels.add(name)

    # Some versions: <Label tag="...">
    for tag in root.findall(".//Label"):
        name = tag.get("tag")
        if name:
            labels.add(name)

    return LabelsResponse(labels=sorted(labels))


@router.post("/movie/{rating_key}/labels/remove")
def api_movie_labels_remove(rating_key: str, req: LabelsRemoveRequest):
    from ..config import plex_remove_label

    for label in req.labels:
        plex_remove_label(rating_key, label)
    return {"status": "ok", "removed": req.labels}


@router.get("/tmdb/{tmdb_id}/images")
def api_tmdb_images(tmdb_id: int):
    try:
        return get_images_for_movie(tmdb_id)
    except TMDBError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/movie/{rating_key}/poster")
def api_movie_poster(rating_key: str):
    direct = f"{settings.PLEX_URL}/library/metadata/{rating_key}/thumb?X-Plex-Token={settings.PLEX_TOKEN}"

    # Try direct poster URL
    try:
        r = requests.get(direct, timeout=5)
        if r.status_code == 200:
            return {"url": direct}
    except:
        pass

    # Fallback: parse metadata for thumb
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = requests.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for video in root.findall(".//Video"):
            thumb = video.get("thumb")
            if thumb:
                return {"url": f"{settings.PLEX_URL}{thumb}?X-Plex-Token={settings.PLEX_TOKEN}"}
    except:
        pass

    return {"url": None}


@router.get("/movies/tmdb")
def api_movies_tmdb():
    movies = get_plex_movies()
    return [
        {"title": m.title, "year": m.year, "rating_key": m.key, "tmdb_id": None}
        for m in movies
    ]
