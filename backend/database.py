# backend/database.py
"""SQLite database for storing application settings and presets."""
import json
import logging
import re
import sqlite3
import os
import shutil
import time
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
    conn.execute("PRAGMA busy_timeout=30000;")  # 30s wait if locked
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
    except sqlite3.Error as e:
        # Table might not exist yet during initial setup
        logger.debug("Could not read app version from database: %s", e)
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
    import time
    
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Retry logic for database lock
    max_retries = 5
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
            _configure_conn(conn)
            cursor = conn.cursor()
            break
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logger.warning(f"[DB] Database locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                raise

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
                season_options_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(template_id, id)
            )
        """)

        # Ensure season_options_json exists for older databases
        cursor.execute("PRAGMA table_info(presets)")
        cols = [row[1] for row in cursor.fetchall()]
        if "season_options_json" not in cols:
            cursor.execute("ALTER TABLE presets ADD COLUMN season_options_json TEXT NOT NULL DEFAULT '{}' ")

        # Backfill/normalize season_options_json:
        # - Empty (newly created column, or a preset with no season customization yet) →
        #   seed it with the standard season-default overrides, stored as a sparse diff
        #   against options_json (not a full clone) — see resolve_season_options()/
        #   diff_season_options() above, which every consumer merges through.
        # - Already populated → normalize to a diff against options_json. This is a one-time
        #   bloat cleanup for presets saved before v1.6.32, which stored a full duplicate of
        #   every field (~45 keys) instead of just the ~8 that actually differ. Diffing an
        #   already-sparse value is a no-op, so this is safe to run on every startup.
        cursor.execute("""
            SELECT id, options_json, season_options_json
            FROM presets
        """)
        rows = cursor.fetchall()
        for row in rows:
            try:
                season_raw = row["season_options_json"] if "season_options_json" in row.keys() else None
                base_opts = json.loads(row["options_json"]) if row["options_json"] else {}

                is_empty = not season_raw or season_raw.strip() in ("", "{}", "null", "NULL")

                if is_empty:
                    season_defaults = {
                        "logo_mode": "none",
                        "poster_filter": "textless",
                        "text_overlay_enabled": True,
                        "custom_text": "{season}",
                        "font_family": "Arial",
                        "font_size": 150,
                        "shadow_enabled": False,
                        "shadow_blur": 0,
                        "letter_spacing": 1,
                        "position_y": 0.85,
                    }
                    season_diff = diff_season_options(base_opts, season_defaults)
                    cursor.execute(
                        "UPDATE presets SET season_options_json = ? WHERE id = ?",
                        (json.dumps(season_diff), row["id"]),
                    )
                else:
                    # User has custom season options — normalize storage to a diff against the
                    # base options without changing effective behavior (resolve_season_options()
                    # reconstructs the same values from a diff or a full copy identically).
                    season_opts = json.loads(season_raw)
                    season_diff = diff_season_options(base_opts, season_opts)
                    if season_diff != season_opts:
                        cursor.execute(
                            "UPDATE presets SET season_options_json = ? WHERE id = ?",
                            (json.dumps(season_diff), row["id"]),
                        )
            except Exception as backfill_err:
                logger.warning("[DB] Failed to backfill season_options_json for preset %s: %s", row["id"], backfill_err)

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
                logo_url TEXT,
                art_url TEXT,
                square_art_url TEXT,
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
        if "video_resolution" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN video_resolution TEXT")
        if "audio_codec" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN audio_codec TEXT")
        if "audio_channels" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN audio_channels TEXT")
        if "video_codec" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN video_codec TEXT")
        if "audio_language" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN audio_language TEXT")
        if "edition" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN edition TEXT")
        if "logo_url" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN logo_url TEXT")
            logger.info("[DB] Added 'logo_url' column to movie_cache")
        if "art_url" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN art_url TEXT")
            logger.info("[DB] Added 'art_url' column to movie_cache")
        if "square_art_url" not in cols:
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN square_art_url TEXT")
            logger.info("[DB] Added 'square_art_url' column to movie_cache")
        if "server_id" not in cols:
            # Which configured media server (see the mediaServers setting) this
            # cached row came from -- 'plex-1' for every existing row, since this
            # app was Plex-only before this column existed. Not yet a composite
            # PK with rating_key: a real collision between a Plex rating_key and
            # a Jellyfin/Emby item GUID is not realistic (completely different ID
            # formats), so this stays a plain indexed column rather than forcing
            # a destructive SQLite table-rebuild migration for a risk that isn't
            # real. See CLAUDE.md Quirk #57.
            cursor.execute("ALTER TABLE movie_cache ADD COLUMN server_id TEXT NOT NULL DEFAULT 'plex-1'")
            logger.info("[DB] Added 'server_id' column to movie_cache")

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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_movie_cache_tmdb
            ON movie_cache(tmdb_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_movie_cache_composite
            ON movie_cache(library_id, rating_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_movie_cache_server
            ON movie_cache(server_id, rating_key)
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
                logo_url TEXT,
                art_url TEXT,
                square_art_url TEXT,
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
        if "video_resolution" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN video_resolution TEXT")
        if "audio_codec" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN audio_codec TEXT")
        if "audio_channels" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN audio_channels TEXT")
        if "video_codec" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN video_codec TEXT")
        if "audio_language" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN audio_language TEXT")
        if "edition" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN edition TEXT")
        if "logo_url" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN logo_url TEXT")
            logger.info("[DB] Added 'logo_url' column to tv_cache")
        if "art_url" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN art_url TEXT")
            logger.info("[DB] Added 'art_url' column to tv_cache")
        if "square_art_url" not in tv_cols:
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN square_art_url TEXT")
            logger.info("[DB] Added 'square_art_url' column to tv_cache")
        if "server_id" not in tv_cols:
            # See the matching movie_cache 'server_id' migration comment above --
            # same reasoning, same default, same non-PK design (CLAUDE.md Quirk #57).
            cursor.execute("ALTER TABLE tv_cache ADD COLUMN server_id TEXT NOT NULL DEFAULT 'plex-1'")
            logger.info("[DB] Added 'server_id' column to tv_cache")

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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_cache_tmdb
            ON tv_cache(tmdb_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_cache_tvdb
            ON tv_cache(tvdb_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_cache_composite
            ON tv_cache(library_id, rating_key)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tv_cache_server
            ON tv_cache(server_id, rating_key)
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
        if "tmdb_collection_id" not in coll_cols:
            # Resolved once via a title search against TMDb's /search/collection
            # (Plex collections carry no TMDb ID of their own) and cached here so
            # opening the Simposter Creator for the same collection again doesn't
            # repeat that search — see get_collection_tmdb_id()/set_collection_tmdb_id().
            cursor.execute("ALTER TABLE collection_cache ADD COLUMN tmdb_collection_id INTEGER")
        if "server_id" not in coll_cols:
            # See the matching movie_cache 'server_id' migration comment (CLAUDE.md Quirk #57).
            cursor.execute("ALTER TABLE collection_cache ADD COLUMN server_id TEXT NOT NULL DEFAULT 'plex-1'")
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

        # Label cache tables for Plex labels
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS label_cache (
                rating_key TEXT PRIMARY KEY,
                labels TEXT, -- JSON array of label names
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tv_label_cache (
                rating_key TEXT PRIMARY KEY,
                labels TEXT, -- JSON array of label names
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
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
                source TEXT DEFAULT 'manual', -- manual | batch | auto
                poster_fallback_used INTEGER DEFAULT 0, -- 0/1 boolean
                poster_fallback_template TEXT,
                poster_fallback_preset TEXT,
                logo_fallback_used INTEGER DEFAULT 0, -- 0/1 boolean
                logo_fallback_template TEXT,
                logo_fallback_preset TEXT,
                thumbnail_path TEXT,
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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_history_template_preset
            ON poster_history(template_id, preset_id)
        """)

        # Migration: add source column to poster_history if it doesn't exist
        cursor.execute("PRAGMA table_info(poster_history)")
        history_cols = [row["name"] for row in cursor.fetchall()]
        if "source" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN source TEXT DEFAULT 'manual'")
            logger.info("[DB] Added 'source' column to poster_history table")

        # Migration: add fallback tracking columns if they don't exist
        if "poster_fallback_used" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN poster_fallback_used INTEGER DEFAULT 0")
            logger.info("[DB] Added 'poster_fallback_used' column to poster_history table")
        if "poster_fallback_template" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN poster_fallback_template TEXT")
            logger.info("[DB] Added 'poster_fallback_template' column to poster_history table")
        if "poster_fallback_preset" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN poster_fallback_preset TEXT")
            logger.info("[DB] Added 'poster_fallback_preset' column to poster_history table")
        if "logo_fallback_used" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN logo_fallback_used INTEGER DEFAULT 0")
            logger.info("[DB] Added 'logo_fallback_used' column to poster_history table")
        if "logo_fallback_template" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN logo_fallback_template TEXT")
            logger.info("[DB] Added 'logo_fallback_template' column to poster_history table")
        if "logo_fallback_preset" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN logo_fallback_preset TEXT")
            logger.info("[DB] Added 'logo_fallback_preset' column to poster_history table")
        if "thumbnail_path" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN thumbnail_path TEXT")
            logger.info("[DB] Added 'thumbnail_path' column to poster_history table")
        if "status" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN status TEXT DEFAULT 'success'")
            logger.info("[DB] Added 'status' column to poster_history table")
        if "error_message" not in history_cols:
            cursor.execute("ALTER TABLE poster_history ADD COLUMN error_message TEXT")
            logger.info("[DB] Added 'error_message' column to poster_history table")
        if "server_id" not in history_cols:
            # See the matching movie_cache 'server_id' migration comment (CLAUDE.md Quirk #57).
            cursor.execute("ALTER TABLE poster_history ADD COLUMN server_id TEXT NOT NULL DEFAULT 'plex-1'")
            logger.info("[DB] Added 'server_id' column to poster_history table")

        # Migration: Consolidate 'default' and 'universal' templates into 'uniformlogo'
        # Convert logo_scale/logo_offset to bounding box zones
        try:
            # Check if any presets use 'default' or 'universal' template_id
            cursor.execute("""
                SELECT COUNT(*) as count FROM presets
                WHERE template_id IN ('default', 'universal')
            """)
            presets_to_migrate = cursor.fetchone()["count"]

            if presets_to_migrate > 0:
                logger.info(f"[DB] Migrating {presets_to_migrate} presets from 'default'/'universal' to 'uniformlogo'")

                # Get all presets that need migration
                cursor.execute("""
                    SELECT id, template_id, options_json, season_options_json FROM presets
                    WHERE template_id IN ('default', 'universal')
                """)
                presets = cursor.fetchall()

                for preset in presets:
                    preset_id = preset["id"]
                    old_template_id = preset["template_id"]
                    options = json.loads(preset["options_json"])
                    season_options_raw = preset["season_options_json"] if "season_options_json" in preset.keys() else "{}"
                    season_options = json.loads(season_options_raw) if season_options_raw else {}

                    # Convert logo_scale/logo_offset to uniform_logo bounding box if they exist
                    # Canvas width is 2000px for the standard poster
                    if "logo_scale" in options and "uniform_logo_max_w" not in options:
                        logo_scale = float(options.get("logo_scale", 0.45))
                        options["uniform_logo_max_w"] = int(logo_scale * 2000)
                        logger.debug(f"[DB] Converted logo_scale {logo_scale} -> uniform_logo_max_w {options['uniform_logo_max_w']} for preset {preset_id}")

                    if "logo_offset" in options and "uniform_logo_offset_y" not in options:
                        options["uniform_logo_offset_y"] = float(options.get("logo_offset", 0.78))
                        logger.debug(f"[DB] Converted logo_offset -> uniform_logo_offset_y for preset {preset_id}")

                    # Set defaults for uniform_logo if not present
                    if "uniform_logo_max_h" not in options:
                        options["uniform_logo_max_h"] = 300  # Default height
                    if "uniform_logo_offset_x" not in options:
                        options["uniform_logo_offset_x"] = 0.5  # Centered

                    # Do the same for season_options if it has logo positioning
                    if season_options:
                        if "logo_scale" in season_options and "uniform_logo_max_w" not in season_options:
                            logo_scale = float(season_options.get("logo_scale", 0.45))
                            season_options["uniform_logo_max_w"] = int(logo_scale * 2000)

                        if "logo_offset" in season_options and "uniform_logo_offset_y" not in season_options:
                            season_options["uniform_logo_offset_y"] = float(season_options.get("logo_offset", 0.78))

                        if "uniform_logo_max_h" not in season_options:
                            season_options["uniform_logo_max_h"] = 300
                        if "uniform_logo_offset_x" not in season_options:
                            season_options["uniform_logo_offset_x"] = 0.5

                    # Update preset with new template_id and converted options
                    cursor.execute("""
                        UPDATE presets
                        SET template_id = 'uniformlogo',
                            options_json = ?,
                            season_options_json = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (json.dumps(options), json.dumps(season_options), preset_id))

                    logger.debug(f"[DB] Migrated preset '{preset_id}' from '{old_template_id}' to 'uniformlogo'")

                logger.info(f"[DB] Successfully migrated {presets_to_migrate} presets to 'uniformlogo'")

            # Migrate poster_history template references
            cursor.execute("""
                SELECT COUNT(*) as count FROM poster_history
                WHERE template_id IN ('default', 'universal')
                   OR poster_fallback_template IN ('default', 'universal')
                   OR logo_fallback_template IN ('default', 'universal')
            """)
            history_to_migrate = cursor.fetchone()["count"]

            if history_to_migrate > 0:
                logger.info(f"[DB] Migrating {history_to_migrate} poster_history entries to use 'uniformlogo'")

                # Update main template_id
                cursor.execute("""
                    UPDATE poster_history
                    SET template_id = 'uniformlogo'
                    WHERE template_id IN ('default', 'universal')
                """)

                # Update fallback template references
                cursor.execute("""
                    UPDATE poster_history
                    SET poster_fallback_template = 'uniformlogo'
                    WHERE poster_fallback_template IN ('default', 'universal')
                """)

                cursor.execute("""
                    UPDATE poster_history
                    SET logo_fallback_template = 'uniformlogo'
                    WHERE logo_fallback_template IN ('default', 'universal')
                """)

                logger.info(f"[DB] Successfully migrated {history_to_migrate} poster_history entries")

            # Migrate fallback template references inside ALL preset options_json / season_options_json
            # A preset with template_id='uniformlogo' can still have fallbackPosterTemplate='default' in its options
            cursor.execute("SELECT id, options_json, season_options_json FROM presets")
            all_presets = cursor.fetchall()
            fallback_keys = ["fallbackPosterTemplate", "fallbackLogoTemplate"]
            migrated_fallback_count = 0

            for preset in all_presets:
                preset_id = preset["id"]
                changed = False

                opts = json.loads(preset["options_json"])
                for key in fallback_keys:
                    if opts.get(key) in ("default", "universal"):
                        opts[key] = "uniformlogo"
                        changed = True

                season_raw = preset["season_options_json"] if "season_options_json" in preset.keys() else "{}"
                season_opts = json.loads(season_raw) if season_raw else {}
                for key in fallback_keys:
                    if season_opts.get(key) in ("default", "universal"):
                        season_opts[key] = "uniformlogo"
                        changed = True

                if changed:
                    cursor.execute("""
                        UPDATE presets SET options_json = ?, season_options_json = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (json.dumps(opts), json.dumps(season_opts), preset_id))
                    migrated_fallback_count += 1

            if migrated_fallback_count > 0:
                logger.info(f"[DB] Migrated fallback template references in {migrated_fallback_count} presets")

        except Exception as migration_err:
            logger.warning(f"[DB] Template consolidation migration failed (non-critical): {migration_err}")

        # Overlay configuration tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS overlay_configs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                elements_json TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS overlay_assets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT,
                width INTEGER,
                height INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: add overlay_config_id column to presets if it doesn't exist
        cursor.execute("PRAGMA table_info(presets)")
        preset_cols = [row["name"] for row in cursor.fetchall()]
        if "overlay_config_id" not in preset_cols:
            cursor.execute("ALTER TABLE presets ADD COLUMN overlay_config_id TEXT")
            logger.info("[DB] Added 'overlay_config_id' column to presets table")

        # Migration: add streaming_region column to overlay_configs if it doesn't exist
        cursor.execute("PRAGMA table_info(overlay_configs)")
        overlay_cols = [row["name"] for row in cursor.fetchall()]
        if "streaming_region" not in overlay_cols:
            cursor.execute("ALTER TABLE overlay_configs ADD COLUMN streaming_region TEXT DEFAULT 'US'")
            logger.info("[DB] Added 'streaming_region' column to overlay_configs table")

        # Streaming provider cache — stores TMDb watch/providers results per item
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS streaming_provider_cache (
                tmdb_id     TEXT NOT NULL,
                media_type  TEXT NOT NULL,
                region      TEXT NOT NULL DEFAULT 'US',
                providers_json TEXT DEFAULT '[]',
                fetched_at  INTEGER,
                PRIMARY KEY (tmdb_id, media_type, region)
            )
        """)

        # Create indexes for overlay tables
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_overlay_configs_name
            ON overlay_configs(name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_overlay_assets_name
            ON overlay_assets(name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_presets_overlay_config
            ON presets(overlay_config_id)
        """)

        # Poster retry queue — tracks items that didn't meet ideal template conditions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS poster_retry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rating_key TEXT NOT NULL UNIQUE,
                media_type TEXT NOT NULL DEFAULT 'movie',
                library_id TEXT,
                template_id TEXT NOT NULL,
                preset_id TEXT NOT NULL,
                title TEXT,
                reason TEXT,
                first_queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_attempted_at TIMESTAMP,
                retry_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_retry_queue_status
            ON poster_retry_queue(status)
        """)
        cursor.execute("PRAGMA table_info(poster_retry_queue)")
        retry_cols = [row["name"] for row in cursor.fetchall()]
        if "server_id" not in retry_cols:
            # See the matching movie_cache 'server_id' migration comment (CLAUDE.md Quirk #57).
            cursor.execute("ALTER TABLE poster_retry_queue ADD COLUMN server_id TEXT NOT NULL DEFAULT 'plex-1'")
            logger.info("[DB] Added 'server_id' column to poster_retry_queue")

        # One-time cleanup for DBs created before "abandoned" retry items were deleted
        # outright instead of just marked -- see scheduler.py's _run_poster_retry(). A
        # stale abandoned row's title commonly reappears under a brand-new rating_key
        # (delete-then-re-add in Plex, see CLAUDE.md Quirk #41), which made the History
        # → Retry Queue view show what looked like the same item twice. Idempotent (a
        # no-op once these rows are gone), safe to run every startup.
        cursor.execute("DELETE FROM poster_retry_queue WHERE status = 'abandoned'")

        # Tracks the last time each TMDb ID was confirmed present in the Plex library,
        # independent of Plex's own rating_key (which changes on a Radarr/Sonarr re-grab
        # or similar). Upserted on every scan for every currently-present item with a
        # known tmdb_id -- deliberately NOT touched when a poster is sent (that's a
        # separate concern, see save_render_cache_by_tmdb() in config.py). This is what
        # lets the "reuseCachedPosterDays" grace period mean "days since this title
        # actually disappeared from the library," not "days since we last rendered its
        # poster" -- a movie that's sat untouched for a year shouldn't lose its reuse
        # eligibility just because nobody's regenerated its poster recently.
        # season_index defaults to -1 (not NULL) for a movie or a TV series-level poster --
        # SQLite's PRIMARY KEY/UNIQUE constraints treat every NULL as distinct from every
        # other NULL, so a nullable PK column here would silently let duplicate "no season"
        # rows pile up per tmdb_id instead of the upsert correctly updating one row.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tmdb_last_seen (
                media_type TEXT NOT NULL,
                tmdb_id INTEGER NOT NULL,
                season_index INTEGER NOT NULL DEFAULT -1,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (media_type, tmdb_id, season_index)
            )
        """)

        conn.commit()
        logger.info(f"[DB] Initialized database at {DB_PATH}")

        # Clean up any invalid TV cache entries (NULL or empty rating_key)
        try:
            cursor.execute("DELETE FROM tv_cache WHERE rating_key IS NULL OR rating_key = ''")
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(f"[DB] Cleaned up {deleted_count} invalid TV cache entries")
                conn.commit()
        except Exception as cleanup_err:
            logger.warning(f"[DB] Failed to clean up TV cache: {cleanup_err}")

        # Seed onboarding_completed flag if it has never been set.
        # Existing users who already have Plex configured get true (skip onboarding).
        # Fresh installs get false (show onboarding).
        try:
            existing = cursor.execute(
                "SELECT value FROM settings WHERE key = 'onboarding_completed' LIMIT 1"
            ).fetchone()
            if existing is None:
                plex_url_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'plex.url' OR key = 'url' AND category = 'plex' LIMIT 1"
                ).fetchone()
                already_configured = bool(plex_url_row and plex_url_row["value"] and plex_url_row["value"].strip())
                flag_value = "true" if already_configured else "false"
                cursor.execute("""
                    INSERT INTO settings (key, value, category)
                    VALUES ('onboarding_completed', ?, NULL)
                """, (flag_value,))
                conn.commit()
                logger.info(f"[DB] Seeded onboarding_completed={flag_value}")
        except Exception as onboard_err:
            logger.warning(f"[DB] Could not seed onboarding_completed: {onboard_err}")

        # Default scheduled cleanup ON for existing installs upgrading into this
        # feature, OFF for genuinely fresh installs -- every other automation
        # setting in this app defaults off (see CLAUDE.md's "no auth gate" and
        # retry/reuse-cache quirks), but an existing user's cache has already had
        # time to accumulate real orphaned bloat by the time they upgrade, while a
        # fresh install has nothing to clean yet. Runs at most once per DB (the
        # key's mere presence, regardless of value, means this already ran or the
        # user has already touched this setting themselves -- either way, never
        # overwrite it). Reuses the exact same "already configured" signal the
        # onboarding_completed seed above already established as the right way to
        # distinguish an existing install from a fresh one in this codebase.
        try:
            existing_cleanup_setting = cursor.execute(
                "SELECT value FROM settings WHERE key = 'scheduler.cleanupEnabled' LIMIT 1"
            ).fetchone()
            if existing_cleanup_setting is None:
                plex_url_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'plex.url' OR key = 'url' AND category = 'plex' LIMIT 1"
                ).fetchone()
                already_configured = bool(plex_url_row and plex_url_row["value"] and plex_url_row["value"].strip())
                if already_configured:
                    for key, value in (
                        ("scheduler.cleanupEnabled", "true"),
                        ("scheduler.cleanupCronExpression", "0 3 * * 0"),
                        ("scheduler.cleanupCategories", json.dumps([
                            "poster_cache", "logo_cache", "backdrop_cache", "square_art_cache",
                            "overlay_effect_cache", "uploaded_files", "overlay_assets", "poster_history",
                        ])),
                        ("scheduler.cleanupHistoryDays", "180"),
                    ):
                        cursor.execute("""
                            INSERT INTO settings (key, value, category)
                            VALUES (?, ?, 'scheduler')
                            ON CONFLICT(key) DO NOTHING
                        """, (key, value))
                    conn.commit()
                    logger.info("[DB] Existing install detected -- defaulted scheduled cleanup to enabled (weekly)")
        except Exception as cleanup_default_err:
            logger.warning(f"[DB] Could not default scheduled cleanup for existing install: {cleanup_default_err}")

        # Seed the mediaServers list (the multi-server model -- see
        # ai_repo/simposter/jellyfin-upgrade-plan.md, CLAUDE.md Quirk #57) for an
        # existing install: its single Plex config becomes exactly one
        # auto-migrated entry with id 'plex-1', matching the server_id default
        # every cached row above already carries -- so nothing changes
        # behaviorally, existing installs just now have a mediaServers[] list
        # of one, ready for a Jellyfin/Emby entry to be added alongside it
        # later. Reuses the exact same "already configured" signal and
        # once-only insert pattern as onboarding_completed/cleanupEnabled above
        # -- a fresh install (no plex.url yet) gets nothing here; it'll be
        # seeded once the user actually configures a server through onboarding
        # or Settings (future phase, not yet wired up as of this seed).
        try:
            existing_media_servers = cursor.execute(
                "SELECT value FROM settings WHERE key = 'mediaServers' LIMIT 1"
            ).fetchone()
            if existing_media_servers is None:
                plex_url_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'plex.url' OR key = 'url' AND category = 'plex' LIMIT 1"
                ).fetchone()
                plex_token_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'plex.token' OR key = 'token' AND category = 'plex' LIMIT 1"
                ).fetchone()
                already_configured = bool(plex_url_row and plex_url_row["value"] and plex_url_row["value"].strip())
                if already_configured:
                    servers = [{
                        "id": "plex-1",
                        "type": "plex",
                        "url": plex_url_row["value"],
                        "token": (plex_token_row["value"] if plex_token_row else "") or "",
                        "enabled": True,
                    }]
                    cursor.execute("""
                        INSERT INTO settings (key, value, category)
                        VALUES ('mediaServers', ?, NULL)
                        ON CONFLICT(key) DO NOTHING
                    """, (json.dumps(servers),))
                    conn.commit()
                    logger.info("[DB] Seeded mediaServers with one auto-migrated Plex entry (id=plex-1)")
        except Exception as media_servers_err:
            logger.warning(f"[DB] Could not seed mediaServers: {media_servers_err}")

        # Seed libraryGroups by converting each existing Plex libraryMappings /
        # tvShowLibraryMappings entry into a single-member LibraryGroup (server_id
        # 'plex-1', matching the mediaServers seed above) -- purely additive: the
        # original plex.libraryMappings/tvShowLibraryMappings settings are left
        # completely untouched by this migration, since existing consumer code
        # (auto-generate, webhooks, the Libraries settings tab) still reads those
        # directly and isn't being rewired to libraryGroups in this pass. This
        # only gives every existing single-server install a ready-made group per
        # library, so adding a second server's library to the same logical group
        # later is just editing that group's members, not starting from scratch.
        # Same once-only, never-overwrite pattern as onboarding_completed/
        # cleanupEnabled/mediaServers above.
        try:
            existing_library_groups = cursor.execute(
                "SELECT value FROM settings WHERE key = 'libraryGroups' LIMIT 1"
            ).fetchone()
            if existing_library_groups is None:
                movie_mappings_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'plex.libraryMappings' LIMIT 1"
                ).fetchone()
                tv_mappings_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'plex.tvShowLibraryMappings' LIMIT 1"
                ).fetchone()
                labels_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'defaultLabelsToRemove' LIMIT 1"
                ).fetchone()
                tv_labels_row = cursor.execute(
                    "SELECT value FROM settings WHERE key = 'defaultTvLabelsToRemove' LIMIT 1"
                ).fetchone()

                def _labels_for(raw_value, lib_id):
                    if not raw_value:
                        return []
                    try:
                        parsed = json.loads(raw_value)
                    except (json.JSONDecodeError, TypeError):
                        return []
                    if isinstance(parsed, dict):
                        return parsed.get(str(lib_id)) or []
                    if isinstance(parsed, list):
                        return parsed
                    return []

                def _groups_from_mappings(raw_value, media_type, labels_raw):
                    groups = []
                    if not raw_value:
                        return groups
                    try:
                        mappings = json.loads(raw_value)
                    except (json.JSONDecodeError, TypeError):
                        return groups
                    if not isinstance(mappings, list):
                        return groups
                    for m in mappings:
                        if not isinstance(m, dict) or not m.get("id"):
                            continue
                        lib_id = str(m["id"])
                        lib_name = m.get("displayName") or m.get("title") or lib_id
                        groups.append({
                            "id": f"group-{media_type}-{lib_id}",
                            "name": lib_name,
                            "mediaType": media_type,
                            "members": [{
                                "serverId": "plex-1",
                                "libraryId": lib_id,
                                "libraryName": lib_name,
                            }],
                            "autoGenerateEnabled": bool(m.get("autoGenerateEnabled", False)),
                            "autoGeneratePresetId": m.get("autoGeneratePresetId"),
                            "autoGenerateTemplateId": m.get("autoGenerateTemplateId"),
                            "labelsToRemove": _labels_for(labels_raw, lib_id),
                        })
                    return groups

                all_groups = (
                    _groups_from_mappings(movie_mappings_row["value"] if movie_mappings_row else None, "movie", labels_row["value"] if labels_row else None)
                    + _groups_from_mappings(tv_mappings_row["value"] if tv_mappings_row else None, "tv", tv_labels_row["value"] if tv_labels_row else None)
                )
                cursor.execute("""
                    INSERT INTO settings (key, value, category)
                    VALUES ('libraryGroups', ?, NULL)
                    ON CONFLICT(key) DO NOTHING
                """, (json.dumps(all_groups),))
                conn.commit()
                logger.info(f"[DB] Seeded libraryGroups with {len(all_groups)} auto-migrated single-member group(s) from existing Plex library mappings")
        except Exception as library_groups_err:
            logger.warning(f"[DB] Could not seed libraryGroups: {library_groups_err}")
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
    except (sqlite3.Error, Exception) as e:
        conn.rollback()
        logger.error("Database transaction failed, rolling back: %s", e)
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


# Dotted "category.field" keys that must always be read back as a raw string, even if
# their value happens to look like a number or "true"/"false" (e.g. a webhook secret of
# "123", or an API key that happens to be all-digits). Without this, the generic
# type-guessing below would coerce them to int/bool and fail UISettings validation
# (automation.webhookSecret expects str, not int) — every settings read (including
# unrelated endpoints like the scheduler) fails until the value changes.
_STRING_ONLY_SETTINGS_KEYS = {
    "plex.token",
    "tmdb.apiKey",
    "tvdb.apiKey",
    "fanart.apiKey",
    "automation.webhookSecret",
    "automation.webhookAutoLabels",
    "automation.labelToAdd",
    "notifications.discordWebhookUrl",
}


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

        if key in _STRING_ONLY_SETTINGS_KEYS:
            parsed_value = value
        else:
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

def resolve_season_options(options: Dict[str, Any], season_options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge season-specific overrides on top of the base preset options.

    season_options_json may hold either a sparse diff (only the fields that differ from
    options — the format used since v1.6.32) or a full legacy copy of every field — both
    resolve identically here, since a value equal to the base is a harmless no-op overwrite.
    Every consumer that needs the effective season option set must go through this function
    rather than treating season_options as already-complete on its own.
    """
    return {**(options or {}), **(season_options or {})}


def diff_season_options(options: Dict[str, Any], season_options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Reduce season_options to only the fields that actually differ from options.

    This is what keeps season_options_json small instead of duplicating the ~45-field base
    preset. Idempotent — diffing an already-sparse dict returns it unchanged — so it's safe
    to run on both new saves and legacy full-copy data (the startup migration in
    init_database() uses this to shrink existing presets in place).
    """
    options = options or {}
    season_options = season_options or {}
    return {k: v for k, v in season_options.items() if k not in options or options[k] != v}


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
        cursor.execute("SELECT id, template_id, name, options_json, season_options_json FROM presets")
        rows = cursor.fetchall()

    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        template_id = row["template_id"]
        if template_id not in result:
            result[template_id] = {"presets": []}

        # Gracefully handle missing season_options_json column (older DBs) by defaulting to {}
        row_keys = row.keys()
        season_payload = row["season_options_json"] if "season_options_json" in row_keys else "{}"

        result[template_id]["presets"].append({
            "id": row["id"],
            "name": row["name"],
            "options": json.loads(row["options_json"]),
            "season_options": json.loads(season_payload)
        })

    return result


def get_preset(template_id: str, preset_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific preset by template_id and preset_id."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, options_json, season_options_json FROM presets
            WHERE template_id = ? AND id = ?
        """, (template_id, preset_id))
        row = cursor.fetchone()

    if row:
        row_keys = row.keys()
        season_payload = row["season_options_json"] if "season_options_json" in row_keys else "{}"
        return {
            "id": row["id"],
            "name": row["name"],
            "options": json.loads(row["options_json"]),
            "season_options": json.loads(season_payload)
        }
    return None


def save_preset(template_id: str, preset_id: str, name: str, options: Dict[str, Any], season_options: Optional[Dict[str, Any]] = None) -> None:
    """Save or update a preset.

    When season_options is None (not explicitly provided), the existing
    season_options_json is preserved so that saving a series preset from the
    editor never clobbers the user's saved season configuration.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        options_json = json.dumps(options)

        if season_options is not None:
            # Caller explicitly provided season_options — store only what differs from
            # options, regardless of whether the caller sent a full copy or a diff already.
            season_json = json.dumps(diff_season_options(options, season_options))
            cursor.execute("""
                INSERT INTO presets (id, template_id, name, options_json, season_options_json, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    options_json = excluded.options_json,
                    season_options_json = excluded.season_options_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (preset_id, template_id, name, options_json, season_json))
        else:
            # season_options not provided — preserve whatever is already stored.
            cursor.execute("""
                INSERT INTO presets (id, template_id, name, options_json, season_options_json, updated_at)
                VALUES (?, ?, ?, ?, '{}', CURRENT_TIMESTAMP)
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


# ═══════════════════════════════════════════════════════════════════════════
# Overlay Configuration Functions
# ═══════════════════════════════════════════════════════════════════════════

def get_all_overlay_configs() -> List[Dict[str, Any]]:
    """Get all overlay configurations."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, elements_json, streaming_region, created_at, updated_at
            FROM overlay_configs
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "elements": json.loads(row["elements_json"]),
            "streaming_region": row["streaming_region"] or "US",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
        for row in rows
    ]


def get_overlay_config(config_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific overlay configuration by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, elements_json, streaming_region, created_at, updated_at
            FROM overlay_configs
            WHERE id = ?
        """, (config_id,))
        row = cursor.fetchone()

    if row:
        return {
            "id": row["id"],
            "name": row["name"],
            "elements": json.loads(row["elements_json"]),
            "streaming_region": row["streaming_region"] or "US",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
    return None


def save_overlay_config(config_id: str, name: str, elements: List[Dict[str, Any]], streaming_region: str = "US") -> None:
    """Save or update an overlay configuration."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO overlay_configs (id, name, elements_json, streaming_region, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                elements_json = excluded.elements_json,
                streaming_region = excluded.streaming_region,
                updated_at = CURRENT_TIMESTAMP
        """, (config_id, name, json.dumps(elements), streaming_region))
    logger.info(f"[DB] Saved overlay config {config_id} ({name})")


def delete_overlay_config(config_id: str) -> bool:
    """Delete an overlay configuration. Returns True if deleted, False if not found."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Unlink the legacy singular column (kept for old data; no live write path today)
        cursor.execute("""
            UPDATE presets
            SET overlay_config_id = NULL
            WHERE overlay_config_id = ?
        """, (config_id,))

        # Strip this id out of every preset's live overlay_config_ids / overlay_config_ids_below
        # arrays — without this, a deleted config's id lingers forever inside options_json
        # (harmless at render time, since _apply_overlay_element already skips missing configs,
        # but confusing/stale saved state otherwise).
        cursor.execute("SELECT id, template_id, options_json FROM presets")
        for row in cursor.fetchall():
            opts = json.loads(row["options_json"])
            changed = False
            for key in ("overlay_config_ids", "overlay_config_ids_below"):
                ids = opts.get(key)
                if ids and config_id in ids:
                    opts[key] = [cid for cid in ids if cid != config_id]
                    changed = True
            if changed:
                cursor.execute(
                    "UPDATE presets SET options_json = ?, updated_at = CURRENT_TIMESTAMP WHERE template_id = ? AND id = ?",
                    (json.dumps(opts), row["template_id"], row["id"])
                )

        # Then delete the config
        cursor.execute("""
            DELETE FROM overlay_configs WHERE id = ?
        """, (config_id,))
        deleted = cursor.rowcount > 0

    if deleted:
        logger.info(f"[DB] Deleted overlay config {config_id}")
    return deleted


def get_presets_using_overlay_config(config_id: str) -> List[Dict[str, str]]:
    """Find every preset whose saved options reference this overlay config, via the
    live overlay_config_ids / overlay_config_ids_below arrays (the only mechanism
    actually reachable from the UI today — the legacy singular presets.overlay_config_id
    column has no live write path, checked separately below for completeness on older data).
    Used to warn the user, by preset name, before they delete a config that's in use."""
    results = []
    all_presets = get_all_presets()
    for template_id, template_data in all_presets.items():
        for preset in template_data.get("presets", []):
            opts = preset.get("options") or {}
            ids = set(opts.get("overlay_config_ids") or []) | set(opts.get("overlay_config_ids_below") or [])
            if config_id in ids:
                results.append({"template_id": template_id, "preset_id": preset["id"], "name": preset.get("name") or preset["id"]})

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT template_id, id, name FROM presets WHERE overlay_config_id = ?", (config_id,))
        for row in cursor.fetchall():
            if not any(r["template_id"] == row["template_id"] and r["preset_id"] == row["id"] for r in results):
                results.append({"template_id": row["template_id"], "preset_id": row["id"], "name": row["name"] or row["id"]})

    return results


def get_all_overlay_assets() -> List[Dict[str, Any]]:
    """Get all overlay assets."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, file_path, file_type, width, height, created_at
            FROM overlay_assets
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "file_path": row["file_path"],
            "file_type": row["file_type"],
            "width": row["width"],
            "height": row["height"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]


def get_overlay_asset(asset_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific overlay asset by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, file_path, file_type, width, height, created_at
            FROM overlay_assets
            WHERE id = ?
        """, (asset_id,))
        row = cursor.fetchone()

    if row:
        return {
            "id": row["id"],
            "name": row["name"],
            "file_path": row["file_path"],
            "file_type": row["file_type"],
            "width": row["width"],
            "height": row["height"],
            "created_at": row["created_at"]
        }
    return None


def save_overlay_asset(asset_id: str, name: str, file_path: str, file_type: str, width: int, height: int) -> None:
    """Save a new overlay asset."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO overlay_assets (id, name, file_path, file_type, width, height, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                file_path = excluded.file_path,
                file_type = excluded.file_type,
                width = excluded.width,
                height = excluded.height
        """, (asset_id, name, file_path, file_type, width, height))
    logger.info(f"[DB] Saved overlay asset {asset_id} ({name})")


def delete_overlay_asset(asset_id: str) -> bool:
    """Delete an overlay asset. Returns True if deleted, False if not found."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM overlay_assets WHERE id = ?
        """, (asset_id,))
        deleted = cursor.rowcount > 0

    if deleted:
        logger.info(f"[DB] Deleted overlay asset {asset_id}")
    return deleted


def link_preset_to_overlay_config(template_id: str, preset_id: str, overlay_config_id: Optional[str]) -> None:
    """Link a preset to an overlay configuration (or unlink if overlay_config_id is None)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE presets
            SET overlay_config_id = ?
            WHERE template_id = ? AND id = ?
        """, (overlay_config_id, template_id, preset_id))
    logger.info(f"[DB] Linked preset {preset_id} to overlay config {overlay_config_id}")


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
                season_options_json = json.dumps(diff_season_options(options, preset.get("season_options") or {}))
                cursor.execute("""
                    INSERT INTO presets (id, template_id, name, options_json, season_options_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (pid, template_id, name, options_json, season_options_json))
    logger.info("[DB] Replaced all presets from import")


def _slugify(text: str) -> str:
    """Convert a display name to a safe preset ID slug."""
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_') or 'preset'


def merge_presets(preset_data: Dict[str, Dict[str, Any]]) -> None:
    """
    Merge imported presets with existing presets.
    Expected shape: { template_id: { presets: [ {name,options} OR {id,name,options} ] } }

    When 'id' is present: update existing preset with that ID (same-machine backup restore).
    When 'id' is absent (shared compact format): generate a fresh unique ID from the name
    so there can never be a conflict with existing presets.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        for template_id, tpl_data in (preset_data or {}).items():
            presets_list = tpl_data.get("presets", []) if isinstance(tpl_data, dict) else []
            for preset in presets_list:
                name = preset.get("name") or "Imported Preset"
                options = preset.get("options") or {}
                pid = preset.get("id")

                if not pid:
                    # Shared/compact import — generate a fresh ID that won't collide
                    base = _slugify(name)
                    pid = base
                    suffix = int(time.time())
                    while cursor.execute("SELECT 1 FROM presets WHERE id = ?", (pid,)).fetchone():
                        pid = f"{base}_{suffix}"
                        suffix += 1

                options_json = json.dumps(options)
                season_options_json = json.dumps(diff_season_options(options, preset.get("season_options") or {}))
                cursor.execute("""
                    INSERT INTO presets (id, template_id, name, options_json, season_options_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        template_id = excluded.template_id,
                        name = excluded.name,
                        options_json = excluded.options_json,
                        season_options_json = excluded.season_options_json,
                        updated_at = CURRENT_TIMESTAMP
                """, (pid, template_id, name, options_json, season_options_json))
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
    edition: Optional[str] = None,
    logo_url: Optional[str] = None,
    art_url: Optional[str] = None,
    square_art_url: Optional[str] = None,
) -> None:
    """Insert or update cached movie metadata."""
    labels_json = json.dumps(labels or [])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO movie_cache (rating_key, title, year, added_at, tmdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, updated_at, library_id, edition)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(rating_key) DO UPDATE SET
                title = excluded.title,
                year = excluded.year,
                added_at = excluded.added_at,
                tmdb_id = COALESCE(excluded.tmdb_id, movie_cache.tmdb_id),
                poster_url = COALESCE(excluded.poster_url, movie_cache.poster_url),
                logo_url = COALESCE(excluded.logo_url, movie_cache.logo_url),
                art_url = COALESCE(excluded.art_url, movie_cache.art_url),
                square_art_url = COALESCE(excluded.square_art_url, movie_cache.square_art_url),
                labels_json = CASE
                    WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                    ELSE movie_cache.labels_json
                END,
                library_id = COALESCE(excluded.library_id, movie_cache.library_id),
                edition = COALESCE(excluded.edition, movie_cache.edition),
                updated_at = CURRENT_TIMESTAMP
        """, (rating_key, title, year, added_at, tmdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, library_id, edition))


def get_movie_labels(rating_key: str) -> List[str]:
    """Return current cached labels for a movie (empty list if not found)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT labels_json FROM movie_cache WHERE rating_key = ?", (rating_key,))
        row = cursor.fetchone()
        if row and row["labels_json"]:
            return json.loads(row["labels_json"])
        return []


def get_tv_labels(rating_key: str) -> List[str]:
    """Return current cached labels for a TV show (empty list if not found)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT labels_json FROM tv_cache WHERE rating_key = ?", (rating_key,))
        row = cursor.fetchone()
        if row and row["labels_json"]:
            return json.loads(row["labels_json"])
        return []


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


def update_movie_logo_url(rating_key: str, logo_url: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE movie_cache SET logo_url = ?, updated_at = CURRENT_TIMESTAMP WHERE rating_key = ?",
            (logo_url, rating_key)
        )


def update_movie_art_url(rating_key: str, art_url: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE movie_cache SET art_url = ?, updated_at = CURRENT_TIMESTAMP WHERE rating_key = ?",
            (art_url, rating_key)
        )


def update_movie_square_art_url(rating_key: str, square_art_url: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE movie_cache SET square_art_url = ?, updated_at = CURRENT_TIMESTAMP WHERE rating_key = ?",
            (square_art_url, rating_key)
        )


def touch_tmdb_last_seen(media_type: str, tmdb_id: Optional[int], season_index: Optional[int] = None) -> None:
    """Mark a TMDb-identified title as confirmed present in the library right now.

    Called during a scan for every currently-present item that has a resolved tmdb_id.
    Deliberately separate from anything poster-render/send related -- this is purely
    "is this title still here," which is what the reuseCachedPosterDays grace period
    actually needs to measure. See tmdb_last_seen's table comment in init_database().
    """
    if not tmdb_id:
        return
    season_key = season_index if season_index is not None else -1
    with get_db() as conn:
        conn.execute("""
            INSERT INTO tmdb_last_seen (media_type, tmdb_id, season_index, last_seen_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(media_type, tmdb_id, season_index) DO UPDATE SET
                last_seen_at = CURRENT_TIMESTAMP
        """, (media_type, tmdb_id, season_key))


def get_tmdb_days_since_last_seen(media_type: str, tmdb_id: Optional[int], season_index: Optional[int] = None) -> Optional[float]:
    """Days since a TMDb-identified title was last confirmed present in the library.

    Returns None if we have no record at all (e.g. it was cached before this table
    existed, or has never been seen) -- callers should treat None as "unknown, don't
    trust the cache" rather than "just seen."
    """
    if not tmdb_id:
        return None
    season_key = season_index if season_index is not None else -1
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT (julianday('now') - julianday(last_seen_at)) AS days_since
            FROM tmdb_last_seen
            WHERE media_type = ? AND tmdb_id = ? AND season_index = ?
        """, (media_type, tmdb_id, season_key))
        row = cursor.fetchone()
        if not row or row[0] is None:
            return None
        return float(row[0])


def purge_stale_tmdb_last_seen(max_age_days: float) -> List[Dict[str, Any]]:
    """Delete tmdb_last_seen rows that have been absent longer than max_age_days.

    Returns the deleted rows (media_type/tmdb_id/season_index) so the caller can also
    remove the matching on-disk cached-poster file for each -- this function only owns
    the DB row, not the file (that lives under CONFIG_DIR, config.py's job).
    """
    if max_age_days <= 0:
        return []
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT media_type, tmdb_id, season_index FROM tmdb_last_seen
            WHERE (julianday('now') - julianday(last_seen_at)) > ?
        """, (max_age_days,))
        rows = [{"media_type": r[0], "tmdb_id": r[1], "season_index": (r[2] if r[2] != -1 else None)} for r in cursor.fetchall()]
        if rows:
            cursor.execute("""
                DELETE FROM tmdb_last_seen
                WHERE (julianday('now') - julianday(last_seen_at)) > ?
            """, (max_age_days,))
        return rows


def update_movie_media_info(rating_key: str, video_resolution: Optional[str] = None,
                            audio_codec: Optional[str] = None, audio_channels: Optional[str] = None,
                            video_codec: Optional[str] = None, audio_language: Optional[str] = None,
                            edition: Optional[str] = None) -> None:
    """Update media stream info for a cached movie."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE movie_cache
            SET video_resolution = ?, audio_codec = ?, audio_channels = ?,
                video_codec = ?, audio_language = ?, edition = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ?
        """, (video_resolution, audio_codec, audio_channels, video_codec, audio_language, edition, rating_key))


def get_cached_media_info(rating_key: str) -> Optional[Dict[str, str]]:
    """Get cached media info for a movie or TV show. Returns None if not cached."""
    fields = "video_resolution, audio_codec, audio_channels, video_codec, audio_language, edition"
    with get_db() as conn:
        cursor = conn.cursor()
        # Try movie_cache first
        cursor.execute(
            f"SELECT {fields} FROM movie_cache WHERE rating_key = ?",
            (rating_key,)
        )
        row = cursor.fetchone()
        if not row:
            # Try tv_cache
            cursor.execute(
                f"SELECT {fields} FROM tv_cache WHERE rating_key = ?",
                (rating_key,)
            )
            row = cursor.fetchone()
        if not row:
            return None
        # Only return if at least one field is populated
        info: Dict[str, str] = {}
        for field in ("video_resolution", "audio_codec", "audio_channels", "video_codec", "audio_language", "edition"):
            if row[field]:
                info[field] = row[field]
        return info if info else None


def _cleanup_orphaned_posters(rating_keys: List[str]) -> None:
    """Remove poster files for deleted items."""
    try:
        # Import here to avoid circular dependency
        from . import config
        poster_dir = Path(config.POSTER_CACHE_DIR)
        if not poster_dir.exists():
            return

        removed_count = 0
        for rating_key in rating_keys:
            for ext in ("jpg", "jpeg", "png", "webp"):
                poster_file = poster_dir / f"{rating_key}.{ext}"
                if poster_file.exists():
                    try:
                        poster_file.unlink()
                        removed_count += 1
                        logger.debug("[DB] Deleted orphaned poster: %s", poster_file.name)
                    except OSError as e:
                        logger.warning("[DB] Failed to delete poster %s: %s", poster_file, e)

        if removed_count > 0:
            logger.info("[DB] Removed %d orphaned poster files", removed_count)
    except Exception as e:
        logger.warning("[DB] Failed to clean up orphaned posters: %s", e)


def bulk_refresh_cache(movies: List[Dict[str, Any]], library_id: str = "default") -> None:
    """
    Replace cache entries to match the provided movies list.
    Each movie dict should include rating_key, title, year, added_at, tmdb_id?, poster_url?, labels?.
    Also removes orphaned poster files and label cache entries.

    Plex-only -- see upsert_media_server_movies() for the equivalent used by
    Jellyfin/Emby. Orphan detection/deletion is scoped to server_id='plex-1'
    explicitly (not just library_id) so this can never delete a non-Plex
    row that happens to share the same library_id string as a Plex library
    -- confirmed as a real, reproducible bug during Jellyfin-integration
    testing before this scoping was added, not a theoretical concern. See
    CLAUDE.md Quirk #61.
    """
    keys = [m["rating_key"] for m in movies]
    with get_db() as conn:
        cursor = conn.cursor()

        # Get rating_keys that will be deleted (orphaned entries)
        if keys:
            cursor.execute(f"""
                SELECT rating_key FROM movie_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = 'plex-1' AND library_id = ?
            """, keys + [library_id])
            orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]
        else:
            cursor.execute("SELECT rating_key FROM movie_cache WHERE server_id = 'plex-1' AND library_id = ?", (library_id,))
            orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]

        for m in movies:
            labels_json = json.dumps(m.get("labels") or [])
            cursor.execute("""
                INSERT INTO movie_cache (rating_key, title, year, added_at, tmdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, updated_at, library_id, edition)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    added_at = excluded.added_at,
                    tmdb_id = COALESCE(excluded.tmdb_id, movie_cache.tmdb_id),
                    poster_url = COALESCE(excluded.poster_url, movie_cache.poster_url),
                    logo_url = COALESCE(excluded.logo_url, movie_cache.logo_url),
                    art_url = COALESCE(excluded.art_url, movie_cache.art_url),
                    square_art_url = COALESCE(excluded.square_art_url, movie_cache.square_art_url),
                    labels_json = CASE
                        WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                        ELSE movie_cache.labels_json
                    END,
                    library_id = COALESCE(excluded.library_id, movie_cache.library_id),
                    edition = COALESCE(excluded.edition, movie_cache.edition),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                m["rating_key"],
                m["title"],
                m.get("year"),
                m.get("added_at"),
                m.get("tmdb_id"),
                m.get("poster_url"),
                m.get("logo_url"),
                m.get("art_url"),
                m.get("square_art_url"),
                labels_json,
                library_id,
                m.get("edition"),
            ))

        # Drop database entries that are no longer present
        if keys:
            cursor.execute(f"""
                DELETE FROM movie_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = 'plex-1' AND library_id = ?
            """, keys + [library_id])

        # Also delete from label_cache (Plex labels cache)
        if orphaned_keys:
            cursor.execute(f"""
                DELETE FROM label_cache
                WHERE rating_key IN ({",".join("?" for _ in orphaned_keys)})
            """, orphaned_keys)

    # Clean up orphaned poster files on disk
    if orphaned_keys:
        _cleanup_orphaned_posters(orphaned_keys)
        logger.info("[DB] Cleaned up %d orphaned movie entries and posters for library %s", len(orphaned_keys), library_id)


def _coerce_added_at(value) -> Optional[int]:
    """`movie_cache`/`tv_cache.added_at` is meant to always hold Unix epoch
    seconds (Plex's own `addedAt` XML attribute convention -- see
    Movie.addedAt: Optional[int] in schemas.py). Jellyfin's `DateCreated` is
    an ISO 8601 string with .NET-style variable-precision fractional seconds
    (e.g. "2026-06-29T22:27:37.1150226Z") -- JellyfinClient.list_items() now
    converts this to epoch seconds before it's ever written, but this
    defensive read-side coercion also protects any row written before that
    fix, and any future server type that isn't as careful. Never raises --
    an unparseable value returns None rather than letting a bad addedAt
    crash the whole /api/movies or /api/tv-shows response (Pydantic's
    Optional[int] response-model validation has no tolerance for a string
    it can't parse as an int)."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.lstrip("-").isdigit():
            return int(value)
        try:
            from datetime import datetime, timezone
            s = value.rstrip("Z")
            if "." in s:
                main, frac = s.split(".", 1)
                s = f"{main}.{(frac + '000000')[:6]}"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (ValueError, TypeError):
            return None
    return None


_MOVIE_CACHE_SELECT_COLUMNS = "rating_key, title, year, added_at, tmdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, updated_at, library_id, edition, server_id"


def _movie_row_to_dict(row) -> Dict[str, Any]:
    try:
        labels = json.loads(row["labels_json"]) if row["labels_json"] else []
    except json.JSONDecodeError:
        labels = []
    return {
        "rating_key": row["rating_key"],
        "title": row["title"],
        "year": row["year"],
        "addedAt": _coerce_added_at(row["added_at"]),
        "tmdb_id": row["tmdb_id"],
        "poster_url": row["poster_url"],
        "logo_url": row["logo_url"] if "logo_url" in row.keys() else None,
        "art_url": row["art_url"] if "art_url" in row.keys() else None,
        "square_art_url": row["square_art_url"] if "square_art_url" in row.keys() else None,
        "labels": labels,
        "updated_at": row["updated_at"],
        "library_id": row["library_id"] if "library_id" in row.keys() else None,
        "edition": row["edition"] if "edition" in row.keys() else None,
        "server_id": row["server_id"] if "server_id" in row.keys() else None,
    }


def get_cached_movies(library_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return cached movies with labels/poster/tmdb if known. Optionally filter by library.

    Deliberately does NOT filter by server_id -- every existing caller assumes
    Plex, and a real Plex/Jellyfin library_id collision is not realistic (Plex
    ids are short digits, Jellyfin's are GUIDs) -- see Quirk #57/#61/#64. For a
    Library Group spanning multiple (server_id, library_id) pairs, use
    get_cached_movies_multi() instead."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute(f"""
                SELECT {_MOVIE_CACHE_SELECT_COLUMNS}
                FROM movie_cache
                WHERE library_id = ?
                ORDER BY COALESCE(updated_at, added_at) DESC
            """, (library_id,))
        else:
            cursor.execute(f"""
                SELECT {_MOVIE_CACHE_SELECT_COLUMNS}
                FROM movie_cache
                ORDER BY COALESCE(updated_at, added_at) DESC
            """)
        rows = cursor.fetchall()

    return [_movie_row_to_dict(row) for row in rows]


def _dedupe_by_tmdb_id(items: List[Dict[str, Any]], preferred_server_id: str = "plex-1") -> List[Dict[str, Any]]:
    """When a Library Group union (get_cached_movies_multi()/_tv_shows_multi())
    returns the same title present on more than one linked server, this
    collapses each tmdb_id group down to a single displayed item instead of
    showing one card per server -- the real fix for the "duplicate cards"
    artifact linking two servers with overlapping libraries would otherwise
    produce. **Rule**: prefer the row matching `preferred_server_id` when one
    exists in the group, otherwise keep whichever row sorts first (already
    most-recently-updated, per the caller's own ORDER BY). `preferred_server_id`
    defaults to `'plex-1'` -- matching this function's original hardcoded
    behavior exactly, so any caller that doesn't pass a real per-group
    `preferredServerId` (config.py's get_library_group_preferred_server(),
    e.g. a future direct call, or a test) still gets today's sensible
    default, not an undefined one. The
    dropped duplicates' server_ids are preserved on the kept row as
    `also_on`, so a per-item badge can still show "also available on
    Jellyfin" even though only one card renders. **Also preserved**: a
    richer `other_servers` list (`[{server_id, rating_key}, ...]`) for the
    same dropped duplicates -- `also_on` alone (just server_id strings) is
    enough for a badge, but the manual editor's per-server "Current
    Poster/Logo" preview toggle and multi-server send picker need each other
    server's own rating_key too, to actually fetch/send against it (see
    CLAUDE.md's Phase 4b editor-parity Quirk). Items with no tmdb_id (can't
    be matched to anything) are never touched -- kept exactly as-is, one card
    each, matching pre-dedup behavior."""
    by_tmdb: Dict[Any, List[Dict[str, Any]]] = {}
    no_tmdb: List[Dict[str, Any]] = []
    order: List[Any] = []
    for item in items:
        tmdb_id = item.get("tmdb_id")
        if not tmdb_id:
            item["also_on"] = []
            item["other_servers"] = []
            no_tmdb.append(item)
            continue
        if tmdb_id not in by_tmdb:
            by_tmdb[tmdb_id] = []
            order.append(tmdb_id)
        by_tmdb[tmdb_id].append(item)

    deduped: List[Dict[str, Any]] = []
    for tmdb_id in order:
        group = by_tmdb[tmdb_id]
        if len(group) == 1:
            group[0]["also_on"] = []
            group[0]["other_servers"] = []
            deduped.append(group[0])
            continue
        winner = next((g for g in group if g.get("server_id") == preferred_server_id), group[0])
        others = [g for g in group if g is not winner and g.get("server_id")]
        winner["also_on"] = [g["server_id"] for g in others]
        winner["other_servers"] = [
            {"server_id": g["server_id"], "rating_key": g.get("rating_key")}
            for g in others if g.get("rating_key")
        ]
        deduped.append(winner)

    return no_tmdb + deduped


def get_cached_movies_multi(pairs: List[tuple], preferred_server_id: str = "plex-1") -> List[Dict[str, Any]]:
    """Like get_cached_movies(), but for a Library Group spanning several
    (server_id, library_id) pairs (Quirk #62/#64) -- unions every pair's rows
    into one list, then de-duplicates by tmdb_id (_dedupe_by_tmdb_id()) so the
    same movie present on more than one linked server shows as one card, not
    several. `preferred_server_id` is the caller's already-resolved choice for
    THIS specific group (config.py's get_library_group_preferred_server(), or
    'plex-1' when the group has no override set) -- this function itself has
    no settings lookup of its own anymore; a single global preference used to
    live here (Quirk #74's automation.preferredPosterServer) but was replaced
    by a per-group one (schemas.py's LibraryGroup.preferredServerId), since
    one global choice wasn't granular enough once an install has more than
    one linked group at once."""
    if not pairs:
        return []
    with get_db() as conn:
        cursor = conn.cursor()
        where_clause = " OR ".join(["(server_id = ? AND library_id = ?)"] * len(pairs))
        params: List[Any] = []
        for server_id, library_id in pairs:
            params.extend([server_id, library_id])
        cursor.execute(f"""
            SELECT {_MOVIE_CACHE_SELECT_COLUMNS}
            FROM movie_cache
            WHERE {where_clause}
            ORDER BY COALESCE(updated_at, added_at) DESC
        """, params)
        rows = cursor.fetchall()

    return _dedupe_by_tmdb_id([_movie_row_to_dict(row) for row in rows], preferred_server_id)


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
    """Delete rows from movie_cache. If library_id provided, only clear that
    library -- currently only ever called for a Plex library ("remove this
    library" flow, Quirk #33), so scoped to server_id='plex-1' whenever a
    library_id is given, for the same cross-server library_id-collision
    reason as bulk_refresh_cache() (Quirk #61). No library_id (the full
    "clear all cache" admin action) deliberately still clears every server's
    rows -- that's a genuine full reset, not a single-library operation."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("DELETE FROM movie_cache WHERE server_id = 'plex-1' AND library_id = ?", (library_id,))
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
    edition: Optional[str] = None,
    logo_url: Optional[str] = None,
    art_url: Optional[str] = None,
    square_art_url: Optional[str] = None,
) -> None:
    """Insert or update cached TV show metadata."""
    labels_json = json.dumps(labels or [])
    seasons_json = json.dumps(seasons or [])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tv_cache (rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, seasons_json, updated_at, library_id, edition)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(rating_key) DO UPDATE SET
                title = excluded.title,
                year = excluded.year,
                added_at = excluded.added_at,
                tmdb_id = COALESCE(excluded.tmdb_id, tv_cache.tmdb_id),
                tvdb_id = COALESCE(excluded.tvdb_id, tv_cache.tvdb_id),
                poster_url = COALESCE(excluded.poster_url, tv_cache.poster_url),
                logo_url = COALESCE(excluded.logo_url, tv_cache.logo_url),
                art_url = COALESCE(excluded.art_url, tv_cache.art_url),
                square_art_url = COALESCE(excluded.square_art_url, tv_cache.square_art_url),
                labels_json = CASE
                    WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                    ELSE tv_cache.labels_json
                END,
                seasons_json = CASE
                    WHEN excluded.seasons_json IS NOT NULL THEN excluded.seasons_json
                    ELSE tv_cache.seasons_json
                END,
                library_id = COALESCE(excluded.library_id, tv_cache.library_id),
                edition = COALESCE(excluded.edition, tv_cache.edition),
                updated_at = CURRENT_TIMESTAMP
        """, (rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, seasons_json, library_id, edition))


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


def update_tv_logo_url(rating_key: str, logo_url: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE tv_cache SET logo_url = ?, updated_at = CURRENT_TIMESTAMP WHERE rating_key = ?",
            (logo_url, rating_key)
        )


def update_tv_art_url(rating_key: str, art_url: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE tv_cache SET art_url = ?, updated_at = CURRENT_TIMESTAMP WHERE rating_key = ?",
            (art_url, rating_key)
        )


def update_tv_square_art_url(rating_key: str, square_art_url: Optional[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE tv_cache SET square_art_url = ?, updated_at = CURRENT_TIMESTAMP WHERE rating_key = ?",
            (square_art_url, rating_key)
        )


def update_tv_seasons(rating_key: str, seasons: List[Dict[str, Any]], library_id: str = "default") -> None:
    seasons_json = json.dumps(seasons or [])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tv_cache
            SET seasons_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ? AND library_id = COALESCE(library_id, ?)
        """, (seasons_json, rating_key, library_id))


def update_tv_media_info(rating_key: str, video_resolution: Optional[str] = None,
                         audio_codec: Optional[str] = None, audio_channels: Optional[str] = None,
                         video_codec: Optional[str] = None, audio_language: Optional[str] = None,
                         edition: Optional[str] = None) -> None:
    """Update media stream info for a cached TV show."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tv_cache
            SET video_resolution = ?, audio_codec = ?, audio_channels = ?,
                video_codec = ?, audio_language = ?, edition = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE rating_key = ?
        """, (video_resolution, audio_codec, audio_channels, video_codec, audio_language, edition, rating_key))


def bulk_refresh_tv_cache(shows: List[Dict[str, Any]], library_id: str = "default") -> None:
    """
    Replace cache entries to match the provided TV shows list.
    Also removes orphaned poster files and label cache entries.

    Plex-only -- see upsert_media_server_tv_shows() for Jellyfin/Emby. Same
    server_id='plex-1' orphan-scoping fix as bulk_refresh_cache() above, for
    the same reason -- see CLAUDE.md Quirk #61.
    """
    keys = [m["rating_key"] for m in shows]
    with get_db() as conn:
        cursor = conn.cursor()

        # Get rating_keys that will be deleted (orphaned entries)
        if keys:
            cursor.execute(f"""
                SELECT rating_key FROM tv_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = 'plex-1' AND library_id = ?
            """, keys + [library_id])
            orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]
        else:
            cursor.execute("SELECT rating_key FROM tv_cache WHERE server_id = 'plex-1' AND library_id = ?", (library_id,))
            orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]

        for m in shows:
            labels_json = json.dumps(m.get("labels") or [])
            seasons_json = json.dumps(m.get("seasons") or [])
            cursor.execute("""
                INSERT INTO tv_cache (rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, seasons_json, updated_at, library_id, edition)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    added_at = excluded.added_at,
                    tmdb_id = COALESCE(excluded.tmdb_id, tv_cache.tmdb_id),
                    tvdb_id = COALESCE(excluded.tvdb_id, tv_cache.tvdb_id),
                    poster_url = COALESCE(excluded.poster_url, tv_cache.poster_url),
                    logo_url = COALESCE(excluded.logo_url, tv_cache.logo_url),
                    art_url = COALESCE(excluded.art_url, tv_cache.art_url),
                    square_art_url = COALESCE(excluded.square_art_url, tv_cache.square_art_url),
                    labels_json = CASE
                        WHEN excluded.labels_json IS NOT NULL THEN excluded.labels_json
                        ELSE tv_cache.labels_json
                    END,
                    seasons_json = CASE
                        WHEN excluded.seasons_json IS NOT NULL THEN excluded.seasons_json
                        ELSE tv_cache.seasons_json
                    END,
                    library_id = COALESCE(excluded.library_id, tv_cache.library_id),
                    edition = COALESCE(excluded.edition, tv_cache.edition),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                m["rating_key"],
                m["title"],
                m.get("year"),
                m.get("added_at"),
                m.get("tmdb_id"),
                m.get("tvdb_id"),
                m.get("poster_url"),
                m.get("logo_url"),
                m.get("art_url"),
                m.get("square_art_url"),
                labels_json,
                seasons_json,
                library_id,
                m.get("edition"),
            ))

        # Drop database entries that are no longer present
        if keys:
            cursor.execute(f"""
                DELETE FROM tv_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = 'plex-1' AND library_id = ?
            """, keys + [library_id])

        # Also delete from tv_label_cache (Plex labels cache for TV shows)
        if orphaned_keys:
            cursor.execute(f"""
                DELETE FROM tv_label_cache
                WHERE rating_key IN ({",".join("?" for _ in orphaned_keys)})
            """, orphaned_keys)

    # Clean up orphaned poster files on disk
    if orphaned_keys:
        _cleanup_orphaned_posters(orphaned_keys)
        logger.info("[DB] Cleaned up %d orphaned TV show entries and posters for library %s", len(orphaned_keys), library_id)


def upsert_media_server_movies(server_id: str, library_id: str, movies: List[Dict[str, Any]]) -> Dict[str, int]:
    """Like bulk_refresh_cache() above, but for a non-Plex server (Jellyfin/
    Emby) -- deliberately a SEPARATE function, not a shared one, so scanning
    a new server type can never risk the existing, working Plex scan path
    (bulk_refresh_cache() has no server_id parameter at all; every row it
    writes silently gets the 'plex-1' column default -- calling it for
    Jellyfin data would mislabel it). Explicit about server_id on every
    write, and orphan cleanup is scoped to (server_id, library_id) so it can
    never touch another server's or another library's rows. See CLAUDE.md
    Quirk #61.

    No poster/logo/backdrop/square_art fetching here -- that's separate,
    later work (mirroring fetch_and_cache_poster()'s pattern via
    JellyfinClient.download_image()). This just establishes the library
    membership itself. No on-disk cache-file cleanup either (nothing this
    function writes creates cache files yet)."""
    keys = [m["rating_key"] for m in movies]
    with get_db() as conn:
        cursor = conn.cursor()

        if keys:
            cursor.execute(f"""
                SELECT rating_key FROM movie_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = ? AND library_id = ?
            """, keys + [server_id, library_id])
        else:
            cursor.execute(
                "SELECT rating_key FROM movie_cache WHERE server_id = ? AND library_id = ?",
                (server_id, library_id),
            )
        orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]

        inserted = 0
        updated = 0
        for m in movies:
            cursor.execute("SELECT 1 FROM movie_cache WHERE rating_key = ?", (m["rating_key"],))
            existed = cursor.fetchone() is not None
            cursor.execute("""
                INSERT INTO movie_cache (rating_key, server_id, title, year, added_at, tmdb_id, tvdb_id, labels_json, updated_at, library_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    server_id = excluded.server_id,
                    title = excluded.title,
                    year = excluded.year,
                    added_at = excluded.added_at,
                    tmdb_id = COALESCE(excluded.tmdb_id, movie_cache.tmdb_id),
                    tvdb_id = COALESCE(excluded.tvdb_id, movie_cache.tvdb_id),
                    library_id = excluded.library_id,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                m["rating_key"], server_id, m["title"], m.get("year"), m.get("added_at"),
                m.get("tmdb_id"), m.get("tvdb_id"), json.dumps(m.get("labels") or []), library_id,
            ))
            updated += 1 if existed else 0
            inserted += 0 if existed else 1

        if keys:
            cursor.execute(f"""
                DELETE FROM movie_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = ? AND library_id = ?
            """, keys + [server_id, library_id])

    logger.info("[DB] Media server '%s' library '%s': %d movies upserted (%d new, %d updated), %d removed",
                server_id, library_id, len(movies), inserted, updated, len(orphaned_keys))
    return {"inserted": inserted, "updated": updated, "removed": len(orphaned_keys)}


def upsert_media_server_tv_shows(server_id: str, library_id: str, shows: List[Dict[str, Any]]) -> Dict[str, int]:
    """TV-show mirror of upsert_media_server_movies() above -- same reasoning,
    same deliberate separation from bulk_refresh_tv_cache()."""
    keys = [m["rating_key"] for m in shows]
    with get_db() as conn:
        cursor = conn.cursor()

        if keys:
            cursor.execute(f"""
                SELECT rating_key FROM tv_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = ? AND library_id = ?
            """, keys + [server_id, library_id])
        else:
            cursor.execute(
                "SELECT rating_key FROM tv_cache WHERE server_id = ? AND library_id = ?",
                (server_id, library_id),
            )
        orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]

        inserted = 0
        updated = 0
        for m in shows:
            cursor.execute("SELECT 1 FROM tv_cache WHERE rating_key = ?", (m["rating_key"],))
            existed = cursor.fetchone() is not None
            cursor.execute("""
                INSERT INTO tv_cache (rating_key, server_id, title, year, added_at, tmdb_id, tvdb_id, labels_json, updated_at, library_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    server_id = excluded.server_id,
                    title = excluded.title,
                    year = excluded.year,
                    added_at = excluded.added_at,
                    tmdb_id = COALESCE(excluded.tmdb_id, tv_cache.tmdb_id),
                    tvdb_id = COALESCE(excluded.tvdb_id, tv_cache.tvdb_id),
                    library_id = excluded.library_id,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                m["rating_key"], server_id, m["title"], m.get("year"), m.get("added_at"),
                m.get("tmdb_id"), m.get("tvdb_id"), json.dumps(m.get("labels") or []), library_id,
            ))
            updated += 1 if existed else 0
            inserted += 0 if existed else 1

        if keys:
            cursor.execute(f"""
                DELETE FROM tv_cache
                WHERE rating_key NOT IN ({",".join("?" for _ in keys)}) AND server_id = ? AND library_id = ?
            """, keys + [server_id, library_id])

    logger.info("[DB] Media server '%s' library '%s': %d TV shows upserted (%d new, %d updated), %d removed",
                server_id, library_id, len(shows), inserted, updated, len(orphaned_keys))
    return {"inserted": inserted, "updated": updated, "removed": len(orphaned_keys)}


_TV_CACHE_SELECT_COLUMNS = "rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, logo_url, art_url, square_art_url, labels_json, seasons_json, updated_at, library_id, edition, server_id"


def _tv_row_to_dict(row) -> Dict[str, Any]:
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
        "addedAt": _coerce_added_at(row["added_at"]),
        "tmdb_id": row["tmdb_id"],
        "tvdb_id": row["tvdb_id"] if "tvdb_id" in row.keys() else None,
        "poster_url": row["poster_url"],
        "logo_url": row["logo_url"] if "logo_url" in row.keys() else None,
        "art_url": row["art_url"] if "art_url" in row.keys() else None,
        "square_art_url": row["square_art_url"] if "square_art_url" in row.keys() else None,
        "labels": labels,
        "seasons": seasons,
        "updated_at": row["updated_at"],
        "library_id": row["library_id"] if "library_id" in row.keys() else None,
        "edition": row["edition"] if "edition" in row.keys() else None,
        "server_id": row["server_id"] if "server_id" in row.keys() else None,
    }


def get_cached_tv_shows(library_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """See get_cached_movies()'s docstring -- identical server_id-agnostic
    single-library behavior; use get_cached_tv_shows_multi() for a Library
    Group spanning several (server_id, library_id) pairs."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute(f"""
                SELECT {_TV_CACHE_SELECT_COLUMNS}
                FROM tv_cache
                WHERE library_id = ?
                ORDER BY COALESCE(updated_at, added_at) DESC
            """, (library_id,))
        else:
            cursor.execute(f"""
                SELECT {_TV_CACHE_SELECT_COLUMNS}
                FROM tv_cache
                ORDER BY COALESCE(updated_at, added_at) DESC
            """)
        rows = cursor.fetchall()

    return [_tv_row_to_dict(row) for row in rows]


def set_library_group_preferred_server(server_id: str, library_id: str, media_type: str, preferred_server_id: str) -> Optional[Dict[str, Any]]:
    """Updates just one Library Group's `preferredServerId` in place and saves
    immediately -- backs the Movies/TV grid toolbar's live "prefer" dropdown
    (Quirk #85), which persists on every change like the page's other
    controls, unlike every other Library Group field (name, auto-generate,
    labels), which is only edited via Settings -> Libraries and saved on that
    page's own Save button. Returns the updated group dict, or None if no
    group matches the given (server_id, library_id, media_type)."""
    settings_row = get_ui_settings() or {}
    groups = settings_row.get("libraryGroups") or []
    updated_group = None
    for group in groups:
        if group.get("mediaType") != media_type:
            continue
        members = group.get("members") or []
        if any(m.get("serverId") == server_id and m.get("libraryId") == str(library_id) for m in members):
            group["preferredServerId"] = preferred_server_id
            updated_group = group
            break
    if updated_group is None:
        return None
    settings_row["libraryGroups"] = groups
    save_ui_settings(settings_row)
    return updated_group


def get_cached_tv_shows_multi(pairs: List[tuple], preferred_server_id: str = "plex-1") -> List[Dict[str, Any]]:
    """TV mirror of get_cached_movies_multi() -- see its docstring and
    _dedupe_by_tmdb_id()'s for the Library Group union + de-duplication
    behavior, and the `preferred_server_id` parameter's own docstring for why
    this no longer reads a global setting itself."""
    if not pairs:
        return []
    with get_db() as conn:
        cursor = conn.cursor()
        where_clause = " OR ".join(["(server_id = ? AND library_id = ?)"] * len(pairs))
        params: List[Any] = []
        for server_id, library_id in pairs:
            params.extend([server_id, library_id])
        cursor.execute(f"""
            SELECT {_TV_CACHE_SELECT_COLUMNS}
            FROM tv_cache
            WHERE {where_clause}
            ORDER BY COALESCE(updated_at, added_at) DESC
        """, params)
        rows = cursor.fetchall()

    return _dedupe_by_tmdb_id([_tv_row_to_dict(row) for row in rows], preferred_server_id)


def get_cached_tv_show(rating_key: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rating_key, title, year, added_at, tmdb_id, tvdb_id, poster_url, logo_url, labels_json, seasons_json, updated_at, library_id
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
        "addedAt": _coerce_added_at(row["added_at"]),
        "tmdb_id": row["tmdb_id"],
        "tvdb_id": row["tvdb_id"] if "tvdb_id" in row.keys() else None,
        "poster_url": row["poster_url"],
        "logo_url": row["logo_url"] if "logo_url" in row.keys() else None,
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
    """See clear_movie_cache() above for the server_id='plex-1' scoping
    rationale when library_id is given (Quirk #61)."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("DELETE FROM tv_cache WHERE server_id = 'plex-1' AND library_id = ?", (library_id,))
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
    """
    Replace cache entries to match the provided collections list.
    Also removes orphaned poster files.

    Plex-only -- orphan detection/deletion scoped to server_id='plex-1' for
    the same reason as bulk_refresh_cache()/bulk_refresh_tv_cache() above
    (a Jellyfin/Emby BoxSet collection row, if that's ever built, must never
    be at risk from a Plex collection scan sharing the same library_id
    string). See CLAUDE.md Quirk #61.
    """
    # Defensively skip any entry with no rating_key — a prior bug (fixed) briefly
    # let a shape-mismatched caller write rows with rating_key=NULL here. Since
    # SQL's `NULL NOT IN (...)` is neither true nor false, the orphan-cleanup
    # query below silently could never match/delete those rows once written —
    # they'd sit as permanent duplicate "blank poster" entries. Guarding the
    # insert here stops new ones; the `IS NULL OR` below cleans up existing ones.
    collections = [c for c in collections if c.get("rating_key")]
    keys = [c["rating_key"] for c in collections]
    with get_db() as conn:
        cursor = conn.cursor()

        # Get rating_keys that will be deleted (orphaned entries) — `rating_key IS
        # NULL OR rating_key NOT IN (...)` so any already-corrupted NULL-keyed
        # rows are finally caught too (plain `NOT IN` never matches NULL).
        if keys:
            cursor.execute(f"""
                SELECT rating_key FROM collection_cache
                WHERE (rating_key IS NULL OR rating_key NOT IN ({",".join("?" for _ in keys)})) AND server_id = 'plex-1' AND library_id = ?
            """, keys + [library_id])
            orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]
        else:
            cursor.execute("SELECT rating_key FROM collection_cache WHERE server_id = 'plex-1' AND library_id = ?", (library_id,))
            orphaned_keys = [row["rating_key"] for row in cursor.fetchall()]

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

        # Drop database entries that are no longer present (including any
        # NULL-keyed rows — see the IS NULL note above). Deliberately left as
        # the original `if keys:` guard — an empty incoming list intentionally
        # leaves existing rows alone rather than wiping the cache, in case
        # that's a transient/failed fetch rather than a genuinely empty library.
        if keys:
            cursor.execute(f"""
                DELETE FROM collection_cache
                WHERE (rating_key IS NULL OR rating_key NOT IN ({",".join("?" for _ in keys)})) AND server_id = 'plex-1' AND library_id = ?
            """, keys + [library_id])

    # Clean up orphaned poster files on disk
    if orphaned_keys:
        _cleanup_orphaned_posters(orphaned_keys)
        logger.info("[DB] Cleaned up %d orphaned collection entries and posters for library %s", len(orphaned_keys), library_id)


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
            "addedAt": _coerce_added_at(row["added_at"]),
            "poster_url": row["poster_url"],
            "updated_at": row["updated_at"],
            "library_id": row["library_id"],
        })
    return out


def get_collection_tmdb_id(rating_key: str) -> Optional[int]:
    """Previously-resolved TMDb collection ID for a Plex collection, if any.
    None means "never looked up yet" — distinct from a stored 0/negative
    sentinel, which callers may use for "looked up, no match found"."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tmdb_collection_id FROM collection_cache WHERE rating_key = ?", (rating_key,))
        row = cursor.fetchone()
    if row is None or row["tmdb_collection_id"] is None:
        return None
    return int(row["tmdb_collection_id"])


def set_collection_tmdb_id(rating_key: str, tmdb_collection_id: Optional[int]) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE collection_cache SET tmdb_collection_id = ? WHERE rating_key = ?",
            (tmdb_collection_id, rating_key),
        )


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
    """See clear_movie_cache() above for the server_id='plex-1' scoping
    rationale when library_id is given (Quirk #61)."""
    with get_db() as conn:
        cursor = conn.cursor()
        if library_id:
            cursor.execute("DELETE FROM collection_cache WHERE server_id = 'plex-1' AND library_id = ?", (library_id,))
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

def get_title_for_rating_key(rating_key: str) -> tuple:
    """Return (title, year) for a rating_key from movie_cache or poster_history. Falls back to (None, None)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT title, year FROM movie_cache WHERE rating_key = ? LIMIT 1", (rating_key,)
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT title, year FROM tv_cache WHERE rating_key = ? LIMIT 1", (rating_key,)
            ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT title, year FROM poster_history WHERE rating_key = ? ORDER BY created_at DESC LIMIT 1",
                (rating_key,)
            ).fetchone()
    if row:
        return row["title"], row["year"]
    return None, None


def get_server_id_for_rating_key(rating_key: str) -> str:
    """Which configured media server (Quirk #57's `mediaServers` model) a
    rating_key/item id belongs to -- checked against movie_cache/tv_cache/
    collection_cache in that order. Defaults to 'plex-1' when not found
    (matches every pre-multi-server assumption already baked into this app --
    a rating_key that isn't cached anywhere yet is far more likely to be a
    Plex item mid-scan than anything else, and 'plex-1' is always a safe
    fallback since every existing single-server install has exactly that
    server_id on every real row). Used by fetch_and_cache_poster()/
    art_cache.py's fetch_and_cache() to route an asset fetch to the right
    MediaServerClient instead of always assuming Plex."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT server_id FROM movie_cache WHERE rating_key = ? LIMIT 1", (rating_key,)
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT server_id FROM tv_cache WHERE rating_key = ? LIMIT 1", (rating_key,)
            ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT server_id FROM collection_cache WHERE rating_key = ? LIMIT 1", (rating_key,)
            ).fetchone()
    if row and row["server_id"]:
        return row["server_id"]
    return "plex-1"


def get_ids_for_rating_key(rating_key: str) -> tuple:
    """Return (tmdb_id, tvdb_id) for a rating_key from movie_cache/tv_cache,
    whichever known cache columns exist (movie_cache has no tvdb_id column
    read here needed by its own endpoint, but sharing one function for both
    is simpler than two near-identical ones). (None, None) if not cached.

    Used by api_movie_tmdb()/api_tv_show_tmdb() as the non-Plex fallback --
    those two endpoints are otherwise Plex-only (a direct
    /library/metadata/{rating_key} fetch), which always fails for a
    Jellyfin/Emby item id, silently starving the manual editor of any
    poster/logo candidates to show (EditorPane.vue bails out entirely once
    tmdb_id comes back null). The tmdb_id/tvdb_id are already known from
    whatever scan/merge cached this row in the first place -- no live fetch
    needed for a non-Plex item."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT tmdb_id, NULL as tvdb_id FROM movie_cache WHERE rating_key = ? LIMIT 1", (rating_key,)
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT tmdb_id, tvdb_id FROM tv_cache WHERE rating_key = ? LIMIT 1", (rating_key,)
            ).fetchone()
    if row:
        return row["tmdb_id"], row["tvdb_id"]
    return None, None


def record_poster_history(
    rating_key: str,
    library_id: Optional[str],
    title: Optional[str],
    year: Optional[int],
    template_id: Optional[str],
    preset_id: Optional[str],
    action: str,
    save_path: Optional[str] = None,
    source: str = 'manual',
    poster_fallback_used: bool = False,
    poster_fallback_template: Optional[str] = None,
    poster_fallback_preset: Optional[str] = None,
    logo_fallback_used: bool = False,
    logo_fallback_template: Optional[str] = None,
    logo_fallback_preset: Optional[str] = None,
    poster_data: Optional[bytes] = None,
    status: str = 'success',
    error_message: Optional[str] = None,
) -> None:
    """Record a poster-related action for tracking, including fallback information."""
    from .config import HISTORY_THUMBNAIL_DIR
    from PIL import Image
    from io import BytesIO
    import uuid

    thumbnail_path = None

    # Save a thumbnail copy if poster_data is provided
    if poster_data:
        try:
            # Generate unique filename
            thumb_filename = f"{rating_key}_{uuid.uuid4().hex[:8]}.jpg"
            thumb_path = Path(HISTORY_THUMBNAIL_DIR) / thumb_filename

            # Create a smaller thumbnail (max 400px wide) to save space
            img = Image.open(BytesIO(poster_data))
            max_width = 400
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Save as JPEG with moderate quality
            img.convert("RGB").save(str(thumb_path), "JPEG", quality=80)
            thumbnail_path = str(thumb_path)
            logger.debug(f"[HISTORY] Saved thumbnail: {thumbnail_path}")
        except Exception as e:
            logger.warning(f"[HISTORY] Failed to save thumbnail for {rating_key}: {e}")

    with get_db() as conn:
        cursor = conn.cursor()

        # Insert new history record (keep all records for full history)
        cursor.execute(
            """
            INSERT INTO poster_history
            (rating_key, library_id, title, year, template_id, preset_id, action, save_path, source,
             poster_fallback_used, poster_fallback_template, poster_fallback_preset,
             logo_fallback_used, logo_fallback_template, logo_fallback_preset, thumbnail_path,
             status, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                source,
                1 if poster_fallback_used else 0,
                poster_fallback_template,
                poster_fallback_preset,
                1 if logo_fallback_used else 0,
                logo_fallback_template,
                logo_fallback_preset,
                thumbnail_path,
                status,
                error_message,
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
        row_keys = row.keys()
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
            "source": row["source"] if "source" in row_keys else "manual",
            "poster_fallback_used": bool(row["poster_fallback_used"]) if "poster_fallback_used" in row_keys else False,
            "poster_fallback_template": row["poster_fallback_template"] if "poster_fallback_template" in row_keys else None,
            "poster_fallback_preset": row["poster_fallback_preset"] if "poster_fallback_preset" in row_keys else None,
            "logo_fallback_used": bool(row["logo_fallback_used"]) if "logo_fallback_used" in row_keys else False,
            "logo_fallback_template": row["logo_fallback_template"] if "logo_fallback_template" in row_keys else None,
            "logo_fallback_preset": row["logo_fallback_preset"] if "logo_fallback_preset" in row_keys else None,
            "created_at": row["created_at"],
        })
    return out


def get_poster_history_by_id(history_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single poster history record by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM poster_history WHERE id = ?", (history_id,))
        row = cursor.fetchone()

    if not row:
        return None

    row_keys = row.keys()
    return {
        "id": row["id"],
        "rating_key": row["rating_key"],
        "library_id": row["library_id"],
        "title": row["title"],
        "year": row["year"],
        "template_id": row["template_id"],
        "preset_id": row["preset_id"],
        "action": row["action"],
        "save_path": row["save_path"],
        "source": row["source"] if "source" in row_keys else "manual",
        "poster_fallback_used": bool(row["poster_fallback_used"]) if "poster_fallback_used" in row_keys else False,
        "poster_fallback_template": row["poster_fallback_template"] if "poster_fallback_template" in row_keys else None,
        "poster_fallback_preset": row["poster_fallback_preset"] if "poster_fallback_preset" in row_keys else None,
        "logo_fallback_used": bool(row["logo_fallback_used"]) if "logo_fallback_used" in row_keys else False,
        "logo_fallback_template": row["logo_fallback_template"] if "logo_fallback_template" in row_keys else None,
        "logo_fallback_preset": row["logo_fallback_preset"] if "logo_fallback_preset" in row_keys else None,
        "thumbnail_path": row["thumbnail_path"] if "thumbnail_path" in row_keys else None,
        "created_at": row["created_at"],
    }


def get_poster_status(
    library_id: Optional[str] = None,
    rating_keys: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return latest sent/saved status per rating_key."""
    clauses = []
    params: List[Any] = []

    if library_id:
        clauses.append("library_id = ?")
        params.append(library_id)

    if rating_keys:
        placeholders = ",".join(["?"] * len(rating_keys))
        clauses.append(f"rating_key IN ({placeholders})")
        params.extend(rating_keys)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    query = f"""
        SELECT rating_key, action, template_id, preset_id, created_at
        FROM poster_history
        {where_clause}
        ORDER BY datetime(created_at) DESC
    """

    result: Dict[str, Dict[str, Any]] = {}
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    for row in rows:
        rating_key = row["rating_key"]
        action = row["action"]
        created_at = row["created_at"]
        template_id = row["template_id"]
        preset_id = row["preset_id"]

        if rating_key not in result:
            result[rating_key] = {
                "sent": None,
                "saved": None,
            }

        # Record the first (latest) occurrence for each action
        if action == "sent_to_plex" and result[rating_key]["sent"] is None:
            result[rating_key]["sent"] = {
                "template_id": template_id,
                "preset_id": preset_id,
                "created_at": created_at,
            }
        elif action == "saved_local" and result[rating_key]["saved"] is None:
            result[rating_key]["saved"] = {
                "template_id": template_id,
                "preset_id": preset_id,
                "created_at": created_at,
            }

    return result


# ============================================
#  Poster Retry Queue Operations
# ============================================

# Reason used when a user manually queues an item from the editor because the
# poster they picked right now isn't textless yet -- distinct from the reasons
# batch.py generates automatically (no_logo, poster_fallback, etc.). Checked by
# batch.py/scheduler.py/history.py to require a genuinely textless poster before
# resolving the item, since the ordinary needs_retry check alone doesn't catch
# this case when fallbackPosterAction is "continue" (the default) -- see
# require_textless_poster in schemas.py.
RETRY_REASON_MANUAL_TEXTLESS = "manual_textless_pending"


def add_to_retry_queue(
    rating_key: str,
    media_type: str,
    library_id: Optional[str],
    template_id: str,
    preset_id: str,
    title: Optional[str],
    reason: str,
) -> None:
    """Add or update an item in the poster retry queue."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO poster_retry_queue
                (rating_key, media_type, library_id, template_id, preset_id, title, reason,
                 first_queued_at, last_attempted_at, retry_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, 'pending')
            ON CONFLICT(rating_key) DO UPDATE SET
                template_id = excluded.template_id,
                preset_id = excluded.preset_id,
                reason = excluded.reason,
                status = 'pending',
                last_attempted_at = CURRENT_TIMESTAMP
        """, (rating_key, media_type, library_id, template_id, preset_id, title, reason))
    logger.debug("[RETRY] Queued %s (%s) reason=%s", rating_key, media_type, reason)


def update_retry_attempt(rating_key: str) -> None:
    """Increment retry_count and update last_attempted_at for an item."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE poster_retry_queue
            SET retry_count = retry_count + 1,
                last_attempted_at = CURRENT_TIMESTAMP
            WHERE rating_key = ?
        """, (rating_key,))


def resolve_retry_queue_item(rating_key: str, status: str = "resolved") -> None:
    """Mark an item as resolved or manually overridden."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE poster_retry_queue SET status = ? WHERE rating_key = ?
        """, (status, rating_key))
    logger.debug("[RETRY] Resolved %s as %s", rating_key, status)


def remove_from_retry_queue(rating_key: str) -> None:
    """Remove an item from the retry queue (used on manual send)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM poster_retry_queue WHERE rating_key = ?", (rating_key,))
    logger.debug("[RETRY] Removed %s from retry queue (manual override)", rating_key)


def clear_retry_queue_for_library(library_id: str) -> int:
    """Remove every retry queue entry for a library (used when a library is removed
    from Settings — there's no point retrying posters for a library Simposter no
    longer tracks). Returns the number of rows removed."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM poster_retry_queue WHERE library_id = ?", (library_id,))
        removed = cursor.rowcount
    logger.info("[RETRY] Cleared %d retry queue entries for library %s", removed, library_id)
    return removed


def get_pending_retry_items(max_attempts: int = 0) -> List[Dict[str, Any]]:
    """
    Return all pending retry items, optionally filtered by max_attempts.
    max_attempts=0 means unlimited.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        if max_attempts > 0:
            cursor.execute("""
                SELECT * FROM poster_retry_queue
                WHERE status = 'pending' AND retry_count < ?
                ORDER BY last_attempted_at ASC
            """, (max_attempts,))
        else:
            cursor.execute("""
                SELECT * FROM poster_retry_queue
                WHERE status = 'pending'
                ORDER BY last_attempted_at ASC
            """)
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_retry_queue(include_resolved: bool = False) -> List[Dict[str, Any]]:
    """Return retry queue items for UI display."""
    with get_db() as conn:
        cursor = conn.cursor()
        if include_resolved:
            cursor.execute("""
                SELECT * FROM poster_retry_queue ORDER BY first_queued_at DESC LIMIT 500
            """)
        else:
            # "abandoned" items are deleted outright when detected (see scheduler.py) rather
            # than kept and filtered here -- an abandoned item's title commonly reappears
            # under a brand-new rating_key (delete-then-re-add, see Quirk #41), and leaving
            # the old abandoned row around made that look like a duplicate queue entry for
            # the same title. This clause only still matters for a legacy DB with rows from
            # before that change (also swept once on startup, see init_database()).
            cursor.execute("""
                SELECT * FROM poster_retry_queue
                WHERE status = 'pending'
                ORDER BY first_queued_at DESC LIMIT 500
            """)
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_retry_queue_count() -> int:
    """Return count of pending retry items."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM poster_retry_queue WHERE status = 'pending'")
        return cursor.fetchone()[0]


def has_poster_been_sent(rating_key: str) -> bool:
    """Check if a poster has already been sent to Plex for this rating_key."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM poster_history WHERE rating_key = ? AND action = 'sent_to_plex' LIMIT 1",
            (rating_key,),
        )
        return cursor.fetchone() is not None


_STREAMING_PROVIDER_TTL = 604800  # 7 days


def get_cached_providers(tmdb_id, media_type: str, region: str):
    """Return cached flatrate provider list for (tmdb_id, media_type, region), or None if missing/stale."""
    import json as _json
    import time as _time
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT providers_json, fetched_at FROM streaming_provider_cache WHERE tmdb_id=? AND media_type=? AND region=?",
            (str(tmdb_id), media_type, region),
        )
        row = cursor.fetchone()
        if row and row["fetched_at"] and (_time.time() - row["fetched_at"]) < _STREAMING_PROVIDER_TTL:
            try:
                return _json.loads(row["providers_json"] or "[]")
            except Exception:
                return None
    return None


def upsert_cached_providers(tmdb_id, media_type: str, region: str, providers: list) -> None:
    """Insert or replace streaming provider cache entry."""
    import json as _json
    import time as _time
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO streaming_provider_cache (tmdb_id, media_type, region, providers_json, fetched_at) VALUES (?,?,?,?,?)",
            (str(tmdb_id), media_type, region, _json.dumps(providers), int(_time.time())),
        )


# ---------------------------------------------------------------------------
# Cleanup tool (backend/api/cleanup.py) -- reference-set lookups used to decide
# whether a cached file/row is still "known good" (referenced by something
# real) or an orphan candidate. See CLAUDE.md's Cleanup Tool quirk.
# ---------------------------------------------------------------------------

def get_all_known_rating_keys() -> set:
    """Every rating_key Simposter currently has a movie_cache/tv_cache row for --
    the reference set disk-cache orphan detection is diffed against. Reflects
    the state as of the last successful library scan, not a live Plex check."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT rating_key FROM movie_cache")
        keys = {row["rating_key"] for row in cursor.fetchall()}
        cursor.execute("SELECT rating_key FROM tv_cache")
        keys.update(row["rating_key"] for row in cursor.fetchall())
    return keys


def get_all_preset_reference_blob() -> str:
    """Every preset's options_json + season_options_json, concatenated into one
    string. Used for a cheap `needle in blob` substring check (e.g. "is this
    uploaded file's URL referenced by any saved preset") instead of one query
    per candidate file -- fine here since presets are small and few, and this
    only needs to answer "does this string appear anywhere," not parse JSON."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT options_json, season_options_json FROM presets")
        rows = cursor.fetchall()
    return "\n".join(f"{r['options_json']}\n{r['season_options_json']}" for r in rows)


def get_all_overlay_elements_blob() -> str:
    """Every overlay_configs.elements_json, concatenated -- same substring-check
    approach as get_all_preset_reference_blob(), used to find overlay_assets
    rows no longer referenced by any overlay config's badge/image elements."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT elements_json FROM overlay_configs")
        rows = cursor.fetchall()
    return "\n".join(r["elements_json"] or "" for r in rows)


def get_all_preset_template_pairs() -> set:
    """Every (template_id, preset_id) pair with a saved preset -- the reference
    set the overlay effect cache (config/overlays/{template_id}/{preset_id}.png)
    is diffed against. A file whose pair isn't in this set means the preset it
    was rendered for has since been deleted or renamed."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT template_id, id FROM presets")
        return {(row["template_id"], row["id"]) for row in cursor.fetchall()}


def get_poster_history_count_older_than(days: int) -> int:
    """Row count for the 'old History entries' cleanup category preview -- kept
    separate from the export+delete function below so the scan/report step
    never mutates anything."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as c FROM poster_history WHERE created_at < datetime('now', ?)",
            (f"-{int(days)} days",),
        )
        row = cursor.fetchone()
        return int(row["c"]) if row else 0


def export_and_delete_poster_history_older_than(days: int) -> list:
    """Used only by the actual 'Clean Selected' step (never by the dry-run scan)
    -- selects every poster_history row older than `days`, returns them as plain
    dicts (the caller writes these to the trash batch's JSON snapshot before
    this function deletes the rows), all inside one transaction so a crash
    between select and delete can't lose or duplicate rows."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM poster_history WHERE created_at < datetime('now', ?)",
            (f"-{int(days)} days",),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        if rows:
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))
            cursor.execute(f"DELETE FROM poster_history WHERE id IN ({placeholders})", ids)
    logger.info("[CLEANUP] Exported and deleted %d old poster_history rows (older than %d days)", len(rows), days)
    return rows


def restore_poster_history_rows(rows: list) -> None:
    """Re-inserts poster_history rows previously removed by
    export_and_delete_poster_history_older_than() -- used by the trash
    'Restore' action. Uses INSERT OR IGNORE on the original id so restoring
    the same batch twice is a harmless no-op rather than a duplicate/error."""
    if not rows:
        return
    with get_db() as conn:
        cursor = conn.cursor()
        for r in rows:
            cols = list(r.keys())
            placeholders = ",".join("?" * len(cols))
            cursor.execute(
                f"INSERT OR IGNORE INTO poster_history ({','.join(cols)}) VALUES ({placeholders})",
                [r[c] for c in cols],
            )
    logger.info("[CLEANUP] Restored %d poster_history rows", len(rows))


# Initialize database on module import
init_database()
# Copy environment variables to UI settings on startup
copy_env_to_ui_settings()
