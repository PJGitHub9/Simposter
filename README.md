# Simposter

> **Template-based poster generation for Plex** — Create clean, consistent custom posters with TMDb/TVDB/Fanart.tv artwork, overlay badges, and full batch automation.

![Simposter UI](https://github.com/user-attachments/assets/bc31ee99-0d68-4ba0-a54f-d6b4a1b119b7)

<!-- SCREENSHOT SUGGESTION: Replace the hero above with a wider, cleaner shot of the movie grid
     showing a mix of generated posters. Ideally captured at 1400–1600px wide. -->

---

## Features

### Poster Editor
- **Live preview** — See changes in real time as you adjust settings
- **Multi-source artwork** — TMDb, TVDB, and Fanart.tv with configurable priority
- **Logo system** — Clearlogos with white/color/first preference, hex tinting, and fallback rules
- **ClearLogo editor** — Browse, select, or upload logos and push them to Plex independently

### Batch & Automation
- **Batch edit** — Select your whole library and apply a preset in one run
- **Webhooks** — Auto-generate posters when Tautulli fires an event (new/updated media)
- **Scheduled scans** — Cron-based library syncing for hands-off automation
- **Smart retry queue** — Items that couldn't get an ideal poster (missing logo, no textless poster) are queued and retried automatically until resolved
- **Existing content mode** — Choose whether a webhook/scan regenerates the poster or resends the last cached one (protects manually tuned posters)

### Overlay Badges
- **Video** — Resolution (4K, 1080p, 720p) and video codec (HEVC, AV1, H.264)
- **Audio** — Codec (Atmos, DTS-X, TrueHD), channels, language
- **Edition** — Theatrical, Extended, Director's Cut, IMAX, Unrated
- **Studio / Streaming platform** — Auto-detected from TMDb
- **Custom images** — Upload your own badge assets (4K logo, Dolby Vision seal, etc.)
- **Text labels** — Custom text with full font/size/color control

### Performance
- **Overlay cache** — Pre-rendered effect layers for 3–5x faster batch rendering
- **Smart caching** — SessionStorage LRU, SQLite-backed poster/label cache, indexed queries
- **Concurrent rendering** — Configurable worker count (1–4)
- **Lazy loading** — Posters load on-demand as you scroll

### Other
- **6 themes** — Neon, Slate, Dracula, Nord, OLED, Light
- **Notifications** — Discord and Apprise (70+ services) with per-event toggles
- **History** — Full audit log with source tracking, fallback indicators, and hover previews
- **Retry queue** — Dedicated tab in History showing pending retries with per-item actions

---

## Quick Start

### Docker (Recommended)

```bash
docker run -d \
  --name simposter \
  -p 8003:8003 \
  -v /path/to/config:/config \
  simposter:latest
```

Open `http://localhost:8003` and configure Plex/TMDb in Settings.

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

### Building Locally

```bash
# Windows
build-docker.bat

# Linux/Mac
./build-docker.sh

# Manual (specify branch label)
docker build --build-arg GIT_BRANCH=dev -t simposter:latest .
```

### Local Development

```bash
# Backend
uvicorn backend.main:app --reload --port 8003

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

---

## Core Concepts

### Templates & Presets

**Templates** define the rendering logic. Currently there is one: **Uniform Logo**, which places the clearlogo inside a configurable bounding box zone with matte, fade, vignette, grain, and wash effects.

**Presets** store a named snapshot of template settings:
- Logo zone (top-left, top-center, bottom-left, etc.)
- Visual effects and intensities
- Text overlays using `{title}` / `{year}` variables
- Linked overlay badge configuration
- Fallback rules (switch templates/presets when a logo or textless poster is missing)

Presets can be exported and imported as JSON.

<!-- SCREENSHOT SUGGESTION: Template Manager page showing a preset list on the left and
     the options panel on the right, with logo zone and effects visible -->

### Logo System

Logos are sourced from TMDb, Fanart.tv, and TVDB, then merged with priority/fallback logic.

| Mode | Behaviour |
|------|-----------|
| Stock | Original logo colors |
| Match | Tints logo to match the poster's dominant color |
| Hex | Custom hex color (best with white logos) |
| None | No logo rendered |

| Preference | Picks |
|------------|-------|
| White | Lowest saturation logo |
| Color | Highest saturation logo |
| First | First available |

**Fallback options when no logo is found:**
- Continue without logo
- Skip rendering entirely
- Switch to a different template/preset (e.g., a text-only fallback)

![Logo Examples](https://github.com/user-attachments/assets/10ba7d2f-0e1b-4ab7-b9cf-67651ec335e0)

<!-- SCREENSHOT SUGGESTION: Side-by-side showing the same poster with white logo, color logo,
     and the hex-tinted variant -->

### Overlay Badges

Badges pull live metadata from Plex (resolution, codec, audio channels, edition title) and render on top of the poster. Each badge value can be individually set to **None**, **Text**, or **Image** mode — so you can show 4K as a badge image but render Dolby Atmos as text, for example.

Badge visibility can also be controlled with Plex labels: `show_if_label` / `hide_if_label`.

<!-- SCREENSHOT SUGGESTION: Overlay Config Manager showing a configured badge set on the left
     and a rendered poster preview with badges visible on the right -->

### Smart Retry Queue

When a poster is generated via batch, webhook, or auto-scan and the ideal template conditions aren't met (e.g., no clearlogo found, or no textless poster available), Simposter adds the item to a **retry queue**. A background job periodically re-attempts the poster until the ideal result is achieved, then resolves the item and removes it from the queue.

- **Toggle** on/off in Settings → Performance
- **Retry interval** — configurable in hours
- **Max attempts** — 0 = unlimited, or set a cap
- **Manual override** — sending a poster manually removes it from the queue immediately

The Retry Queue is visible in **History → Retry Queue tab**, with per-item Retry Now and Dismiss actions.

<!-- SCREENSHOT SUGGESTION: History page with the Retry Queue tab active, showing a handful
     of items with their reason badges (No Logo / Poster Fallback) and action buttons -->

---

## Workflows

### Single Poster

1. Open **Movies** or **TV Shows** and click a title
2. Choose a template and preset in the editor panel
3. Preview updates live — switch poster/logo sources, adjust effects
4. **Save to disk** and/or **Send to Plex**

<!-- SCREENSHOT SUGGESTION: Movie editor pane open alongside the movie grid — show the
     live preview panel with a poster visible and some sliders/options on the right -->

### Batch Processing

1. Go to **Batch Edit** (Movies or TV)
2. Select items — use search, label filters, or select all
3. Choose template + preset
4. **Preview** — step through selected items to spot-check renders
5. Set labels to remove (optional)
6. Run the batch — progress tracked live, results summary shown when complete

<!-- SCREENSHOT SUGGESTION: Batch Edit page with several items selected (checkboxes visible)
     and the batch results panel open at the bottom showing succeeded/fallback counts -->

![Batch Editor](https://github.com/user-attachments/assets/e6e60d93-5913-4054-aa47-b38a04bd5435)

### Automation

**Webhook (Tautulli):**
```
http://your-server:8003/api/webhook/tautulli?template_id=uniformlogo&preset_id=default&event_types=added
```

**Scheduled scans:** Configure a cron expression in Settings → Libraries (e.g., `0 2 * * *` for 2 AM daily).

**Existing content mode** (Settings → Performance):
- `Regenerate` *(default)* — always creates a fresh poster
- `Resend` — if a Simposter poster already exists for the title, pushes the cached render back to Plex without regenerating. Useful when you've manually tuned a poster and don't want webhooks overwriting it.

**Smart retry:** Items that couldn't get an ideal poster during any automated run are queued and retried on the configured interval. See [Smart Retry Queue](#smart-retry-queue).

---

## Settings

| Tab | What's in it |
|-----|--------------|
| **General** | Theme, poster display density, deduplication, default sort |
| **Libraries** | Plex connection, library mappings, auto-generate preset, webhook ignore labels, label removal |
| **Save Locations** | Output path templates for movies and TV shows, batch subfolder option |
| **Performance** | Image format/quality, concurrent renders, overlay cache, API rate limits, automation (retry queue, existing content mode) |
| **Notifications** | Discord webhook and Apprise URLs, per-event toggles (batch / manual / webhook / auto-generate) |
| **Advanced** | API source priority order, database backup/restore |

---

## History & Retry Queue

**History tab** — every poster generation is logged:
- Timestamp, template, preset, source (manual / batch / webhook / auto-generate)
- Whether a fallback template was used
- Hover "View" to preview the poster thumbnail
- Filter by library, template, action

**Retry Queue tab** — shows items still waiting for an ideal poster:
- Reason badge: *No Logo*, *Poster Fallback*, or *Both*
- Attempt count and last-tried timestamp
- **Retry Now** — trigger an immediate retry
- **Dismiss** — remove from queue without retrying

![History](https://github.com/user-attachments/assets/2e7b7b23-770e-463e-91e6-62f0d061fff1)

<!-- SCREENSHOT SUGGESTION: Replace the above with a shot showing both the History tab and
     Retry Queue tab — ideally with the Retry Queue tab active and 2-3 items visible -->

---

## Tautulli Webhook Setup

### 1. Webhook URL

```
http://your-server:8003/api/webhook/tautulli?template_id=uniformlogo&preset_id=default&event_types=added
```

**Method:** POST  
**Trigger:** Recently Added

### 2. JSON Payload

**Movies:**
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

**TV Shows:**
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

### 3. Event Types

| Tautulli Event | Simposter value | Fires when |
|----------------|-----------------|------------|
| `library.new` / `created` | `added` | New media added |
| `library.update` | `updated` | Metadata updated |
| `playback.stop` | `watched` | Playback finished |

### 4. Ignore Labels

In Settings → Libraries → Webhook Ignore Labels, list Plex labels that should skip poster generation (e.g., `Custom`, `NoOverlay`). Case-insensitive.

### 5. Test Mode

```
http://your-server:8003/api/webhook/tautulli?template_id=uniformlogo&preset_id=default&event_types=added&test=true
```

Dry-run — logs the event without generating a poster.

---

## Configuration

### Environment Variables

| Variable | Required | Example |
|----------|----------|---------|
| `PLEX_URL` | Yes | `http://plex:32400` |
| `PLEX_TOKEN` | Yes | `xxxyyyzzz` |
| `PLEX_MOVIE_LIBRARY_NAME` | Yes | `Movies` |
| `PLEX_TV_LIBRARY_NAME` | No | `TV Shows` |
| `TMDB_API_KEY` | Yes | `abcd1234` |
| `TVDB_API_KEY` | No | `efgh5678` |
| `FANART_API_KEY` | No | `ijkl9012` |
| `CONFIG_DIR` | No (Docker) | `/config` |

All of these can also be set (and overridden) via the Settings UI.

### File Layout

```
config/
├── settings/
│   └── simposter.db       # SQLite — settings, presets, history, cache
├── logs/
│   └── simposter.log      # Application logs
├── cache/
│   └── poster_renders/    # Cached rendered posters for resend mode
└── output/                # Saved poster files
    └── {Library}/
        └── {Title} ({Year}).jpg
```

Legacy `presets.json` and `ui_settings.json` migrate automatically to SQLite on first run. A database backup is created automatically on version upgrades.

---

## Tips

- **Textless posters** look best with matte and fade effects — filter for them in the poster picker
- **Save presets** before running a batch so you can reproduce the same look later
- **Overlay cache** gives the biggest batch speed boost — keep it on (Settings → Performance)
- **Retry queue** means a missing logo today won't be missing forever — Fanart.tv gets new logos regularly
- **Check logs** in Settings → Logs to diagnose webhook or API key issues

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Technical architecture, API routers, rendering pipeline
- [CHANGELOG.md](CHANGELOG.md) — Full version history

---

## Special Thanks

*No affiliation — just projects worth knowing about.*

**Poster styles that inspired Simposter:**
- [darkmatte](https://www.reddit.com/r/PlexPosters/) — Iconic dark matte poster aesthetic
- [ikonok](https://www.reddit.com/r/PlexPosters/) — Clean, minimal poster style

**Related projects:**
- [Posterizarr](https://github.com/fscorrupt/Posterizarr) — Another poster automation tool for Plex
- [Kometa](https://kometa.wiki/) — Plex metadata and collection manager
- [TitleCardMaker](https://github.com/CollinHeist/TitleCardMaker) — Automated title card generation for TV shows
- [UMTK](https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa) — Upcoming media overlays for Plex

---

## License

MIT License — See [LICENSE](LICENSE) for details.

---

## Credits

Built with [FastAPI](https://fastapi.tiangolo.com/), [Vue 3](https://vuejs.org/), [Pillow](https://python-pillow.org/), [TMDb API](https://www.themoviedb.org/documentation/api), [TVDB API](https://thetvdb.com/api-information), and [Fanart.tv API](https://fanart.tv/get-an-api-key/).

Developed with the assistance of [Claude](https://claude.ai/). All features are designed, directed, and tested by a human. (Still learning! :D)
