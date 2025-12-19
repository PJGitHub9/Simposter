# backend/database.py
"""SQLite database for storing application settings and presets."""
import json
import logging
import sqlite3
import os
import shutil
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


def _configure_conn(conn: sqlite3.Connection):
    """Set safe defaults for concurrency on SQLite."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")  # 5s wait if locked
    conn.row_factory = sqlite3.Row


def get_db_version() -> Optional[str]:
    """Get the current database version."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'app.version'")
            row = cursor.fetchone()
            if row:
                return row["value"]
    except Exception:
        # Table might not exist yet
        pass
    return None


def _backup_database(db_version: str) -> None:
    """
    Create a versioned backup of the current database before migrations.
    Output file example: simposter_v1.4.3.db.bak
    """
    try:
        db_file = Path(DB_PATH)
        if not db_file.exists():
            logger.info("[DB] Skip backup: database file does not exist yet")
            return

        safe_version = (db_version or "unknown").replace(" ", "_")
        backup_name = f"simposter_{safe_version}.db.bak"
        backup_path = db_file.parent / backup_name

        # Avoid overwriting an existing backup: append numeric suffix if needed
        if backup_path.exists():
            idx = 1
            while True:
                candidate = db_file.parent / f"{backup_name}.{idx}"
                if not candidate.exists():
                    backup_path = candidate
                    break
                idx += 1

        shutil.copy2(db_file, backup_path)
        logger.info("[DB] Backed up database to %s", backup_path)
    except Exception as e:
        logger.warning("[DB] Failed to back up database before migration: %s", e)


def set_db_version(version: str) -> None:
    """Set the database version."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value, category, updated_at)
            VALUES ('app.version', ?, 'app', CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (version,))
    logger.info(f"[DB] Set database version to {version}")


def get_app_version() -> str:
    """Get the current application version from the frontend version file."""
    try:
        # Read version from the frontend version file
        version_file = Path(__file__).parent.parent / "frontend" / "src" / "version.ts"
        if version_file.exists():
            content = version_file.read_text()
            # Parse: export const APP_VERSION = 'v1.4.4'
            for line in content.split('\n'):
                if 'APP_VERSION' in line and '=' in line:
                    # Extract version between quotes
                    version = line.split('=')[1].strip().strip("'\"")
                    return version
    except Exception as e:
        logger.warning(f"[DB] Could not read app version from version.ts: {e}")

    # Fallback version
    return "v1.0.0"


def check_and_update_version() -> None:
    """
    Check the database version against the current app version.
    Log version changes and update the database version.
    This allows future migration logic based on version differences.
    """
    current_app_version = get_app_version()
    db_version = get_db_version()

    if db_version is None:
        logger.info(f"[DB] New database - setting initial version to {current_app_version}")
        set_db_version(current_app_version)
    elif db_version != current_app_version:
        logger.info(f"[DB] Version change detected: {db_version} -> {current_app_version}")
        _backup_database(db_version)
        # Future: Add migration logic here based on version comparison
        # For now, just update the version
        set_db_version(current_app_version)
    else:
        logger.debug(f"[DB] Database version {db_version} matches app version")


def init_database():
    """Initialize the database with required tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    _configure_conn(conn)
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

        # Cache table for Plex movies (metadata + labels/poster/tmdb)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movie_cache (
                rating_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                year INTEGER,
                added_at INTEGER,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                poster_url TEXT,
                labels_json TEXT DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                library_id TEXT DEFAULT 'default'
            )
        """)
        # Migration: ensure library_id column exists before creating indexes that depend on it
        cursor.execute("PRAGMA table_info(movie_cache)")
        cols = [row["name"] for row in cursor.fetchall()]
        if "library_id" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN library_id TEXT DEFAULT 'default'")
        if "tvdb_id" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN tvdb_id INTEGER")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_movie_cache_updated
            ON movie_cache(updated_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_movie_cache_title
            ON movie_cache(title)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_movie_cache_library
            ON movie_cache(library_id)
        """)

        # Cache table for Plex TV shows (metadata + labels/poster/tmdb + seasons)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tv_cache (
                rating_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                year INTEGER,
                added_at INTEGER,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                poster_url TEXT,
                labels_json TEXT DEFAULT '[]',
                seasons_json TEXT DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                library_id TEXT DEFAULT 'default'
            )
        """)
        cursor.execute("PRAGMA table_info(tv_cache)")
        tv_cols = [row["name"] for row in cursor.fetchall()]
        if "library_id" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN library_id TEXT DEFAULT 'default'")
        if "seasons_json" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN seasons_json TEXT DEFAULT '[]'")
        if "tvdb_id" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN tvdb_id INTEGER")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_cache_updated
            ON tv_cache(updated_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_cache_title
            ON tv_cache(title)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_cache_library
            ON tv_cache(library_id)
        """)

        # Cache table for Plex collections
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collection_cache (
                rating_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                year INTEGER,
                added_at INTEGER,
                poster_url TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                library_id TEXT DEFAULT 'default'
            )
        """)
        cursor.execute("PRAGMA table_info(collection_cache)")
        coll_cols = [row["name"] for row in cursor.fetchall()]
        if "library_id" not in coll_cols:
            cursor.execute("ALTER TABLE collection_cache ADD COLUMN library_id TEXT DEFAULT 'default'")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_cache_updated
            ON collection_cache(updated_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_cache_title
            ON collection_cache(title)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_cache_library
            ON collection_cache(library_id)
        """)

        # Poster history table - track poster actions (local save / send to Plex)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS poster_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rating_key TEXT NOT NULL,
                library_id TEXT,
                title TEXT,
                year INTEGER,
                template_id TEXT,
                preset_id TEXT,
                action TEXT NOT NULL, -- saved_local | sent_to_plex
                save_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_history_rating
            ON poster_history(rating_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_history_library
            ON poster_history(library_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_history_created
            ON poster_history(created_at DESC)
        """)

        conn.commit()
        logger.info(f"[DB] Initialized database at {DB_PATH}")
    except Exception as e:
        logger.error(f"[DB] Initialization/migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    # Check and update database version
    check_and_update_version()


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    _configure_conn(conn)
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


def get_log_config() -> Optional[Dict[str, Any]]:
    """Get log configuration stored in the database."""
    rows = get_settings_by_category("logs")
    if not rows:
        return None

    def _parse_int(value: Optional[str], default: int) -> int:
        try:
            return int(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    # Keys may be stored with or without the logs. prefix depending on legacy data
    level = rows.get("logs.level") or rows.get("level")
    max_size = rows.get("logs.maxSize") or rows.get("maxSize")
    max_backups = rows.get("logs.maxBackups") or rows.get("maxBackups")

    return {
        "level": level or "INFO",
        "maxSize": _parse_int(max_size, 20),
        "maxBackups": _parse_int(max_backups, 7),
    }


def save_log_config(config: Dict[str, Any]) -> None:
    """Persist log configuration in the database."""
    normalized = {
        "logs.level": str(config.get("level", "INFO")),
        "logs.maxSize": str(config.get("maxSize", 20)),
        "logs.maxBackups": str(config.get("maxBackups", 7)),
    }

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM settings WHERE category = ?", ("logs",))

        for key, value in normalized.items():
            cursor.execute(
                """
                INSERT INTO settings (key, value, category, updated_at)
                VALUES (?, ?, 'logs', CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    logger.debug("[DB] Saved log configuration to database")


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


def replace_all_presets(preset_data: Dict[str, Dict[str, Any]]) -> None:
    """
    Replace all presets in the database with the provided structure.
    Expected shape: { template_id: { presets: [ {id,name,options}, ... ] } }
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM presets")

        for template_id, tpl_data in (preset_data or {}).items():
            presets_list = tpl_data.get("presets", []) if isinstance(tpl_data, dict) else []
            for preset in presets_list:
                pid = preset.get("id")
                name = preset.get("name") or pid
                options = preset.get("options") or {}
                if not pid:
                    continue
                options_json = json.dumps(options)
                cursor.execute("""
                    INSERT INTO presets (id, template_id, name, options_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (pid, template_id, name, options_json))
    logger.info("[DB] Replaced all presets from import")


def merge_presets(preset_data: Dict[str, Dict[str, Any]]) -> None:
    """
    Merge imported presets with existing presets (append mode).
    Expected shape: { template_id: { presets: [ {id,name,options}, ... ] } }
    Existing presets with matching IDs will be updated, new ones will be added.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        for template_id, tpl_data in (preset_data or {}).items():
            presets_list = tpl_data.get("presets", []) if isinstance(tpl_data, dict) else []
            for preset in presets_list:
                pid = preset.get("id")
                name = preset.get("name") or pid
                options = preset.get("options") or {}
                if not pid:
                    continue
                options_json = json.dumps(options)
                # Use INSERT OR REPLACE to update existing or add new
                cursor.execute("""
                    INSERT INTO presets (id, template_id, name, options_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        template_id = excluded.template_id,
                        name = excluded.name,
                        options_json = excluded.options_json,
                        updated_at = CURRENT_TIMESTAMP
                """, (pid, template_id, name, options_json))
    logger.info("[DB] Merged imported presets with existing presets")


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


# ============================================
#  Movie Cache Operations
# ============================================

def upsert_movie_cache(
    rating_key: str,
    title: str,
    year: Optional[int],
    added_at: Optional[int],
    tmdb_id: Optional[int] = None,
    poster_url: Optional[str] = None,
    labels: Optional[List[str]] = None,
    library_id: str = "default",
) -> None:
    """Insert or update cached movie metadata."""
    labels_json = json.dumps(labels or [])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO movie_cache (rating_key, title, year, added_at, tmdb_id, poster_url, labels_json, updated_at, library_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(rating_key) DO UPDATE SET
                title = excluded.title,
                year = excluded.year,
                added_at = excluded.added_at,
                tmdb_id = COALESCE(excluded.tmdb_id, movie_cache.tmdb_id),
                poster_url = COALESCE(excluded.poster_url, movie_cache.poster_url),
                labels_json = CASE
                    WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                    ELSE movie_cache.labels_json
                END,
                library_id = COALESCE(excluded.library_id, movie_cache.library_id),
                updated_at = CURRENT_TIMESTAMP
        """, (rating_key, title, year, added_at, tmdb_id, poster_url, labels_json, library_id))


def update_movie_labels(rating_key: str, labels: List[str], library_id: str = "default") -> None:
    """Update labels for a cached movie."""
    labels_json = json.dumps(labels)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE movie_cache
            SET labels_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (labels_json, rating_key, library_id))


def update_movie_tmdb(rating_key: str, tmdb_id: Optional[int], library_id: str = "default") -> None:
    """Update TMDB id for a cached movie."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE movie_cache
            SET tmdb_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (tmdb_id, rating_key, library_id))


def update_movie_poster(rating_key: str, poster_url: Optional[str], library_id: str = "default") -> None:
    """Update poster url for a cached movie."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE movie_cache
            SET poster_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (poster_url, rating_key, library_id))


def bulk_refresh_cache(movies: List[Dict[str, Any]], library_id: str = "default") -> None:
    """
    Replace cache entries to match the provided movies list.
    Each movie dict should include rating_key, title, year, added_at, tmdb_id?, poster_url?, labels?.
    """
    keys = [m["rating_key"] for m in movies]
    with get_db() as conn:
        cursor = conn.cursor()
        for m in movies:
            labels_json = json.dumps(m.get("labels") or [])
            cursor.execute("""
                INSERT INTO movie_cache (rating_key, title, year, added_at, tmdb_id, poster_url, labels_json, updated_at, library_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    added_at = excluded.added_at,
                    tmdb_id = COALESCE(excluded.tmdb_id, movie_cache.tmdb_id),
                    poster_url = COALESCE(excluded.poster_url, movie_cache.poster_url),
                    labels_json = CASE
                        WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                        ELSE movie_cache.labels_json
                    END,
                    library_id = COALESCE(excluded.library_id, movie_cache.library_id),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                m["rating_key"],
                m["title"],
                m.get("year"),
                m.get("added_at"),
                m.get("tmdb_id"),
                m.get("poster_url"),
                labels_json,
                library_id,
            ))

        # Drop entries that are no longer present
        if keys:
            cursor.execute(f"""
                DELETE FROM movie_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND library_id = ?
            """, keys + [library_id])


def get_cached_movies(library_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return cached movies with labels/poster/tmdb if known. Optionally filter by library."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("""
                SELECT rating_key, title, year, added_at, tmdb_id, poster_url, labels_json, updated_at, library_id
                FROM movie_cache
                WHERE library_id = ?
                ORDER BY COALESCE(updated_at, added_at) DESC
            """, (library_id,))
        else:
            cursor.execute("""
                SELECT rating_key, title, year, added_at, tmdb_id, poster_url, labels_json, updated_at, library_id
                FROM movie_cache
                ORDER BY COALESCE(updated_at, added_at) DESC
            """)
        rows = cursor.fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            labels = json.loads(row["labels_json"]) if row["labels_json"] else []
        except json.JSONDecodeError:
            labels = []
        out.append({
            "rating_key": row["rating_key"],
            "title": row["title"],
            "year": row["year"],
            "addedAt": row["added_at"],
            "tmdb_id": row["tmdb_id"],
            "poster_url": row["poster_url"],
            "labels": labels,
            "updated_at": row["updated_at"],
            "library_id": row["library_id"] if "library_id" in row.keys() else None,
        })
    return out


def get_movie_cache_stats(library_id: Optional[str] = None) -> Dict[str, Any]:
    """Return count and last updated timestamp for movie_cache."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as max_updated FROM movie_cache WHERE library_id = ?", (library_id,))
        else:
            cursor.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as max_updated FROM movie_cache")
        row = cursor.fetchone()
    return {"count": row["cnt"] if row else 0, "max_updated": row["max_updated"] if row else None}


def clear_movie_cache(library_id: Optional[str] = None) -> None:
    """Delete rows from movie_cache. If library_id provided, only clear that library."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("DELETE FROM movie_cache WHERE library_id = ?", (library_id,))
            logger.info("[DB] Cleared movie_cache for library %s", library_id)
        else:
            cursor.execute("DELETE FROM movie_cache")
            logger.info("[DB] Cleared movie_cache")


# ============================================
#  TV Cache Operations
# ============================================

def upsert_tv_cache(
    rating_key: str,
    title: str,
    year: Optional[int],
    added_at: Optional[int],
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    poster_url: Optional[str] = None,
    labels: Optional[List[str]] = None,
    seasons: Optional[List[Dict[str, Any]]] = None,
    library_id: str = "default",
) -> None:
    """Insert or update cached TV show metadata."""
    labels_json = json.dumps(labels or [])
    seasons_json = json.dumps(seasons or [])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tv_cache (rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, labels_json, seasons_json, updated_at, library_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(rating_key) DO UPDATE SET
                title = excluded.title,
                year = excluded.year,
                added_at = excluded.added_at,
                tmdb_id = COALESCE(excluded.tmdb_id, tv_cache.tmdb_id),
                tvdb_id = COALESCE(excluded.tvdb_id, tv_cache.tvdb_id),
                poster_url = COALESCE(excluded.poster_url, tv_cache.poster_url),
                labels_json = CASE
                    WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                    ELSE tv_cache.labels_json
                END,
                seasons_json = CASE
                    WHEN excluded.seasons_json IS NOT NULL THEN excluded.seasons_json
                    ELSE tv_cache.seasons_json
                END,
                library_id = COALESCE(excluded.library_id, tv_cache.library_id),
                updated_at = CURRENT_TIMESTAMP
        """, (rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, labels_json, seasons_json, library_id))


def update_tv_labels(rating_key: str, labels: List[str], library_id: str = "default") -> None:
    labels_json = json.dumps(labels)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tv_cache
            SET labels_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (labels_json, rating_key, library_id))


def update_tv_tmdb(rating_key: str, tmdb_id: Optional[int], library_id: str = "default") -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tv_cache
            SET tmdb_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (tmdb_id, rating_key, library_id))


def update_tv_tvdb(rating_key: str, tvdb_id: Optional[int], library_id: str = "default") -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tv_cache
            SET tvdb_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (tvdb_id, rating_key, library_id))


def update_tv_poster(rating_key: str, poster_url: Optional[str], library_id: str = "default") -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tv_cache
            SET poster_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (poster_url, rating_key, library_id))


def update_tv_seasons(rating_key: str, seasons: List[Dict[str, Any]], library_id: str = "default") -> None:
    seasons_json = json.dumps(seasons or [])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tv_cache
            SET seasons_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (seasons_json, rating_key, library_id))


def bulk_refresh_tv_cache(shows: List[Dict[str, Any]], library_id: str = "default") -> None:
    """Replace cache entries to match the provided TV shows list."""
    keys = [m["rating_key"] for m in shows]
    with get_db() as conn:
        cursor = conn.cursor()
        for m in shows:
            labels_json = json.dumps(m.get("labels") or [])
            seasons_json = json.dumps(m.get("seasons") or [])
            cursor.execute("""
                INSERT INTO tv_cache (rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, labels_json, seasons_json, updated_at, library_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    added_at = excluded.added_at,
                    tmdb_id = COALESCE(excluded.tmdb_id, tv_cache.tmdb_id),
                    tvdb_id = COALESCE(excluded.tvdb_id, tv_cache.tvdb_id),
                    poster_url = COALESCE(excluded.poster_url, tv_cache.poster_url),
                    labels_json = CASE
                        WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                        ELSE tv_cache.labels_json
                    END,
                    seasons_json = CASE
                        WHEN excluded.seasons_json IS NOT NULL THEN excluded.seasons_json
                        ELSE tv_cache.seasons_json
                    END,
                    library_id = COALESCE(excluded.library_id, tv_cache.library_id),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                m["rating_key"],
                m["title"],
                m.get("year"),
                m.get("added_at"),
                m.get("tmdb_id"),
                m.get("tvdb_id"),
                m.get("poster_url"),
                labels_json,
                seasons_json,
                library_id,
            ))

        if keys:
            cursor.execute(f"""
                DELETE FROM tv_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND library_id = ?
            """, keys + [library_id])


def get_cached_tv_shows(library_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("""
                SELECT rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, labels_json, seasons_json, updated_at, library_id
                FROM tv_cache
                WHERE library_id = ?
                ORDER BY COALESCE(updated_at, added_at) DESC
            """, (library_id,))
        else:
            cursor.execute("""
                SELECT rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, labels_json, seasons_json, updated_at, library_id
                FROM tv_cache
                ORDER BY COALESCE(updated_at, added_at) DESC
            """)
        rows = cursor.fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            labels = json.loads(row["labels_json"]) if row["labels_json"] else []
        except json.JSONDecodeError:
            labels = []
        try:
            seasons = json.loads(row["seasons_json"]) if row["seasons_json"] else []
        except json.JSONDecodeError:
            seasons = []
        out.append({
            "rating_key": row["rating_key"],
            "title": row["title"],
            "year": row["year"],
            "addedAt": row["added_at"],
            "tmdb_id": row["tmdb_id"],
            "tvdb_id": row["tvdb_id"] if "tvdb_id" in row.keys() else None,
            "poster_url": row["poster_url"],
            "labels": labels,
            "seasons": seasons,
            "updated_at": row["updated_at"],
            "library_id": row["library_id"] if "library_id" in row.keys() else None,
        })
    return out


def get_cached_tv_show(rating_key: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, labels_json, seasons_json, updated_at, library_id
            FROM tv_cache
            WHERE rating_key = ?
        """, (rating_key,))
        row = cursor.fetchone()
    if not row:
        return None
    try:
        labels = json.loads(row["labels_json"]) if row["labels_json"] else []
    except json.JSONDecodeError:
        labels = []
    try:
        seasons = json.loads(row["seasons_json"]) if row["seasons_json"] else []
    except json.JSONDecodeError:
        seasons = []
    return {
        "rating_key": row["rating_key"],
        "title": row["title"],
        "year": row["year"],
        "addedAt": row["added_at"],
        "tmdb_id": row["tmdb_id"],
        "tvdb_id": row["tvdb_id"] if "tvdb_id" in row.keys() else None,
        "poster_url": row["poster_url"],
        "labels": labels,
        "seasons": seasons,
        "updated_at": row["updated_at"],
        "library_id": row["library_id"] if "library_id" in row.keys() else None,
    }


def get_tv_cache_stats(library_id: Optional[str] = None) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as max_updated FROM tv_cache WHERE library_id = ?", (library_id,))
        else:
            cursor.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as max_updated FROM tv_cache")
        row = cursor.fetchone()
    return {"count": row["cnt"] if row else 0, "max_updated": row["max_updated"] if row else None}


def clear_tv_cache(library_id: Optional[str] = None) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("DELETE FROM tv_cache WHERE library_id = ?", (library_id,))
            logger.info("[DB] Cleared tv_cache for library %s", library_id)
        else:
            cursor.execute("DELETE FROM tv_cache")
            logger.info("[DB] Cleared tv_cache")


# ============================================
#  Collection Cache Operations
# ============================================

def upsert_collection_cache(
    rating_key: str,
    title: str,
    year: Optional[int],
    added_at: Optional[int],
    poster_url: Optional[str] = None,
    library_id: str = "default",
) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO collection_cache (rating_key, title, year, added_at, poster_url, updated_at, library_id)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(rating_key) DO UPDATE SET
                title = excluded.title,
                year = excluded.year,
                added_at = excluded.added_at,
                poster_url = COALESCE(excluded.poster_url, collection_cache.poster_url),
                library_id = COALESCE(excluded.library_id, collection_cache.library_id),
                updated_at = CURRENT_TIMESTAMP
        """, (rating_key, title, year, added_at, poster_url, library_id))


def bulk_refresh_collection_cache(collections: List[Dict[str, Any]], library_id: str = "default") -> None:
    keys = [c["rating_key"] for c in collections]
    with get_db() as conn:
        cursor = conn.cursor()
        for c in collections:
            cursor.execute("""
                INSERT INTO collection_cache (rating_key, title, year, added_at, poster_url, updated_at, library_id)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    added_at = excluded.added_at,
                    poster_url = COALESCE(excluded.poster_url, collection_cache.poster_url),
                    library_id = COALESCE(excluded.library_id, collection_cache.library_id),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                c["rating_key"],
                c["title"],
                c.get("year"),
                c.get("added_at"),
                c.get("poster_url"),
                library_id,
            ))

        if keys:
            cursor.execute(f"""
                DELETE FROM collection_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND library_id = ?
            """, keys + [library_id])


def get_cached_collections(library_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("""
                SELECT rating_key, title, year, added_at, poster_url, updated_at, library_id
                FROM collection_cache
                WHERE library_id = ?
                ORDER BY COALESCE(updated_at, added_at) DESC
            """, (library_id,))
        else:
            cursor.execute("""
                SELECT rating_key, title, year, added_at, poster_url, updated_at, library_id
                FROM collection_cache
                ORDER BY COALESCE(updated_at, added_at) DESC
            """)
        rows = cursor.fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append({
            "rating_key": row["rating_key"],
            "title": row["title"],
            "year": row["year"],
            "addedAt": row["added_at"],
            "poster_url": row["poster_url"],
            "updated_at": row["updated_at"],
            "library_id": row["library_id"],
        })
    return out


def get_collection_cache_stats(library_id: Optional[str] = None) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as max_updated FROM collection_cache WHERE library_id = ?", (library_id,))
        else:
            cursor.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as max_updated FROM collection_cache")
        row = cursor.fetchone()
    return {"count": row["cnt"] if row else 0, "max_updated": row["max_updated"] if row else None}


def clear_collection_cache(library_id: Optional[str] = None) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("DELETE FROM collection_cache WHERE library_id = ?", (library_id,))
            logger.info("[DB] Cleared collection_cache for library %s", library_id)
        else:
            cursor.execute("DELETE FROM collection_cache")
            logger.info("[DB] Cleared collection_cache")


def copy_env_to_ui_settings():
    """
    Copy environment variables to UI settings in the database on container startup.
    This allows ENV vars to be the initial values that users can then modify via the UI.
    
    Only copies ENV vars on first run or when settings are still at default values.
    If admins want to force ENV values, they will still override via the normal ENV override mechanism.
    """
    import os
    
    # Check if we should skip ENV copying (e.g., if settings already exist and are non-default)
    existing_settings = get_ui_settings()
    
    if existing_settings:
        # Check if this looks like a fresh container by seeing if critical settings are still defaults
        plex_data = existing_settings.get("plex", {})
        existing_url = plex_data.get("url", "")
        existing_token = plex_data.get("token", "")
        
        # If URL and token are already set to non-default values, skip ENV copying
        # This prevents overwriting user-configured settings on container restart
        if (existing_url and existing_url != "http://localhost:32400" and 
            existing_token and existing_token != ""):
            logger.debug("[DB] UI settings already configured, skipping ENV copy")
            return
        
        # Also check if we have any non-default TMDB key
        tmdb_data = existing_settings.get("tmdb", {})
        if tmdb_data.get("apiKey"):
            logger.debug("[DB] TMDB API key already configured, skipping ENV copy")
            return
    
    env_mappings = [
        ("PLEX_URL", "plex.url"),
        ("PLEX_TOKEN", "plex.token"), 
        ("PLEX_MOVIE_LIBRARY_NAME", "plex.movieLibraryName"),
        ("PLEX_MOVIE_LIBRARY_NAMES", "plex.movieLibraryNames"),
        ("TMDB_API_KEY", "tmdb.apiKey"),
    ]
    
    updates_made = []
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    _configure_conn(conn)
    cursor = conn.cursor()
    
    try:
        for env_var, setting_key in env_mappings:
            env_value = os.getenv(env_var)
            if env_value:
                # Special handling for comma-separated library names
                if env_var == "PLEX_MOVIE_LIBRARY_NAMES":
                    env_value = json.dumps([s.strip() for s in env_value.split(",") if s.strip()])
                elif env_var in ("PLEX_URL", "PLEX_TOKEN", "PLEX_MOVIE_LIBRARY_NAME", "TMDB_API_KEY"):
                    env_value = str(env_value)
                
                category = setting_key.split(".")[0]
                
                # Insert or update setting (upsert)
                cursor.execute("""
                    INSERT INTO settings (key, value, category, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                """, (setting_key, env_value, category))
                updates_made.append(f"{env_var} -> {setting_key}")
        
        conn.commit()
        
        if updates_made:
            logger.info(f"[DB] Copied ENV variables to UI settings: {', '.join(updates_made)}")
        else:
            logger.debug("[DB] No ENV variables to copy to UI settings")
            
    except Exception as e:
        logger.error(f"[DB] Failed to copy ENV variables to UI settings: {e}")
        conn.rollback()
    finally:
        conn.close()


# ============================================
#  Poster History Operations
# ============================================

def record_poster_history(
    rating_key: str,
    library_id: Optional[str],
    title: Optional[str],
    year: Optional[int],
    template_id: Optional[str],
    preset_id: Optional[str],
    action: str,
    save_path: Optional[str] = None,
) -> None:
    """Record a poster-related action for tracking."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO poster_history
            (rating_key, library_id, title, year, template_id, preset_id, action, save_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                rating_key,
                library_id,
                title,
                year if year is not None else None,
                template_id,
                preset_id,
                action,
                save_path,
            ),
        )


def get_poster_history(
    library_id: Optional[str] = None,
    template_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Fetch poster history records with optional filters."""
    query = "SELECT * FROM poster_history"
    clauses = []
    params: List[Any] = []

    if library_id:
        clauses.append("library_id = ?")
        params.append(library_id)
    if template_id:
        clauses.append("template_id = ?")
        params.append(template_id)
    if action:
        clauses.append("action = ?")
        params.append(action)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY datetime(created_at) DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append({
            "id": row["id"],
            "rating_key": row["rating_key"],
            "library_id": row["library_id"],
            "title": row["title"],
            "year": row["year"],
            "template_id": row["template_id"],
            "preset_id": row["preset_id"],
            "action": row["action"],
            "save_path": row["save_path"],
            "created_at": row["created_at"],
        })
    return out


# Initialize database on module import
init_database()
# Copy environment variables to UI settings on startup
copy_env_to_ui_settings()
