# Database Migration Guide

Simposter has migrated from JSON files to SQLite database for better performance and reliability.

## What Changed

### Before (JSON-based)
- UI settings stored in `config/settings/ui_settings.json`
- Presets stored in `config/settings/presets.json`
- Multiple file I/O operations
- Risk of file corruption
- No transaction safety

### After (SQLite-based)
- UI settings and presets stored in `config/settings/simposter.db`
- Single database file
- ACID compliance (Atomic, Consistent, Isolated, Durable)
- Better performance
- Transaction safety

## Migration Process

### Automatic Migration
The migration happens automatically when you:
1. **Start the application** - The database is initialized on first run
2. **Access UI settings** - JSON files are automatically migrated to database on first read
3. **Save settings** - JSON files are backed up as `.json.migrated` after successful migration

### Manual Migration
If you want to manually migrate your existing JSON files:

```bash
# From the project root
cd backend
python -m backend.migrate_to_db
```

This will:
- Read existing `ui_settings.json` and `presets.json`
- Import all data into the SQLite database
- Create backup files with `.backup` extension
- Remove original JSON files

## Database Schema

### `ui_settings` Table
```sql
CREATE TABLE ui_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    settings_json TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

Stores a single row containing all UI settings as JSON.

### `presets` Table
```sql
CREATE TABLE presets (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    name TEXT NOT NULL,
    options_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(template_id, id)
)
```

Stores preset configurations with indexing on `template_id` for fast lookups.

## Backup Files

After migration, you'll find backup files:
- `ui_settings.json.migrated` - Backed up after first save to database
- `presets.json.migrated` - Backed up after first access
- `*.backup` - Created by manual migration script

**These backup files can be safely deleted after verifying the migration was successful.**

## Database Location

The database is stored at:
```
config/settings/simposter.db
```

This location can be customized via the `SETTINGS_DIR` environment variable.

## Rolling Back

If you need to roll back to JSON files:

1. Stop the application
2. Delete or rename `simposter.db`
3. Rename backup files back to original names:
   ```bash
   mv ui_settings.json.migrated ui_settings.json
   mv presets.json.migrated presets.json
   ```
4. Restart the application

## Benefits

1. **Better Performance** - Database queries are faster than JSON file parsing
2. **Data Integrity** - ACID transactions prevent data corruption
3. **Concurrent Access** - SQLite handles multiple reads/writes safely
4. **Easier Backups** - Single file to backup instead of multiple JSON files
5. **Query Capabilities** - Can add search and filter features in the future

## Development

### Adding New Tables

Edit `backend/database.py` and add your table schema in the `init_database()` function:

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS your_table (
        id INTEGER PRIMARY KEY,
        ...
    )
""")
```

### Database Utilities

The `backend/database.py` module provides utility functions:
- `get_db()` - Context manager for database connections
- `get_ui_settings()` - Get UI settings
- `save_ui_settings()` - Save UI settings
- `get_all_presets()` - Get all presets
- `save_preset()` - Save a preset
- `delete_preset()` - Delete a preset

## Troubleshooting

### Database Locked Error
If you see "database is locked" errors:
1. Make sure only one instance of the app is running
2. Check that no other process has the database file open
3. Restart the application

### Migration Failed
If automatic migration fails:
1. Check the logs for error details
2. Try manual migration: `python -m backend.migrate_to_db`
3. Restore from backup files if needed

### Corrupt Database
If the database becomes corrupted:
1. Stop the application
2. Delete `simposter.db`
3. Restore from backup JSON files
4. Restart - database will be recreated and remigrated
