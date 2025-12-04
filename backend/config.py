# backend/config.py
from dotenv import load_dotenv
import os
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import requests

from pydantic_settings import BaseSettings

# Project base dir (repo root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load env files in order of priority:
# 1) /config/.env (if CONFIG_DIR env is set, use that)
# 2) repo root .env (BASE_DIR/.env)
env_candidates = []
config_dir_env = os.environ.get("CONFIG_DIR")
if config_dir_env:
    env_candidates.append(Path(config_dir_env) / ".env")
else:
    env_candidates.append(Path("/config/.env"))
env_candidates.append(BASE_DIR / ".env")
for env_path in env_candidates:
    load_dotenv(env_path, override=True)

# ===============================
#  Settings (loads .env properly)
# ===============================
class Settings(BaseSettings):
    PLEX_URL: str = "http://localhost:32400"
    PLEX_TOKEN: str = ""
    PLEX_MOVIE_LIBRARY_NAME: str = "1"
    PLEX_VERIFY_TLS: bool = True
    LOG_LEVEL: str = "INFO"

    TMDB_API_KEY: str = ""

    OUTPUT_ROOT: str = "./output"
    CONFIG_DIR: str = "./config"
    SETTINGS_DIR: str = ""
    UPLOAD_DIR: str = "./uploads"
    LOG_DIR: str = ""
    LOG_FILE: str = ""

    WEBHOOK_DEFAULT_PRESET: str = "default"
    WEBHOOK_AUTO_SEND: bool = True
    WEBHOOK_AUTO_LABELS: str = "Overlay"
    WEBHOOK_SECRET: str = ""

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"


settings = Settings()


# ===============================
#  Load from ui_settings.json as fallback
# ===============================
def _load_ui_settings_fallback():
    """
    Load Plex/TMDB credentials from ui_settings.json if they weren't provided via environment.
    This allows users to configure via GUI without needing .env or docker-compose.

    Priority order:
    1. Environment variables (docker-compose/.env) - highest priority
    2. ui_settings.json (GUI settings) - fallback
    3. Defaults - lowest priority
    """
    # Only load from ui_settings if env vars are at default/empty values
    needs_fallback = (
        settings.PLEX_URL == "http://localhost:32400" and
        settings.PLEX_TOKEN == "" and
        settings.TMDB_API_KEY == ""
    )

    if not needs_fallback:
        return  # Environment variables are set, no need for fallback

    # Resolve settings path (needs CONFIG_DIR to be normalized first)
    settings_dir = Path(settings.CONFIG_DIR) / "settings"
    ui_settings_file = settings_dir / "ui_settings.json"

    # Also check legacy location
    legacy_ui_settings = Path(settings.CONFIG_DIR) / "ui_settings.json"

    settings_file = ui_settings_file if ui_settings_file.exists() else legacy_ui_settings

    if not settings_file.exists():
        return  # No ui_settings.json to load from

    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))

        # Load Plex settings
        plex_data = data.get("plex", {})
        if plex_data.get("url") and settings.PLEX_URL == "http://localhost:32400":
            settings.PLEX_URL = plex_data["url"]
        if plex_data.get("token") and settings.PLEX_TOKEN == "":
            settings.PLEX_TOKEN = plex_data["token"]
        if plex_data.get("movieLibraryName") and settings.PLEX_MOVIE_LIBRARY_NAME == "1":
            settings.PLEX_MOVIE_LIBRARY_NAME = plex_data["movieLibraryName"]

        # Load TMDB settings
        tmdb_data = data.get("tmdb", {})
        if tmdb_data.get("apiKey") and settings.TMDB_API_KEY == "":
            settings.TMDB_API_KEY = tmdb_data["apiKey"]

    except Exception:
        pass  # Silently fail if ui_settings.json is malformed

# Normalize paths relative to repo root so npm/uvicorn cwd doesn't matter
def _resolve_path(p: str) -> str:
    path = Path(p)
    if path.is_absolute():
        return str(path)
    return str((BASE_DIR / path).resolve())

settings.CONFIG_DIR = _resolve_path(settings.CONFIG_DIR)
settings.SETTINGS_DIR = _resolve_path(settings.SETTINGS_DIR or str(Path(settings.CONFIG_DIR) / "settings"))
settings.OUTPUT_ROOT = _resolve_path(settings.OUTPUT_ROOT)
settings.UPLOAD_DIR = _resolve_path(settings.UPLOAD_DIR)
settings.LOG_DIR = _resolve_path(settings.LOG_DIR or str(Path(settings.CONFIG_DIR) / "logs"))
settings.LOG_FILE = _resolve_path(settings.LOG_FILE) if settings.LOG_FILE else str(Path(settings.LOG_DIR) / "simposter.log")

# Load from ui_settings.json if environment variables weren't provided
_load_ui_settings_fallback()

# Ensure folders exist
Path(settings.CONFIG_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.OUTPUT_ROOT).mkdir(parents=True, exist_ok=True)
Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)

# Migrate legacy log locations into the dedicated config/logs folder
preferred_log = Path(settings.LOG_FILE).resolve()
legacy_log_in_config = (Path(settings.CONFIG_DIR) / "simposter.log").resolve()
legacy_log_in_repo_logs = (BASE_DIR / "logs" / "simposter.log").resolve()
for candidate in (legacy_log_in_config, legacy_log_in_repo_logs):
    if candidate == preferred_log:
        continue
    if candidate.exists() and not preferred_log.exists():
        try:
            preferred_log.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(preferred_log)
        except OSError:
            shutil.copy2(candidate, preferred_log)
settings.LOG_FILE = str(preferred_log)


# ==========================
#  Logging
# ==========================
logger = logging.getLogger("simposter")
level_name = settings.LOG_LEVEL.upper()
level = getattr(logging, level_name, logging.INFO)
logger.setLevel(level)

if not logger.handlers:
    log_dir = os.path.dirname(settings.LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    fh = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
    sh = logging.StreamHandler()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)


# ==========================
#  Presets
# ==========================
DEFAULT_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "presets.json")
LEGACY_PRESETS_PATH = os.path.join(settings.CONFIG_DIR, "presets.json")
USER_PRESETS_PATH = os.path.join(settings.SETTINGS_DIR, "presets.json")


# FRONTEND DIRECTORY (serve built dist if present; otherwise use source for dev)
_frontend_base = Path(__file__).resolve().parent.parent / "frontend"
_frontend_dist = _frontend_base / "dist"
FRONTEND_DIR = str(_frontend_dist if _frontend_dist.exists() else _frontend_base)


def load_presets() -> dict:
    """Load presets from config dir or fallback to defaults."""
    # Migrate legacy location if present
    if not os.path.exists(USER_PRESETS_PATH) and os.path.exists(LEGACY_PRESETS_PATH):
        try:
            Path(USER_PRESETS_PATH).parent.mkdir(parents=True, exist_ok=True)
            Path(LEGACY_PRESETS_PATH).replace(USER_PRESETS_PATH)
        except OSError:
            shutil.copy2(LEGACY_PRESETS_PATH, USER_PRESETS_PATH)

    if not os.path.exists(USER_PRESETS_PATH):
        try:
            with open(DEFAULT_PRESETS_PATH, "r", encoding="utf-8") as f:
                defaults = json.load(f)
        except FileNotFoundError:
            defaults = {"default": {"presets": []}}

        with open(USER_PRESETS_PATH, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=2)

        return defaults

    with open(USER_PRESETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_presets(data: dict) -> None:
    with open(USER_PRESETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ==========================
#  Plex Helpers
# ==========================
def plex_headers() -> Dict[str, str]:
    return {"X-Plex-Token": settings.PLEX_TOKEN} if settings.PLEX_TOKEN else {}


def resolve_library_id(name: str) -> str:
    """Resolve library section name → id (Plex)"""
    name = name.strip()
    if name.isdigit():
        return name

    url = f"{settings.PLEX_URL}/library/sections"
    try:
        r = requests.get(url, headers=plex_headers(), timeout=8, verify=settings.PLEX_VERIFY_TLS)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        logger.debug("[PLEX] Resolved sections from %s", url)
    except Exception as e:
        logger.warning("[PLEX] Failed to resolve sections from %s: %s", url, e)
        return "1"

    for directory in root.findall(".//Directory"):
        if (directory.get("title") or "").strip().lower() == name.lower():
            return directory.get("key")

    return "1"


PLEX_MOVIE_LIB_ID = resolve_library_id(settings.PLEX_MOVIE_LIBRARY_NAME)


# --- Fetch Plex Movies ---
def get_plex_movies():
    from .schemas import Movie

    url = f"{settings.PLEX_URL}/library/sections/{PLEX_MOVIE_LIB_ID}/all?type=1"

    try:
        r = requests.get(url, headers=plex_headers(), timeout=6, verify=settings.PLEX_VERIFY_TLS)
        r.raise_for_status()
        logger.debug("[PLEX] GET %s -> %s", url, r.status_code)
    except Exception as e:
        logger.warning("[PLEX] Unreachable while listing movies: %s", e)
        return []

    root = ET.fromstring(r.text)
    out = []

    for video in root.findall(".//Video"):
        key = video.get("ratingKey")
        title = video.get("title") or ""
        year = video.get("year")
        added_at = video.get("addedAt")
        out.append(Movie(key=key, title=title, year=int(year) if year else None, addedAt=int(added_at) if added_at else None))

    logger.info("[PLEX] Loaded %d movies from library %s", len(out), PLEX_MOVIE_LIB_ID)
    return out


def extract_tmdb_id_from_metadata(xml_text: str) -> Optional[int]:
    import re
    if xml_text.startswith("<html"):
        return None

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    for g in root.findall(".//Guid"):
        gid = g.get("id") or ""
        match = re.search(r"(?:tmdb|themoviedb)://(\d+)", gid)
        if match:
            return int(match.group(1))
    return None


def get_movie_tmdb_id(rating_key: str) -> Optional[int]:
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"

    try:
        r = requests.get(url, headers=plex_headers(), timeout=6, verify=settings.PLEX_VERIFY_TLS)
        r.raise_for_status()
        logger.debug("[PLEX] GET %s -> %s", url, r.status_code)
    except Exception as e:
        logger.warning("[PLEX] Failed to fetch metadata for %s: %s", rating_key, e)
        return None

    return extract_tmdb_id_from_metadata(r.text)


def find_rating_key_by_title_year(title: str, year: Optional[int]):
    movies = get_plex_movies()
    title_norm = title.lower().strip()

    for m in movies:
        if m.title.lower().strip() == title_norm:
            if year is None or m.year == year:
                logger.debug("[PLEX] Matched title/year '%s' (%s) -> rating_key=%s", title, year, m.key)
                return m.key

    logger.warning("[PLEX] Could not match '%s' (%s) to a rating_key", title, year)
    return None


def plex_remove_label(rating_key: str, label: str):
    """Attempts 3 different Plex label removal methods."""

    if not label:
        return

    # Method 1
    try:
        url = f"{settings.PLEX_URL}/library/sections/{PLEX_MOVIE_LIB_ID}/all"
        params = {"type": "1", "id": rating_key, "label[].tag.tag-": label}
        r = requests.put(url, headers=plex_headers(), params=params, timeout=8, verify=settings.PLEX_VERIFY_TLS)
        if r.status_code in (200, 204):
            logger.debug("[PLEX] Removed label via sections endpoint rating_key=%s label=%s", rating_key, label)
            return
    except Exception:
        pass

    # Method 2
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/labels"
        params = {"tag.tag": label, "tag.type": "label"}
        r = requests.delete(url, headers=plex_headers(), params=params, timeout=8, verify=settings.PLEX_VERIFY_TLS)
        if r.status_code in (200, 204):
            logger.debug("[PLEX] Removed label via metadata/labels rating_key=%s label=%s", rating_key, label)
            return
    except Exception:
        pass

    # Method 3
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        params = {"label[].tag.tag-": label, "type": "1"}
        r = requests.put(url, headers=plex_headers(), params=params, timeout=8, verify=settings.PLEX_VERIFY_TLS)
        logger.debug("[PLEX] Attempted label removal via metadata PUT rating_key=%s label=%s status=%s", rating_key, label, r.status_code)
    except Exception:
        pass
