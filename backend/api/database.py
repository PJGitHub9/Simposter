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
from ..config import logger, settings, SECRET_FIELD_PATHS, same_origin

router = APIRouter()

# Dotted DB keys ("section.field") that hold credentials — see database.save_ui_settings
# for how the nested UISettings shape gets flattened into these keys.
_SECRET_DB_KEYS = {f"{section}.{field}" for section, field in SECRET_FIELD_PATHS}
_MEDIA_SERVER_SECRET_FIELDS = ("token", "apiKey")
_BACKUP_FORMAT = "simposter-db-backup"
_BACKUP_VERSION = 2

# Saved credentials that belong to one server address: restoring a backup that
# points the address somewhere else must not carry this install's key over.
_HOST_BOUND_SECRETS = {
    "plex.token": "plex.url",
    "floppy.token": "floppy.url",
    "maintainerr.apiKey": "maintainerr.url",
}


def _setting_text(value) -> str:
    """A settings-table value as plain text (strings may be stored JSON-quoted)."""
    if value is None:
        return ""
    s = str(value)
    if s.startswith('"'):
        try:
            return str(json.loads(s))
        except ValueError:
            pass
    return s


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
        # Only hand over a stored credential when the server address is the same;
        # a backup pointing the same id at another server must not get our key.
        if not same_origin(s.get("url"), existing.get("url")):
            continue
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
                    if key in ("mediaServers", "arrInstances") and value:
                        value = _strip_media_server_secrets(value)
                settings_out[key] = {"value": value, "category": row["category"]}

            cursor.execute("PRAGMA table_info(presets)")
            preset_cols = {r["name"] for r in cursor.fetchall()}
            cols = [c for c in ("id", "template_id", "name", "options_json", "season_options_json", "overlay_config_id") if c in preset_cols]
            cursor.execute(f"SELECT {', '.join(cols)} FROM presets")
            presets = [{c: row[c] for c in cols} for row in cursor.fetchall()]

        overlays = build_bundle(None, all_assets=True)

        pinned = _export_pinned_posters()
        return {
            "format": _BACKUP_FORMAT,
            "version": _BACKUP_VERSION,
            "app_version": db.get_app_version(),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "secrets_included": include_secrets,
            "settings": settings_out,
            "presets": presets,
            "overlays": overlays,
            "poster_api_pinned": pinned,
        }
    except Exception as e:
        logger.error(f"[DB EXPORT] Failed to export database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export database: {e}")


def _export_pinned_posters() -> list:
    """Pinned Poster API posters (hand-made, not regenerable) as base64 JPEG."""
    import base64
    out = []
    try:
        rows, _ = db.poster_api_cache_list("", None, "pinned", 0, 100000)
    except Exception as e:
        logger.warning(f"[DB EXPORT] Couldn't list pinned Poster API posters: {e}")
        return out
    for r in rows:
        try:
            data = Path(r["file_path"]).read_bytes()
        except OSError:
            continue
        out.append({
            "media_type": r["media_type"], "tmdb_id": r["tmdb_id"], "season_index": r["season_index"],
            "title": r.get("title") or "", "image_b64": base64.b64encode(data).decode("ascii"),
        })
    return out


def _import_pinned_posters(entries) -> int:
    """Recreate pinned posters; malformed entries are skipped, never fatal."""
    import base64
    from .. import poster_api_store as store
    n = 0
    if not isinstance(entries, list):
        return 0
    for e in entries:
        try:
            media_type = e["media_type"]
            if media_type not in ("movie", "tv"):
                continue
            season = int(e.get("season_index", -1))
            img = base64.b64decode(e["image_b64"], validate=True)
            if not img:
                continue
            key = store.CacheKey(media_type, int(e["tmdb_id"]), None if season < 0 else season, "")
            store.put_entry(key, "pinned", img, e.get("title") or "", "")
            n += 1
        except Exception as err:
            logger.warning(f"[DB IMPORT] Skipped a malformed pinned Poster API entry: {err}")
    return n


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
            # Stored Radarr/Sonarr tags belong to the connections being replaced.
            cursor.execute("DELETE FROM arr_tags")
            cursor.execute("DELETE FROM arr_tag_sync")
            restored_keys = set()
            restored_values = {}
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
                if key in ("mediaServers", "arrInstances") and value and current.get(key):
                    value = _fill_media_server_secrets(value, current[key])
                cursor.execute(
                    "INSERT INTO settings (key, value, category, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (key, value, category),
                )
                restored_keys.add(key)
                restored_values[key] = value

            # Credentials left out of the backup: keep this install's own.
            for key in _SECRET_DB_KEYS:
                if key not in restored_keys and current.get(key):
                    url_key = _HOST_BOUND_SECRETS.get(key)
                    if url_key and not same_origin(_setting_text(restored_values.get(url_key)),
                                                   _setting_text(current.get(url_key))):
                        logger.info(f"[DB IMPORT] Not keeping {key}: the backup uses a different address")
                        continue
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

        pinned_restored = _import_pinned_posters(data.get("poster_api_pinned"))
        if pinned_restored:
            logger.info(f"[DB IMPORT] Restored {pinned_restored} pinned Poster API posters")

        overlays = data.get("overlays")
        if isinstance(overlays, dict):
            from ..overlay_bundle import restore_bundle
            restore_bundle(overlays, replace=True)

        # The cached overlay effect layers belong to the old presets; they regenerate on next render.
        shutil.rmtree(Path(settings.CONFIG_DIR) / "overlays", ignore_errors=True)
        # Rebuild them for the restored presets in the background.
        import threading
        from ..overlay_cache import warm_all
        threading.Thread(target=warm_all, daemon=True, name="overlay-cache-warm").start()

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
