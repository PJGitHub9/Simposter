import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings, logger, resolve_library_ids
from ..schemas import UISettings
from .. import database as db

router = APIRouter()

# Legacy file paths for migration check
_settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
_legacy_settings_file = Path(settings.CONFIG_DIR) / "ui_settings.json"


def _normalize_plex_payload(data: dict) -> dict:
    """
    Normalize plex-related fields to strings/lists of strings.
    Prevents pydantic validation errors when older data stored ints or missing lists.
    """
    if not isinstance(data, dict):
        return {}

    plex = data.get("plex", {}) or {}
    normalized = plex.copy()

    if "movieLibraryName" in normalized:
        normalized["movieLibraryName"] = str(normalized["movieLibraryName"])
    # Ensure list exists and is stringified
    if "movieLibraryNames" in normalized and isinstance(normalized["movieLibraryNames"], list):
        normalized["movieLibraryNames"] = [str(x) for x in normalized["movieLibraryNames"]]
    elif normalized.get("movieLibraryName"):
        normalized["movieLibraryNames"] = [str(normalized["movieLibraryName"])]
    else:
        normalized["movieLibraryNames"] = []

    # Normalize library mappings if present
    if "libraryMappings" in normalized and isinstance(normalized["libraryMappings"], list):
        normalized["libraryMappings"] = [
            {
                "id": str(m.get("id", "")),
                "title": str(m.get("title", "")),
                "displayName": str(m.get("displayName", "")),
            }
            for m in normalized["libraryMappings"]
            if isinstance(m, dict)
        ]

    data["plex"] = normalized
    return data


def _apply_runtime_settings(merged: dict):
    """Update global settings with latest UI settings so runtime calls use fresh values."""
    plex_data = merged.get("plex", {}) or {}
    tmdb_data = merged.get("tmdb", {}) or {}
    fanart_data = merged.get("fanart", {}) or {}
    library_mappings = plex_data.get("libraryMappings") or []
    url = plex_data.get("url") or ""
    token = plex_data.get("token") or ""
    names = plex_data.get("movieLibraryNames") or []
    if not names and plex_data.get("movieLibraryName"):
        names = [plex_data.get("movieLibraryName")]
    names = [str(n) for n in names if str(n).strip()]

    # Use object.__setattr__ to avoid pydantic field restrictions
    object.__setattr__(settings, "PLEX_URL", url)
    object.__setattr__(settings, "PLEX_TOKEN", token)
    object.__setattr__(settings, "PLEX_MOVIE_LIBRARY_NAMES", names or ["1"])
    object.__setattr__(settings, "PLEX_MOVIE_LIBRARY_NAME", (names or ["1"])[0])

    # Resolve IDs from names or IDs (passes through numeric IDs)
    try:
        ids = resolve_library_ids(settings.PLEX_MOVIE_LIBRARY_NAMES)
    except Exception:
        ids = settings.PLEX_MOVIE_LIBRARY_NAMES

    # Persist resolved IDs back on settings for downstream use
    object.__setattr__(settings, "PLEX_MOVIE_LIB_IDS", ids)

    default_id = ids[0] if ids else "1"
    object.__setattr__(settings, "PLEX_DEFAULT_MOVIE_LIB_ID", default_id)

    # TMDB runtime key
    tmdb_key = tmdb_data.get("apiKey") or ""
    object.__setattr__(settings, "TMDB_API_KEY", tmdb_key)

    # Fanart runtime key
    fanart_key = fanart_data.get("apiKey") or ""
    object.__setattr__(settings, "FANART_API_KEY", fanart_key)

    # Library mappings for name/id resolution
    object.__setattr__(settings, "PLEX_LIBRARY_MAPPINGS", library_mappings)


def _default_ui_settings() -> UISettings:
    """Defaults seeded from environment to make docker-compose setup easier."""
    return UISettings(
        plex={
            "url": settings.PLEX_URL,
            "token": settings.PLEX_TOKEN,
            "movieLibraryName": settings.PLEX_MOVIE_LIBRARY_NAME,
            "movieLibraryNames": getattr(settings, "PLEX_MOVIE_LIBRARY_NAMES", []) or [settings.PLEX_MOVIE_LIBRARY_NAME],
            "libraryMappings": [
                {
                    "id": lid,
                    "title": getattr(settings, "PLEX_MOVIE_LIBRARY_NAMES", [settings.PLEX_MOVIE_LIBRARY_NAME])[idx]
                    if idx < len(getattr(settings, "PLEX_MOVIE_LIBRARY_NAMES", [])) else settings.PLEX_MOVIE_LIBRARY_NAME,
                    "displayName": getattr(settings, "PLEX_MOVIE_LIBRARY_NAMES", [settings.PLEX_MOVIE_LIBRARY_NAME])[idx]
                    if idx < len(getattr(settings, "PLEX_MOVIE_LIBRARY_NAMES", [])) else settings.PLEX_MOVIE_LIBRARY_NAME,
                }
                for idx, lid in enumerate(getattr(settings, "PLEX_MOVIE_LIB_IDS", []))
            ],
        },
        tmdb={"apiKey": getattr(settings, "TMDB_API_KEY", "")},
        tvdb={"apiKey": "", "comingSoon": True},
        fanart={"apiKey": getattr(settings, "FANART_API_KEY", "")},
        saveBatchInSubfolder=False,
    )


def _env_overrides() -> dict:
    """Use explicit environment variables to override stored UI settings."""
    out: dict = {}
    plex_url = os.getenv("PLEX_URL")
    plex_token = os.getenv("PLEX_TOKEN")
    plex_lib = os.getenv("PLEX_MOVIE_LIBRARY_NAME")
    plex_libs = os.getenv("PLEX_MOVIE_LIBRARY_NAMES")
    tmdb_key = os.getenv("TMDB_API_KEY")
    fanart_key = os.getenv("FANART_API_KEY")

    if plex_url:
        out.setdefault("plex", {})["url"] = plex_url
    if plex_token:
        out.setdefault("plex", {})["token"] = plex_token
    if plex_lib:
        out.setdefault("plex", {})["movieLibraryName"] = plex_lib
    if plex_libs:
        out.setdefault("plex", {})["movieLibraryNames"] = [s.strip() for s in plex_libs.split(",") if s.strip()]
    if tmdb_key:
        out.setdefault("tmdb", {})["apiKey"] = tmdb_key
    if fanart_key:
        out.setdefault("fanart", {})["apiKey"] = fanart_key
    return out


def _read_settings(include_env: bool = True) -> UISettings:
    """
    Read settings from database, creating defaults if missing.
    Falls back to JSON files for backward compatibility during migration.
    
    Note: include_env is now primarily for backward compatibility.
    ENV variables are copied to DB on startup, so DB values should take precedence.
    """
    try:
        # Try reading from database first
        try:
            data = db.get_ui_settings()
        except Exception as db_err:
            # Initialize database if missing table, then retry once
            if "no such table: settings" in str(db_err):
                logger.warning("[DB] Settings table missing; initializing database...")
                try:
                    db.init_database()
                    data = db.get_ui_settings()
                except Exception:
                    data = None
            else:
                raise

        # If no database settings, try legacy JSON files
        if data is None:
            logger.info("[UI_SETTINGS] No database settings found, checking JSON files...")

            if not _settings_file.exists() and _legacy_settings_file.exists():
                try:
                    _settings_file.parent.mkdir(parents=True, exist_ok=True)
                    _legacy_settings_file.replace(_settings_file)
                except OSError:
                    data = json.loads(_legacy_settings_file.read_text(encoding="utf-8"))

            if _settings_file.exists():
                data = json.loads(_settings_file.read_text(encoding="utf-8"))
                logger.info("[UI_SETTINGS] Loaded from JSON, will migrate to database on next save")

        # If still no data, use defaults
        if data is None:
            logger.info("[UI_SETTINGS] No existing settings, using defaults")
            defaults = _default_ui_settings().model_dump(
                exclude_none=False, exclude_defaults=False, exclude_unset=False
            )
            # Save defaults to database
            db.save_ui_settings(defaults)
            return UISettings(**defaults)

        # Normalize legacy values before merging
        data = _normalize_plex_payload(data)

        # Merge with defaults so newly added fields are included
        defaults = _default_ui_settings().model_dump(exclude_none=False, exclude_defaults=False)
        merged = {**defaults, **data}
        for nested_key in ("plex", "tmdb", "tvdb", "fanart", "imageQuality", "performance"):
            merged[nested_key] = {**defaults.get(nested_key, {}), **data.get(nested_key, {})}

        # ENV variables are now copied to DB on container startup instead of runtime overrides
        # This allows users to modify the values via UI after initial setup
        # Only apply ENV overrides for completely fresh/default databases
        if include_env:
            env_overrides = _env_overrides()
            if env_overrides:
                # Check if database has any non-default values
                plex_data = merged.get("plex", {})
                tmdb_data = merged.get("tmdb", {})
                
                has_configured_settings = (
                    (plex_data.get("url") and plex_data.get("url") != "http://localhost:32400") or
                    (plex_data.get("token") and plex_data.get("token") != "") or
                    (tmdb_data.get("apiKey") and tmdb_data.get("apiKey") != "")
                )
                
                if not has_configured_settings:
                    logger.debug("[UI_SETTINGS] Database appears empty, applying ENV overrides")
                    for nested_key, nested_values in env_overrides.items():
                        merged[nested_key] = {**merged.get(nested_key, {}), **nested_values}
                else:
                    logger.debug("[UI_SETTINGS] Database has user settings, ENV overrides disabled")

        merged = _normalize_plex_payload(merged)
        _apply_runtime_settings(merged)
        return UISettings(**merged)
    except Exception as e:
        logger.error(f"[UI_SETTINGS] Failed to read settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {e}")


@router.get("/ui-settings")
def get_ui_settings():
    settings_obj = _read_settings()
    return JSONResponse(content=settings_obj.model_dump(exclude_none=False, exclude_defaults=False, exclude_unset=False))


@router.post("/ui-settings")
def save_ui_settings_endpoint(payload: UISettings):
    try:
        # Merge defaults + current + incoming payload to avoid losing fields
        defaults = _default_ui_settings().model_dump(exclude_none=False, exclude_defaults=False, exclude_unset=False)
        current = _read_settings(include_env=False).model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        incoming = payload.model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        merged = {**defaults, **current, **incoming}
        for nested_key in ("plex", "tmdb", "tvdb", "fanart", "imageQuality", "performance"):
            merged[nested_key] = {
                **defaults.get(nested_key, {}),
                **current.get(nested_key, {}),
                **incoming.get(nested_key, {}),
            }

        merged = _normalize_plex_payload(merged)
        _apply_runtime_settings(merged)

        # Save to database (ensure DB exists)
        try:
            db.save_ui_settings(merged)
        except Exception as db_err:
            if "no such table: settings" in str(db_err):
                logger.warning("[DB] Settings table missing; initializing database before save...")
                db.init_database()
                db.save_ui_settings(merged)
            else:
                raise
        logger.info("[UI_SETTINGS] Saved to database")

        # Delete JSON files after successful migration
        for json_file in [_settings_file, _legacy_settings_file]:
            if json_file.exists():
                try:
                    backup_path = json_file.with_suffix(".json.migrated")
                    json_file.rename(backup_path)
                    logger.info(f"[UI_SETTINGS] Migrated {json_file} to database, backed up as .migrated")
                except Exception as e:
                    logger.warning(f"[UI_SETTINGS] Could not remove {json_file}: {e}")

        # Return merged view including environment overrides so UI reflects runtime values
        merged_with_env = merged.copy()
        env_overrides = _env_overrides()
        for nested_key, nested_values in env_overrides.items():
            merged_with_env[nested_key] = {**merged_with_env.get(nested_key, {}), **nested_values}
        return merged_with_env
    except Exception as e:
        logger.error(f"[UI_SETTINGS] Failed to save settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")
