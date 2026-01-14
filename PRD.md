# Simposter Product Requirements Document (PRD)

## Document Information
- **Product Name**: Simposter
- **Version**: 1.0
- **Last Updated**: 2026-01-02
- **Document Owner**: Development Team

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Product Overview](#product-overview)
3. [Problem Statement](#problem-statement)
4. [Goals & Objectives](#goals--objectives)
5. [System Architecture](#system-architecture)
6. [Core Features](#core-features)
7. [Technical Specifications](#technical-specifications)
8. [Data Models](#data-models)
9. [API Endpoints](#api-endpoints)
10. [External Integrations](#external-integrations)
11. [Rendering Pipeline](#rendering-pipeline)
12. [User Workflows](#user-workflows)
13. [Performance & Scalability](#performance--scalability)
14. [Security & Privacy](#security--privacy)
15. [Future Roadmap](#future-roadmap)

---

## Executive Summary

**Simposter** is a self-hosted poster generation tool designed for Plex media server users who want professional, consistent, and customizable artwork for their movie and TV show libraries. It solves the problem of inconsistent library artwork by providing:

- Template-based poster generation with real-time preview
- Batch processing for entire libraries
- Integration with TMDB, Fanart.tv, and TVDB for high-quality source material
- Direct Plex integration for seamless poster uploads
- Automation via scheduled Plex library scans
- Intelligent logo selection and color matching

**Target Users**: Self-hosted media enthusiasts, Plex power users, home lab administrators

**Key Differentiator**: Fast, modern web UI with real-time preview and sophisticated template system that balances creative control with consistency

---

## Product Overview

### What is Simposter?

Simposter is a web application that generates custom posters for Plex media libraries by:
1. Fetching movie/TV metadata and artwork from external APIs
2. Applying user-defined templates and presets
3. Rendering high-quality posters with customizable effects
4. Uploading directly to Plex or saving locally

### Technology Stack

**Backend:**
- FastAPI (Python 3.x)
- Pillow + NumPy for image processing
- SQLite with WAL mode
- CairoSVG/resvg for SVG handling
- APScheduler for cron-based scheduling

**Frontend:**
- Vue 3 (Composition API)
- TypeScript
- Vite build system
- Tailwind CSS 4

**Deployment:**
- Docker containerized
- Volume mounts for configuration and output
- Production: Single-container serving Vue SPA via FastAPI

---

## Problem Statement

### Current Pain Points

1. **Inconsistent Artwork**: Plex libraries often have mixed poster styles from different metadata providers
2. **Manual Labor**: Creating custom posters for thousands of movies is time-consuming
3. **Limited Control**: Standard metadata providers don't offer customization
4. **No Automation**: Adding new movies requires manual poster creation
5. **Multi-Source Complexity**: Aggregating artwork from TMDB, Fanart, and TVDB is tedious

### User Stories

**As a Plex user**, I want:
- Uniform, professional-looking posters across my entire library
- Quick poster generation without learning Photoshop
- Automatic poster creation when new movies are added
- Ability to batch-process hundreds of movies at once
- Real-time preview before committing changes

---

## Goals & Objectives

### Primary Goals

1. **Speed**: Generate posters in < 2 seconds per movie
2. **Quality**: Output high-resolution (2000x3000) posters with professional effects
3. **Consistency**: Template-based system ensures uniform library appearance
4. **Automation**: Scheduled Plex library scans (no webhooks)
5. **User Experience**: Real-time preview with < 800ms response time

### Success Metrics

- Average render time: < 2 seconds
- Batch processing: 100 movies in < 5 minutes (with overlay cache)
- Preview latency: < 800ms
- User satisfaction: Minimal manual adjustments required

### Non-Goals

- Cloud-hosted SaaS offering (self-hosted only)
- Multi-user authentication (single-user assumption)
- Advanced video editing or metadata scraping
- Support for non-Plex media servers

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Movies    │  │  TV Shows   │  │   Batch     │         │
│  │    View     │  │    View     │  │    Edit     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Settings   │  │  Templates  │  │   Logs      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/REST API
┌────────────────────────▼────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              API Layer (Routes)                      │   │
│  │  movies • tv_shows • preview • save • batch          │   │
│  │  presets • templates • settings                      │   │
│  │  scheduler                                           │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Core Services                              │   │
│  │  • Rendering Engine  • Cache Manager                │   │
│  │  • Database Layer    • Configuration                │   │
│  │  • Scheduler (APScheduler)                          │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        External API Clients                          │   │
│  │  TMDB • Fanart.tv • TVDB • Plex                      │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
            ┌────────────┼────────────┐
            │            │            │
┌───────────▼───┐  ┌─────▼─────┐  ┌──▼──────────┐
│  SQLite DB    │  │   File    │  │  External   │
│  (metadata,   │  │  Storage  │  │     APIs    │
│   presets)    │  │  (cache,  │  │  (TMDB,     │
│               │  │  output)  │  │   Fanart,   │
│               │  │           │  │   TVDB,     │
│               │  │           │  │   Plex)     │
└───────────────┘  └───────────┘  └─────────────┘
```

### Directory Structure

```
simposter/
├── backend/                 # Python FastAPI backend
│   ├── main.py             # Application entry point
│   ├── config.py           # Settings & Plex helpers
│   ├── database.py         # SQLite operations
│   ├── rendering.py        # Core rendering pipeline
│   ├── schemas.py          # Pydantic models
│   ├── scheduler.py        # APScheduler background service
│   ├── tmdb_client.py      # TMDB API client
│   ├── tvdb_client.py      # TVDB API client
│   ├── fanart_client.py    # Fanart.tv API client
│   ├── logo_sources.py     # Multi-source logo merging
│   ├── api/                # API route handlers
│   │   ├── movies.py
│   │   ├── tv_shows.py
│   │   ├── preview.py
│   │   ├── save.py
│   │   ├── plexsend.py
│   │   ├── batch.py
│   │   ├── presets.py
│   │   ├── templates.py
│   │   ├── scheduler.py   # Scheduler API endpoints
│   │   └── ...
│   ├── templates/          # Template renderers
│   │   ├── universal.py
│   │   └── uniformlogo.py
│   └── assets/
│       └── selection.py    # Poster/logo selection logic
├── frontend/               # Vue 3 frontend
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router.ts
│   │   ├── views/          # Page components
│   │   ├── components/     # Reusable components
│   │   ├── stores/         # Pinia state management
│   │   └── services/       # API services
│   └── package.json
├── config/                 # Runtime configuration (volume)
│   ├── settings/
│   │   └── simposter.db    # SQLite database
│   ├── logs/
│   │   └── simposter.log   # Application logs
│   ├── output/             # Saved posters
│   ├── cache/              # Cached images
│   └── overlays/           # Pre-generated overlays
└── Dockerfile
```

---

## Core Features

### 1. Movie Poster Generation

**Description**: Generate custom posters for individual movies with real-time preview

**Key Capabilities:**
- Fetch movie metadata from Plex
- Load TMDB/Fanart/TVDB artwork
- Select from multiple poster styles (textless, text, all)
- Choose logo source and style (white, color, custom hex)
- Apply template (Universal or UniformLogo)
- Customize effects (matte, fade, vignette, grain, wash)
- Add text overlays with template variables
- Save locally and/or upload to Plex
- Remove Plex labels

**User Flow:**
1. Navigate to Movies view
2. Select movie from grid
3. Choose template and preset
4. Select poster and logo from thumbnails
5. Adjust settings (real-time preview updates)
6. Click "Save" or "Send to Plex"

### 2. TV Show Poster Generation

**Description**: Generate posters for TV shows and individual seasons

**Key Capabilities:**
- Fetch TV show metadata from Plex
- Load TVDB season-specific artwork
- Generate series poster (show-level)
- Generate season posters with season text overlay
- Separate preset options for series vs. seasons
- Batch render all seasons with "All" button
- Coming soon indicator support (TVDB)
- **Smart poster fallback**: When "textless" filter is selected for seasons, falls back to series textless posters if no season-specific textless posters are available (since textless posters have no text, they work for any season)

**User Flow:**
1. Navigate to TV Shows view
2. Select show from grid
3. Choose between series or season
4. Select template, preset, poster, logo
5. For seasons: Add season text (e.g., "Season 1")
6. Render individual or all seasons
7. Save/upload to Plex

### 3. Batch Processing

**Description**: Process multiple movies/shows simultaneously with progress tracking

**Key Capabilities:**
- Multi-select movies/shows from library
- Search and filter by title, year, labels
- Library-based filtering
- Real-time preview sidebar with template/preset updates
- Navigate through selected items before processing
- **TV Show Season Support**: Toggle "Include Seasons" to render all seasons for selected shows
- Season navigation in preview (Prev/Next Season buttons)
- Concurrent rendering (configurable workers)
- Progress tracking with detailed status
- Send to Plex and/or save locally
- Label removal for selected labels
- Session caching for performance
- Sent/Saved status indicators with timestamps
- Pagination for large libraries

**User Flow (Movies):**
1. Navigate to Movie Batch Edit view
2. Search/filter movies
3. Select multiple movies (checkboxes)
4. Choose template and preset
5. Preview first movie (navigate with arrow keys)
6. Click "Process Batch"
7. Monitor progress (shows X/Y completed)
8. Review results

**User Flow (TV Shows):**
1. Navigate to TV Batch Edit view
2. Search/filter shows
3. Select multiple shows (checkboxes)
4. Enable "Include Seasons" if rendering seasons
5. Choose template and preset (preview updates automatically)
6. Preview first show/season (navigate with Prev/Next buttons)
7. For seasons: Use Prev/Next Season to cycle through seasons
8. Click "Process Batch"
9. Monitor progress
10. Review results

**TV Show Batch Processing:**
- When "Include Seasons" is **disabled**: Renders series-level posters for each selected show
- When "Include Seasons" is **enabled**: Renders all seasons for each selected show with season text
- Preview shows current season with proper season text overlay
- Season text is automatically applied (e.g., "Season 1", "Season 2", "Specials")
- Uses season-specific posters when available, falls back to series posters

**Performance:**
- Default: 2 concurrent workers
- With overlay cache: ~3-5x faster
- 100 movies in ~5 minutes (cached)

### 4. Template System

**Description**: Extensible template system with two built-in templates

#### Template 1: Universal

**Purpose**: Full creative control for individual customization

**Features:**
- Poster zoom and vertical shift
- Matte gradient overlay (height, color)
- Fade effect (gradient blend)
- Vignette (radial darkening)
- Film grain (NumPy-based noise)
- Wash effect (color tone overlay)
- Logo modes: stock, match (extract color), hex (custom)
- Logo scaling and Y-offset positioning
- Text overlay with font customization
- Shadow and stroke effects
- Rounded corners and border

**Best For**: Single posters, creative projects, diverse library styles

#### Template 2: UniformLogo

**Purpose**: Precise, consistent logo placement across library

**Features:**
- All Universal features
- Bounding box logo placement
- Auto-scaling within max width/height
- Centered positioning at X/Y percentages
- Override mode for manual adjustments

**Best For**: Batch processing, uniform library appearance, logo-centric designs

**Template API:**
```python
def render_{template_id}(
    background: Image.Image,
    logo: Optional[Image.Image],
    options: Dict[str, Any]
) -> Image.Image
```

### 5. Preset Management

**Description**: Save and reuse poster settings for consistency

**Key Capabilities:**
- Create/edit/delete presets
- Organize by template
- Season-specific options (TV shows)
- Import/export presets as JSON
- Merge or replace on import
- Database storage with versioning

**Preset Structure:**
```json
{
  "id": "neon-blue",
  "template_id": "universal",
  "name": "Neon Blue",
  "options": {
    "posterZoom": 1.2,
    "matteHeight": 0.3,
    "fadeHeight": 0.2,
    "logoMode": "hex",
    "logoHex": "#00ffff",
    "logoScale": 0.4,
    "logoOffsetY": 0.15
  },
  "season_options": {
    "season_text": "Season {season}"
  }
}
```

### 6. Automation

Simposter provides multiple automation channels:

**Scheduled Library Scans** — Automatic Plex library scanning via cron-based scheduler
**Webhook Integration** — Real-time poster generation via Radarr, Sonarr, and Tautulli webhooks

**Capabilities:**
- Scheduled scans: Configure cron in Settings to keep Simposter in sync with Plex
- Webhook automation: Receive events from Radarr/Sonarr/Tautulli and auto-generate posters
- Preview-first workflow: Manual generation remains fast and consistent

No webhook endpoints or integration polling are available.

### 7. Library Scanning & Caching

**Description**: Pre-cache all movies/shows for instant UI loading

**Key Capabilities:**
- Scan all Plex libraries
- Cache metadata (title, year, TMDB ID, labels)
- Download and cache poster images
- Progress tracking API
- SessionStorage caching (frontend)
- Library-based filtering

**Benefits:**
- Instant movie grid loading
- No Plex API calls on page load
- Faster batch processing

### 8. Settings Management

**Description**: Centralized configuration for all aspects of Simposter

**Settings Categories:**

#### Plex Configuration
- Server URL and token
- Movie/TV library names
- Library mappings
- TLS verification toggle

#### API Keys
- TMDB API key (required)
- TVDB API key (optional)
- Fanart.tv API key (optional)
- Test API keys endpoint

#### Automation
- Scheduled Plex library scans configuration
- No external integrations or polling

#### Performance
- Concurrent renders (1-8 workers)
- TMDB rate limit (req/10s)
- TVDB rate limit (req/10s)
- Memory limit (MB)
- Overlay cache enable/disable

#### Image Quality
- Output format (JPG, PNG, WebP)
- JPG quality (1-100)
- PNG compression (0-9)
- WebP quality (1-100)

#### UI Preferences
- Theme (neon)
- Poster grid density
- Default labels to remove
- API source priority
- Save location template

**Storage Priority:**
1. Environment variables (highest)
2. Database (`settings` table)
3. Legacy JSON files
4. Pydantic defaults (lowest)

### 9. Poster History Tracking (v1.5.0+)

**Description**: Complete audit log of all poster operations with source tracking

**Tracked Data:**
- Rating key, title, year
- Template and preset used
- Action (saved_local, sent_to_plex)
- Source (manual, batch, auto)
- Save path
- Timestamp
- Library ID

**History UI:**
- Dedicated History page (/history) with filterable table
- Filter by library (shows display names, not IDs)
- Filter by template, action, and source
- Color-coded source badges:
  - Green: Auto (from integration polling)
  - Purple: Batch (batch operations)
  - Gray: Manual (individual edits)
- Refresh button for real-time updates
- Results count display
- Sortable columns

**API:**
```
GET /api/history?library={id}&template={id}&action={action}&limit=500
GET /api/poster-status (POST)
Body: {"rating_keys": [], "library_id": "1"}
Response: {"status": {rating_key: {action, timestamp, template_id, preset_id}}}
```

**Use Cases:**
- Track which posters were auto-generated vs manual
- Audit batch operations
- Identify which movies have custom posters
- Re-apply same template/preset
- Troubleshooting and debugging
- Monitor integration polling effectiveness

### 10. Local Assets Management

**Description**: Browse and manage saved posters

**Features:**
- List all saved posters from output directory
- File metadata (size, modified date)
- Delete saved posters
- Organized by library/title/year

**Output Path Template:**
```
/config/output/{library}/{title} ({year})/poster.jpg
```

---

## Technical Specifications

### Backend Technologies

#### FastAPI Application (`main.py`)

**Key Features:**
- Async request handling
- CORS middleware (allow all origins)
- Static file serving (Vue SPA)
- API routing with prefix `/api`
- Graceful shutdown handling

**Startup Tasks:**
- Initialize database
- Check and update version (automatic backups)
- Load settings from DB
- Initialize Plex connection pool

#### Image Processing (`rendering.py`)

**Dependencies:**
- **Pillow (PIL)**: Core image manipulation
- **NumPy**: Film grain generation
- **CairoSVG**: Primary SVG converter
- **pillow-resvg**: SVG plugin fallback
- **resvg binary**: External converter fallback
- **Inkscape**: Last-resort SVG converter

**SVG Handling Strategy:**
1. Try CairoSVG (high quality, requires Cairo)
2. Try pillow-resvg (bundled, no deps)
3. Try resvg binary (external binary)
4. Try Inkscape CLI (widely available)
5. Raise error if all fail

**Overlay Caching System:**
```python
def generate_overlay(options: Dict, w: int, h: int) -> Image.Image:
    """Pre-generate deterministic effects"""
    # Cached: matte + fade + vignette + wash
    # Not cached: grain (per-render freshness)
```

**Cache Path:**
```
/config/overlays/{template_id}/{preset_id}.png
```

**Benefits:**
- 3-5x faster batch rendering
- Reduced CPU usage
- Consistent visual results

#### Database Layer (`database.py`)

**SQLite Configuration:**
- WAL mode (Write-Ahead Logging)
- Busy timeout: 5 seconds
- Journal mode: WAL
- Auto-vacuum: Incremental
- Synchronous: Normal (balance safety/speed)

**Key Functions:**
```python
init_database()                    # Create tables, run migrations
check_and_update_version()         # Version check + backup
save_ui_settings(settings: dict)   # Persist settings to DB
load_ui_settings() -> dict         # Load settings from DB
save_preset(preset: dict)          # UPSERT preset
delete_preset(id: str, template: str) # Remove preset
get_all_presets() -> dict          # Load all presets grouped by template
cache_movie(rating_key: str, data: dict) # Cache movie metadata
get_cached_movies(library: str) -> list # Retrieve cached movies
```

**Automatic Backups:**
- Triggered on version mismatch
- Backup format: `simposter_v{old_version}.db.bak`
- Preserves all user data (presets, settings, cache)

#### External API Clients

##### TMDB Client (`tmdb_client.py`)

**Base URL:** `https://api.themoviedb.org/3`

**Key Methods:**
```python
get_movie_details(tmdb_id: int) -> dict
get_images_for_movie(tmdb_id: int) -> dict
get_tv_show_details(tmdb_id: int) -> dict
get_tv_season_images(tmdb_id: int, season: int) -> dict
get_movie_external_ids(tmdb_id: int) -> dict  # IMDB, TVDB
```

**Rate Limiting:**
- Sliding window implementation
- Default: 40 requests per 10 seconds
- Configurable via settings
- Automatic retry with exponential backoff

**Language Fallback:**
1. User preference (e.g., `en-US`)
2. Original language (from movie metadata)
3. English (`en`)
4. No language (`null` = textless)

**Image Metadata:**
```python
{
  "url": "https://image.tmdb.org/t/p/original/...",
  "thumb": "https://image.tmdb.org/t/p/w342/...",
  "width": 2000,
  "height": 3000,
  "language": "en" | "null",
  "has_text": bool,
  "source": "tmdb"
}
```

##### Fanart.tv Client (`fanart_client.py`)

**Base URL:** `https://webservice.fanart.tv/v3`

**Key Methods:**
```python
get_logos_for_movie(tmdb_id: int) -> list
get_images_for_movie(tmdb_id: int) -> dict
get_images_for_tv_show(tvdb_id: int) -> dict
```

**Logo Types:**
- `hdmovielogo`: High-definition PNG logos (priority)
- `movielogo`: Standard movie logos
- `clearlogo`: Additional clearlogos
- `hdmovieclearart`: Clearart (merged into logos)

**Language Codes:**
- `"00"`: Textless/universal
- `"en"`: English
- `"es"`: Spanish
- etc.

##### TVDB Client (`tvdb_client.py`)

**Base URL:** `https://api4.thetvdb.com/v4`

**Authentication:**
- Bearer token (24h validity)
- Automatic refresh with 6h TTL
- Login endpoint: `/login`
- Optional PIN for subscriber features

**Key Methods:**
```python
login() -> str  # Get bearer token
get_series_images(tvdb_id: int) -> list
get_season_images(tvdb_id: int, season: int) -> list
get_movie_images(tvdb_id: int) -> list
```

**Artwork Types:**
- Type ID `2`: Poster
- Type ID `3`: Backdrop/fanart
- Type ID `23`: Clearlogo
- Type ID `24`: Clearart

**Season Filtering:**
- Uses `seasonId` field to filter season-specific art
- Supports coming soon indicators

##### Multi-Source Logo Merging (`logo_sources.py`)

**Purpose**: Aggregate logos from TMDB and Fanart.tv based on user preference

**Source Preference Options:**
- `tmdb`: TMDB logos only
- `fanart`: Fanart logos only
- `merged`: Combine both (TMDB first, then Fanart)
- `auto`: Try preferred source, fallback to other

**Merge Strategy:**
```python
def get_logos_merged(
    tmdb_id: int,
    source_preference: str,
    original_language: str,
    tmdb_imgs: dict
) -> List[dict]:
    # 1. Get TMDB logos
    # 2. Get Fanart logos
    # 3. Merge based on preference
    # 4. Deduplicate by URL
    # 5. Return unified list
```

**Logo Preference** (post-merge):
- `white`: Prefer low-saturation logos (< 0.3 avg saturation)
- `color`: Prefer high-saturation logos
- `first`: Use first available logo

### Frontend Technologies

#### Vue 3 Composition API

**Key Composables:**
```typescript
// Reactive state
const tmdbId = ref<number | null>(null)
const posters = ref<Poster[]>([])
const selectedPoster = ref<Poster | null>(null)
const options = ref<PresetOptions>({})

// Computed properties
const bgUrl = computed(() => selectedPoster.value?.url || '')
const logoUrl = computed(() => selectedLogo.value?.url || '')

// Watchers
watch([bgUrl, logoUrl, options], () => {
  // Debounced preview update
  doPreview()
}, { deep: true })
```

**Component Structure:**
```
views/
├── MoviesView.vue           # Movie library grid
├── TvShowsView.vue          # TV show library
├── BatchEditView.vue        # Movie batch processing UI
├── TvBatchEditView.vue      # TV show batch processing UI
├── SettingsView.vue         # Settings management
└── TemplateManagerView.vue  # Template/preset manager

components/
├── editor/
│   ├── MovieEditorPane.vue      # Single movie editor
│   ├── TvShowEditorPane.vue     # TV show editor (2000+ lines)
│   ├── PosterSelector.vue       # Poster thumbnail grid
│   └── LogoSelector.vue         # Logo thumbnail grid
├── movies/
│   └── MovieCard.vue            # Movie grid item
└── layout/
    ├── Navbar.vue               # Top navigation
    └── Sidebar.vue              # Side navigation
```

#### State Management (Pinia)

**Stores:**
```typescript
// operationStatus.ts
export const useOperationStatusStore = defineStore('operationStatus', {
  state: () => ({
    scanning: false,
    batchProcessing: false,
    progress: { current: 0, total: 0 }
  })
})

// scan.ts
export const useScanStore = defineStore('scan', {
  state: () => ({
    scanProgress: null,
    cacheStatus: {}
  })
})

// ui.ts
export const useUIStore = defineStore('ui', {
  state: () => ({
    theme: 'neon',
    posterDensity: 20,
    sidebarCollapsed: false
  })
})
```

#### API Service Layer (`services/render.ts`)

**Key Functions:**
```typescript
export const preview = async (
  movie: MovieInput,
  bgUrl: string,
  logoUrl?: string,
  options?: PresetOptions,
  templateId?: string,
  presetId?: string,
  disableCache?: boolean,
  skipLastPreviewUpdate?: boolean
): Promise<{ image_base64: string }>

export const save = async (
  movie: MovieInput,
  bgUrl: string,
  logoUrl: string,
  options: PresetOptions,
  templateId: string,
  sendToPlex: boolean,
  saveLocally: boolean
): Promise<{ success: boolean }>
```

#### Caching Strategy (Frontend)

**SessionStorage Cache:**
```typescript
// Cache structure
{
  "movies": [...],           // All movies from Plex
  "labels": {...},           // Movie labels
  "posters": {...},          // Poster URLs
  "tv_shows": [...],         // All TV shows
  "settings": {...}          // UI settings
}
```

**Benefits:**
- Instant page loads on refresh
- Reduced API calls
- Persists during session
- Auto-invalidates on app close

**Cache Keys:**
```typescript
const CACHE_KEYS = {
  movies: 'simposter_movies',
  labels: 'simposter_labels',
  posters: 'simposter_posters',
  tv_shows: 'simposter_tv_shows'
}
```

#### Styling (Tailwind CSS 4)

**Theme:**
- Neon theme (default)
- Dark background with vibrant accents
- Cyan/purple gradient highlights
- Card-based layout

**Custom Classes:**
```css
.btn-primary: Cyan gradient button
.btn-secondary: Purple outline button
.card: Dark card with border
.grid-poster: Responsive poster grid
```

---

## Data Models

### Database Schema

#### Settings Table
```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    category TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Example rows:
-- ('plex.url', 'http://localhost:32400', 'plex', '2024-01-15 10:00:00')
-- ('tmdb.apiKey', 'abc123...', 'tmdb', '2024-01-15 10:00:00')
-- ('app.version', '1.2.3', 'app', '2024-01-15 10:00:00')
```

#### Presets Table
```sql
CREATE TABLE presets (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    name TEXT NOT NULL,
    options_json TEXT NOT NULL,
    season_options_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_presets_template ON presets(template_id);
```

#### Movie Cache Table
```sql
CREATE TABLE movie_cache (
    rating_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER,
    added_at INTEGER,
    tmdb_id INTEGER,
    tvdb_id INTEGER,
    poster_url TEXT,
    labels_json TEXT,
    library_id TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_movie_cache_updated ON movie_cache(updated_at);
CREATE INDEX idx_movie_cache_title ON movie_cache(title);
CREATE INDEX idx_movie_cache_library ON movie_cache(library_id);
```

#### TV Cache Table
```sql
CREATE TABLE tv_cache (
    rating_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER,
    added_at INTEGER,
    tmdb_id INTEGER,
    tvdb_id INTEGER,
    seasons_json TEXT,
    poster_url TEXT,
    labels_json TEXT,
    library_id TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tv_cache_updated ON tv_cache(updated_at);
CREATE INDEX idx_tv_cache_title ON tv_cache(title);
CREATE INDEX idx_tv_cache_library ON tv_cache(library_id);
```

#### Poster History Table
```sql
CREATE TABLE poster_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rating_key TEXT NOT NULL,
    library_id TEXT,
    title TEXT,
    year INTEGER,
    template_id TEXT,
    preset_id TEXT,
    action TEXT,  -- 'saved_local' | 'sent_to_plex'
    save_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_poster_history_rating ON poster_history(rating_key);
CREATE INDEX idx_poster_history_library ON poster_history(library_id);
CREATE INDEX idx_poster_history_created ON poster_history(created_at);
```

### Pydantic Models (`schemas.py`)

#### Movie Model
```python
class Movie(BaseModel):
    key: str                    # Plex rating key
    title: str
    year: Optional[int] = None
    added_at: Optional[int] = None
    poster: Optional[str] = None
    labels: List[str] = []
    library_id: Optional[str] = None
```

#### Preview Request
```python
class PreviewRequest(BaseModel):
    movie: Movie
    bg_url: str
    logo_url: Optional[str] = None
    options: Dict[str, Any] = {}
    template_id: str = "universal"
    preset_id: Optional[str] = None
    disable_cache: bool = False
    season_text: Optional[str] = None  # For TV seasons
```

#### Save Request
```python
class SaveRequest(BaseModel):
    movie: Movie
    bg_url: str
    logo_url: Optional[str] = None
    options: Dict[str, Any] = {}
    template_id: str = "universal"
    preset_id: Optional[str] = None
    send_to_plex: bool = False
    save_locally: bool = True
    labels_to_remove: List[str] = []
    season_text: Optional[str] = None
```

#### Batch Request
```python
class BatchRequest(BaseModel):
    rating_keys: List[str]
    template_id: str
    preset_id: Optional[str] = None
    send_to_plex: bool = False
    save_locally: bool = True
    labels: List[str] = []  # Labels to remove
    options: Dict[str, Any] = {}
```

#### Preset Models
```python
class PresetSaveRequest(BaseModel):
    id: str
    template_id: str
    name: str
    options: Dict[str, Any]
    season_options: Optional[Dict[str, Any]] = None

class PresetDeleteRequest(BaseModel):
    id: str
    template_id: str
```

#### Settings Models
```python
class PlexSettings(BaseModel):
    url: str
    token: str
    movieLibraryName: Optional[str] = None
    tvShowLibraryName: Optional[str] = None
    verifyTLS: bool = True

class TMDBSettings(BaseModel):
    apiKey: str
    languagePreference: str = "en-US"

class PerformanceSettings(BaseModel):
    concurrentRenders: int = 2
    tmdbRateLimit: int = 40
    tvdbRateLimit: int = 20
    memoryLimit: int = 2048
    useOverlayCache: bool = True

class ImageQualitySettings(BaseModel):
    outputFormat: str = "jpg"
    jpgQuality: int = 95
    pngCompression: int = 6
    webpQuality: int = 90

class UISettings(BaseModel):
    plex: PlexSettings
    tmdb: TMDBSettings
    tvdb: Optional[TVDBSettings] = None
    fanart: Optional[FanartSettings] = None
    performance: PerformanceSettings
    imageQuality: ImageQualitySettings
    theme: str = "neon"
    posterDensity: int = 20
    saveLocation: str = "/config/output/{library}/{title} ({year})/poster.jpg"
    defaultLabelsToRemove: List[str] = []
    apiOrder: List[str] = ["tmdb", "fanart", "tvdb"]
```


---

## API Endpoints

### Movies API

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/api/movies` | GET | List all movies from Plex | Query: `library={id}` | `[{key, title, year, ...}]` |
| `/api/movie/{rating_key}/tmdb` | GET | Get TMDB ID for movie | - | `{tmdb_id: 12345}` |
| `/api/movie/{rating_key}/poster` | GET | Fetch/serve cached poster | Query: `raw=1` | Image (JPEG) |
| `/api/movie/{rating_key}/labels` | GET | Get Plex labels | - | `{labels: ["Overlay"]}` |
| `/api/movie/{rating_key}/labels` | DELETE | Remove labels | Query: `labels=Overlay,Test` | `{success: true}` |
| `/api/movies/labels/bulk` | POST | Get labels for multiple movies | `{rating_keys: []}` | `{rating_key: [labels]}` |
| `/api/tmdb/{tmdb_id}/images` | GET | Fetch TMDB+Fanart images | Query: `source_preference=merged` | `{posters: [], logos: []}` |
| `/api/scan-library` | POST | Scan Plex library | `{library_id: "1"}` | `{message: "Scan started"}` |
| `/api/scan-progress` | GET | Get scan progress | - | `{total: 100, current: 50}` |

### TV Shows API

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/api/tv-shows` | GET | List TV shows | Query: `library={id}` | `[{key, title, year, ...}]` |
| `/api/tv-show/{rating_key}/poster` | GET | Serve TV show poster | Query: `raw=1` | Image (JPEG) |
| `/api/tv-show/{rating_key}/labels` | GET | Get TV show labels | - | `{labels: []}` |
| `/api/tv-show/{rating_key}/seasons` | GET | Get season info | - | `[{index: 1, title: "Season 1"}]` |
| `/api/tvdb/{tvdb_id}/season/{season}/images` | GET | Fetch TVDB season images | - | `{posters: [], logos: []}` |

### Rendering API

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/api/preview` | POST | Generate preview | `PreviewRequest` | `{image_base64: "data:image/jpeg;base64,..."}` |
| `/api/save` | POST | Save poster | `SaveRequest` | `{success: true, path: "/config/output/..."}` |
| `/api/plexsend` | POST | Upload to Plex | `PlexSendRequest` | `{success: true, message: "Uploaded"}` |
| `/api/batch` | POST | Batch process movies/shows | `BatchRequest` (supports both movies and TV shows) | `{message: "Batch started"}` |
| `/api/batch-progress` | GET | Get batch progress | - | `{total: 100, current: 50, status: "processing"}` |

**Batch Request Format:**
```typescript
{
  rating_keys: string[]          // Array of Plex rating keys (shows or movies)
  template_id: string
  preset_id?: string
  options: Record<string, any>   // Template-specific options
  send_to_plex: boolean
  save_locally: boolean
  labels?: string[]              // Labels to remove (if send_to_plex=true)
  library_id?: string
  include_seasons?: boolean      // TV shows only: render all seasons
}
```

**TV Show Batch Behavior:**
- If `include_seasons=false`: Renders series-level posters
- If `include_seasons=true`: Renders all seasons for each show with automatic season text

### Presets & Templates API

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/api/presets` | GET | Get all presets | - | `{universal: [{id, name, options}]}` |
| `/api/presets` | POST | Save preset | `PresetSaveRequest` | `{success: true}` |
| `/api/presets` | DELETE | Delete preset | `PresetDeleteRequest` | `{success: true}` |
| `/api/presets/import` | POST | Import presets | `{presets: {}, mode: "merge"}` | `{imported: 5}` |
| `/api/presets/export` | GET | Export presets | - | `{universal: [...]}` (JSON) |
| `/api/templates` | GET | List templates | - | `[{id, name, description}]` |
| `/api/template-manager/overlays` | POST | Generate overlay cache | `{template_id, preset_id}` | `{success: true}` |

### Settings API

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/api/ui-settings` | GET | Get UI settings | - | `UISettings` object |
| `/api/ui-settings` | POST | Save UI settings | `UISettings` | `{success: true}` |
| `/api/test-api-keys` | POST | Test API keys | `{tmdb, tvdb, fanart}` | `{tmdb: {status: "ok"}}` |

### Utility API

| Endpoint | Method | Description | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/api/logs` | GET | Retrieve logs | Query: `lines=100` | `{logs: "..."}` |
| `/api/history` | GET | Get poster history | Query: `library={id}&limit=500` | `[{id, title, template_id, ...}]` |
| `/api/cache/clear` | POST | Clear caches | `{type: "movies"}` | `{success: true, cleared: 150}` |

| `/api/local-assets` | GET | List saved posters | - | `[{path, size, modified}]` |
| `/api/local-assets/{path}` | DELETE | Delete saved poster | - | `{success: true}` |

---

## External Integrations

### Plex Media Server

**Purpose**: Primary media library source and poster upload destination

**Authentication:**
- Header: `X-Plex-Token: {token}`
- Token obtained from Plex account settings

**Key Endpoints Used:**
```
GET  /library/sections/{id}/all?type=1        # List movies
GET  /library/metadata/{rating_key}           # Movie metadata
POST /library/metadata/{rating_key}/posters?url={url}  # Upload poster
PUT  /library/sections/{id}/all?type=1&id={rating_key}&label[].tag.tag={label}  # Add label
DELETE /library/metadata/{rating_key}/labels/{label_id}  # Remove label
GET  /library/metadata/{rating_key}/refresh   # Refresh metadata
```

**Connection Pooling:**
```python
session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=32,
    pool_maxsize=64,
    max_retries=Retry(
        total=2,
        backoff_factor=0.2,
        status_forcelist=[502, 503, 504]
    )
)
session.mount('http://', adapter)
session.mount('https://', adapter)
```

**Label Removal Strategy** (3 fallback methods):
1. Try DELETE `/library/metadata/{rating_key}/labels/{label_id}`
2. Try PUT with empty label array
3. Try DELETE with alternative endpoint structure

### TMDB (The Movie Database)

**Purpose**: Movie/TV metadata, posters, and logos

**Authentication:**
- Query param: `api_key={key}`

**Key Endpoints:**
```
GET /movie/{tmdb_id}                           # Movie details
GET /movie/{tmdb_id}/images                    # Posters, backdrops, logos
GET /movie/{tmdb_id}/external_ids              # IMDB, TVDB IDs
GET /tv/{tmdb_id}                              # TV show details
GET /tv/{tmdb_id}/images                       # TV show images
GET /tv/{tmdb_id}/season/{season}/images      # Season images
```

**Rate Limiting:**
- Default: 40 requests per 10 seconds
- Sliding window implementation
- Auto-retry with exponential backoff

**Image URLs:**
```
Original: https://image.tmdb.org/t/p/original/{file_path}
Thumb: https://image.tmdb.org/t/p/w342/{file_path}
```

**Language Handling:**
- Textless posters: `iso_639_1: null`
- Text posters: `iso_639_1: "en"`
- Fallback chain: preference → original → en → null

### Fanart.tv

**Purpose**: High-quality HD clearlogos and additional artwork

**Authentication:**
- Header: `api-key: {key}`

**Key Endpoints:**
```
GET /v3/movies/{tmdb_id}    # Movie artwork (requires TMDB ID)
GET /v3/tv/{tvdb_id}        # TV show artwork (requires TVDB ID)
```

**Logo Types:**
- `hdmovielogo`: PNG logos (priority)
- `movielogo`: Standard logos
- `clearlogo`: Additional clearlogos
- `hdmovieclearart`: Clearart

**Language Codes:**
- `"00"`: Textless/universal
- `"en"`, `"es"`, etc.: Language-specific

### TVDB (TheTVDB)

**Purpose**: TV show metadata, season posters

**Authentication:**
- Bearer token (24h validity)
- Login required before API access

**Login Flow:**
```python
POST /login
Body: {"apikey": "{key}", "pin": "{pin}"}  # PIN optional
Response: {"data": {"token": "{bearer_token}"}}
```

**Key Endpoints:**
```
GET /series/{tvdb_id}/extended?meta=translations  # Full series data
GET /artworks?seriesId={tvdb_id}&type=2           # Posters (type=2)
GET /artworks?seriesId={tvdb_id}&type=23          # Logos (type=23)
```

**Artwork Type IDs:**
- `2`: Poster
- `3`: Backdrop/fanart
- `23`: Clearlogo
- `24`: Clearart

**Season Filtering:**
- Filter by `seasonId` field in artwork response
- Season 0 = Specials

**Rate Limiting:**
- Default: 20 requests per 10 seconds
- Token auto-refresh every 6 hours

---

## Rendering Pipeline

### High-Level Flow

```
User Input → Fetch Assets → Select Poster/Logo → Render Template → Output
```

### Detailed Pipeline

#### Step 1: Asset Fetching

**For Movies:**
1. Get TMDB ID from Plex metadata
2. Fetch TMDB images (posters, backdrops, logos)
3. Fetch Fanart.tv logos (if API key provided)
4. Merge logos based on source preference
5. Apply language and text filters

**For TV Shows:**
1. Get TVDB ID from Plex metadata
2. Fetch TVDB series images
3. Fetch TVDB season images (for specific season)
4. Fetch TMDB images (fallback)
5. Merge and filter

#### Step 2: Poster/Logo Selection

**Poster Selection Logic** (`assets/selection.py`):
```python
def select_best_poster(
    posters: List[dict],
    filter: str,  # "all", "textless", "text"
    language_preference: str = "en"
) -> dict:
    # 1. Filter by text preference
    # 2. Filter by language (prefer user pref → original → en → null)
    # 3. Sort by width (prefer higher resolution)
    # 4. Return first match
```

**TV Season Poster Selection** (Frontend: `TvShowEditorPane.vue`):

For season posters with **textless** filter:
```typescript
// Priority order:
1. Season-specific textless poster (TVDB/TMDB)
2. Series textless poster (fallback - works because no text)
3. Plex default poster

// Logic:
const seasonTextless = seasonPosters.find(p => p.has_text === false)
const seriesTextless = seriesPosters.find(p => p.has_text === false)
const choice = seasonTextless || seriesTextless || plexDefault
```

**Rationale**: Textless posters have no text overlay, so a series textless poster can be used for any season without looking incorrect. This maximizes the chances of finding a high-quality textless poster.

For season posters with **text** or **all** filters:
- Only use season-specific posters (no fallback to series)
- Series posters may have show title text that would be incorrect for seasons

**Known Issue - Textless Poster Detection:**

The current implementation determines if a poster has text based on language metadata from TMDB/TVDB APIs:
- `language=null` or `language=""` → `has_text=False` (textless)
- `language="en"` or any language → `has_text=True` (has text)

**Problem**: TMDB/TVDB language tags indicate the "intended audience language" or show language, NOT whether the poster physically contains text overlays. Many posters tagged with `language="en"` or `language="eng"` are actually textless (clean artwork with no title/text), while some posters with no language tag may have text.

**Current Workaround**: Use the "all" filter instead of "textless" to see all available posters, then manually select the ones without text.

**Proposed Solutions** (Future Enhancement):
1. **Manual Override**: Add UI checkbox "Mark as textless" to override API metadata
2. **OCR Detection**: Use optical character recognition to detect text on posters automatically
3. **Community Database**: Build a community-contributed database of textless poster IDs
4. **Machine Learning**: Train a model to detect text presence in posters
5. **Provider Priority**: Add option to prioritize specific providers known for better textless tagging (e.g., Fanart.tv with `lang="00"` is more reliable)

**Logo Selection Logic:**
```python
def select_best_logo(
    logos: List[dict],
    preference: str,  # "white", "color", "first"
    source_preference: str = "merged"
) -> dict:
    # 1. Merge sources based on preference
    # 2. Calculate average saturation for each logo
    # 3. Sort by saturation (white = low, color = high)
    # 4. Return first match
```

#### Step 3: Image Download

**Download Function:**
```python
def download_image(url: str) -> Image.Image:
    # 1. Check disk cache (/config/cache/posters/)
    # 2. If cached, load from disk
    # 3. If not cached:
    #    a. Download with retry logic (3 attempts)
    #    b. Convert SVG if needed (4 fallback strategies)
    #    c. Convert to RGB
    #    d. Cache to disk
    # 4. Return PIL Image
```

**SVG Conversion Fallback:**
```python
def convert_svg(svg_data: bytes) -> Image.Image:
    try:
        # Strategy 1: CairoSVG (high quality)
        return cairosvg.svg2png(bytestring=svg_data)
    except:
        try:
            # Strategy 2: pillow-resvg (bundled)
            return Image.open(io.BytesIO(svg_data))
        except:
            try:
                # Strategy 3: resvg binary (external)
                return subprocess_convert_svg(svg_data)
            except:
                # Strategy 4: Inkscape CLI
                return inkscape_convert_svg(svg_data)
```

#### Step 4: Template Rendering

**Universal Template Rendering Flow:**

```python
def render_universal(bg: Image, logo: Image, options: dict) -> Image:
    # 1. Initialize canvas (2000x3000 RGB)
    canvas = Image.new("RGB", (2000, 3000), (0, 0, 0))

    # 2. Process background
    bg_resized = resize_cover(bg, 2000, 3000)
    bg_zoomed = apply_zoom(bg_resized, options["posterZoom"])
    bg_shifted = apply_shift_y(bg_zoomed, options["posterShiftY"])
    canvas.paste(bg_shifted, (0, 0))

    # 3. Apply matte + fade
    matte = create_matte_gradient(options["matteHeight"], options["matteColor"])
    fade = create_fade_gradient(options["fadeHeight"])
    canvas = Image.alpha_composite(canvas.convert("RGBA"), matte)
    canvas = Image.alpha_composite(canvas, fade)

    # 4. Apply vignette
    vignette = create_vignette(options["vignette"])
    canvas = Image.alpha_composite(canvas, vignette)

    # 5. Add grain (NumPy-based)
    grain = generate_grain(2000, 3000, options["grain"])
    canvas_array = np.array(canvas)
    canvas_array = np.clip(canvas_array + grain, 0, 255).astype(np.uint8)
    canvas = Image.fromarray(canvas_array)

    # 6. Apply wash
    wash = create_wash_overlay(options["wash"])
    canvas = Image.alpha_composite(canvas, wash)

    # 7. Process and composite logo
    if logo:
        # Apply logo mode (stock, match, hex)
        if options["logoMode"] == "match":
            logo_colored = extract_color_from_poster(canvas, logo)
        elif options["logoMode"] == "hex":
            logo_colored = recolor_logo(logo, options["logoHex"])
        else:
            logo_colored = logo

        # Scale and position
        logo_scaled = scale_logo(logo_colored, options["logoScale"])
        logo_y = int(3000 * options["logoOffsetY"])
        logo_x = (2000 - logo_scaled.width) // 2  # Center horizontally

        # Composite with anti-aliasing
        canvas.paste(logo_scaled, (logo_x, logo_y), logo_scaled)

    # 8. Render text overlay (if enabled)
    if options["textOverlayEnabled"]:
        text = options["customText"].format(
            title=movie["title"],
            year=movie["year"]
        )
        canvas = render_text(canvas, text, options)

    # 9. Apply rounded corners
    if options["roundedCorners"]:
        canvas = apply_rounded_corners(canvas, options["cornerRadius"])

    # 10. Add border
    if options["borderEnabled"]:
        canvas = add_border(canvas, options["borderWidth"], options["borderColor"])

    # 11. Convert back to RGB
    return canvas.convert("RGB")
```

**UniformLogo Template Differences:**

```python
def render_uniform_logo(bg: Image, logo: Image, options: dict) -> Image:
    # Same steps 1-6 as Universal

    # 7. Uniform logo placement with bounding box
    if logo:
        # Calculate bounding box
        max_width = 2000 * options["uniform_logo_max_w"]
        max_height = 3000 * options["uniform_logo_max_h"]

        # Auto-scale to fit within bounds
        logo_scaled = scale_to_fit(logo, max_width, max_height)

        # Position at percentage offsets
        logo_x = int(2000 * options["uniform_logo_offset_x"]) - logo_scaled.width // 2
        logo_y = int(3000 * options["uniform_logo_offset_y"]) - logo_scaled.height // 2

        # Override mode allows manual adjustments
        if options.get("uniform_override"):
            logo_scaled = scale_logo(logo, options["scale"])
            logo_y = int(3000 * options["offset_y"])

        canvas.paste(logo_scaled, (logo_x, logo_y), logo_scaled)

    # Same steps 8-11 as Universal
    return canvas.convert("RGB")
```

#### Step 5: Overlay Caching (Optimization)

**Cache Generation:**
```python
def generate_overlay(options: dict) -> Image:
    # Create transparent canvas
    overlay = Image.new("RGBA", (2000, 3000), (0, 0, 0, 0))

    # Apply matte + fade
    matte = create_matte_gradient(options["matteHeight"])
    overlay = Image.alpha_composite(overlay, matte)

    # Apply vignette
    vignette = create_vignette(options["vignette"])
    overlay = Image.alpha_composite(overlay, vignette)

    # Apply wash
    wash = create_wash_overlay(options["wash"])
    overlay = Image.alpha_composite(overlay, wash)

    # Save to /config/overlays/{template}/{preset}.png
    overlay.save(cache_path, "PNG")
    return overlay
```

**Fast Render with Cache:**
```python
def render_with_overlay_cache(bg: Image, logo: Image, options: dict, cache_path: str) -> Image:
    # 1. Load cached overlay (matte + fade + vignette + wash)
    overlay = Image.open(cache_path)

    # 2. Process background (zoom + shift)
    bg_processed = process_background(bg, options)
    canvas = Image.new("RGB", (2000, 3000))
    canvas.paste(bg_processed, (0, 0))

    # 3. Composite cached overlay
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

    # 4. Add fresh grain (not cached for proper blending)
    grain = generate_grain(2000, 3000, options["grain"])
    canvas_array = np.array(canvas)
    canvas_array = np.clip(canvas_array + grain, 0, 255).astype(np.uint8)
    canvas = Image.fromarray(canvas_array)

    # 5. Composite logo and text (same as regular render)
    canvas = composite_logo(canvas, logo, options)
    canvas = render_text(canvas, options)

    # 6. Apply border and corners
    return finalize_poster(canvas, options)
```

**Performance Comparison:**
- Regular render: ~2-3 seconds per poster
- Cached render: ~0.5-1 second per poster
- Speedup: 3-5x faster

#### Step 6: Output

**Save Locally:**
```python
def save_poster(image: Image, save_path: str, quality_settings: dict):
    # Create directory if needed
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # Save based on format
    if quality_settings["outputFormat"] == "jpg":
        image.save(save_path, "JPEG", quality=quality_settings["jpgQuality"])
    elif quality_settings["outputFormat"] == "png":
        image.save(save_path, "PNG", compress_level=quality_settings["pngCompression"])
    elif quality_settings["outputFormat"] == "webp":
        image.save(save_path, "WebP", quality=quality_settings["webpQuality"])
```

**Upload to Plex:**
```python
def upload_to_plex(image: Image, rating_key: str):
    # 1. Convert image to bytes
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95)
    buffer.seek(0)

    # 2. Upload to temporary URL (data URI)
    image_base64 = base64.b64encode(buffer.read()).decode()
    poster_url = f"data:image/jpeg;base64,{image_base64}"

    # 3. Send to Plex
    response = plex_session.post(
        f"{plex_url}/library/metadata/{rating_key}/posters",
        params={"url": poster_url},
        headers={"X-Plex-Token": plex_token}
    )

    # 4. Trigger metadata refresh
    plex_session.get(
        f"{plex_url}/library/metadata/{rating_key}/refresh",
        headers={"X-Plex-Token": plex_token}
    )

    return response.status_code == 200
```

### Effect Implementations

#### Matte Gradient
```python
def create_matte_gradient(height_percent: float, color: tuple = (0, 0, 0)) -> Image:
    """Black gradient from bottom to transparent"""
    height = int(3000 * height_percent)
    gradient = Image.new("RGBA", (2000, 3000), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)

    for y in range(height):
        alpha = int(255 * (1 - y / height))
        draw.rectangle([(0, 3000 - y), (2000, 3000)], fill=(*color, alpha))

    return gradient
```

#### Film Grain
```python
def generate_grain(width: int, height: int, intensity: float) -> np.ndarray:
    """NumPy-based film grain"""
    grain = np.random.randint(-intensity, intensity, (height, width, 3), dtype=np.int16)
    return grain
```

#### Vignette
```python
def create_vignette(intensity: float) -> Image:
    """Radial darkening from edges"""
    vignette = Image.new("RGBA", (2000, 3000), (0, 0, 0, 0))
    draw = ImageDraw.Draw(vignette)

    center_x, center_y = 1000, 1500
    max_radius = 2000  # Diagonal

    for radius in range(max_radius, 0, -10):
        alpha = int(intensity * 255 * (1 - radius / max_radius))
        draw.ellipse(
            [(center_x - radius, center_y - radius), (center_x + radius, center_y + radius)],
            fill=(0, 0, 0, alpha)
        )

    return vignette
```

#### Logo Color Matching
```python
def extract_color_from_poster(poster: Image, logo: Image) -> Image:
    """Extract dominant color from poster and apply to white logo"""
    # 1. Sample center region of poster
    sample_region = poster.crop((800, 1200, 1200, 1800))

    # 2. Get dominant color
    pixels = list(sample_region.getdata())
    avg_color = tuple(int(sum(c) / len(pixels)) for c in zip(*pixels))

    # 3. Recolor logo
    logo_colored = recolor_logo(logo, rgb_to_hex(avg_color))

    return logo_colored

def recolor_logo(logo: Image, hex_color: str) -> Image:
    """Replace white pixels with target color"""
    r, g, b = hex_to_rgb(hex_color)
    logo_rgba = logo.convert("RGBA")
    data = np.array(logo_rgba)

    # Replace white (or near-white) with target color
    white_mask = (data[:, :, :3] > 200).all(axis=2)
    data[white_mask] = [r, g, b, 255]

    return Image.fromarray(data)
```

---

## User Workflows

### Workflow 1: Single Movie Poster

**Goal**: Generate a custom poster for one movie

**Steps:**
1. **Navigate to Movies**
   - URL: `/movies`
   - Grid displays cached movies with thumbnails

2. **Select Movie**
   - Click movie card
   - Editor pane opens on right side

3. **Load Assets**
   - Backend fetches TMDB ID from Plex
   - Fetches posters and logos from TMDB/Fanart
   - Thumbnails populate in editor

4. **Choose Template & Preset**
   - Select template (Universal or UniformLogo)
   - Select preset (e.g., "Neon Blue")
   - Options load into editor

5. **Select Poster**
   - Click desired poster thumbnail
   - Filter by textless/text/all
   - Filter by language

6. **Select Logo**
   - Click desired logo thumbnail
   - Choose logo preference (white/color/first)
   - Choose logo mode (stock/match/hex)

7. **Customize (Optional)**
   - Adjust poster zoom/shift
   - Modify matte/fade heights
   - Change vignette/grain intensity
   - Customize logo scale/position
   - Add text overlay

8. **Preview Updates**
   - Real-time preview (debounced 800ms)
   - Shows final poster in editor

9. **Save/Upload**
   - Click "Save Locally" → Saves to `/config/output/{title} ({year})/poster.jpg`
   - Click "Send to Plex" → Uploads and sets as poster
   - Optionally remove labels (e.g., "Overlay")

10. **Confirmation**
    - Success message displays
    - Poster history recorded

**Time Estimate**: 30-60 seconds per movie

---

### Workflow 2: Batch Processing

**Goal**: Generate posters for 100+ movies at once

**Steps:**
1. **Navigate to Batch Edit**
   - URL: `/batch-edit`
   - Movie grid loads with checkboxes

2. **Filter Movies**
   - Search by title
   - Filter by library
   - Filter by labels (e.g., "Needs Poster")

3. **Select Movies**
   - Check individual movies
   - Or use "Select All" (filtered results)

4. **Choose Template & Preset**
   - Select template (usually UniformLogo for consistency)
   - Select preset (e.g., "Dark Minimal")

5. **Preview First Movie**
   - Right panel shows preview of first selected movie
   - Use arrow keys to navigate through selections
   - Verify poster/logo selection logic

6. **Configure Batch Options**
   - ✓ Send to Plex
   - ✓ Save Locally
   - Select labels to remove: "Overlay", "Needs Poster"

7. **Start Batch**
   - Click "Process Batch"
   - Backend starts ThreadPoolExecutor with 2 workers
   - Progress bar appears

8. **Monitor Progress**
   - Frontend polls `/api/batch-progress` every 2s
   - Shows "Processing: 45/100"
   - Displays current movie being processed

9. **Completion**
   - Success message: "100 posters generated"
   - Shows stats: "95 sent to Plex, 100 saved locally, 5 failed"
   - Failed movies listed for retry

**Time Estimate**:
- Without overlay cache: ~5-10 minutes for 100 movies
- With overlay cache: ~2-3 minutes for 100 movies

---


### Workflow 4: TV Show Season Posters

**Goal**: Generate posters for all seasons of a TV show

**Steps:**
1. **Navigate to TV Shows**
   - URL: `/tv-shows`
   - Select show from grid

2. **Choose Series vs Season**
   - Click "Series" tab for show-level poster
   - Click "Seasons" tab for season posters

3. **Select All Seasons**
   - Click "All" button to select all seasons
   - Editor shows Season 1 preview

4. **Choose Template & Preset**
   - Select template (usually Universal)
   - Select preset with season options (e.g., "TV - Clean")

5. **Configure Season Text**
   - Preset includes `season_text: "Season {season}"`
   - Variable auto-replaced per season

6. **Preview**
   - Real-time preview shows Season 1
   - Navigate to other seasons to verify

7. **Render All Seasons**
   - Backend fetches TVDB images for each season
   - Applies textless filter
   - Renders in parallel
   - Updates thumbnails as each completes

8. **Upload to Plex**
   - Click "Send to Plex" for all seasons
   - Uploads each season poster
   - Removes labels

**Time Estimate**: ~30-60 seconds for 10 seasons

---

## Performance & Scalability

### Current Performance Metrics

**Single Poster Render:**
- Without cache: 1.5-3 seconds
- With overlay cache: 0.5-1 second
- Preview latency: < 800ms

**Batch Processing:**
- 100 movies (no cache): ~8-10 minutes
- 100 movies (with cache): ~2-3 minutes
- Concurrent workers: 2 (default), up to 8 (configurable)

**Memory Usage:**
- Base: ~200 MB
- Per render: ~50-100 MB (temporary)
- Cache (overlays): ~10-20 MB per preset
- Image cache: Depends on library size (~1 GB for 1000 movies)

### Optimization Strategies

#### 1. Overlay Caching
**Impact**: 3-5x speedup for batch rendering

**How it works:**
- Pre-generate matte + fade + vignette + wash effects
- Save as PNG to `/config/overlays/{template}/{preset}.png`
- Composite cached overlay instead of re-rendering effects

**When to use:**
- Batch processing with same preset
- Minimal customization per movie

**Trade-off:**
- Disk space: ~2-5 MB per cached overlay
- Initial generation time: ~1 second per overlay

#### 2. Concurrent Rendering
**Impact**: Linear speedup with worker count (up to CPU cores)

**Configuration:**
```json
{
  "performance": {
    "concurrentRenders": 2  // 1-8 workers
  }
}
```

**Implementation:**
```python
with ThreadPoolExecutor(max_workers=settings.performance.concurrentRenders) as executor:
    futures = [executor.submit(render_poster, movie) for movie in movies]
    for future in as_completed(futures):
        result = future.result()
```

**Trade-off:**
- More workers = higher CPU/memory usage
- Diminishing returns beyond 4-6 workers
- I/O bound (image downloads) limits scaling

#### 3. SessionStorage Caching (Frontend)
**Impact**: Instant page loads, 90% reduction in API calls

**What's cached:**
- All movies from Plex (title, year, poster URL, labels)
- All TV shows
- Poster/logo selections per movie

**Cache invalidation:**
- On app close (sessionStorage cleared)
- Manual refresh via Settings → Clear Cache

#### 4. Image Disk Caching
**Impact**: 50-80% reduction in download time

**What's cached:**
- Plex poster thumbnails: `/config/cache/posters/{rating_key}.jpg`
- TMDB/Fanart images: `/config/cache/tmdb/{tmdb_id}_{hash}.jpg`

**Cache size:**
- ~500 KB per poster
- ~1 GB for 2000 movies

**Cache management:**
- LRU eviction (oldest first)
- Manual clear via `/api/cache/clear`

#### 5. Rate Limiting (External APIs)
**Purpose**: Avoid hitting API limits and rate throttling

**Configuration:**
```json
{
  "performance": {
    "tmdbRateLimit": 40,  // Requests per 10 seconds
    "tvdbRateLimit": 20   // Requests per 10 seconds
  }
}
```

**Implementation:**
- Sliding window algorithm
- Per-endpoint tracking
- Auto-retry with exponential backoff

#### 6. Connection Pooling
**Purpose**: Reduce HTTP connection overhead

**Plex Session:**
```python
session = requests.Session()
session.mount('http://', HTTPAdapter(pool_connections=32, pool_maxsize=64))
```

**Benefits:**
- Reuses TCP connections
- Reduces SSL handshake overhead
- Faster API calls (10-30% speedup)

### Scalability Considerations

**Current Limitations:**
- SQLite (not suitable for multi-instance deployment)
- Single-user assumption (no authentication/multi-tenancy)
- File-based caching (not distributed)

**Scaling to Larger Libraries:**
- 10,000+ movies: Increase cache size limits, use database indexes
- Multiple libraries: Library-based filtering already supported
- Multiple users: Requires authentication layer, database migration to PostgreSQL

**Future Optimizations:**
- Redis for distributed caching
- PostgreSQL for multi-instance support
- S3/GCS for poster storage
- CDN for serving images
- Message queue (Celery) for batch processing

---

## Security & Privacy

### Current Security Measures

**Input Validation:**
- Pydantic models validate all API inputs
- Type checking (Python + TypeScript)
- SQL injection prevention (parameterized queries)
- Path traversal prevention (absolute paths, validation)

**API Key Protection:**
- API keys redacted in logs
- Not exposed in frontend (stored in backend only)
- Environment variable override support

**CORS:**
- Allow all origins (self-hosted assumption)
- Suitable for local network deployment

**TLS:**
- Configurable TLS verification for Plex
- Supports self-signed certificates

**Authentication:**
- None (single-user assumption)
- Suitable for trusted network only

### Security Best Practices (User Responsibility)

**Recommended:**
- Deploy behind reverse proxy (Nginx, Traefik) with authentication
- Use firewall to restrict access to trusted IPs
- Regularly update Docker image
- Use strong Plex token (never share)
- Enable Plex TLS

**Not Recommended:**
- Exposing Simposter directly to internet without auth
- Sharing API keys or Plex token
- Using default/weak passwords for Plex

### Data Privacy

**What Data is Stored:**
- Movie/TV metadata (cached from Plex)
- TMDB/TVDB/Fanart images (cached)
- User presets and settings
- Poster history (local operations)

**What Data is NOT Stored:**
- User passwords (no authentication)
- Plex token in database (loaded from env/settings only)
- Personal information

**Data Retention:**
- Cached data: Persists until manual clear
- Poster history: Indefinite (can delete manually)
- Logs: 14 days (auto-rotation)

**Data Sharing:**
- None (all data stays local)
- External API calls: TMDB, TVDB, Fanart (for images only)

---

## Future Roadmap

### Short-Term (Next 3-6 Months)

**1. Collections Support**
- UI already exists (`CollectionsView.vue`)
- Generate collection posters
- Batch process entire collections

**2. Additional Templates**
- Text-based templates (no logo)
- Minimalist templates
- Vintage/retro styles
- User-contributed templates

**3. TV Enhancements**
- Season poster automation via scheduled scans
- Improved TV metadata handling

**4. Advanced Filters**
- Filter posters by aspect ratio
- Filter logos by color palette
- Filter by rating/popularity

**5. Font Management**
- Web UI for uploading custom fonts
- Font preview in editor
- Google Fonts integration

### Medium-Term (6-12 Months)

**1. Performance Improvements**
- Redis caching layer
- Async image downloads (aiohttp)
- WebP default output format
- Lazy loading optimizations

**2. Multi-Library Support**
- Separate settings per library
- Library-specific presets
- Cross-library batch processing

**3. Advanced Text Overlay**
- Multiple text layers
- Gradient text
- Custom positioning per layer
- Image overlays (badges, ratings)

**4. Template Marketplace**
- Share templates with community
- Import/export templates
- Template version control

**5. API Improvements**
- Rate limiting (internal)
- Input validation enhancements
- Better error messages
- API documentation (OpenAPI/Swagger)

### Long-Term (12+ Months)

**1. Multi-User Support**
- User authentication
- Role-based access control
- User-specific presets and history

**2. Cloud Storage Integration**
- S3/GCS for poster storage
- CDN for image serving
- Distributed caching

**3. Advanced Image Processing**
- AI-powered logo extraction
- Auto color grading
- Smart cropping
- Background removal

**4. Database Migration**
- PostgreSQL support
- Multi-instance deployment
- Better indexing and query performance

**5. Plugin System**
- Custom template plugins
- External integrations removed
- Custom effects and filters

**6. Mobile App**
- React Native or Flutter app
- On-the-go poster generation
- Push notifications for automation

---

## Appendix

### A. Template Options Reference

#### Universal Template Options
```json
{
  "posterZoom": 1.0,          // 0.5 - 2.0
  "posterShiftY": 0,          // -500 to 500 pixels
  "matteHeight": 0.3,         // 0 - 1.0 (percentage)
  "matteColor": "#000000",    // Hex color
  "fadeHeight": 0.2,          // 0 - 1.0
  "vignette": 0.5,            // 0 - 1.0 (intensity)
  "grain": 10,                // 0 - 50 (intensity)
  "wash": 0.2,                // 0 - 1.0 (opacity)
  "logoMode": "hex",          // "stock" | "match" | "hex" | "none"
  "logoHex": "#00ffff",       // Hex color (if logoMode = "hex")
  "logoScale": 0.4,           // 0.1 - 1.0 (percentage of canvas width)
  "logoOffsetY": 0.15,        // 0 - 1.0 (vertical position)
  "textOverlayEnabled": false,
  "customText": "{title}",    // Variables: {title}, {year}
  "fontFamily": "Arial",
  "fontSize": 120,            // 20 - 300
  "fontWeight": "700",        // "300" | "400" | "700" | "900"
  "textColor": "#ffffff",
  "textAlign": "center",      // "left" | "center" | "right"
  "textTransform": "uppercase", // "none" | "uppercase" | "lowercase" | "capitalize"
  "letterSpacing": 0,         // -10 to 50
  "lineHeight": 1.2,          // 0.8 - 2.0
  "positionY": 0.8,           // 0 - 1.0
  "shadowEnabled": true,
  "shadowBlur": 10,           // 0 - 50
  "shadowOffsetX": 2,         // -50 to 50
  "shadowOffsetY": 2,         // -50 to 50
  "shadowColor": "#000000",
  "shadowOpacity": 0.8,       // 0 - 1.0
  "strokeEnabled": false,
  "strokeWidth": 3,           // 1 - 20
  "strokeColor": "#000000",
  "roundedCorners": true,
  "cornerRadius": 20,         // 0 - 100
  "borderEnabled": false,
  "borderWidth": 10,          // 1 - 50
  "borderColor": "#ffffff"
}
```

#### UniformLogo Template Options
```json
{
  // All Universal options, plus:
  "uniform_logo_max_w": 0.8,      // 0.1 - 1.0 (max logo width as % of canvas)
  "uniform_logo_max_h": 0.3,      // 0.1 - 1.0 (max logo height as % of canvas)
  "uniform_logo_offset_x": 0.5,   // 0 - 1.0 (horizontal center position)
  "uniform_logo_offset_y": 0.15,  // 0 - 1.0 (vertical center position)
  "uniform_override": false,      // Enable manual scale/offset override
  "scale": 0.4,                   // 0.1 - 1.0 (if override = true)
  "offset_y": 0.15                // 0 - 1.0 (if override = true)
}
```

### B. Database Version History

| Version | Changes | Backup Required |
|---------|---------|-----------------|
| 1.0.0   | Initial schema | No |
| 1.1.0   | Added `season_options_json` to presets | Yes |
| 1.2.0   | Added `poster_history` table | Yes |
| 1.3.0   | Added `library_id` to movie_cache | Yes |

### C. Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PLEX_URL` | Plex server URL | http://localhost:32400 |
| `PLEX_TOKEN` | Plex authentication token | - |
| `TMDB_API_KEY` | TMDB API key | - |
| `TVDB_API_KEY` | TVDB API key | - |
| `FANART_API_KEY` | Fanart.tv API key | - |

| `LOG_LEVEL` | Logging level | INFO |

### D. File Paths

| Path | Purpose | Volume Mount |
|------|---------|--------------|
| `/config/settings/simposter.db` | SQLite database | Yes |
| `/config/logs/simposter.log` | Application logs | Yes |
| `/config/output/` | Saved posters | Yes |
| `/config/cache/posters/` | Cached images | Yes |
| `/config/overlays/` | Pre-generated overlays | Yes |
| `/config/fonts/` | Custom fonts | Yes |
| `/uploads/` | User uploads | Yes |

### E. API Error Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 200 | Success | - |
| 400 | Bad Request | Invalid input, missing required fields |
| 404 | Not Found | Invalid rating key, TMDB ID not found |
| 500 | Internal Server Error | Rendering failure, API timeout |
| 503 | Service Unavailable | Rate limit exceeded, external API down |

---

## Glossary

- **Rating Key**: Plex's unique identifier for media items
- **TMDB**: The Movie Database (external API)
- **TVDB**: TheTVDB (external API for TV shows)
- **Fanart.tv**: Community artwork repository
- **Preset**: Saved template configuration
- **Template**: Rendering algorithm (Universal, UniformLogo)
- **Overlay**: Pre-generated effects layer (matte, fade, vignette, wash)
- **Matte**: Black gradient from bottom edge
- **Fade**: Gradient blend effect
- **Vignette**: Radial darkening from edges
- **Grain**: Film grain noise effect
- **Wash**: Color tone overlay
- **Logo Mode**: How logo is colored (stock, match, hex)
- **Textless**: Poster without text overlay
- **Clearlogo**: Transparent PNG logo
- **WAL**: Write-Ahead Logging (SQLite mode)

---

**End of PRD**
