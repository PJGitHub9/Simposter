# backend/migrate_to_db.py
"""Migration script to convert JSON files to SQLite database."""
import json
import shutil
from pathlib import Path

from .config import settings, logger
from .database import save_log_config, save_ui_settings, save_preset, DB_PATH


def migrate_ui_settings():
    """Migrate ui_settings.json to database."""
    settings_dir = Path(settings.SETTINGS_DIR)
    ui_settings_file = settings_dir / "ui_settings.json"
    legacy_ui_settings = Path(settings.CONFIG_DIR) / "ui_settings.json"

    # Find the settings file
    settings_file = ui_settings_file if ui_settings_file.exists() else legacy_ui_settings

    if not settings_file.exists():
        logger.info("[MIGRATE] No ui_settings.json found to migrate")
        return False

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Save to database
        save_ui_settings(data)

        # Backup the JSON file
        backup_path = settings_file.with_suffix(".json.backup")
        shutil.copy2(settings_file, backup_path)
        logger.info(f"[MIGRATE] Backed up ui_settings.json to {backup_path}")

        # Remove original file
        settings_file.unlink()
        logger.info(f"[MIGRATE] Migrated ui_settings.json to database")
        return True

    except Exception as e:
        logger.error(f"[MIGRATE] Failed to migrate ui_settings.json: {e}")
        return False


def migrate_presets():
    """Migrate presets.json to database."""
    from .config import USER_PRESETS_PATH, DEFAULT_PRESETS_PATH

    presets_file = Path(USER_PRESETS_PATH)

    if not presets_file.exists():
        logger.info("[MIGRATE] No presets.json found to migrate")
        return False

    try:
        with open(presets_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # data structure: {"template_id": {"presets": [{"id": ..., "name": ..., "options": ...}]}}
        preset_count = 0
        for template_id, template_data in data.items():
            if "presets" in template_data and isinstance(template_data["presets"], list):
                for preset in template_data["presets"]:
                    preset_id = preset.get("id")
                    preset_name = preset.get("name", preset_id)
                    options = preset.get("options", {})

                    if preset_id:
                        save_preset(template_id, preset_id, preset_name, options)
                        preset_count += 1

        # Backup the JSON file
        backup_path = presets_file.with_suffix(".json.backup")
        shutil.copy2(presets_file, backup_path)
        logger.info(f"[MIGRATE] Backed up presets.json to {backup_path}")

        # Remove original file
        presets_file.unlink()
        logger.info(f"[MIGRATE] Migrated {preset_count} presets to database")
        return True

    except Exception as e:
        logger.error(f"[MIGRATE] Failed to migrate presets.json: {e}")
        return False


def migrate_log_config():
    """Migrate log_config.json to database."""
    settings_dir = Path(settings.SETTINGS_DIR)
    log_config_file = settings_dir / "log_config.json"
    legacy_log_config = Path(settings.CONFIG_DIR) / "log_config.json"

    log_file = log_config_file if log_config_file.exists() else legacy_log_config

    if not log_file.exists():
        logger.info("[MIGRATE] No log_config.json found to migrate")
        return False

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        save_log_config(data)

        backup_path = log_file.with_suffix(".json.backup")
        shutil.copy2(log_file, backup_path)
        logger.info(f"[MIGRATE] Backed up log_config.json to {backup_path}")

        log_file.unlink()
        logger.info("[MIGRATE] Migrated log_config.json to database")
        return True
    except Exception as e:
        logger.error(f"[MIGRATE] Failed to migrate log_config.json: {e}")
        return False


def run_migration():
    """Run all migrations."""
    logger.info("[MIGRATE] Starting migration to database...")

    if DB_PATH.exists():
        logger.info(f"[MIGRATE] Database already exists at {DB_PATH}")
        logger.info("[MIGRATE] Checking for JSON files to migrate...")

    ui_migrated = migrate_ui_settings()
    presets_migrated = migrate_presets()
    logs_migrated = migrate_log_config()

    if ui_migrated or presets_migrated or logs_migrated:
        logger.info("[MIGRATE] Migration complete! JSON files have been backed up with .backup extension")
    else:
        logger.info("[MIGRATE] No files to migrate")


if __name__ == "__main__":
    run_migration()
