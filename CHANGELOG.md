# Changelog

## v1.4.6 (In Progress)
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
