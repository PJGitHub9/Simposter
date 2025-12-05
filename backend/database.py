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

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check if old ui_settings table exists (needs migration)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ui_settings'")
        has_old_table = cursor.fetchone() is not None

        # Check if new settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        has_new_table = cursor.fetchone() is not None

        if has_old_table and not has_new_table:
            logger.info("[DB] Migrating from old ui_settings table to normalized settings table...")
            # Get old settings
            cursor.execute("SELECT settings_json FROM ui_settings WHERE id = 1")
            row = cursor.fetchone()
            if row:
                settings_data = json.loads(row["settings_json"])

                # Create new settings table
                cursor.execute("""
                    CREATE TABLE settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        category TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migrate data
                for key, value in settings_data.items():
                    if isinstance(value, dict):
                        category = key
                        for sub_key, sub_value in value.items():
                            full_key = f"{category}.{sub_key}"
                            if isinstance(sub_value, (dict, list)):
                                str_value = json.dumps(sub_value)
                            elif isinstance(sub_value, bool):
                                str_value = 'true' if sub_value else 'false'
                            else:
                                str_value = str(sub_value)
                            cursor.execute("""
                                INSERT INTO settings (key, value, category, updated_at)
                                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                            """, (full_key, str_value, category))
                    else:
                        if isinstance(value, (dict, list)):
                            str_value = json.dumps(value)
                        elif isinstance(value, bool):
                            str_value = 'true' if value else 'false'
                        else:
                            str_value = str(value)
                        cursor.execute("""
                            INSERT INTO settings (key, value, category, updated_at)
                            VALUES (?, ?, NULL, CURRENT_TIMESTAMP)
                        """, (key, str_value))

                # Drop old table
                cursor.execute("DROP TABLE ui_settings")
                logger.info("[DB] Migration complete - dropped old ui_settings table")

        # Settings table - normalized key-value storage
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                category TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index on category for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_settings_category
            ON settings(category)
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
        logger.info(f"[DB] Initialized database at {DB_PATH}")
    except Exception as e:
        logger.error(f"[DB] Initialization/migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


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
#  Settings Operations
# ============================================

def get_setting(key: str) -> Optional[str]:
    """Get a single setting value by key."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            return row["value"]
        return None


def set_setting(key: str, value: str, category: Optional[str] = None) -> None:
    """Set a single setting value."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value, category, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                category = excluded.category,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value, category))
    logger.debug(f"[DB] Set setting {key}")


def get_settings_by_category(category: str) -> Dict[str, str]:
    """Get all settings in a category."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings WHERE category = ?", (category,))
        rows = cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}


def get_all_settings() -> Dict[str, str]:
    """Get all settings as a flat key-value dict."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}


def get_ui_settings() -> Optional[Dict[str, Any]]:
    """
    Get UI settings organized in the legacy JSON structure.
    This maintains compatibility with existing code.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, category FROM settings")
        rows = cursor.fetchall()

    if not rows:
        return None

    # Build nested structure
    result: Dict[str, Any] = {}

    for row in rows:
        key = row["key"]
        value = row["value"]
        category = row["category"]

        # Parse JSON values if they look like JSON
        try:
            if value and (value.startswith('{') or value.startswith('[')):
                parsed_value = json.loads(value)
            elif value and value.isdigit():
                parsed_value = int(value)
            elif value in ('true', 'false'):
                parsed_value = value == 'true'
            else:
                parsed_value = value
        except (json.JSONDecodeError, ValueError):
            parsed_value = value

        if category:
            # Nested setting (e.g., category="plex", key="url")
            if category not in result:
                result[category] = {}
            # Remove category prefix from key if present
            setting_key = key.replace(f"{category}.", "", 1) if key.startswith(f"{category}.") else key
            result[category][setting_key] = parsed_value
        else:
            # Top-level setting
            result[key] = parsed_value

    return result


def save_ui_settings(settings_data: Dict[str, Any]) -> None:
    """
    Save UI settings from the legacy JSON structure.
    Converts nested structure to flat key-value pairs.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Clear existing settings
        cursor.execute("DELETE FROM settings")

        # Flatten and save
        for key, value in settings_data.items():
            if isinstance(value, dict):
                # Nested object - store each sub-key with category
                category = key
                for sub_key, sub_value in value.items():
                    full_key = f"{category}.{sub_key}"
                    if isinstance(sub_value, (dict, list)):
                        str_value = json.dumps(sub_value)
                    elif isinstance(sub_value, bool):
                        str_value = 'true' if sub_value else 'false'
                    else:
                        str_value = str(sub_value)

                    cursor.execute("""
                        INSERT INTO settings (key, value, category, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """, (full_key, str_value, category))
            else:
                # Top-level value
                if isinstance(value, (dict, list)):
                    str_value = json.dumps(value)
                elif isinstance(value, bool):
                    str_value = 'true' if value else 'false'
                else:
                    str_value = str(value)

                cursor.execute("""
                    INSERT INTO settings (key, value, category, updated_at)
                    VALUES (?, ?, NULL, CURRENT_TIMESTAMP)
                """, (key, str_value))

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
