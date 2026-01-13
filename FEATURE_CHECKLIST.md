## v1.4.5 (Current)
- [x] TV show library support with TVDB integration
- [x] Template manager (UI/Backend with preset fallback system)
- [x] Fanart.tv logo source integration
- [x] Logo/poster fallback to different templates
- [x] Multi-library support (movies and TV)
- [x] JPEG quality settings wired up
- [x] Concurrent rendering functional
- [x] Cache reliability improvements (library validation, stale detection)
- [x] Library ID normalization (fixed "default" errors)

## v1.4.4 (Completed)
- [x] Template manager section (UI/Backend)
- [x] Asset manager tweaks (delete assets, re-render new assets)
- [x] Fanart logo integration
- [x] Database optimizations

## Docker
- [x] Support GUID/PUID env variables
- [x] Multi-library support with environment variables
- [x] TVDB/Fanart API key support

## v1.4.6 (Planned)
- [ ] Update notification on first startup (show changelog modal after version bump)
- [ ] Template overlay caching system:
  - [ ] Generate overlay PNG when saving template/preset (matte/fade/vignette/grain pre-rendered)
  - [ ] Store overlays in `config/overlays/{template_id}/{preset_id}.png`
  - [ ] Batch operations load cached overlay instead of re-rendering effects per poster
  - [ ] Performance setting: Enable/disable overlay cache (default: enabled)
  - [ ] Regenerate overlay when preset options change

## v1.5.0 (Current - 2026-01-11)
- [x] Poster generation history tracking with source column
- [x] History page with filtering (library, template, action, source)
- [x] Database migration for source column
- [x] History navigation with clock icon

## In Progress
- [ ] Batch edit refinements and testing
- [ ] Collection poster generation
- [ ] Sonarr TV show auto-generation (series-level complete, seasons pending)

## Roadmap
- [ ] Jellyfin integration
- [ ] Overlay manager (Kometa YAML generator)
- [ ] Advanced text overlay features
- [ ] Custom template upload/management
