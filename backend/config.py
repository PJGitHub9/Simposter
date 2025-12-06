# backend/config.py
from dotenv import load_dotenv
import os
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pydantic_settings import BaseSettings
from . import cache

# Project base dir (repo root)
BASE_DIR = Path(__file__).resolve().parent.parent

# Simple docker/container detection for better guidance when connecting to Plex
def _running_in_container() -> bool:
    try:
        if Path("/.dockerenv").exists():
            return True
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists() and "docker" in cgroup.read_text():
            return True
    except Exception:
        pass
    return False

# Load env files in order of priority:
# 1) /config/.env (or ${CONFIG_DIR}/.env) if present
# 2) repo root .env
# Use override=False so container ENV (e.g., CONFIG_DIR=/config) is not clobbered by .env defaults.
env_candidates = []
config_dir_env = os.environ.get("CONFIG_DIR")
if config_dir_env:
    env_candidates.append(Path(config_dir_env) / ".env")
else:
    env_candidates.append(Path("/config/.env"))
env_candidates.append(BASE_DIR / ".env")
for env_path in env_candidates:
    load_dotenv(env_path, override=False)

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
    Load Plex/TMDB credentials from database or JSON fallback.
    This allows users to configure via GUI without needing .env or docker-compose.

    Priority order:
    1. Explicit environment variables (docker-compose/.env) - highest priority
    2. Database (simposter.db) - user-facing config
    3. ui_settings.json (legacy) - backward compatibility
    4. Defaults - lowest priority

    Note: Environment variables still override everything so docker deployments can force values,
    while database/UI settings remain the primary interactive config.
    """
    data = None

    # Try loading from database first
    try:
        # Import database module dynamically to avoid circular import issues
        import importlib
        import sys

        # Get the parent directory of this file (backend/)
        backend_dir = Path(__file__).parent
        if str(backend_dir.parent) not in sys.path:
            sys.path.insert(0, str(backend_dir.parent))

        db = importlib.import_module('backend.database')
        data = db.get_ui_settings()
    except Exception:
        # Silently ignore database errors during initial load
        pass

    # Fallback to JSON files if database is empty
    if not data:
        settings_dir = Path(settings.CONFIG_DIR) / "settings"
        ui_settings_file = settings_dir / "ui_settings.json"
        legacy_ui_settings = Path(settings.CONFIG_DIR) / "ui_settings.json"

        settings_file = ui_settings_file if ui_settings_file.exists() else legacy_ui_settings

        if settings_file.exists():
            try:
                data = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                return

    if not data:
        return  # No settings to load

    try:
        # Load Plex settings - database/JSON takes priority over defaults
        plex_data = data.get("plex", {})
        if plex_data.get("url"):
            settings.PLEX_URL = plex_data["url"]
        if plex_data.get("token"):
            settings.PLEX_TOKEN = plex_data["token"]
        if plex_data.get("movieLibraryName"):
            settings.PLEX_MOVIE_LIBRARY_NAME = plex_data["movieLibraryName"]

        # Load TMDB settings
        tmdb_data = data.get("tmdb", {})
        if tmdb_data.get("apiKey"):
            settings.TMDB_API_KEY = tmdb_data["apiKey"]

        # Explicit environment variables override database/JSON so docker-compose can force values
        plex_url_env = os.getenv("PLEX_URL")
        plex_token_env = os.getenv("PLEX_TOKEN")
        plex_lib_env = os.getenv("PLEX_MOVIE_LIBRARY_NAME")
        tmdb_key_env = os.getenv("TMDB_API_KEY")

        if plex_url_env:
            settings.PLEX_URL = plex_url_env
        if plex_token_env:
            settings.PLEX_TOKEN = plex_token_env
        if plex_lib_env:
            settings.PLEX_MOVIE_LIBRARY_NAME = plex_lib_env
        if tmdb_key_env:
            settings.TMDB_API_KEY = tmdb_key_env

    except Exception:
        pass  # Silently ignore errors during settings application

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
POSTER_CACHE_DIR = str(Path(settings.CONFIG_DIR) / "cache" / "posters")

# Load from ui_settings.json if environment variables weren't provided
_load_ui_settings_fallback()

# Ensure folders exist
Path(settings.CONFIG_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.OUTPUT_ROOT).mkdir(parents=True, exist_ok=True)
Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
Path(POSTER_CACHE_DIR).mkdir(parents=True, exist_ok=True)

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
#  Logging with sensitive data redaction
# ==========================
class RedactingFormatter(logging.Formatter):
    """Custom formatter that redacts sensitive information from logs."""

    def format(self, record):
        # Tag API (uvicorn*) logs - keep original level but add API tag
        if record.name.startswith("uvicorn"):
            record.api_tag = "[API] "
        else:
            record.api_tag = ""

        original = super().format(record)
        # Redact tokens and API keys
        redacted = original
        if settings.PLEX_TOKEN and len(settings.PLEX_TOKEN) > 4:
            redacted = redacted.replace(settings.PLEX_TOKEN, settings.PLEX_TOKEN[:4] + "***REDACTED***")
        if settings.TMDB_API_KEY and len(settings.TMDB_API_KEY) > 4:
            redacted = redacted.replace(settings.TMDB_API_KEY, settings.TMDB_API_KEY[:4] + "***REDACTED***")
        return redacted

class APILogDowngradeFilter(logging.Filter):
    """Force uvicorn access logs to DEBUG level so they don't spam INFO."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("uvicorn"):
            record.levelname = "DEBUG"
            record.levelno = logging.DEBUG
        return True

logger = logging.getLogger("simposter")
level_name = settings.LOG_LEVEL.upper()
level = getattr(logging, level_name, logging.INFO)
logger.setLevel(level)

if not logger.handlers:
    log_dir = os.path.dirname(settings.LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    def _rotate_namer(default_name: str) -> str:
        """Rename uvicorn rotation file to simposter-YYYYMMDD.log style."""
        p = Path(default_name)
        # default_name ends with .YYYY-MM-DD; normalize to YYYYMMDD
        date_part = p.name.split(".")[-1].replace("-", "")
        base_stem = Path(settings.LOG_FILE).stem
        return str(p.with_name(f"{base_stem}-{date_part}.log"))

    fh = TimedRotatingFileHandler(
        settings.LOG_FILE,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        utc=False,
    )
    fh.suffix = "%Y-%m-%d"
    fh.namer = _rotate_namer
    sh = logging.StreamHandler()

    fmt = RedactingFormatter("%(asctime)s %(api_tag)s[%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    downgrade_filter = APILogDowngradeFilter()
    fh.addFilter(downgrade_filter)
    sh.addFilter(downgrade_filter)

    logger.addHandler(fh)
    logger.addHandler(sh)

# Attach handlers to uvicorn loggers so access logs land in our file too, labeled as [API] at DEBUG.
api_formatter = RedactingFormatter("%(asctime)s %(api_tag)s[%(levelname)s] %(message)s")
for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
    uv_logger = logging.getLogger(name)
    uv_logger.handlers = []
    for h in logger.handlers:
        clone = h
        # Only adjust formatter on the clone if it's a Stream/FileHandler
        try:
            clone.setFormatter(api_formatter)
        except Exception:
            pass
        uv_logger.addHandler(clone)
    uv_logger.setLevel(logging.DEBUG)
    uv_logger.propagate = False

# Warn early if Plex URL points to localhost inside a container (common unRAID/Docker pitfall)
if _running_in_container():
    plex_url_lower = settings.PLEX_URL.lower()
    if "localhost" in plex_url_lower or "127.0.0.1" in plex_url_lower:
        logger.warning(
            "[PLEX] PLEX_URL is set to %s inside a container. "
            "If Plex runs on the host, use the host IP (e.g. http://192.168.x.x:32400) "
            "or run the container with host networking/extra_hosts so Plex is reachable.",
            settings.PLEX_URL,
        )


def _build_plex_session() -> requests.Session:
    """
    Shared requests session for Plex calls with connection pooling and light retries.
    This keeps sockets open so we can handle many concurrent label/poster lookups faster.
    """
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=32,
        pool_maxsize=64,
        max_retries=Retry(total=2, backoff_factor=0.2, status_forcelist=[502, 503, 504]),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.verify = settings.PLEX_VERIFY_TLS
    return session


plex_session = _build_plex_session()


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
    """Load presets from database or fallback to defaults."""
    try:
        # Import database module dynamically to avoid circular import issues
        import importlib
        import sys

        # Get the parent directory of this file (backend/)
        backend_dir = Path(__file__).parent
        if str(backend_dir.parent) not in sys.path:
            sys.path.insert(0, str(backend_dir.parent))

        db = importlib.import_module('backend.database')
        presets = db.get_all_presets()

        # If database has presets, return them
        if presets:
            logger.debug("[PRESETS] Loaded %d templates from database", len(presets))
            return presets
    except Exception as e:
        logger.warning("[PRESETS] Failed to load from database: %s", e)

    # Fallback to JSON file if database is empty or fails
    logger.debug("[PRESETS] Falling back to JSON file")

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
        r = plex_session.get(url, headers=plex_headers(), timeout=8)
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
        r = plex_session.get(url, headers=plex_headers(), timeout=6)
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
    try:
        cache.refresh_from_list(out)
    except Exception:
        logger.debug("[CACHE] refresh_from_list failed", exc_info=True)
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
        r = plex_session.get(url, headers=plex_headers(), timeout=6)
        r.raise_for_status()
        logger.debug("[PLEX] GET %s -> %s", url, r.status_code)
    except Exception as e:
        logger.warning("[PLEX] Failed to fetch metadata for %s: %s", rating_key, e)
        return None

    tmdb_id = extract_tmdb_id_from_metadata(r.text)
    try:
        cache.update_tmdb(rating_key, tmdb_id)
    except Exception:
        logger.debug("[CACHE] update_tmdb failed", exc_info=True)
    return tmdb_id


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
        r = plex_session.put(url, headers=plex_headers(), params=params, timeout=8)
        if r.status_code in (200, 204):
            logger.debug("[PLEX] Removed label via sections endpoint rating_key=%s label=%s", rating_key, label)
            return
    except Exception:
        pass

    # Method 2
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/labels"
        params = {"tag.tag": label, "tag.type": "label"}
        r = plex_session.delete(url, headers=plex_headers(), params=params, timeout=8)
        if r.status_code in (200, 204):
            logger.debug("[PLEX] Removed label via metadata/labels rating_key=%s label=%s", rating_key, label)
            return
    except Exception:
        pass

    # Method 3
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        params = {"label[].tag.tag-": label, "type": "1"}
        r = plex_session.put(url, headers=plex_headers(), params=params, timeout=8)
        logger.debug("[PLEX] Attempted label removal via metadata PUT rating_key=%s label=%s status=%s", rating_key, label, r.status_code)
    except Exception:
        pass
