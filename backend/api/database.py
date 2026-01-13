"""
API endpoints for database backup and restore operations.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from .. import database as db
from ..config import logger
import sqlite3
from pathlib import Path

router = APIRouter()


class DatabaseImportRequest(BaseModel):
    """Request model for database import."""
    settings: Dict[str, Any]
    presets: list
    templates: list


@router.get("/database/export")
def api_export_database():
    """
    Export the complete database as JSON.

    Returns:
        JSON object containing all settings, presets, and templates
    """
    try:
        with db.get_db() as conn:
            cursor = conn.cursor()

            # Export settings
            cursor.execute("SELECT key, value, category FROM settings")
            settings_rows = cursor.fetchall()
            settings = {
                row["key"]: {
                    "value": row["value"],
                    "category": row["category"]
                }
                for row in settings_rows
            }

            # Export presets
            cursor.execute("SELECT id, name, template_options, is_default FROM presets")
            presets_rows = cursor.fetchall()
            presets = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "template_options": row["template_options"],
                    "is_default": bool(row["is_default"])
                }
                for row in presets_rows
            ]

            # Export templates (if table exists)
            templates = []
            try:
                cursor.execute("SELECT id, name, type, path, created_at FROM templates")
                templates_rows = cursor.fetchall()
                templates = [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "type": row["type"],
                        "path": row["path"],
                        "created_at": row["created_at"]
                    }
                    for row in templates_rows
                ]
            except sqlite3.OperationalError:
                # Templates table might not exist in older versions
                logger.info("[DB EXPORT] Templates table not found, skipping")

            return {
                "version": "1.0",
                "settings": settings,
                "presets": presets,
                "templates": templates
            }

    except Exception as e:
        logger.error(f"[DB EXPORT] Failed to export database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export database: {e}")


@router.post("/database/import")
def api_import_database(data: Dict[str, Any]):
    """
    Import and restore database from JSON backup.

    WARNING: This completely replaces the current database.
    """
    try:
        # Validate input structure
        if "settings" not in data or "presets" not in data:
            raise HTTPException(status_code=400, detail="Invalid backup format: missing required fields")

        with db.get_db() as conn:
            cursor = conn.cursor()

            # Clear existing data
            cursor.execute("DELETE FROM settings WHERE key != 'app.version'")
            cursor.execute("DELETE FROM presets")
            try:
                cursor.execute("DELETE FROM templates")
            except sqlite3.OperationalError:
                # Templates table might not exist
                pass

            # Import settings
            for key, setting_data in data["settings"].items():
                # Skip app.version as it should remain current
                if key == "app.version":
                    continue

                value = setting_data.get("value") if isinstance(setting_data, dict) else setting_data
                category = setting_data.get("category", "app") if isinstance(setting_data, dict) else "app"

                cursor.execute("""
                    INSERT INTO settings (key, value, category, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        category = excluded.category,
                        updated_at = CURRENT_TIMESTAMP
                """, (key, value, category))

            # Import presets
            for preset in data["presets"]:
                cursor.execute("""
                    INSERT INTO presets (id, name, template_options, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        template_options = excluded.template_options,
                        is_default = excluded.is_default,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    preset["id"],
                    preset["name"],
                    preset["template_options"],
                    1 if preset.get("is_default", False) else 0
                ))

            # Import templates if present
            if "templates" in data:
                for template in data["templates"]:
                    try:
                        cursor.execute("""
                            INSERT INTO templates (id, name, type, path, created_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                name = excluded.name,
                                type = excluded.type,
                                path = excluded.path
                        """, (
                            template["id"],
                            template["name"],
                            template["type"],
                            template["path"],
                            template.get("created_at", "CURRENT_TIMESTAMP")
                        ))
                    except sqlite3.OperationalError:
                        # Templates table might not exist
                        logger.warning("[DB IMPORT] Templates table not found, skipping template import")
                        break

            conn.commit()
            logger.info("[DB IMPORT] Database imported successfully")

            return {
                "status": "success",
                "message": "Database restored successfully"
            }

    except Exception as e:
        logger.error(f"[DB IMPORT] Failed to import database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to import database: {e}")
