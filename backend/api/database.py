"""
API endpoints for database backup and restore operations.

The backup is one JSON file: settings, presets, overlay configs and the
overlay asset files (base64). Caches, history and the retry queue are left
out -- a library scan rebuilds the caches.
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from .. import database as db
from ..config import logger, settings, SECRET_FIELD_PATHS

router = APIRouter()

# Dotted DB keys ("section.field") that hold credentials — see database.save_ui_settings
# for how the nested UISettings shape gets flattened into these keys.
_SECRET_DB_KEYS = {f"{section}.{field}" for section, field in SECRET_FIELD_PATHS}
_MEDIA_SERVER_SECRET_FIELDS = ("token", "apiKey")
_BACKUP_FORMAT = "simposter-db-backup"
_BACKUP_VERSION = 2


def _strip_media_server_secrets(value: str) -> str:
    try:
        servers = json.loads(value)
    except Exception:
        return value
    if not isinstance(servers, list):
        return value
    for s in servers:
        if isinstance(s, dict):
            for f in _MEDIA_SERVER_SECRET_FIELDS:
                s.pop(f, None)
    return json.dumps(servers)


def _fill_media_server_secrets(value: str, current_value: str) -> str:
    """Give restored media servers the credentials this install already has
    (matched by id) when the backup was exported without them."""
    try:
        servers = json.loads(value)
        current = json.loads(current_value) if current_value else []
    except Exception:
        return value
    if not isinstance(servers, list) or not isinstance(current, list):
        return value
    by_id = {s.get("id"): s for s in current if isinstance(s, dict)}
    for s in servers:
        if not isinstance(s, dict):
            continue
        existing = by_id.get(s.get("id")) or {}
        for f in _MEDIA_SERVER_SECRET_FIELDS:
            if not s.get(f) and existing.get(f):
                s[f] = existing[f]
    return json.dumps(servers)


@router.get("/database/export")
def api_export_database(
    include_secrets: bool = Query(
        False,
        description="Include Plex token / TMDb / TVDB / Fanart API keys / webhook secret / media server "
                     "credentials in the export. Defaults to False so a bare request never leaks credentials; "
                     "the Settings UI passes true explicitly when the user opts in."
    )
):
    """Export settings, presets, overlay configs and overlay assets as JSON."""
    try:
        from ..overlay_bundle import build_bundle

        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value, category FROM settings")
            settings_out: Dict[str, Any] = {}
            for row in cursor.fetchall():
                key, value = row["key"], row["value"]
                if not include_secrets:
                    if key in _SECRET_DB_KEYS:
                        continue
                    if key == "mediaServers" and value:
                        value = _strip_media_server_secrets(value)
                settings_out[key] = {"value": value, "category": row["category"]}

            cursor.execute("PRAGMA table_info(presets)")
            preset_cols = {r["name"] for r in cursor.fetchall()}
            cols = [c for c in ("id", "template_id", "name", "options_json", "season_options_json", "overlay_config_id") if c in preset_cols]
            cursor.execute(f"SELECT {', '.join(cols)} FROM presets")
            presets = [{c: row[c] for c in cols} for row in cursor.fetchall()]

        overlays = build_bundle(None, all_assets=True)

        return {
            "format": _BACKUP_FORMAT,
            "version": _BACKUP_VERSION,
            "app_version": db.get_app_version(),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "secrets_included": include_secrets,
            "settings": settings_out,
            "presets": presets,
            "overlays": overlays,
        }
    except Exception as e:
        logger.error(f"[DB EXPORT] Failed to export database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export database: {e}")


def _preset_row(p: Dict[str, Any]):
    """(id, template_id, name, options_json, season_options_json, overlay_config_id) or None."""
    pid = p.get("id")
    if not pid:
        return None
    if "options_json" in p:
        options_json = p.get("options_json") or "{}"
        season_json = p.get("season_options_json") or "{}"
    elif isinstance(p.get("options"), dict):
        options_json = json.dumps(p["options"])
        season_json = json.dumps(p.get("season_options") or {})
    else:
        return None
    return (
        pid,
        p.get("template_id") or "uniformlogo",
        p.get("name") or pid,
        options_json if isinstance(options_json, str) else json.dumps(options_json),
        season_json if isinstance(season_json, str) else json.dumps(season_json),
        p.get("overlay_config_id"),
    )


@router.post("/database/import")
def api_import_database(data: Dict[str, Any]):
    """
    Restore from a backup made by /database/export.

    Replaces settings, presets and overlay configs/assets. Credentials missing
    from the backup (exported without them) keep their current values.
    """
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict) or not isinstance(data.get("presets"), list):
        raise HTTPException(status_code=400, detail="This isn't a Simposter database backup (missing settings or presets).")

    preset_rows = [r for r in (_preset_row(p) for p in data["presets"] if isinstance(p, dict)) if r]
    if data["presets"] and not preset_rows:
        raise HTTPException(status_code=400, detail="The backup's presets are in an unknown format; nothing was changed.")

    try:
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            current = {row["key"]: row["value"] for row in cursor.fetchall()}

            cursor.execute("DELETE FROM settings WHERE key != 'app.version'")
            restored_keys = set()
            for key, setting_data in data["settings"].items():
                if key == "app.version":
                    continue
                if isinstance(setting_data, dict):
                    value = setting_data.get("value")
                    category = setting_data.get("category")
                else:
                    value, category = setting_data, None
                if value is not None and not isinstance(value, str):
                    value = json.dumps(value)
                if key == "mediaServers" and value and current.get("mediaServers"):
                    value = _fill_media_server_secrets(value, current["mediaServers"])
                cursor.execute(
                    "INSERT INTO settings (key, value, category, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (key, value, category),
                )
                restored_keys.add(key)

            # Credentials left out of the backup: keep this install's own.
            for key in _SECRET_DB_KEYS:
                if key not in restored_keys and current.get(key):
                    cursor.execute(
                        "INSERT INTO settings (key, value, category, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                        (key, current[key], key.split(".", 1)[0]),
                    )

            cursor.execute("DELETE FROM presets")
            cursor.executemany(
                """INSERT INTO presets (id, template_id, name, options_json, season_options_json, overlay_config_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                preset_rows,
            )

        overlays = data.get("overlays")
        if isinstance(overlays, dict):
            from ..overlay_bundle import restore_bundle
            restore_bundle(overlays, replace=True)

        # The cached overlay effect layers belong to the old presets; they regenerate on next render.
        shutil.rmtree(Path(settings.CONFIG_DIR) / "overlays", ignore_errors=True)

        # Apply the restored settings now instead of waiting for a restart.
        try:
            from .ui_settings import _read_settings
            _read_settings()
        except Exception as apply_err:
            logger.warning(f"[DB IMPORT] Restored, but applying settings failed: {apply_err}")
        try:
            from ..scheduler import shutdown_scheduler, init_scheduler
            shutdown_scheduler()
            init_scheduler()
        except Exception as sched_err:
            logger.warning(f"[DB IMPORT] Restored, but restarting the scheduler failed: {sched_err}")

        logger.info(
            "[DB IMPORT] Restored %d settings, %d presets, %d overlay configs, %d overlay assets",
            len(restored_keys), len(preset_rows),
            len((overlays or {}).get("configs") or []) if isinstance(overlays, dict) else 0,
            len((overlays or {}).get("assets") or []) if isinstance(overlays, dict) else 0,
        )
        return {
            "status": "success",
            "message": "Database restored successfully",
            "settings": len(restored_keys),
            "presets": len(preset_rows),
            "overlay_configs": len(overlays.get("configs") or []) if isinstance(overlays, dict) else 0,
            "overlay_assets": len(overlays.get("assets") or []) if isinstance(overlays, dict) else 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DB IMPORT] Failed to import database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to import database: {e}")
