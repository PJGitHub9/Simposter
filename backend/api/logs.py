import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import database as db
from ..config import settings, logger

router = APIRouter()

class LogConfig(BaseModel):
    level: str = "INFO"
    maxSize: int = 20  # MB
    maxBackups: int = 7

_log_config_file = Path(settings.SETTINGS_DIR) / "log_config.json"
_legacy_log_config_file = Path(settings.CONFIG_DIR) / "log_config.json"


def _default_log_config() -> LogConfig:
    """Default log configuration."""
    return LogConfig()


def _load_legacy_log_config() -> Optional[LogConfig]:
    """Load log config from legacy JSON files (settings/ or config/), migrating if found."""
    if not _log_config_file.exists() and _legacy_log_config_file.exists():
        try:
            _log_config_file.parent.mkdir(parents=True, exist_ok=True)
            _legacy_log_config_file.replace(_log_config_file)
        except OSError:
            _log_config_file.write_text(_legacy_log_config_file.read_text(encoding="utf-8"), encoding="utf-8")

    if not _log_config_file.exists():
        return None

    data = json.loads(_log_config_file.read_text(encoding="utf-8"))
    return LogConfig(**data)


def _read_log_config() -> LogConfig:
    """Read log configuration from database, migrating legacy files if needed."""
    try:
        # Prefer database
        db_config = db.get_log_config()
        if db_config:
            return LogConfig(**db_config)

        # Migrate from legacy file, if present
        legacy = _load_legacy_log_config()
        if legacy:
            db.save_log_config(legacy.model_dump())
            try:
                backup_path = _log_config_file.with_suffix(".json.migrated")
                _log_config_file.rename(backup_path)
                logger.info(f"[LOGS] Migrated log_config.json to database, backed up as {backup_path.name}")
            except Exception as rename_err:
                logger.warning(f"[LOGS] Saved legacy log_config.json to DB but could not rename file: {rename_err}")
            return legacy

        # Nothing stored - seed defaults into DB
        defaults = _default_log_config()
        db.save_log_config(defaults.model_dump())
        return defaults
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log config: {e}")

@router.get("/logs")
def api_logs():
    try:
        with open(settings.LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except:
        return {"text": ""}

    return {"text": "".join(lines[-500:])}

@router.get("/log-config")
def get_log_config():
    config = _read_log_config()
    return config.model_dump()

@router.post("/log-config")
def save_log_config(payload: LogConfig):
    try:
        db.save_log_config(payload.model_dump())
        return payload.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save log config: {e}")
