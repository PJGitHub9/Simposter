# Simposter Architecture & Execution Flow

This doc explains how Simposter starts, how the backend and frontend interact, and what the key modules/functions do. It is written for developers who want a deeper, code-level understanding rather than a deploy guide.

## Runtime Overview
- **Frontend**: Vue 3 + Vite (`frontend/`). Builds to static assets; during development Vite serves the SPA, in production FastAPI serves the built assets.
- **Backend**: FastAPI (`backend/`) with routers under `backend/api/`. Entrypoint is `backend/main.py`.
- **Database**: SQLite at `config/settings/simposter.db` (or `SETTINGS_DIR/simposter.db`). Accessed via helpers in `backend/database.py`.
- **External services**: Plex (library metadata/posters), TMDb (movies metadata/posters/logos), TVDB (TV shows metadata/posters/logos), Fanart.tv (HD clearlogos), optional webhooks.
- **Images**: Posters/logos fetched from multiple sources and cached; rendered via templates with fallback support; returned to the frontend or saved to disk and/or Plex.

## Startup Flow (what runs)
1. **Backend start** (`backend/main.py`)
   - Loads config from `backend/config.py` (env + fallbacks to db/json).
   - Mounts all routers from `backend/api/`.
   - Calls `init_database()` to ensure tables exist and to run version checks.
   - Initializes APScheduler (`init_scheduler()`) and restores any saved schedules from database.
2. **Database init & versioning** (`backend/database.py`)
   - `_get_db_path()` decides where `simposter.db` lives (uses `SETTINGS_DIR`/`CONFIG_DIR`).
   - `init_database()` creates/migrates tables, migrates legacy `ui_settings` to `settings`, then calls `check_and_update_version()`.
   - `check_and_update_version()` compares stored `app.version` (from `settings` table) with `frontend/src/version.ts`; on change it calls `_backup_database()` to create `simposter_vX.Y.Z.db.bak`, then updates the stored version.
3. **Scheduler initialization** (`backend/scheduler.py`)
   - `init_scheduler()` creates background scheduler daemon
   - Reads scheduler settings from database
   - If enabled, restores cron schedule for automatic library scans
4. **Frontend** (dev vs prod)
   - Dev: Vite serves the SPA and proxies API calls to FastAPI.
   - Prod: FastAPI serves the built `dist/` assets; frontend calls `/api/*`.

## Backend Deep Dive
### `backend/config.py`
- **settings = Settings()**: Pydantic `BaseSettings` that reads `.env` and env vars. Normalizes paths (CONFIG_DIR, SETTINGS_DIR, OUTPUT_ROOT).
- **_load_ui_settings_fallback()**: Loads UI settings from DB or JSON if env vars are absent; sets `settings.TMDB_API_KEY`, `settings.FANART_API_KEY`, etc.
- **resolve_library_ids() / resolve_library_id()**: Map Plex library names/ids to numeric section IDs.
- **plex_headers()**: Returns Plex auth headers.
- **get_plex_movies()**: Hits Plex sections, builds `Movie` objects, caches them.
- **fetch poster helpers**: In `api/movies.py` but rely on config paths such as `POSTER_CACHE_DIR`.

### `backend/database.py`
- **_get_db_path()**: Computes the SQLite path based on env/config.
- **_configure_conn()**: Applies WAL, sync, busy_timeout defaults.
- **get_db() (contextmanager)**: Yields a configured SQLite connection; used across API modules.
- **get_db_version() / set_db_version()**: Store/read `app.version` in the `settings` table.
- **get_app_version()**: Reads `frontend/src/version.ts`.
- **_backup_database(db_version)**: Copies `simposter.db` to `simposter_v<db_version>.db.bak` before version bumps.
- **check_and_update_version()**: Compares DB/app versions, triggers backup, then writes new version.
- **init_database()**: Creates tables, migrates legacy `ui_settings`, seeds indexes, then calls `check_and_update_version()`.

Tables created:
- `settings` (key/value + category for UI settings and app version)
- `presets` (template/preset storage with options JSON)
- `history` (render/send events tracking)
- `movie_cache`, `poster_cache`, `label_cache` (cached Plex/TMDb movie data)
- `tv_cache`, `tv_poster_cache`, `tv_label_cache` (cached Plex/TVDB TV show data)
- `webhooks` (outbound webhook configs)

### Key API Routers (`backend/api/`)
- **movies.py**
  - `api_movies`: List movies (cached DB if fresh, otherwise Plex); handles library_id normalization.
  - `api_movie_poster`: Fetch/cached poster bytes or JSON meta; supports force refresh.
  - `api_movie_labels` / `api_movie_labels_bulk`: Fetch Plex labels.
  - `api_tmdb_images`: Merge TMDb + Fanart images respecting priority.
  - `api_scan_library`: Walk Plex library, cache movies/posters/labels.
  - Local assets handlers for listing/serving/deleting rendered files.
- **tv_shows.py**
  - `api_tv_shows`: List TV shows (cached DB if fresh, otherwise Plex); handles library_id normalization.
  - `api_tv_show_poster`: Fetch/cached TV show poster with metadata.
  - TVDB metadata integration with season/episode support.
- **preview.py**
  - `api_preview`: Compose poster with template/options; returns base64 JPEG.
  - Supports logo fallback to different template/preset when logos missing.
  - Respects JPEG quality settings from DB.
- **save.py**
  - `save_rendered`: Save rendered poster locally and/or send to Plex; optional label handling.
  - Uses JPEG quality from settings.
- **batch.py**
  - `api_batch_render`: Process multiple movies with template/preset; supports concurrent rendering.
  - Logo/poster fallback logic matching preview behavior.
  - Uses ui_settings for quality and concurrency.
- **scheduler.py (module)**
  - `init_scheduler()`: Initializes APScheduler background instance on app startup.
  - `schedule_library_scan()`: Schedules cron-based automatic library scans.
  - `cancel_library_scan()`: Cancels scheduled scans.
  - Integrations polling removed (Radarr/Sonarr).
  - `cancel_integration_polling()` (v1.5.0): Cancels integration polling.
  - Restores schedules from database on startup.
- **scheduler.py (API router)**
  - `api_schedule_library_scan` (POST): Schedule library scans with cron expression and optional library_id.
  - `api_cancel_library_scan` (DELETE): Cancel scheduled scans.
  - `api_get_library_scan_schedule` (GET): Get current schedule status and next run time.
  - `api_schedule_integration_poll` (POST) (v1.5.0): Enable/disable integration polling with interval.
  - `api_get_integration_poll_schedule` (GET) (v1.5.0): Get polling status and next run time.
  - `api_scheduler_status` (GET): Check if scheduler is running.
  - Settings persist to `ui_settings` in database.
- **integrations_poller.py (v1.5.0)**
  - Integration poller removed.
  - `generate_poster_for_content()`: Generates poster for newly detected content.
  - `process_new_content()`: Processes list of detected content items.
  - Tracks last poll time per instance in database.
  - Records history with source='auto'.
- **presets.py / template_manager.py**
  - CRUD for presets; import/export (merge mode); fallback rule configuration per preset/template.
  - Global template preferences (logo source, poster filter, logo mode).
- **ui_settings.py**
  - `api_ui_settings` (GET/POST): Read/write UI settings (including scheduler config).
  - `_apply_runtime_settings`: Immediately updates runtime keys/paths so new settings take effect without restart.
- **logs.py, history.py, cache.py, webhooks.py**
  - Logs retrieval, history listing, cache endpoints, webhook management.

### Rendering Flow (what functions run)
1. Frontend picks template/preset and movie → calls `/api/preview`.
2. `preview.py::render_preview`:
   - Resolves poster/logo URLs.
   - Applies template options; calls renderer (see `backend/rendering.py`).
   - Returns base64 image.
3. On save, frontend calls `/api/save`:
   - `save.py::save_rendered` writes to disk (respecting output path templating) and can send to Plex.

## Frontend Deep Dive (Vue 3 + Pinia)
- **State stores** (Pinia): (JPEG quality, concurrent renders).
  - `stores/scan.ts`: Scan progress and overlay state.
  - `composables/useMovies.ts`: Shared movies cache + poster hydration from sessionStorage.
- **Views**:
  - `TemplateManagerView.vue`: Manage presets, fallbacks (poster/logo), preview rendering (with movie search/selection), export/import.
  - `BatchEditView.vue`: Bulk select movies, apply templates, render/send in batches with progress tracking.
  - `SettingsView.vue`: Configure Plex/API keys/perf options (JPEG quality, concurrent rendering); test keys; reorder API source priority; manage library mappings; configure integrations (v1.5.0).
  - `MoviesView.vue`: Movie library grid with sessionStorage caching, library filtering, label filtering; validates cached movies by library_id.
  - `TVView.vue`: TV show library (similar to movies).
  - `HistoryView.vue` (v1.5.0): Poster generation history with filtering by library, template, action, and source.
  - `LocalAssetsView.vue`, `LogsView.vue`, `CollectionsView.vue`: Asset management, log viewing, collection handling.
- **API calls**: Built on `getApiBase()` to form `/api/*` requests; plain `fetch` used throughout.
, TV shows to reduce Plex/TMDb/TVDB/Fanart calls.
- **Disk poster cache**: Files in `POSTER_CACHE_DIR`; served via `/api/movie/{rating_key}/poster` and `/api/tv-show/{rating_key}/poster`.
- **Browser caches**: SessionStorage for posters/labels/movies (per library) to speed UI; validates library_id on load to prevent cross-library contamination.
- **Concurrent rendering**: ThreadPoolExecutor in batch operations with configurable worker count (default 2, respects `concurrentRenders` setting).
- **JPEG quality**: Configurable quality (default 95) applied across all save/render operations (preview, save, batch, plexsend, webhooks).
- **Rate limits**: TMDb/TVDB/Fanart limits configurable in settings; honored for pacing API callsster`.
- **Browser caches**: SessionStorage for posters/labels/movies (per library) to speed UI.
- **Rate limits**: TMDb/TVDB limits configurable in settings; honored client-side for pacing.

## Configuration & Deployment
- **Env/config**: `.env` or container env vars configure Plex URL/token, TMDb/Fanart keys, paths. Fallbacks pulled from DB/JSON via `config.py`.
- **Docker**: `Dockerfile` + `docker-compose.yml` build the backend (which also serves the built frontend). Volumes map config/output.
- **Paths**:
  - Config/settings: `config/` (or `/config`) holds `settings/` and `ui_settings.json` fallback.
  - Output: `/output` (configurable) for rendered assets.
  - Uploads: `uploads/` for user-uploaded templates/assets.

## Request Tracing (practical steps)
1. Frontend action triggers `fetch('/api/xyz')`.
2. FastAPI router handles → may read/write DB via `get_db()` or hit Plex/TMDb/Fanart.
3. Response (JSON or image/base64) updates Pinia state and the view.
 with priority), `logo_sources.py::get_logos_merged`
- TV shows: `api/tv_shows.py::api_tv_shows`, `tvdb_client.py` for TVDB metadata
- Previews: `api/preview.py::api_preview` (supports logo fallback to different template/preset)
- Save/post-processing: `api/save.py::save_rendered`
- Batch rendering: `api/batch.py::api_batch_render` (concurrent processing with fallback logic)
- Presets/fallbacks: `api/presets.py` CRUD with merge import; `api/template_manager.py` fallback preferences
- Cache control: `api/cache.py`, `cache.py` module, helpers in `config.py`/`movies.py`
- Integrations removed: `integrations_poller.py` and related scheduler endpoints removed.
- History tracking (v1.5.0): `api/history.py` provides poster history with source filtering

## Tips for Exploring
- Start at `backend/main.py` to see router wiring.
- Grep for `/api/<route>` inside `backend/api/` to find handlers.
- Frontend: check `frontend/src/views` for page logic; `stores/` for state shape.
- For database schema/migrations, see `backend/database.py` (auto-migrations on version change with backups)
- Start at `backend/main.py` to see router wiring.
- Grep for `/api/<route>` inside `backend/api/` to find handlers.
- Frontend: check `frontend/src/views` for page logic; `stores/` for state shape.
- For migrations/version changes, see `backend/database.py` and `DATABASE_MIGRATION.md`.
