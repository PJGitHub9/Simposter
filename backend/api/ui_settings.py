import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings
from ..schemas import UISettings

router = APIRouter()

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
    Read settings from disk, creating the file with defaults if missing.
    Mirrors the simple JSON read/write pattern we use for presets.
    """
    try:
        if not _settings_file.exists() and _legacy_settings_file.exists():
            try:
                _settings_file.parent.mkdir(parents=True, exist_ok=True)
                _legacy_settings_file.replace(_settings_file)
            except OSError:
                data = json.loads(_legacy_settings_file.read_text(encoding="utf-8"))
                _settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        if not _settings_file.exists():
            defaults = _default_ui_settings().model_dump(
                exclude_none=False, exclude_defaults=False, exclude_unset=False
            )
            _settings_file.parent.mkdir(parents=True, exist_ok=True)
            _settings_file.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
            return UISettings(**defaults)

        data = json.loads(_settings_file.read_text(encoding="utf-8"))
        # Merge with defaults so newly added fields are included (nested merge for settings groups)
        defaults = _default_ui_settings().model_dump(exclude_none=False, exclude_defaults=False)
        merged_file = {**defaults, **data}
        for nested_key in ("plex", "tmdb", "tvdb"):
            merged_file[nested_key] = {**defaults.get(nested_key, {}), **data.get(nested_key, {})}

        if merged_file != data:
            _settings_file.write_text(json.dumps(merged_file, indent=2), encoding="utf-8")

        # Apply environment overrides on top of merged file values (do not persist them)
        if include_env:
            env_overrides = _env_overrides()
            if env_overrides:
                for nested_key, nested_values in env_overrides.items():
                    merged_file[nested_key] = {**merged_file.get(nested_key, {}), **nested_values}

        return UISettings(**merged_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {e}")


@router.get("/ui-settings")
def get_ui_settings():
    settings_obj = _read_settings()
    return JSONResponse(content=settings_obj.model_dump(exclude_none=False, exclude_defaults=False, exclude_unset=False))


@router.post("/ui-settings")
def save_ui_settings(payload: UISettings):
    try:
        _settings_file.parent.mkdir(parents=True, exist_ok=True)
        # Merge defaults + current file + incoming payload to avoid losing fields
        defaults = _default_ui_settings().model_dump(exclude_none=False, exclude_defaults=False, exclude_unset=False)
        current = _read_settings(include_env=False).model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        incoming = payload.model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        merged = {**defaults, **current, **incoming}
        for nested_key in ("plex", "tmdb", "tvdb"):
            merged[nested_key] = {
                **defaults.get(nested_key, {}),
                **current.get(nested_key, {}),
                **incoming.get(nested_key, {}),
            }

        _settings_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        # Return merged view including environment overrides so UI reflects runtime values
        merged_with_env = merged.copy()
        env_overrides = _env_overrides()
        for nested_key, nested_values in env_overrides.items():
            merged_with_env[nested_key] = {**merged_with_env.get(nested_key, {}), **nested_values}
        return merged_with_env
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")
