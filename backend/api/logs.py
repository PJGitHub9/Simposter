import json
import os
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import APIRouter, HTTPException, Query
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

def _list_log_files() -> List[Dict[str, str]]:
    log_dir = Path(settings.LOG_DIR)
    files = []
    if log_dir.exists():
        for f in sorted(log_dir.glob("*.log"), reverse=True):
            try:
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "current": str(f.resolve()) == str(Path(settings.LOG_FILE).resolve()),
                })
            except OSError:
                continue
    return files


def _resolve_log_path(date: Optional[str]) -> Path:
    """
    Resolve a log file path by date string YYYYMMDD.
    If date is None, return current log file.
    """
    if not date:
        return Path(settings.LOG_FILE)
    log_dir = Path(settings.LOG_DIR)
    candidate = log_dir / f"{Path(settings.LOG_FILE).stem}-{date}.log"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Log file for {date} not found")


@router.get("/log-files")
def list_log_files():
    return {"files": _list_log_files()}


@router.get("/logs")
def get_logs(date: Optional[str] = Query(default=None, description="Log date YYYYMMDD"), tail: int = 500):
    try:
        # Build list of candidate files (requested date first, then newest others)
        candidates: List[Path] = []
        try:
            candidates.append(_resolve_log_path(date))
        except FileNotFoundError:
            pass

        if date is None:
            # Add other logs (newest first) to fall back if current is empty
            for entry in _list_log_files():
                p = Path(settings.LOG_DIR) / entry["name"]
                if candidates and p.resolve() == candidates[0].resolve():
                    continue
                candidates.append(p)

        lines: List[str] = []
        used_path: Optional[Path] = None
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                used_path = candidate
                if lines:
                    break
            except Exception:
                continue

        if used_path is None:
            return {"text": "", "date": date or "current"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {e}")

    return {
        "text": "".join(lines[-tail:]),
        "date": date or "current",
        "path": str(used_path),
        "lines": len(lines),
    }


@router.post("/logs/clear")
def clear_logs():
    try:
        # Empty the current log file by truncating it
        current_log = Path(settings.LOG_FILE)
        if current_log.exists():
            current_log.write_text("", encoding="utf-8")

        # Remove rotated/backup log files (not the current one)
        removed = 0
        for entry in _list_log_files():
            if not entry.get("current", False):
                fpath = Path(settings.LOG_DIR) / entry["name"]
                try:
                    fpath.unlink()
                    removed += 1
                except OSError:
                    pass

        logger.info("[LOGS] Cleared current log and removed %d backup files", removed)
        return {"status": "ok", "removed": removed, "cleared_current": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear logs: {e}")

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
