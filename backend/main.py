#V1.2
# backend/main.py
import base64
import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any, Dict, List, Optional
from tempfile import NamedTemporaryFile
import logging
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from PIL import Image
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from .templates import list_templates, get_renderer
from .tmdb_client import get_images_for_movie, TMDBError
from typing import Any, Dict, List, Optional
import time  # make sure this is imported near the top
import json

# ---------------- Environment ----------------

PLEX_URL = os.getenv("PLEX_URL", "http://localhost:32400")
PLEX_TOKEN = os.getenv("PLEX_TOKEN", "")
RAW_PLEX_LIBRARY = os.getenv("PLEX_MOVIE_LIBRARY_NAME", "1")

def resolve_library_id(name: str) -> str:
    name = name.strip()
    if name.isdigit():
        return name

    url = f"{PLEX_URL}/library/sections"
    try:
        r = requests.get(url, headers=_plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except:
        return "1"

    for directory in root.findall(".//Directory"):
        title = (directory.get("title") or "").strip().lower()
        key = directory.get("key")
        if title == name.lower():
            return key

    return "1"
    
PLEX_MOVIE_LIB_ID = resolve_library_id(RAW_PLEX_LIBRARY)

OUTPUT_ROOT = os.getenv("OUTPUT_ROOT", "/poster-outputs")
PRESETS_PATH = os.path.join(os.path.dirname(__file__), "presets.json")
LOG_FILE = os.getenv("LOG_FILE", "/config/simposter.log")
CONFIG_DIR = os.getenv("CONFIG_DIR", "/config")
DEFAULT_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "presets.json")
USER_PRESETS_PATH = os.path.join(CONFIG_DIR, "presets.json")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/simposter_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
WEBHOOK_DEFAULT_PRESET = os.getenv("WEBHOOK_DEFAULT_PRESET", "default")
WEBHOOK_AUTO_SEND = os.getenv("WEBHOOK_AUTO_SEND", "true").lower() == "true"
WEBHOOK_AUTO_LABELS = os.getenv("WEBHOOK_AUTO_LABELS", "Overlay").split(",")  # labels to remove
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")  # optional, not enforced yet



# ---------------- Logging ----------------

logger = logging.getLogger("simposter")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_dir = os.path.dirname(LOG_FILE) or "/config"
    os.makedirs(log_dir, exist_ok=True)

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    sh = logging.StreamHandler()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

# ---------------- FastAPI ----------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


def load_presets():
    """
    Load presets, preferring user-editable /config/presets.json.
    On first run, if /config/presets.json doesn't exist, copy the
    bundled defaults from backend/presets.json into /config.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)

    # First-run: copy defaults into /config if missing
    if not os.path.exists(USER_PRESETS_PATH):
        try:
            with open(DEFAULT_PRESETS_PATH, "r", encoding="utf-8") as f:
                default_data = json.load(f)
        except FileNotFoundError:
            # Absolute worst case: no bundled presets either
            default_data = {"default": {"presets": []}}

        with open(USER_PRESETS_PATH, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)

        return default_data

    # Normal run – just read from /config
    with open(USER_PRESETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)





# ---------------- Data Models ----------------

class Movie(BaseModel):
    key: str
    title: str
    year: Optional[int] = None


class MovieTMDbResponse(BaseModel):
    tmdb_id: Optional[int]


class PreviewRequest(BaseModel):
    template_id: str
    background_url: str
    logo_url: Optional[str] = None
    options: Optional[Dict[str, Any]] = None


class SaveRequest(PreviewRequest):
    movie_title: str
    movie_year: Optional[int] = None
    filename: Optional[str] = "poster.jpg"  # kept for compatibility; we override


class PresetSaveRequest(BaseModel):
    preset_id: str
    options: Dict[str, Any]


class PlexSendRequest(PreviewRequest):
    rating_key: str
    labels: Optional[List[str]] = None


class LabelsResponse(BaseModel):
    labels: List[str]


class LabelsRemoveRequest(BaseModel):
    labels: List[str]

class BatchRequest(BaseModel):
    rating_keys: List[str]              # Plex ratingKeys (WAY faster)
    template_id: str = "default"
    options: Dict[str, Any]
    send_to_plex: bool = True
    labels: Optional[List[str]] = None


    
class RadarrWebhookMovie(BaseModel):
    title: str
    year: Optional[int] = None
    tmdbId: Optional[int] = None


class RadarrWebhook(BaseModel):
    eventType: str
    movie: RadarrWebhookMovie
# ---------------- Helpers ----------------

def _plex_headers() -> Dict[str, str]:
    if not PLEX_TOKEN:
        return {}
    return {"X-Plex-Token": PLEX_TOKEN}

def _rating_key_from_tmdb(tmdb_id: int) -> Optional[str]:
    """
    Finds the Plex ratingKey for a given TMDb ID.
    """
    movies = _get_plex_movies()
    for m in movies:
        rk = m.key
        if get_movie_tmdb_id(rk) == tmdb_id:
            return rk
    return None


def _get_plex_movies() -> List[Movie]:
    url = f"{PLEX_URL}/library/sections/{PLEX_MOVIE_LIB_ID}/all?type=1"
    r = requests.get(url, headers=_plex_headers(), timeout=15)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    movies: List[Movie] = []

    for video in root.findall(".//Video"):
        key = video.get("ratingKey")
        title = video.get("title") or ""
        year = video.get("year")
        movies.append(Movie(key=key, title=title, year=int(year) if year else None))

    # Show most recently added at the top.
    #movies.reverse()
    return movies


def _find_rating_key_by_title_year(title: str, year: Optional[int]) -> Optional[str]:
    movies = _get_plex_movies()
    norm = title.lower().strip()
    cand = []

    for m in movies:
        if m.title.lower().strip() == norm:
            if year is None or m.year is None or m.year == year:
                cand.append(m.key)

    return cand[0] if cand else None


def extract_tmdb_id_from_metadata(xml_text: str) -> Optional[int]:
    if xml_text.startswith("<html"):
        return None

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    for guid in root.findall(".//Guid"):
        gid = guid.get("id") or ""
        match = re.search(r"(?:tmdb|themoviedb)://(\d+)", gid)
        if match:
            return int(match.group(1))

    return None


def _extract_labels_from_metadata(xml_text: str) -> List[str]:
    labels: List[str] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return labels

    for tag in root.findall(".//Tag"):
        tag_type = tag.get("tagType") or tag.get("type") or ""
        if tag_type.lower() == "label":
            name = tag.get("tag") or ""
            if name and name not in labels:
                labels.append(name)
    return labels


def get_movie_tmdb_id(rating_key: str) -> Optional[int]:
    url = f"{PLEX_URL}/library/metadata/{rating_key}"
    r = requests.get(url, headers=_plex_headers(), timeout=10)
    r.raise_for_status()
    return extract_tmdb_id_from_metadata(r.text)


def _render_poster_image(template_id: str,
                         background_url: str,
                         logo_url: Optional[str],
                         options: Dict[str, Any]) -> Image.Image:
    """
    Shared renderer used by preview, save, plex send, webhooks, and batch.
    """
    bg = _download_image(background_url)
    if bg is None:
        raise HTTPException(status_code=400, detail="Invalid background image.")

    logo = _download_image(logo_url) if logo_url else None
    renderer = get_renderer(template_id)
    return renderer(bg, logo, options or {})


def _download_image(url: str) -> Optional[Image.Image]:
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()

        img = Image.open(BytesIO(r.content))
        img.load()
        return img

    except Exception:
        logger.warning("[WARN] Failed to load image: %s", url)
        return None



def _remove_label(rating_key: str, label: str):
    """
    Universal Plex label removal compatible with:
    - modern Plex
    - Kometa / Plex Meta Manager labels
    - Aura / Mediux labels
    - TCM labels
    """

    if not label:
        return

    # Method 1: Direct PUT to /library/sections/{section}/all endpoint
    # This is the most reliable method for most Plex versions
    try:
        url = f"{PLEX_URL}/library/sections/{PLEX_MOVIE_LIB_ID}/all"
        params = {
            "type": "1",
            "id": rating_key,
            "label[].tag.tag-": label
        }
        
        r = requests.put(url, headers=_plex_headers(), params=params, timeout=10)
        
        if r.status_code in (200, 201, 204):
            logger.info("Removed label '%s' from ratingKey=%s (Method 1)", label, rating_key)
            return
        else:
            logger.warning("Method 1 failed for label '%s': HTTP %s", label, r.status_code)
    
    except Exception as e:
        logger.warning("Method 1 exception for label '%s': %s", label, str(e))

    # Method 2: DELETE with query parameters
    try:
        url = f"{PLEX_URL}/library/metadata/{rating_key}/labels"
        params = {
            "tag.tag": label,
            "tag.type": "label"
        }
        
        r = requests.delete(url, headers=_plex_headers(), params=params, timeout=10)
        
        if r.status_code in (200, 201, 204):
            logger.info("Removed label '%s' from ratingKey=%s (Method 2)", label, rating_key)
            return
        else:
            logger.warning("Method 2 failed for label '%s': HTTP %s", label, r.status_code)
    
    except Exception as e:
        logger.warning("Method 2 exception for label '%s': %s", label, str(e))

    # Method 3: PUT with label removal syntax
    try:
        url = f"{PLEX_URL}/library/metadata/{rating_key}"
        params = {
            "label[].tag.tag-": label,
            "type": "1"
        }
        
        r = requests.put(url, headers=_plex_headers(), params=params, timeout=10)
        
        if r.status_code in (200, 201, 204):
            logger.info("Removed label '%s' from ratingKey=%s (Method 3)", label, rating_key)
            return
        else:
            logger.warning("Method 3 failed for label '%s': HTTP %s", label, r.status_code)
    
    except Exception as e:
        logger.warning("Method 3 exception for label '%s': %s", label, str(e))

    logger.error("All methods failed to remove label '%s' from ratingKey=%s", label, rating_key)


# ---------------- API Routes ----------------

@app.get("/api/templates")
def api_templates():
    """
    Returns template groups from templates/__init__.py.
    """
    return list_templates()


@app.get("/api/presets")
def api_presets():
    return load_presets()


@app.post("/api/presets/save")
def api_save_preset(req: PresetSaveRequest):
    preset_id = req.preset_id
    options = req.options

    os.makedirs(CONFIG_DIR, exist_ok=True)

    try:
        with open(USER_PRESETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"default": {"presets": []}}

    presets = data.setdefault("default", {}).setdefault("presets", [])

    # overwrite existing if found
    existing = next((p for p in presets if p.get("id") == preset_id), None)
    if existing:
        existing["options"] = options
    else:
        presets.append({
            "id": preset_id,
            "name": preset_id,
            "options": options
        })

    with open(USER_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return {"message": f"Preset '{preset_id}' saved."}


@app.get("/api/movies", response_model=List[Movie])
def api_movies():
    return _get_plex_movies()


@app.get("/api/movie/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_movie_tmdb(rating_key: str):
    tmdb_id = get_movie_tmdb_id(rating_key)
    return MovieTMDbResponse(tmdb_id=tmdb_id)


@app.get("/api/movie/{rating_key}/labels")
def api_movie_labels(rating_key: str):
    url = f"{PLEX_URL}/library/metadata/{rating_key}"
    r = requests.get(url, headers=_plex_headers(), timeout=10)
    r.raise_for_status()

    try:
        root = ET.fromstring(r.text)
    except:
        return {"labels": []}

    labels = set()

    # ----- CASE A: Modern Plex (Tag tagType="label") -----
    for tag in root.findall(".//Tag"):
        tag_type = (tag.get("tagType") or tag.get("type") or "").lower()
        if tag_type == "label":
            name = tag.get("tag")
            if name:
                labels.add(name)

    # ----- CASE B: Some versions use <Label tag="..."> -----
    for tag in root.findall(".//Label"):
        name = tag.get("tag")
        if name:
            labels.add(name)

    return {"labels": sorted(labels)}


@app.post("/api/movie/{rating_key}/labels/remove")
def api_movie_labels_remove(rating_key: str, req: LabelsRemoveRequest):
    for label in req.labels:
        _remove_label(rating_key, label)
    return {"status": "ok", "removed": req.labels}


@app.get("/api/tmdb/{tmdb_id}/images")
def api_tmdb_images(tmdb_id: int):
    try:
        return get_images_for_movie(tmdb_id)
    except TMDBError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/preview")
def api_preview(req: PreviewRequest):
    bg = _download_image(req.background_url)
    if bg is None:
        raise HTTPException(status_code=400, detail="Invalid background image.")

    logo = _download_image(req.logo_url) if req.logo_url else None

    renderer = get_renderer(req.template_id)
    img = renderer(bg, logo, req.options or {})

    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)
    logger.info("Preview rendered for template=%s", req.template_id)
    return {"image_base64": base64.b64encode(buf.getvalue()).decode()}


@app.get("/api/movie/{rating_key}/poster")
def api_movie_poster(rating_key: str):
    """
    Returns the directly resolvable poster URL from Plex.
    Works across all Plex versions.
    """

    # Direct endpoint for artwork
    direct = f"{PLEX_URL}/library/metadata/{rating_key}/thumb?X-Plex-Token={PLEX_TOKEN}"

    # Validate that the URL exists
    try:
        r = requests.get(direct, timeout=5)
        if r.status_code == 200 and r.content:
            return {"url": direct}
    except:
        pass

    # Fallback: parse metadata XML
    try:
        meta_url = f"{PLEX_URL}/library/metadata/{rating_key}"
        r = requests.get(meta_url, headers=_plex_headers(), timeout=10)
        r.raise_for_status()

        root = ET.fromstring(r.text)

        # The <Video> element has the actual thumb attribute
        for video in root.findall(".//Video"):
            thumb = video.get("thumb")
            if thumb:
                return {
                    "url": f"{PLEX_URL}{thumb}?X-Plex-Token={PLEX_TOKEN}"
                }
    except:
        pass

    return {"url": None}



@app.post("/api/save")
def api_save(req: SaveRequest):
    bg = _download_image(req.background_url)
    if bg is None:
        raise HTTPException(status_code=400, detail="Invalid background image.")

    logo = _download_image(req.logo_url) if req.logo_url else None

    renderer = get_renderer(req.template_id)
    img = renderer(bg, logo, req.options or {})

    # Folder name: "Movie Title (Year)" or just title
    if req.movie_year:
        folder_name = f"{req.movie_title} ({req.movie_year})"
    else:
        folder_name = req.movie_title

    # sanitize filename / folder
    safe_folder = "".join(c for c in folder_name if c.isalnum() or c in " _-()")
    out_dir = os.path.join(OUTPUT_ROOT, safe_folder)
    os.makedirs(out_dir, exist_ok=True)

    out_filename = f"{safe_folder}.jpg"
    out_path = os.path.join(out_dir, out_filename)

    img.convert("RGB").save(out_path, "JPEG", quality=95)
    logger.info("Saved poster to %s", out_path)
    return {"status": "ok", "path": out_path}


@app.post("/api/plex/send")
def api_plex_send(req: PlexSendRequest):
    if not PLEX_URL or not PLEX_TOKEN:
        raise HTTPException(status_code=400, detail="PLEX_URL and PLEX_TOKEN must be configured.")

    bg = _download_image(req.background_url)
    if bg is None:
        raise HTTPException(status_code=400, detail="Invalid background image.")

    logo = _download_image(req.logo_url) if req.logo_url else None
    renderer = get_renderer(req.template_id)
    img = renderer(bg, logo, req.options or {})

    # --- Save to temp file ---
    with NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        temp_path = tmp.name
        img.convert("RGB").save(tmp, "JPEG", quality=95)

    logger.info(f"Prepared Plex upload temp file: {temp_path}")

    # --- Upload using the real file ---
    try:
        upload_url = f"{PLEX_URL}/library/metadata/{req.rating_key}/posters"
        
        headers = {
            "X-Plex-Token": PLEX_TOKEN,
            "Content-Type": "image/jpeg"
        }
        
        # img is the rendered PIL image
        buf = BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=95)
        payload = buf.getvalue()
        
        r = requests.post(upload_url, headers=headers, data=payload, timeout=20)
        r.raise_for_status()

    except Exception as e:
        logger.exception("Failed to send poster to Plex")
        raise HTTPException(status_code=500, detail="Failed to send poster to Plex.")

    # Remove labels
    for label in (req.labels or []):
        _remove_label(req.rating_key, label)

    logger.info(f"Sent poster to Plex for ratingKey={req.rating_key}")

    return {"status": "ok"}

@app.get("/api/logs")
def api_logs():
    """
    Return the last ~500 lines of the Simposter log file so the UI
    can display them.
    """
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return {"text": ""}

    tail = lines[-500:]
    return {"text": "".join(tail)}

@app.post("/api/batch")
def api_batch(req: BatchRequest):
    """
    Batch-generate posters using rating_keys (fast UI),
    resolve TMDb IDs ONLY for selected movies.
    """
    results = []

    for idx, rating_key in enumerate(req.rating_keys):
        try:
            # 1) Resolve TMDb ID for this Plex item
            tmdb_id = get_movie_tmdb_id(rating_key)
            if not tmdb_id:
                results.append({
                    "rating_key": rating_key,
                    "status": "error",
                    "error": "No TMDb ID"
                })
                continue

            # 2) Fetch TMDb assets
            imgs = get_images_for_movie(tmdb_id)
            posters = imgs.get("posters") or []
            logos = imgs.get("logos") or []

            if not posters:
                results.append({
                    "rating_key": rating_key,
                    "status": "error",
                    "error": "No posters from TMDb"
                })
                continue

            bg_url = posters[0]["url"]
            logo_url = logos[0]["url"] if logos else None

            # 3) Render
            img = _render_poster_image(
                req.template_id,
                bg_url,
                logo_url,
                req.options
            )

            # 4) Upload?
            if req.send_to_plex:
                buf = BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=95)
                payload = buf.getvalue()

                upload_url = f"{PLEX_URL}/library/metadata/{rating_key}/posters"
                headers = {"X-Plex-Token": PLEX_TOKEN, "Content-Type": "image/jpeg"}
                r = requests.post(upload_url, headers=headers, data=payload, timeout=20)
                r.raise_for_status()

                # Label removal
                for label in (req.labels or []):
                    _remove_label(rating_key, label)

                results.append({
                    "rating_key": rating_key,
                    "status": "ok",
                    "sent_to_plex": True
                })
            else:
                results.append({
                    "rating_key": rating_key,
                    "status": "ok",
                    "sent_to_plex": False
                })

            # Avoid rate limiting
            time.sleep(0.7)

        except Exception as e:
            logger.exception("Batch error for rating_key=%s", rating_key)
            results.append({
                "rating_key": rating_key,
                "status": "error",
                "error": str(e)
            })

    return {"results": results}



@app.post("/api/upload/background")
async def api_upload_background(file: UploadFile = File(...)):
    """
    Accept a local image (drag/drop) and make it addressable by URL
    so the renderer can use it like a TMDb URL.
    """
    contents = await file.read()
    # simple unique-ish name
    ext = os.path.splitext(file.filename or "bg.jpg")[1] or ".jpg"
    fname = f"bg_{int(time.time()*1000)}{ext}"
    path = os.path.join(UPLOAD_DIR, fname)

    with open(path, "wb") as f:
        f.write(contents)

    return {"url": f"/api/uploaded/{fname}"}

@app.get("/api/uploaded/{filename}")
def api_uploaded(filename: str):
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")

@app.get("/api/movies/tmdb")
def api_movies_tmdb():
    """
    FAST list for batch mode:
    Returns Plex movies with rating_keys only.
    No TMDb lookups here.
    """
    movies = _get_plex_movies()
    out = []

    for m in movies:
        out.append({
            "title": m.title,
            "year": m.year,
            "rating_key": m.key,
            "tmdb_id": None  # resolved later during batch
        })
    return out




#radarr webhooks
@app.post("/api/webhook/radarr")
def api_webhook_radarr(payload: RadarrWebhook):
    """
    Radarr → Simposter → Plex auto poster pipeline.
    Configure this URL in Radarr's webhook settings.
    """
    if payload.eventType.lower() not in ("download", "grab"):
        return {"status": "ignored", "reason": "eventType not handled"}

    title = payload.movie.title
    year = payload.movie.year
    tmdb_id = payload.movie.tmdbId

    logger.info("Radarr webhook for '%s' (%s), tmdb=%s",
                title, year, tmdb_id)

    rating_key = _find_rating_key_by_title_year(title, year)
    if not rating_key:
        logger.warning("No Plex match for '%s' (%s)", title, year)
        return {"status": "error", "error": "No Plex match"}

    # Resolve TMDb if missing
    if not tmdb_id:
        tmdb_id = get_movie_tmdb_id(rating_key)

    if not tmdb_id:
        logger.warning("No TMDb id for '%s' (%s)", title, year)
        return {"status": "error", "error": "No TMDb id"}

    # Get TMDb images
    imgs = get_images_for_movie(tmdb_id)
    posters = imgs.get("posters") or []
    logos = imgs.get("logos") or []

    if not posters:
        return {"status": "error", "error": "No posters from TMDb"}

    bg_url = posters[0]["url"]
    logo_url = logos[0]["url"] if logos else None

    # Load preset options
    presets_data = load_presets()
    presets_list = presets_data.get("default", {}).get("presets", [])
    preset = next((p for p in presets_list if p.get("id") == WEBHOOK_DEFAULT_PRESET), None)
    options = preset["options"] if preset else {}

    # Render
    img = _render_poster_image("default", bg_url, logo_url, options)

    if not WEBHOOK_AUTO_SEND:
        # Just log + done
        logger.info("Webhook rendered poster for '%s' but auto-send disabled.", title)
        return {"status": "ok", "sent_to_plex": False}

    # Send to Plex
    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)
    payload_bytes = buf.getvalue()

    upload_url = f"{PLEX_URL}/library/metadata/{rating_key}/posters"
    headers = {
        "X-Plex-Token": PLEX_TOKEN,
        "Content-Type": "image/jpeg"
    }
    r = requests.post(upload_url, headers=headers, data=payload_bytes, timeout=20)
    r.raise_for_status()

    # Label cleanup
    labels = [l.strip() for l in WEBHOOK_AUTO_LABELS if l.strip()]
    for lab in labels:
        _remove_label(rating_key, lab)

    logger.info("Webhook poster sent to Plex for ratingKey=%s", rating_key)
    return {"status": "ok", "sent_to_plex": True, "rating_key": rating_key}
