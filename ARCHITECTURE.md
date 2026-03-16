# Simposter Architecture & Execution Flow

This document explains how Simposter starts, how the backend and frontend interact, and what the key modules/functions do. It is written for developers who want a deeper, code-level understanding rather than a deployment guide.

---

## Runtime Overview

- **Frontend**: Vue 3 + Vite (`frontend/`). Builds to static assets; during development Vite serves the SPA, in production FastAPI serves the built assets.
- **Backend**: FastAPI (`backend/`) with routers under `backend/api/`. Entrypoint is `backend/main.py`.
- **Database**: SQLite at `config/settings/simposter.db` (or `SETTINGS_DIR/simposter.db`). Accessed via helpers in `backend/database.py`.
- **External services**: Plex (library metadata/posters), TMDb (movies metadata/posters/logos), TVDB (TV shows metadata/posters/logos), Fanart.tv (HD clearlogos)
- **Images**: Posters/logos fetched from multiple sources and cached; rendered via templates with fallback support; returned to the frontend or saved to disk and/or Plex.

---

## Startup Flow

### 1. Backend Initialization (`backend/main.py`)
- Loads configuration from `backend/config.py` (environment variables + database fallbacks)
- Mounts all API routers from `backend/api/`
- Calls `init_database()` to ensure tables exist and run version checks
- Initializes APScheduler (`init_scheduler()`) and restores any saved schedules from database

### 2. Database Initialization (`backend/database.py`)
- `_get_db_path()` determines where `simposter.db` lives (uses `SETTINGS_DIR`/`CONFIG_DIR`)
- `init_database()` creates/migrates tables, migrates legacy `ui_settings` to `settings`, then calls `check_and_update_version()`
- `check_and_update_version()` compares stored `app.version` (from `settings` table) with `frontend/src/version.ts`
- On version change: calls `_backup_database()` to create `simposter_vX.Y.Z.db.bak`, then updates the stored version

**Tables created:**
- `settings` — Key/value pairs + category for UI settings and app version
- `presets` — Template/preset storage with options JSON
- `history` — Poster generation history tracking
- `movie_cache`, `poster_cache`, `label_cache` — Cached Plex/TMDb movie data
- `tv_cache`, `tv_poster_cache`, `tv_label_cache` — Cached Plex/TVDB TV show data
- `overlay_configs`, `overlay_assets` — Overlay configuration and badge assets
- `media_metadata_cache` — Plex media metadata (resolution, codec, audio)
- `streaming_provider_cache` — TMDb watch provider results per `(tmdb_id, media_type, region)`, 7-day TTL

### 3. Scheduler Initialization (`backend/scheduler.py`)
- `init_scheduler()` creates background scheduler daemon
- Reads scheduler settings from database
- If enabled, restores cron schedule for automatic library scans

### 4. Frontend Initialization (Dev vs Prod)
- **Dev**: Vite serves the SPA and proxies API calls to FastAPI
- **Prod**: FastAPI serves the built `dist/` assets; frontend calls `/api/*`

---

## Backend Deep Dive

### Configuration (`backend/config.py`)
- **`settings = Settings()`**: Pydantic `BaseSettings` that reads `.env` and environment variables
- **`_load_ui_settings_fallback()`**: Loads UI settings from database or JSON if env vars are absent
- **`resolve_library_ids()` / `resolve_library_id()`**: Map Plex library names/IDs to numeric section IDs
- **`plex_headers()`**: Returns Plex authentication headers
- **`get_plex_movies()`**: Hits Plex sections, builds `Movie` objects, caches them

### Database (`backend/database.py`)
- **`_get_db_path()`**: Computes the SQLite path based on env/config
- **`_configure_conn()`**: Applies WAL mode, sync settings, busy_timeout defaults
- **`get_db()` (context manager)**: Yields a configured SQLite connection; used across API modules
- **`get_db_version()` / `set_db_version()`**: Store/read `app.version` in the `settings` table
- **`get_app_version()`**: Reads `frontend/src/version.ts`
- **`_backup_database(db_version)`**: Copies `simposter.db` to `simposter_v<db_version>.db.bak` before version bumps
- **`check_and_update_version()`**: Compares database/app versions, triggers backup, then writes new version
- **`init_database()`**: Creates tables, migrates legacy `ui_settings`, seeds indexes, then calls `check_and_update_version()`

### Simposter Assets (`backend/simposter_assets.py`)
- Fetches `logos.json` from the [simposter-assets](https://github.com/PJGitHub9/simposter-assets) GitHub repo (refreshed hourly)
- Builds two in-memory lookup caches:
  - `_logos_slug_cache: dict[str, str]` — studio slug → raw asset URL
  - `_logos_id_cache: dict[int, str]` — TMDb company ID → raw asset URL (keyed on `tmdb_production_company_id` column)
- **`get_asset_url(slug, company_id=None)`**: Checks ID cache first (more reliable), then slug cache; returns `None` if not found
- Thread-safe cache prewarm with double-checked locking (`_fetch_lock`)

### Key API Routers (`backend/api/`)

#### `version_info.py`
- `get_version_info` (GET `/version-info`) — Returns `version`, `branch`, `docker_tag`, `display_version`, `update_available`, `latest_version`, `update_url`
- `get_current_version()`: Reads from `frontend/src/version.ts`, falls back to `build-info.json` (Docker builds)
- `get_git_branch()`: Checks `GIT_BRANCH` env var → `git rev-parse` → `.git/HEAD` → `build-info.json`
- `get_docker_tag()`: Checks `DOCKER_TAG` env var → `build-info.json`
- **`build-info.json`**: Written at Docker build time (`RUN ... echo {...} > /app/build-info.json`) with `git_branch`, `app_version`, `docker_tag`; read at runtime when git/version.ts are unavailable

#### `movies.py`
- `api_movies` — List movies (cached DB if fresh, otherwise Plex)
- `api_movie_poster` — Fetch/cached poster bytes or JSON metadata
- `api_movie_labels` / `api_movie_labels_bulk` — Fetch Plex labels
- `api_tmdb_images` — Merge TMDb + Fanart images respecting priority
- `api_scan_library` — Walk Plex library, cache movies/posters/labels

#### `tv_shows.py`
- `api_tv_shows` — List TV shows (cached DB if fresh, otherwise Plex)
- `api_tv_show_poster` — Fetch/cached TV show poster with metadata
- TVDB metadata integration with season/episode support

#### `preview.py`
- `api_preview` — Compose poster with template/options; returns base64 JPEG
- Supports logo/poster fallback to different template/preset when assets missing
- **`skip_fallback`**: When `True` (sent by the manual editor), no fallback is applied — selected preset always renders as-is
- Respects JPEG quality settings from database

#### `save.py`
- `save_rendered` — Save rendered poster locally and/or send to Plex
- Optional label handling (add/remove Plex labels)
- Uses JPEG quality from settings

#### `batch.py`
- `api_batch_render` — Process multiple movies with template/preset
- Supports concurrent rendering via ThreadPoolExecutor
- Logo/poster fallback logic matching preview behavior

#### `overlay_config.py`
- `api_list_overlay_configs` — List all overlay configurations
- `api_create_overlay_config` — Create new overlay config
- `api_update_overlay_config` — Update existing overlay config (includes `streaming_region` field)
- `api_delete_overlay_config` — Delete overlay config
- `api_list_overlay_assets` — List uploaded badge assets
- `api_upload_overlay_asset` — Upload new badge asset (PNG/JPG)
- `GET /api/asset-image` — Proxy for simposter-assets badge image, accepts optional `company_id` for TMDb ID lookup
- `GET /api/overlay-preview-metadata` — Returns metadata for canvas preview (studio slug, studio_company_id, streaming_platform)

#### `scheduler.py`
- `api_schedule_library_scan` (POST) — Schedule library scans with cron expression
- `api_cancel_library_scan` (DELETE) — Cancel scheduled scans
- `api_get_library_scan_schedule` (GET) — Get current schedule status and next run time
- `api_scheduler_status` (GET) — Check if scheduler is running
- Settings persist to database

#### `webhooks.py`
- `/webhook/tautulli` — Tautulli event handler (added/watched/updated events)
- `/webhook/radarr` — Radarr movie webhook (deprecated, use Tautulli)
- `/webhook/sonarr` — Sonarr TV webhook (deprecated, use Tautulli)

#### `presets.py` / `template_manager.py`
- CRUD for presets; import/export (merge mode)
- Fallback rule configuration per preset/template
- Global template preferences (logo source, poster filter, logo mode)

#### `ui_settings.py`
- `api_ui_settings` (GET/POST) — Read/write UI settings
- `_apply_runtime_settings` — Immediately updates runtime keys/paths so new settings take effect without restart

#### `history.py`
- `api_poster_history` — List poster generation history with filtering
- Tracks manual, batch, webhook, and auto-generate operations
- Filterable by library, template, preset, action, source

---

## Rendering Flow

### 1. Preview Rendering
```
User selects movie → Frontend calls /api/preview
→ Backend resolves poster/logo URLs from TMDb/Fanart/TVDB
→ Apply template options (matte/fade/vignette/logo positioning)
→ Inject overlay badges if preset has overlayConfigId
  → Fetch Plex media metadata (resolution, codec, audio)
  → Render badges with text/image modes
→ Generate final poster with PIL
→ Return base64 JPEG to frontend
```

### 2. Save to Disk / Upload to Plex
```
User clicks "Save" or "Send to Plex" → Frontend calls /api/save
→ Backend renders poster (same pipeline as preview)
→ Save to disk at configured output path (supports {library}, {title}, {year}, {season} variables)
→ (Optional) Upload to Plex via `/library/metadata/{rating_key}/posters`
→ (Optional) Remove configured Plex labels
→ Record history entry with action='sent_to_plex' or 'saved'
```

### 3. Batch Rendering
```
User selects movies + template/preset → Frontend calls /api/batch/render
→ Backend creates ThreadPoolExecutor (concurrentRenders workers)
→ For each movie:
  → Render poster (with overlay badges if configured)
  → Save locally and/or upload to Plex
  → Record history entry with source='batch'
→ Return progress updates to frontend
```

### 4. Overlay Badge Rendering
```
Backend receives render request with preset_id
→ Load preset options from database
→ If overlayConfigId present, load overlay config
→ Pre-pass resolves dynamic metadata fields:
  - studio_badge present + tmdb_id available → call get_studio_name() + get_studio_company_id() → inject metadata["studio"] + metadata["studio_company_id"]
  - streaming_platform_badge present + tmdb_id available → call get_watch_providers(tmdb_id, media_type, region) → inject metadata["streaming_platform"]
→ Fetch Plex media metadata for item:
  - rating_key → /library/metadata/{rating_key}
  - Extract: videoResolution, videoCodec, audioCodec, audioChannels, audioLanguageCode, editionTitle
→ For each overlay element (video_badge, audio_badge, edition_badge, studio_badge, streaming_platform_badge, custom_image, text_label):
  - Check show_if_label / hide_if_label conditions (case-insensitive)
  - Get metadata value (e.g., resolution='4k', codec='hevc', studio='a24')
  - Check badge_modes[value] (none/text/image/asset)
  - If 'text': render text with custom font/color/size
  - If 'image': composite badge asset from overlay_assets table (user-uploaded)
  - If 'asset': fetch from simposter-assets repo via get_asset_url(slug, company_id)
  - Position at element.position_x, element.position_y
→ Composite all badges onto poster
```

**Element types:**
- `video_badge` — Video metadata (resolution, codec)
- `audio_badge` — Audio metadata (codec, channels, language)
- `edition_badge` — Edition metadata (theatrical, extended, director's cut)
- `studio_badge` — Production studio / network (auto-detected from TMDb)
- `streaming_platform_badge` — Streaming platform (auto-detected from TMDb watch providers)
- `custom_image` — User-uploaded badge asset
- `text_label` — Custom text overlay

**Legacy aliases (backwards compatibility):** `resolution_badge` → `video_badge`, `codec_badge` → `audio_badge`

---

## Frontend Deep Dive

### State Management (Pinia)
- **`stores/ui.ts`**: SessionStorage cache with LRU eviction (4MB limit)
  - Stores posters, labels, movies per library
  - Auto-evicts least-recently-used items when quota exceeded

### Key Views

#### `MoviesView.vue` / `TvShowsView.vue`
- Movie/TV show library grid with filtering and sorting
- SessionStorage caching for instant load
- Library-specific cache keys to prevent contamination

#### `BatchEditView.vue` / `TvBatchEditView.vue`
- Bulk poster generation interface
- Preview sidebar with real-time rendering
- Progress tracking during batch operations

#### `TemplateManagerView.vue`
- Preset CRUD (create, update, delete, import, export)
- Fallback configuration (poster/logo missing → switch template/preset)
- Preview rendering with movie search

#### `OverlayConfigManagerView.vue`
- Visual overlay editor with drag-and-drop positioning
- Badge asset library (upload/manage badge images)
- Live canvas preview with metadata value switcher
- Per-value badge modes (none/text/image)

#### `SettingsView.vue`
- Plex/TMDb/TVDB/Fanart API key configuration
- Performance settings (concurrent rendering, JPEG quality, overlay cache)
- Library management (output paths, ignore labels, auto-generate)
- Scheduled scans configuration

#### `HistoryView.vue`
- Poster generation history table
- Filtering by library, template, preset, action, source
- Preview on hover (loads poster from disk or Plex)

---

## Caching Strategy

### Frontend Caching
- **SessionStorage** with LRU eviction (4MB limit)
- **Cache keys**: `movies_${library_id}`, `posters_${library_id}`, `labels_${library_id}`
- **Validation**: On load, filter cached items by current `library_id` to prevent contamination

### Backend Caching
- **SQLite tables**:
  - `movie_cache` / `tv_cache` — Item metadata (title, year, TMDb ID, etc.)
  - `poster_cache` / `tv_poster_cache` — Poster metadata (URL, width, height)
  - `label_cache` / `tv_label_cache` — Plex labels per item
  - `media_metadata_cache` — Plex media metadata (resolution, codec, audio)
- **Disk cache**: Downloaded poster/logo files in `POSTER_CACHE_DIR`
- **Overlay cache**: Pre-rendered template effect layers (matte/fade/vignette) for faster batch rendering

### Cache Invalidation
- **Manual**: "Refresh Cache" button in Settings
- **Automatic**: Cache refreshes when `forceRefresh=true` in API calls
- **Scheduled**: Library scans update cache with new/changed items

---

## Request Tracing (Practical Steps)

1. **Frontend action** triggers `fetch('/api/xyz')`
2. **FastAPI router** handles request → may read/write database via `get_db()` or hit Plex/TMDb/TVDB/Fanart
3. **Response** (JSON or image/base64) updates Pinia state and the view

**Key API flows:**
- **Movies**: `api/movies.py::api_movies`, `tmdb_client.py`, `fanart_client.py`, `logo_sources.py::get_logos_merged`
- **TV shows**: `api/tv_shows.py::api_tv_shows`, `tvdb_client.py` for TVDB metadata
- **Previews**: `api/preview.py::api_preview` (supports logo fallback to different template/preset)
- **Save/upload**: `api/save.py::save_rendered`
- **Batch rendering**: `api/batch.py::api_batch_render` (concurrent processing with fallback logic)
- **Overlay configs**: `api/overlay_config.py` for badge/asset management
- **Presets/fallbacks**: `api/presets.py` CRUD with merge import; `api/template_manager.py` fallback preferences
- **Cache control**: `api/cache.py`, `cache.py` module, helpers in `config.py`/`movies.py`
- **Webhooks**: `api/webhooks.py` with endpoints for Tautulli integration
- **History tracking**: `api/history.py` provides poster history with source filtering

---

## Configuration & Deployment

### Environment Variables
```bash
# Required
PLEX_URL=http://plex:32400       # Plex server URL
PLEX_TOKEN=xxxxxxxxxxxx          # Plex authentication token
TMDB_API_KEY=xxxxxxxxxxxx        # TMDb API key

# Optional
PLEX_MOVIE_LIBRARY_NAME=Movies   # Movie library name (or use library_id)
PLEX_TV_LIBRARY_NAME=TV Shows    # TV library name (or use library_id)
TVDB_API_KEY=xxxxxxxxxxxx        # TVDB API key (for TV shows)
FANART_API_KEY=xxxxxxxxxxxx      # Fanart.tv API key (for logos)
CONFIG_DIR=/config               # Config directory path (Docker)
```

### Docker Deployment
```yaml
services:
  simposter:
    image: simposter:latest
    ports:
      - "8003:8003"
    volumes:
      - ./config:/config           # Persistent settings/database/logs
    environment:
      - PLEX_URL=http://plex:32400
      - PLEX_TOKEN=xxxxxxxxxxxx
      - TMDB_API_KEY=xxxxxxxxxxxx
      # Optional: override Docker tag shown in UI (default read from build-info.json)
      - DOCKER_TAG=latest
```

**Build with tag injection** (use `build-docker.bat` on Windows or):
```bash
docker build --build-arg DOCKER_TAG=latest -t simposter:latest .
```
The `DOCKER_TAG` arg is baked into `/app/build-info.json` at build time alongside `git_branch` and `app_version`. This allows the UI to warn users if they are running an unsupported/unmaintained image tag.

### File Paths
- **Config/settings**: `config/` (or `/config`) holds `settings/` and `ui_settings.json` fallback
- **Output**: `/output` (configurable) for rendered assets
- **Uploads**: `uploads/` for user-uploaded templates/assets
- **Logs**: `config/logs/simposter.log`

---

## Tips for Exploring the Codebase

### Start Here
- **Backend**: `backend/main.py` to see router wiring
- **Frontend**: `frontend/src/views` for page logic; `stores/` for state shape
- **Database**: `backend/database.py` for schema and migrations

### Finding Specific Functionality
- **API routes**: Grep for `/api/<route>` inside `backend/api/`
- **Rendering logic**: Check `backend/templates/uniformlogo.py` and `backend/rendering.py`
- **Overlay badges**: `backend/templates/universal.py` for badge rendering

### Understanding Data Flow
1. User interacts with Vue component
2. Component calls API endpoint via `fetch()`
3. FastAPI router handles request (may read DB, hit external APIs)
4. Response updates Pinia store
5. Vue reactivity updates UI

---

## Performance Considerations

### Rendering Optimization
- **Overlay cache**: Pre-render template effects for 3-5x speedup (uniformlogo only)
- **Logo selection**: Analyzes top 6 candidates using TMDb w300 thumbnails
- **Concurrent batch**: ThreadPoolExecutor with configurable workers (default: 2)

### Database Optimization
- **Indexed queries**: Composite indexes on `library_id + rating_key` for 5-10x faster lookups
- **WAL mode**: Better concurrency for simultaneous reads/writes
- **Batch inserts**: Use `executemany()` for bulk cache updates

### Frontend Optimization
- **SessionStorage LRU cache**: 4MB limit with auto-eviction
- **Lazy loading**: Images load on-demand with `loading="lazy"`
- **Debounced saves**: 300ms delay on slider changes reduces I/O

---

## Testing & Debugging

### Backend Debugging
```bash
# View logs in real-time
tail -f config/logs/simposter.log

# Inspect database
sqlite3 config/settings/simposter.db
> SELECT * FROM settings WHERE category = 'performance';
> SELECT * FROM presets WHERE template_id = 'uniformlogo';

# Test API endpoints
curl http://localhost:8003/api/movies?library_id=1
```

### Frontend Debugging
```javascript
// Check sessionStorage cache in browser console
JSON.parse(sessionStorage.getItem('movies_1'))

// Clear all cache
sessionStorage.clear()

// Use Vue Devtools
// Install: https://devtools.vuejs.org/
```

---

**Last Updated**: 2026-03-16
**Current Version**: v1.5.71
