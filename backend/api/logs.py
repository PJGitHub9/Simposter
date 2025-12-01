import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..config import settings

router = APIRouter()

class LogConfig(BaseModel):
    level: str = "INFO"
    maxSize: int = 20  # MB
    maxBackups: int = 7

_log_config_file = Path(settings.SETTINGS_DIR) / "log_config.json"
_legacy_log_config_file = Path(settings.CONFIG_DIR) / "log_config.json"

def _read_log_config() -> LogConfig:
    """Read log configuration from disk, creating with defaults if missing."""
    try:
        if not _log_config_file.exists() and _legacy_log_config_file.exists():
            try:
                _log_config_file.parent.mkdir(parents=True, exist_ok=True)
                _legacy_log_config_file.replace(_log_config_file)
            except OSError:
                _log_config_file.write_text(_legacy_log_config_file.read_text(encoding="utf-8"), encoding="utf-8")

        if not _log_config_file.exists():
            defaults = LogConfig().model_dump()
            _log_config_file.parent.mkdir(parents=True, exist_ok=True)
            _log_config_file.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
            return LogConfig(**defaults)

        data = json.loads(_log_config_file.read_text(encoding="utf-8"))
        return LogConfig(**data)
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
        _log_config_file.parent.mkdir(parents=True, exist_ok=True)
        _log_config_file.write_text(json.dumps(payload.model_dump(), indent=2), encoding="utf-8")
        return payload.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save log config: {e}")
