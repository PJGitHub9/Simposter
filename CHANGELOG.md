# Changelog

## v1.5.0 (2026-01-11)
### Major Features
- **Poster Generation History Tracking**: Complete audit log of all poster operations
  - New History page with filterable table view
  - Tracks manual and batch poster generations
  - Source column distinguishes between manual/batch operations
  - Color-coded badges (purple=batch, gray=manual)
  - Library-aware filtering with display name resolution
  - Template, preset, and action filtering capabilities
  - Records save path and timestamps for all operations

### Removed Features
- **Radarr/Sonarr Integration Polling** (removed in v1.6.0): Integration polling and webhooks have been removed
  - Simposter now focuses on core poster generation with scheduled Plex library scans
  - Use scheduled scans in Settings → Automation for keeping poster library in sync
  - Manual batch processing remains the primary workflow

- **Automatic Cache Cleanup** (`backend/database.py`):
  - Orphaned entries are automatically removed when items are deleted from Plex/Radarr/Sonarr
  - Cleans up database cache (`movie_cache`, `tv_cache`, `collection_cache`)
  - Removes orphaned label cache entries (`label_cache`, `tv_label_cache`)
  - Deletes orphaned poster files from disk
  - Triggered automatically during library scans and cache refreshes
  - Prevents stale data from showing in the UI

- **Database Schema Updates**:
  - Added `source` column to `poster_history` table (manual/batch/auto)
  - Automatic migration for existing databases
  - Integration settings stored in UI settings
  - Last poll timestamps stored per integration instance

- **History API** (`backend/api/history.py`):
  - Enhanced filtering by library, template, and action
  - Pagination support (up to 2000 records)
  - Status endpoint for bulk poster status queries

### Frontend Enhancements
- **UI Polish & Modern Interactions** (`frontend/src/assets/main.css`):
  - Smooth transitions on all interactive elements (buttons, inputs, panels)
  - Enhanced button hover effects with lift animations
  - Improved input focus states with accent-colored glow
  - Refined glass panel hover effects
  - Better disabled states with visual feedback
  - Card hover animations with shadow depth
  - Accessibility improvements (focus-visible outlines)
  - Custom scrollbar styling across all themes
  - Loading and badge pulse animations
  - Smooth scroll behavior

- **History View** (`frontend/src/views/HistoryView.vue`):
  - Full-featured history table with sortable columns
  - Multi-filter support (library, template, action)
  - Library name resolution from settings
  - Real-time refresh capability
  - Clear filters button
  - Results count display
  - Clock icon in sidebar navigation

### Technical Improvements
- Batch operations record source='batch' in history
- Manual operations record source='manual' (default)
- Settings store exports LibraryMapping type for reuse
- Router includes /history route with component import
- Sidebar icon system extended with clock SVG

## v1.4.9 (2026-01-07)
### Major Features
- **Separate Save Locations for Movies and TV Shows**: Enhanced local asset saving with media-type-specific save locations
  - Split single save location into `movieSaveLocation` and `tvShowSaveLocation` settings
  - Movie save location supports variables: `{library}`, `{title}`, `{year}`, `{key}`
  - TV show save location adds `{season}` variable for season-specific saving (formats as `s01`, `s02`, etc.)
  - Automatic cleanup of empty variables to prevent dangling punctuation in filenames
  - Library folder names now use display names instead of numeric IDs
  - Full backwards compatibility with legacy `saveLocation` field
  - Settings UI shows separate inputs with available variable hints

### Bug Fixes
- **TV Show Save to Disk**: Fixed critical issue where `/api/save` endpoint didn't support TV shows properly
  - Updated SaveRequest schema to include `season_index` and `is_tv` fields
  - `/api/save` now uses correct media type and passes season to path variables
  - `/api/save` now loads preset season_options for season-specific rendering (matching preview behavior)
  - Frontend render service updated to pass library_id and season_index
  - TV show editor builds season-specific options for each season (poster, logo, text overlay)
  - TV show editor correctly retrieves library_id from route and passes season index
  - Fixes "wrong library", "Season X.jpg" filename, and "all seasons same poster" issues

- **Library Cache Contamination (FIXED)**: Resolved persistent issue where movies/shows from one library appeared in another
  - Root cause: `hydratePostersFromSession()` was loading from hardcoded global cache key instead of library-specific keys
  - Removed composable's `hydratePostersFromSession` calls, using library-specific poster cache directly
  - Fixed poster hydration to only apply posters from the current library's cache

- **Library Parameter Loss**: Fixed critical bug where library parameter was removed from URL when applying filters/sorting
  - URL sync watcher now preserves the `library` query parameter
  - Prevents switching to "all libraries" view when changing sort order or filters
  - Applied to both MoviesView and TvShowsView

- **Save Location Settings Change Detection**: Fixed unsaved changes indicator not showing when editing save location text fields
  - Added proper event handlers to trigger change detection on input

### UX Improvements
- **Browser Navigation Support**: Added URL state management for filters, sorting, pagination, and edit mode
  - Browser back/forward buttons now work correctly when editing items
  - Filters, sort order, and page number preserved in URL
  - Edit mode includes item ID in URL (e.g., `?edit=12345&library=1`)
  - URL state restored when using browser navigation

- **Conditional Navigation**: Navigation sidebar now adapts to Plex configuration state
  - Only Settings shown when Plex not configured
  - Full navigation restored once Plex configured
  - Automatic redirect to Settings on fresh instances

### Technical Improvements
- Added comprehensive debug logging to track cache operations and library switches
- Added `library_id` field to Movie type definition
- Removed unused `hydratePostersFromSession` imports from both view components
- Settings page now checks Plex configuration before attempting to load labels
- Enhanced `resolve_library_label()` to load from database instead of settings module
- Updated `apply_save_location_variables()` with regex-based cleanup for empty variables
- Improved `get_save_location_template()` to accept media_type parameter
- Enhanced batch save logging with absolute paths for better file location visibility

## v1.4.8 (2026-01-06)
### Bug Fixes
- **Library Switching Cache Contamination**: Fixed critical issue where items from one library appeared in another
  - Deferred initial cache load until route is fully ready
  - Added immediate display clear when switching libraries (`movies.value = []`, `tvShows.value = []`)
  - Strengthened library ID validation to strictly filter by current library
  - Eliminated race conditions between cache loading and route resolution

- **Settings Labels Not Populating**: Fixed inconsistent label loading in Settings
  - Added loading state with spinner indicator
  - Made label fetching properly await completion before displaying
  - Added "Refresh Labels" button when no labels found
  - Better error logging and empty result caching
  - Shows clear "Loading labels..." state during fetch

### UX Improvements
- **Template Manager Fallback Clarity**: Improved wording and added visual fallback chain
  - Changed "If X logo missing" to "If X logo not found" for clarity
  - Added numbered fallback priority chain showing exact order of operations
  - Clarified that global white logo fallback applies between preset preference and preset fallback
  - Better explanation of when fallback settings apply (batch edit mode only)

### Performance & Reliability
- Strict library filtering prevents cross-contamination in multi-library setups
- Cached empty label results prevent repeated failed API calls
- Improved timing of cache operations for more reliable data display

## v1.4.7 (2026-01-06)
### Major Features
- **TV Show Seasons Support**: Enhanced TV show rendering with season-specific poster generation
  - Season suffixes in local asset filenames (e.g., `Show Name_s01.jpg` for Season 1)
  - Season metadata passed through rendering pipeline with proper schema validation
  - Settings checkbox for season-specific local asset saving
  - "Coming Soon" badge support for unreleased seasons via TVDB integration

- **Scheduled Library Scans**: Automatic cron-based library scanning to keep Simposter synced with Plex
  - Configure cron schedule in Settings (e.g., "0 2 * * *" for daily 2 AM scans)
  - Optional library-specific scans or scan all libraries
  - APScheduler background daemon with proper initialization and restoration
  - Schedule status and next run time visible in Settings
  - Comprehensive cron validation (supports wildcards, ranges, steps, lists)

### Performance Optimizations
- **Database Indexing**: Added 6 new database indexes for 5-10x faster queries
  - `idx_movie_cache_tmdb`, `idx_movie_cache_composite` (library + rating_key)
  - `idx_tv_cache_tmdb`, `idx_tv_cache_tvdb`, `idx_tv_cache_composite`
  - `idx_poster_history_template_preset` for faster history filtering

- **Smart SessionStorage Caching**: LRU eviction system prevents quota errors
  - 4MB cache limit with automatic eviction of least-recently-used items
  - Access time tracking for intelligent cache management
  - Graceful QuotaExceededError handling
  - Cache statistics API (`getCacheStats()`)
  - Integrated in SettingsView with plans for full rollout

- **Debounced Editor Saves**: 300ms debounce on localStorage writes
  - 60-80% reduction in storage operations during slider adjustments
  - Eliminates UI stuttering when dragging sliders
  - Applied to both MovieEditorPane and TvShowEditorPane

- **Memory Leak Fixes**: Eliminated interval/timer memory leaks
  - Fixed scanPoller leak in SettingsView (interval continued after navigation)
  - Added proper cleanup in `onBeforeUnmount` hooks

### API & Security
- **Enhanced Rate Limiting**: Added rate limits for scheduler endpoints
  - `/api/scheduler/*` limited to 10 req/60s
  - Updated API_SECURITY.md documentation with scheduler endpoints

- **Improved Error Handling**: More specific network error handling
  - Separate handlers for `ConnectionError`, `RequestException`, and `Timeout`
  - Better logging with stack traces for unexpected errors

- **Cron Expression Validation**: Comprehensive validation for scheduler
  - Validates individual fields (minute: 0-59, hour: 0-23, etc.)
  - Supports wildcards (*), ranges (1-5), steps (*/5), lists (1,3,5)
  - Clear error messages for invalid expressions

### Technical Improvements
- **Simplified Library ID Handling**: Reduced complexity in scheduler API
  - Single-line normalization instead of verbose type checking
  - Pydantic already ensures correct types

- **Settings Architecture**: Unified scheduler settings persistence
  - Scheduler settings integrated into main settings store
  - Proper change detection with unsaved changes indicator
  - Settings snapshot system tracks all scheduler fields

### Documentation
- **Updated README**: Performance & Caching section highlights all optimizations
  - Smart caching, indexed database, debounced saves, memory leak protection
  - Updated Performance tips section with new best practices

- **Architecture Documentation**: Added scheduler initialization flow
  - Scheduler startup process documented
  - API router descriptions for all scheduler endpoints

- **PRD Updates**: APScheduler added to tech stack and architecture diagrams

### Bug Fixes
- Scheduler settings now persist correctly across page refreshes
- Scheduler shows unsaved changes indicator when modified
- SessionStorage operations no longer throw uncaught errors
- Scan polling properly stops when navigating away from Settings

## v1.4.6
### Major Features
- **Overlay Caching for Fast Rendering**: Pre-generated template effect overlays (matte, fade, vignette, grain, wash) for rapid batch poster generation
  - Composites cached PNG overlays with posters instead of rendering effects from scratch
  - 3-5x speed improvement for `uniformlogo` templates with or without logos
  - Configurable via "Use Overlay Cache" toggle in Performance settings (enabled by default)
  - Full uniformlogo support: logo positioning, text overlays, and borders all work in fast path
  - Other templates fall back to full render when logos present (future enhancement)

### Performance
- **Logo Selection Optimization**: Drastically faster logo selection in preview and batch operations
  - Analyzes only top 6 logo candidates (sorted by size/source priority) instead of all logos
  - Uses TMDb thumbnail images (w300) instead of full-resolution downloads
  - Concurrent color analysis via ThreadPoolExecutor instead of serial processing
  - Batch logo selection now completes in seconds instead of 20+ seconds
  - Batch rendering speed improvements: 3-5x faster with overlay cache, 2-3x faster logo selection

### Improvements
- **Batch Edit Fallback Logic**: Batch now correctly re-selects posters/logos after applying template fallback (matches preview behavior)
  - Respects fallback template and preset options in correct order
  - Re-picks logo after fallback to ensure compatibility with new template
- **Settings Labels UI Consolidation**: Unified "Default Labels to Remove" section displays both movie and TV libraries with type badges
  - Type badges (Movies/TV) clearly distinguish library type
  - Single organized section instead of separate movie/TV sections
  - Labels auto-refresh after library scan without manual "Refresh Cache" click

### Technical
- Added `useOverlayCache` field to PerformanceSettings schema (default: true)
- New `generate_overlay()` function in `rendering.py` extracts effect pipeline
- Optimized `pick_logo()` and `analyze_logo_color()` with thumbnail-based concurrent analysis
- Preset save endpoint generates and caches overlay PNG automatically
- Batch rendering checks overlay cache before falling back to standard render

## v1.4.5
### Major Features
- **TV Show Library Support**: Full TV show library integration with TVDB as metadata source, poster rendering, and library management
- **TVDB Integration**: Added TVDB API client for TV show metadata, logos, and poster fetching with language preference support
- **Fanart.tv Logo Fallback**: Enhanced logo source selection with TMDB/Fanart priority modes and automatic fallback when logos are missing
- **Preset Fallback System**: Template/preset fallback logic for missing posters and logos (e.g., switch to text-based template when logo unavailable)

### Improvements
- **Cache Reliability**: Fixed stale poster cache on app startup after inactivity; movies now refresh properly without manual cache clear
- **Library Switching**: Improved library switching to prevent cross-library contamination; display clears immediately when changing libraries
- **Library ID Handling**: Fixed "default" library errors; backend now correctly handles empty/default library IDs
- **Preview Rendering**: Preview endpoint now respects fallback templates and preset options (text overlay, logo mode) matching batch behavior
- **Settings UI**: Reorganized performance/quality settings; concurrent rendering functional (JPEG quality setting currently unused)

### Testing & In Progress
- **Batch Edit**: Continued refinements and testing for bulk poster operations

## v1.4.4
- **Database Tweaks**: Optimized the SQLite settings/presets path (initial migration landed in 1.4.2) for smoother reads/writes.
- **Template Manager**: New UI to manage presets plus poster/logo fallback logic (currently in testing).
- **Fanart Integration**: Added Fanart.tv logo source option and merge/fallback behavior alongside TMDB logos.
- **Batch Edit History**: Recorded actions/history groundwork to surface within batch edit (iterating on UI merge next).
- **Settings UI Cleanup**: Reorganized sections, clearer controls, better state handling.
- **Logo Selection Tweaks**: Improved white-logo preference and selection heuristics for clearer marks.

## v1.4.3
- **Multiple Library Support**: Enhanced UI with separate movie libraries subsection in Settings, improved library mapping management
- **Scanning Improvements**: Added 10-second cooldown to prevent multiple scan button clicks, backend protection against duplicate simultaneous scans
- **Cache Management**: Added "Clear Backend Cache" button with proper scan state protection, improved cache clearing UX
- **Docker Environment**: Environment variables now copy to database on container startup for initial setup, users can modify via UI afterwards
- **Performance**: Bulk API optimization for movie labels (50% reduction in API calls), better session storage caching
- **UI Polish**: Reorganized Settings page structure, improved button disable states, better visual feedback during operations

## v1.4.2
- Added SQLite-backed cache for Plex movies (labels/tmdb/poster metadata) with new `/api/cache/*` endpoints and incremental updates from live calls.
- Improved concurrency by pooling Plex HTTP connections (faster label/poster fetches on unRAID).
- Batch edit tab updates and local asset tab improvements.
- Settings persistence now centralized in the SQL db (legacy JSON migrated automatically).
- Version badge bumped to v1.4.2.

## v1.4.1
- Added visible version badge (top nav and Settings) and centralized version constant.
- Fixed presets: text overlay state and fields now reset/apply correctly; reload pulls fresh values.
- Preview/batch rendering now merges preset options with live slider values so UI tweaks reflect in renders.
- Batch mode improvements: preview caching when cycling movies; status overlay while batch runs; saves honor `saveLocation` and optional batch subfolder.
- Save-to-disk fixes: paths mapped under `/config/output`, template filename respected, frontend shows saved path.
- Settings: new “save batch runs into subfolder” toggle; scan library overlay shows progress/items.
