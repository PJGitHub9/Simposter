import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings, logger
from ..schemas import UISettings
from .. import database as db

router = APIRouter()

# Legacy file paths for migration check
_settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
_legacy_settings_file = Path(settings.CONFIG_DIR) / "ui_settings.json"


def _default_ui_settings() -> UISettings:
    """Defaults seeded from environment to make docker-compose setup easier."""
    return UISettings(
        plex={
            "url": settings.PLEX_URL,
            "token": settings.PLEX_TOKEN,
            "movieLibraryName": settings.PLEX_MOVIE_LIBRARY_NAME,
        },
        tmdb={"apiKey": getattr(settings, "TMDB_API_KEY", "")},
        tvdb={"apiKey": "", "comingSoon": True},
        saveBatchInSubfolder=False,
    )


def _env_overrides() -> dict:
    """Use explicit environment variables to override stored UI settings."""
    out: dict = {}
    plex_url = os.getenv("PLEX_URL")
    plex_token = os.getenv("PLEX_TOKEN")
    plex_lib = os.getenv("PLEX_MOVIE_LIBRARY_NAME")
    tmdb_key = os.getenv("TMDB_API_KEY")

    if plex_url:
        out.setdefault("plex", {})["url"] = plex_url
    if plex_token:
        out.setdefault("plex", {})["token"] = plex_token
    if plex_lib:
        out.setdefault("plex", {})["movieLibraryName"] = plex_lib
    if tmdb_key:
        out.setdefault("tmdb", {})["apiKey"] = tmdb_key
    return out


def _read_settings(include_env: bool = True) -> UISettings:
    """
    Read settings from database, creating defaults if missing.
    Falls back to JSON files for backward compatibility during migration.
    """
    try:
        # Try reading from database first
        data = db.get_ui_settings()

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

        # Merge with defaults so newly added fields are included
        defaults = _default_ui_settings().model_dump(exclude_none=False, exclude_defaults=False)
        merged = {**defaults, **data}
        for nested_key in ("plex", "tmdb", "tvdb", "imageQuality", "performance"):
            merged[nested_key] = {**defaults.get(nested_key, {}), **data.get(nested_key, {})}

        # Apply environment overrides on top of merged values (do not persist them)
        if include_env:
            env_overrides = _env_overrides()
            if env_overrides:
                for nested_key, nested_values in env_overrides.items():
                    merged[nested_key] = {**merged.get(nested_key, {}), **nested_values}

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
        for nested_key in ("plex", "tmdb", "tvdb", "imageQuality", "performance"):
            merged[nested_key] = {
                **defaults.get(nested_key, {}),
                **current.get(nested_key, {}),
                **incoming.get(nested_key, {}),
            }

        # Save to database
        db.save_ui_settings(merged)
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
