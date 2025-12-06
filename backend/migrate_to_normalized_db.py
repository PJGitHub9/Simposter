# backend/migrate_to_normalized_db.py
"""Migration script to convert old ui_settings table to normalized settings table."""
import sqlite3
import json
import shutil
import os
from pathlib import Path

def _get_db_path():
    """Get database path without importing database module."""
    settings_dir = os.environ.get("SETTINGS_DIR")
    if not settings_dir:
        backend_dir = Path(__file__).parent
        repo_root = backend_dir.parent
        config_dir = os.environ.get("CONFIG_DIR")
        if config_dir:
            config_path = Path(config_dir)
            if not config_path.is_absolute():
                config_path = repo_root / config_path
        else:
            config_path = repo_root / "config"
        settings_dir = str(config_path / "settings")
    return Path(settings_dir) / "simposter.db"

def migrate_to_normalized_schema():
    """Migrate from old ui_settings JSON blob to normalized settings table."""

    DB_PATH = _get_db_path()

    print(f"[MIGRATE] Starting migration to normalized schema...")
    print(f"[MIGRATE] Database: {DB_PATH}")

    if not DB_PATH.exists():
        print("[MIGRATE] No database found, nothing to migrate")
        return

    # Backup the database first
    backup_path = DB_PATH.with_suffix('.db.backup')
    shutil.copy2(DB_PATH, backup_path)
    print(f"[MIGRATE] Created backup at {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check if old ui_settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ui_settings'")
        if not cursor.fetchone():
            print("[MIGRATE] No ui_settings table found, nothing to migrate")
            return

        # Get data from old table
        cursor.execute("SELECT settings_json FROM ui_settings WHERE id = 1")
        row = cursor.fetchone()

        if not row:
            print("[MIGRATE] No settings found in ui_settings table")
            return

        settings_data = json.loads(row["settings_json"])
        print(f"[MIGRATE] Found settings data with {len(settings_data)} top-level keys")

        # Check if new settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        if not cursor.fetchone():
            print("[MIGRATE] Creating new settings table...")
            cursor.execute("""
                CREATE TABLE settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX idx_settings_category ON settings(category)
            """)

        # Clear existing data in new table
        cursor.execute("DELETE FROM settings")

        # Migrate data to new normalized structure
        total_settings = 0
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
                    total_settings += 1
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
                total_settings += 1

        conn.commit()
        print(f"[MIGRATE] Migrated {total_settings} settings to normalized table")

        # Drop old table
        cursor.execute("DROP TABLE ui_settings")
        conn.commit()
        print("[MIGRATE] Dropped old ui_settings table")

        print("[MIGRATE] Migration complete!")
        print(f"[MIGRATE] Backup available at: {backup_path}")

    except Exception as e:
        conn.rollback()
        print(f"[MIGRATE] Migration failed: {e}")
        print(f"[MIGRATE] Database backup available at: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_to_normalized_schema()
