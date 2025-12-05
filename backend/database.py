# backend/database.py
"""SQLite database for storing application settings and presets."""
import json
import logging
import sqlite3
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

# Get logger without importing from config to avoid circular imports
logger = logging.getLogger("simposter")

# Determine DB path without importing settings
def _get_db_path():
    """Get database path without circular import."""
    settings_dir = os.environ.get("SETTINGS_DIR")
    if not settings_dir:
        # Get the repo root (parent of backend/)
        backend_dir = Path(__file__).parent
        repo_root = backend_dir.parent

        config_dir = os.environ.get("CONFIG_DIR")
        if config_dir:
            config_path = Path(config_dir)
            # Make absolute if relative
            if not config_path.is_absolute():
                config_path = repo_root / config_path
        else:
            config_path = repo_root / "config"

        settings_dir = str(config_path / "settings")

    return Path(settings_dir) / "simposter.db"

DB_PATH = _get_db_path()


def init_database():
    """Initialize the database with required tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # UI Settings table - stores single row of JSON settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ui_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            settings_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Presets table - stores preset configurations per template
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS presets (
            id TEXT PRIMARY KEY,
            template_id TEXT NOT NULL,
            name TEXT NOT NULL,
            options_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(template_id, id)
        )
    """)

    # Create indexes for better query performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_presets_template
        ON presets(template_id)
    """)

    conn.commit()
    conn.close()
    logger.info(f"[DB] Initialized database at {DB_PATH}")


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================
#  UI Settings Operations
# ============================================

def get_ui_settings() -> Optional[Dict[str, Any]]:
    """Get UI settings from database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT settings_json FROM ui_settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            return json.loads(row["settings_json"])
        return None


def save_ui_settings(settings_data: Dict[str, Any]) -> None:
    """Save UI settings to database."""
    with get_db() as conn:
        cursor = conn.cursor()
        settings_json = json.dumps(settings_data, indent=2)

        cursor.execute("""
            INSERT INTO ui_settings (id, settings_json, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                settings_json = excluded.settings_json,
                updated_at = CURRENT_TIMESTAMP
        """, (settings_json,))

    logger.debug("[DB] Saved UI settings")


# ============================================
#  Presets Operations
# ============================================

def get_all_presets() -> Dict[str, Dict[str, Any]]:
    """
    Get all presets organized by template_id.

    Returns:
        {
            "template_id": {
                "presets": [
                    {"id": "preset1", "name": "Preset 1", "options": {...}},
                    ...
                ]
            }
        }
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, template_id, name, options_json FROM presets")
        rows = cursor.fetchall()

    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        template_id = row["template_id"]
        if template_id not in result:
            result[template_id] = {"presets": []}

        result[template_id]["presets"].append({
            "id": row["id"],
            "name": row["name"],
            "options": json.loads(row["options_json"])
        })

    return result


def get_preset(template_id: str, preset_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific preset by template_id and preset_id."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, options_json FROM presets
            WHERE template_id = ? AND id = ?
        """, (template_id, preset_id))
        row = cursor.fetchone()

    if row:
        return {
            "id": row["id"],
            "name": row["name"],
            "options": json.loads(row["options_json"])
        }
    return None


def save_preset(template_id: str, preset_id: str, name: str, options: Dict[str, Any]) -> None:
    """Save or update a preset."""
    with get_db() as conn:
        cursor = conn.cursor()
        options_json = json.dumps(options)

        cursor.execute("""
            INSERT INTO presets (id, template_id, name, options_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                options_json = excluded.options_json,
                updated_at = CURRENT_TIMESTAMP
        """, (preset_id, template_id, name, options_json))

    logger.debug(f"[DB] Saved preset {preset_id} for template {template_id}")


def delete_preset(template_id: str, preset_id: str) -> bool:
    """Delete a preset. Returns True if deleted, False if not found."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM presets WHERE template_id = ? AND id = ?
        """, (template_id, preset_id))
        deleted = cursor.rowcount > 0

    if deleted:
        logger.info(f"[DB] Deleted preset {preset_id} from template {template_id}")
    return deleted


def get_presets_for_template(template_id: str) -> List[Dict[str, Any]]:
    """Get all presets for a specific template."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, options_json FROM presets
            WHERE template_id = ?
            ORDER BY created_at ASC
        """, (template_id,))
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "options": json.loads(row["options_json"])
        }
        for row in rows
    ]


# Initialize database on module import
init_database()
