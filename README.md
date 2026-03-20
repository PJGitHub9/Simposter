# Simposter 🎬🖼️

> **Template-based poster generation for Plex** — Create clean, consistent custom posters with TMDb/TVDB artwork, intelligent caching, and batch processing.

![Simposter UI](https://github.com/user-attachments/assets/bc31ee99-0d68-4ba0-a54f-d6b4a1b119b7)

---

## ✨ Features

### 🎨 Modern Interface
- **Full-page batch editor** with grid view and real-time preview sidebar
- **Live preview** with TMDB poster integration (textless/text variants)
- **Drag-and-drop overlay editor** for resolution, codec, and audio badges
- **Dark/light themes** with responsive mobile design

### ⚡ Performance
- **Smart caching** — SessionStorage with LRU eviction, 5-10x faster database queries
- **Overlay cache** — Pre-rendered effects for 3-5x faster batch rendering
- **Concurrent rendering** — Process multiple posters simultaneously (configurable workers)
- **Lazy loading** — Images load on-demand as you scroll
- **Scheduled scans** — Automatic cron-based library syncing

### 🎬 Multi-Source Artwork
- **TMDb** — Movies & TV show posters with textless/text variants, high-res logos
- **TVDB** — TV show posters, season artwork, logos, coming-soon indicators
- **Fanart.tv** — HD clearlogos with priority/fallback logic
- **Configurable priority** — Drag to reorder API sources

### 🔧 Advanced Features
- **Template system** — Bounding box logo placement, matte/fade/vignette effects
- **Preset management** — Save, import, export configurations with fallback rules
- **Overlay badges** — Resolution, codec, audio, edition metadata from Plex
- **Label management** — Smart label removal, ignore labels for webhooks
- **History tracking** — Complete audit log with filtering and hover previews
- **Webhook integration** — Auto-generate from Tautulli events

---

## 🚀 Quick Start

### Docker (Recommended)

```bash
docker run -d \
  --name simposter \
  -p 8003:8003 \
  -v /path/to/config:/config \
  simposter:latest
```

Then visit `http://localhost:8003` and configure Plex/TMDb settings in the GUI.

### Docker Compose

```yaml
services:
  simposter:
    image: simposter:latest
    ports:
      - "8003:8003"
    volumes:
      - ./config:/config
    environment:
      - PLEX_URL=http://plex:32400
      - PLEX_TOKEN=your_token_here
      - TMDB_API_KEY=your_tmdb_key
```

### Building Docker Image

To build the Docker image with git branch detection:

```bash
# Linux/Mac
./build-docker.sh

# Windows
build-docker.bat

# Manual build (specify branch)
docker build --build-arg GIT_BRANCH=dev -t simposter:latest .
```

The build script automatically detects your current git branch and embeds it in the image, so the version badge displays correctly (e.g., `v1.5.5-dev`).

### Local Development

```bash
# Backend
uvicorn backend.main:app --reload --port 8003

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

---

## 📖 Core Concepts

### Templates & Presets

**Templates** define the rendering logic (logo placement, effects, overlays):
- **Uniform Logo** — Bounding box zones for consistent logo placement across your library

**Presets** store template-specific settings:
- Logo positioning (top-left, top-center, center, etc.)
- Visual effects (matte, fade, vignette, grain, wash)
- Text overlays with `{title}` and `{year}` variables
- Overlay badges (resolution, codec, audio metadata)
- Fallback rules (switch templates when logos/posters missing)

**Save/Import/Export** — Share presets as JSON files

### Logo System

**Sources:**
- TMDb movie logos
- Fanart.tv HD clearlogos
- Merged mode with priority

**Modes:**
- **Stock** — Original logo colors
- **Match** — Color-match logo to poster dominant color
- **Hex** — Custom color (works best with white logos)
- **None** — No logo rendering

**Preferences:**
- **White** — Prefer white/light logos (low saturation)
- **Color** — Prefer colored logos (high saturation)
- **First** — Use first available

**Fallback:**
- Continue without logo
- Skip rendering entirely
- Switch to different template/preset (e.g., text-based fallback)

![Logo Examples](https://github.com/user-attachments/assets/10ba7d2f-0e1b-4ab7-b9cf-67651ec335e0)

### Overlay Badges

Add resolution, codec, and audio metadata badges to your posters:

**Badge Types:**
- **Video Badge** — Resolution (4K, 1080p, 720p) and video codec (HEVC, H.264, AV1)
- **Audio Badge** — Audio codec (Atmos, DTS-X, TrueHD), channels (2.0, 5.1, 7.1), language
- **Edition Badge** — Theatrical, Extended, Director's Cut, Unrated, IMAX
- **Custom Images** — Upload your own badge assets (4K logo, Dolby Vision, etc.)
- **Text Labels** — Custom text with font controls

**Badge Modes** (per metadata value):
- **None** — Don't render badge for this value
- **Text** — Render as text with custom font/color/size
- **Image** — Render as uploaded badge asset

**Metadata Source:**
- Fetches real media info from Plex (resolution, codec, audio channels)
- Cached in database for fast subsequent renders
- Case-insensitive label matching for conditional rendering

---

## 🎯 Workflows

### Single Poster

1. **Select movie/show** from your Plex library
2. **Choose template + preset** (or adjust settings manually)
3. **Preview** in real-time as you make changes
4. **Save locally** or **Send to Plex** (with optional label removal)

### Batch Processing

1. **Navigate to Batch Edit** (Movies or TV Shows submenu)
2. **Select items** using grid view, search, or label filters
3. **Apply template + preset** (both required for consistency)
4. **Preview renders** — Navigate through selected items to verify
5. **Choose labels to remove** (optional, per-library configured)
6. **Process batch** — Send to Plex and/or save locally with progress tracking

![Batch Editor](https://github.com/user-attachments/assets/e6e60d93-5913-4054-aa47-b38a04bd5435)

### Automation

**Scheduled Library Scans:**
- Configure cron schedule in Settings → Libraries tab
- Example: `0 2 * * *` (daily at 2 AM)
- Auto-scans keep Simposter synced with Plex additions/changes

**Webhooks (Tautulli):**
```
http://your-server:8003/api/webhook/tautulli?template_id=uniformlogo&preset_id=default&event_types=added
```

Configure in Tautulli → Settings → Notification Agents → Webhook

**Supported Events:**
- `added` — New media added to library
- `watched` — Media finished playing
- `updated` — Media metadata updated

See [Webhook Setup](#-tautulli-webhook-setup) for full configuration details.

---

## ⚙️ Settings

Settings are organized into 5 tabs:

### 🏠 General
- Theme (Dark/Light mode)
- Poster display density
- Library refresh interval

### 📚 Libraries
- **Plex connection** — Server URL, API token, SSL verification
- **Library mappings** — Enable/disable per-library, set display names
- **Auto-generate** — Template/preset for new content
- **Webhook ignore labels** — Skip poster generation for labeled items
- **Label removal** — Choose which Plex labels to remove
- **Scheduled scans** — Cron schedule for automatic syncing

### 💾 Save Locations
- **Movie output** — Path template with `{library}`, `{title}`, `{year}`, `{key}`
- **TV show output** — Path template with `{season}` for season-specific saving
- **Batch subfolder** — Organize batch-generated posters

### ⚡ Performance
- **Image format** — JPEG/PNG/WebP with quality sliders
- **Concurrent renders** — 1-4 workers (balance speed vs memory)
- **Overlay cache** — Pre-generate effects for faster rendering
- **API rate limits** — TMDb/TVDB request throttling
- **Cache management** — Clear application/image/database cache

### 🔧 Advanced
- **API source priority** — Drag to reorder TMDb/TVDB/Fanart
- **Database backup/restore** — Export/import settings database

---

## 📜 History & Tracking

**Complete Audit Log:**
- Every poster generation tracked (timestamp, template, preset, source)
- Filter by library, template, action (sent to Plex / saved locally)
- Source tracking (manual / batch / webhook / auto-generate)
- Fallback tracking (see which posters used template fallback)

**Preview on Hover:**
- Hover "View" button to see poster thumbnail
- Works for locally saved posters and Plex-uploaded posters

![Logs](https://github.com/user-attachments/assets/2e7b7b23-770e-463e-91e6-62f0d061fff1)

---

## 🎙️ Tautulli Webhook Setup

### 1. Configure Simposter

In Settings → Performance tab:
- Enable **"Automatically Send to Plex"** (optional)
- Set **"Default Labels for Webhook Posters"** (e.g., `Overlay, Auto`)

### 2. Configure Tautulli

In Tautulli → Settings → Notification Agents → Add Webhook:

**Webhook URL:**
```
http://your-server:8003/api/webhook/tautulli?template_id=uniformlogo&preset_id=default&event_types=added
```

**Method:** POST

**JSON Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**JSON Data (Movies):**
```json
{
  "event": "{action}",
  "media_type": "{media_type}",
  "title": "{title}",
  "year": "{year}",
  "rating_key": "{rating_key}",
  "tmdb_id": "{themoviedb_id}",
  "thetvdb_id": "{thetvdb_id}"
}
```

**JSON Data (TV Shows):**
```json
{
  "event": "{action}",
  "media_type": "{media_type}",
  "title": "{show_name}",
  "year": "{year}",
  "rating_key": "{rating_key}",
  "tmdb_id": "{themoviedb_id}",
  "thetvdb_id": "{thetvdb_id}"
}
```

**Triggers:** Recently Added

### 3. Testing

Test mode (dry-run without generating):
```
http://your-server:8003/api/webhook/tautulli?template_id=uniformlogo&preset_id=default&event_types=added&test=true
```

Check logs at `/config/logs/simposter.log` for webhook events.

### Event Types

| Tautulli Event | Simposter Event | Description |
|---------------|----------------|-------------|
| `library.new` | `added` | New media added |
| `created` | `added` | Alternative new media event |
| `library.update` | `updated` | Metadata updated |
| `playback.stop` | `watched` | Playback finished |

### Ignore Labels

Configure in Settings → Libraries → Webhook Ignore Labels:
- Mark items with labels like `Custom`, `NoOverlay`, `Manual`
- Simposter skips poster generation for labeled items
- Case-insensitive matching
- Works with webhooks and auto-generate (not manual batch)

---

## 🔧 Configuration

### Environment Variables

| Variable | Required | Purpose | Example |
|----------|----------|---------|---------|
| `PLEX_URL` | * | Plex server URL | `http://plex:32400` |
| `PLEX_TOKEN` | * | Plex auth token | `xxxyyyzzz` |
| `PLEX_MOVIE_LIBRARY_NAME` | * | Movie library name | `Movies` |
| `PLEX_TV_LIBRARY_NAME` | | TV library name | `TV Shows` |
| `TMDB_API_KEY` | * | TMDb API key | `abcd1234` |
| `TVDB_API_KEY` | | TVDB API key | `efgh5678` |
| `FANART_API_KEY` | | Fanart.tv API key | `ijkl9012` |
| `CONFIG_DIR` | | Config directory (Docker) | `/config` |

\* Can be set via GUI Settings OR environment variables (env vars override GUI)

### File Paths

```
config/
├── settings/
│   └── simposter.db         # SQLite database (settings, presets, cache)
├── logs/
│   └── simposter.log        # Application logs
└── output/                  # Saved poster files
    └── {Library}/
        └── {Title} ({Year})/
            └── poster.jpg
```

**Database Migration:**
- Legacy `presets.json` and `ui_settings.json` automatically migrate to SQLite on first startup
- Automatic backup created on version changes: `simposter_v1.5.4.db.bak`

---

## 💡 Tips

### General
- **Use textless posters** — Better for matte/fade effects
- **Save presets** — Speed up library-wide poster creation
- **Check logs** — Debug API issues in Settings → Logs

### Batch Processing
- **Preview first** — Navigate through selected items to verify renders
- **Filter by labels** — Quickly find items with specific Plex labels
- **SessionStorage cache** — Posters load instantly on subsequent visits

### Performance
- **Enable overlay cache** — 3-5x faster batch rendering (Settings → Performance)
- **Adjust concurrent renders** — Increase workers for faster batch (max: 4)
- **Use indexed database** — Keep cache enabled for 5-10x faster queries
- **Lazy loading** — Images load as you scroll (automatic)

---

## 📁 Project Structure

```
simposter/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration loader
│   ├── database.py          # SQLite connection & migrations
│   ├── rendering.py         # Core PIL rendering logic
│   ├── scheduler.py         # APScheduler for cron scans
│   ├── api/                 # API routers
│   │   ├── movies.py        # Movie endpoints
│   │   ├── tv_shows.py      # TV show endpoints
│   │   ├── preview.py       # Real-time preview
│   │   ├── batch.py         # Batch rendering
│   │   ├── overlay_config.py # Overlay management
│   │   └── webhooks.py      # Webhook handlers
│   ├── templates/
│   │   ├── universal.py     # Overlay badge rendering
│   │   └── uniformlogo.py   # Main template
│   ├── assets/
│   │   └── selection.py     # Poster/logo selection
│   ├── tmdb_client.py       # TMDb API wrapper
│   ├── tvdb_client.py       # TVDB API wrapper
│   └── fanart_client.py     # Fanart.tv API wrapper
├── frontend/
│   ├── src/
│   │   ├── views/           # Page components
│   │   ├── components/      # Reusable UI components
│   │   └── stores/          # Pinia state management
│   └── vite.config.ts
├── config/                  # Persistent data (volume mount)
├── Dockerfile
└── docker-compose.yml
```

---

## 📄 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Technical architecture, startup flow, API routers
- **[CHANGELOG.md](CHANGELOG.md)** — Release notes and version history
- **[CLAUDE.md](CLAUDE.md)** — AI assistant context (gitignored)

---

## 📜 License

MIT License — See [LICENSE](LICENSE) for details

---

## 🙌 Special Thanks

*No affiliation — just projects worth knowing about.*

**Poster styles that inspired Simposter:**
- [darkmatte](https://www.reddit.com/r/PlexPosters/) — Iconic dark matte poster aesthetic
- [ikonok](https://www.reddit.com/r/PlexPosters/) — Clean, minimal poster style

**Alternate projects:**
- [Posterizarr](https://github.com/fscorrupt/Posterizarr) — Another great poster automation tool for Plex

**Related projects to check out:**
- [Kometa](https://kometa.wiki/) — Powerful Plex metadata and collection manager
- [TitleCardMaker](https://github.com/CollinHeist/TitleCardMaker) — Automated title card generation for TV shows
- [UMTK](https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa) — Upcoming media overlays for Plex (Kometa files)

---

## 🤖 AI Disclosure

Simposter is developed with the assistance of [Claude](https://claude.ai/). AI is used to help write, review, and iterate on code — all features are designed, directed, and tested by a human developer. (I'm still learning as I work on this! :D )

---

## 🙏 Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) — High-performance Python web framework
- [Vue 3](https://vuejs.org/) — Progressive JavaScript framework
- [Pillow](https://python-pillow.org/) — Python imaging library
- [TMDb API](https://www.themoviedb.org/documentation/api) — Movie & TV metadata
- [TVDB API](https://thetvdb.com/api-information) — TV show metadata
- [Fanart.tv API](https://fanart.tv/get-an-api-key/) — HD clearlogos
