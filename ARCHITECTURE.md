# Simposter Architecture & Execution Flow

This doc explains how Simposter starts, how the backend and frontend interact, and what the key modules/functions do. It is written for developers who want a deeper, code-level understanding rather than a deploy guide.

## Runtime Overview
- **Frontend**: Vue 3 + Vite (`frontend/`). Builds to static assets; during development Vite serves the SPA, in production FastAPI serves the built assets.
- **Backend**: FastAPI (`backend/`) with routers under `backend/api/`. Entrypoint is `backend/main.py`.
- **Database**: SQLite at `config/settings/simposter.db` (or `SETTINGS_DIR/simposter.db`). Accessed via helpers in `backend/database.py`.
- **External services**: Plex (library metadata/posters), TMDb (metadata/posters), Fanart.tv (logos/posters), optional webhooks.
- **Images**: Posters/logos fetched and cached; rendered via templates; returned to the frontend or saved to disk and/or Plex.

## Startup Flow (what runs)
1. **Backend start** (`backend/main.py`)
   - Loads config from `backend/config.py` (env + fallbacks to db/json).
   - Mounts all routers from `backend/api/`.
   - Calls `init_database()` to ensure tables exist and to run version checks.
2. **Database init & versioning** (`backend/database.py`)
   - `_get_db_path()` decides where `simposter.db` lives (uses `SETTINGS_DIR`/`CONFIG_DIR`).
   - `init_database()` creates/migrates tables, migrates legacy `ui_settings` to `settings`, then calls `check_and_update_version()`.
   - `check_and_update_version()` compares stored `app.version` (from `settings` table) with `frontend/src/version.ts`; on change it calls `_backup_database()` to create `simposter_vX.Y.Z.db.bak`, then updates the stored version.
3. **Frontend** (dev vs prod)
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
- `settings` (key/value + category)
- `presets` (template/preset storage)
- `history` (render/send events)
- `movies_cache`, `posters_cache`, `labels_cache` (cached Plex/TMDb data)
- `webhooks` (outbound webhook configs)

### Key API Routers (`backend/api/`)
- **movies.py**
  - `api_movies`: List movies (cached DB if fresh, otherwise Plex).
  - `api_movie_poster`: Fetch/cached poster bytes or JSON meta; supports force refresh.
  - `api_movie_labels` / `api_movie_labels_bulk`: Fetch Plex labels.
  - `api_tmdb_images`: Merge TMDb + Fanart images respecting priority.
  - `api_scan_library`: Walk Plex library, cache movies/posters/labels.
  - Local assets handlers for listing/serving/deleting rendered files.
- **preview.py**
  - `render_preview`: Compose poster with template/options; returns base64 JPEG.
- **save.py**
  - `save_rendered`: Save rendered poster locally and/or send to Plex; optional label handling.
- **presets.py / template_manager.py**
  - CRUD for presets; import/export; fallback rule configuration per preset/template.
- **ui_settings.py**
  - `api_ui_settings` (GET/POST): Read/write UI settings.
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
- **State stores** (Pinia):
  - `stores/settings.ts`: Loads/saves UI settings; holds API keys, Plex settings, performance options.
  - `stores/scan.ts`: Scan progress and overlay state.
  - `composables/useMovies.ts`: Shared movies cache + poster hydration from sessionStorage.
- **Views**:
  - `TemplateManagerView.vue`: Manage presets, fallbacks, preview rendering (with movie search/selection).
  - `BatchEditView.vue`: Bulk select movies, apply templates, render/send in batches.
  - `SettingsView.vue`: Configure Plex/API keys/perf options; test keys; reorder API source priority.
  - `MoviesView.vue`, `LocalAssetsView.vue`, `LogsView.vue`, `TemplateManagerView.vue` handle their respective domains.
- **API calls**: Built on `getApiBase()` to form `/api/*` requests; plain `fetch` used throughout.

## Caching & Performance
- **DB cache tables**: movies, posters, labels to reduce Plex/TMDb/Fanart calls.
- **Disk poster cache**: Files in `POSTER_CACHE_DIR`; served via `/api/movie/{rating_key}/poster`.
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

## Quick Map of Important Functions
- Startup/versioning: `init_database()`, `check_and_update_version()`, `_backup_database()`
- Settings runtime refresh: `api/ui_settings.py::_apply_runtime_settings`
- Posters/logos: `api/movies.py::api_movie_poster`, `api_tmdb_images` (TMDb/Fanart merge)
- Previews: `api/preview.py::render_preview`
- Save/post-processing: `api/save.py::save_rendered`
- Presets/fallbacks: `api/presets.py` CRUD; `api/template_manager.py` fallback logic
- Cache control: `api/cache.py` plus helpers in `config.py`/`movies.py`

## Tips for Exploring
- Start at `backend/main.py` to see router wiring.
- Grep for `/api/<route>` inside `backend/api/` to find handlers.
- Frontend: check `frontend/src/views` for page logic; `stores/` for state shape.
- For migrations/version changes, see `backend/database.py` and `DATABASE_MIGRATION.md`.
