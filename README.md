# **Simposter 🎬🖼️ — Template-Based Poster Builder with TMDb + Plex**

> **Simposter** is a fast, modern poster-generation tool for Plex users who want **clean, consistent, template-driven artwork** — now with a **completely redesigned UI**, **enhanced batch editing**, **real-time preview**, **TMDB-integrated rendering**, and **intelligent caching**.

![Image](https://github.com/user-attachments/assets/bc31ee99-0d68-4ba0-a54f-d6b4a1b119b7)
---

## ✨ Key Features

### 🎨 **Complete UI Overhaul**
- 🖥️ **New full-page batch edit interface** — Grid view with movie selection
- 👁️ **Real-time preview sidebar** — See rendered output with template + preset applied
- 🔄 **Preview navigation** — Cycle through selected movies with prev/next controls
- 📋 **Quick movie list** — Jump to any selected movie instantly
- 🏷️ **Smart label selector** — Choose specific labels to remove per library

### ⚡ **Performance & Caching**
- 💾 **Smart sessionStorage caching** — LRU eviction prevents quota errors, cache works indefinitely
- 🗄️ **Optimized database** — Indexed queries for 5-10x faster movie/TV lookups
- 🚀 **Lazy loading** — Images load on-demand for better performance
- ⚡ **Debounced saves** — Editor state saves reduced by 60-80%, eliminates UI stuttering
- 🔍 **Label filtering** — Filter movies by existing labels in batch edit
- ⏰ **Scheduled library scans** — Automatic cron-based scanning to keep Simposter synced with Plex
- 🧹 **Memory leak protection** — Automatic cleanup prevents memory leaks on navigation
- 🎬 **Overlay caching** — Pre-generated template overlays for 3-5x faster batch rendering

### 🎬 **Enhanced Preview System**
- 🖼️ **TMDB integration** — Preview uses TMDB posters based on preset filter (textless, text, any)
- 🎭 **Logo mode support** — Respects 'none' setting (no logo fetch when disabled)
- 📐 **Accurate rendering** — Preview shows exact output with all preset options applied

### 🔗 **Webhook Integration**
- 🤖 **Radarr support** — Auto-generate posters for new movies
- 📺 **Sonarr support** — Auto-generate posters for new TV shows (with season support)
- 🎙️ **Tautulli support** — Generate posters on Plex events (added, watched, updated)
- ⚙️ **Flexible configuration** — Choose templates, presets, and event types per integration
- 📤 **Auto-upload** — Automatically send generated posters to Plex
- 🧪 **Test mode** — Dry-run testing with detailed logging (`?test=true`)
- 🏷️ **Ignore Labels** — Skip poster generation for items with specific Plex labels (per-library)

### 🎞 **Multi-Source Artwork**
- 🎬 **TMDb integration** — Movies & TV show posters with textless/text variants
- 🖼️ **Fanart.tv logos** — HD clearlogos and artwork for movies
- 📺 **TVDB support** — TV show posters, season artwork, logos, and coming-soon indicators
- 🔀 **Source priority** — Reorder API sources (TMDb, TVDB, Fanart) - configurable in Advanced Settings
- 🔄 **Smart fallback** — Switch sources if preferred artwork unavailable

### 🧪 **Experimental Features**
- 📝 **Custom text overlay** — Add template variables like {title} and {year}
- 🏷️ **Library-specific label removal** — Configure which labels to remove per library

### 📜 **History & Tracking**
- 📋 **Poster history** — Complete log of all generated posters with filtering
- 👁️ **Preview on hover** — View button shows poster preview popup without leaving page
- 🔍 **Filter by library, template, source, action** — Find specific history records quickly
- 📊 **Fallback tracking** — See which posters used template fallback

---

# ✨ Core Features

## 🎞 Plex-Aware Movie Picker

Simposter connects directly to Plex using:

- `PLEX_URL`  
- `PLEX_TOKEN`  
- `PLEX_MOVIE_LIBRARY_NAME`  

Selecting a movie automatically loads:

✔ TMDb ID  
✔ TMDb posters and logos  
✔ Plex’s existing poster  
✔ All Plex labels for removal  

---

## 🖼 Multi-Source Artwork Integration

Simposter pulls artwork from multiple sources:

### TMDb (Movies & TV)
- Posters (original, textless, text variants)
- High-resolution logos
- Multi-language support with fallback

### Fanart.tv (Movies)
- HD clearlogos
- High-quality artwork
- Merged with TMDB or standalone

### TVDB (TV Shows)
- TV show posters
- Season posters
- Logos and banners
- Coming soon indicator support

UI includes:
- Thumbnail strips  
- "View All" modal  
- Filters: **all**, **textless**, **text**
- Source priority selection

---

## 🧩 Templates (Universal + UniformLogo)

### 1️⃣ Universal Template  (better for manual control)
Full creative controls for cinematic posters.

### 2️⃣ Uniform Logo Template (better for bulk edits/consistent logo placement)
Precise bounding-box placement for ultra-clean minimalist sets.

---

## 🔣 Logo System

### Logo Sources
- **TMDB** — Movie logos from The Movie Database
- **Fanart.tv** — High-quality HD clearlogos
- **Merged** — Combine both sources with priority
- **Auto-fallback** — Switch sources if preferred unavailable

### Logo Modes
- **Stock** — Keep logo as-is
- **Match** — Color match logo to poster
- **Hex** — Custom color (works best with white logos)
- **None** — No logo rendering

### Logo Preference
- **White** — Prefer white/light logos (low saturation)
- **Color** — Prefer colored logos (high saturation)
- **First** — Use first available logo

### Fallback System
- **Continue** — Render without logo if missing
- **Skip** — Don't render if logo unavailable
- **Template** — Switch to different template/preset (e.g., text-based)
- **Template** — Switch to different template/preset (e.g., text-based)

![Image](https://github.com/user-attachments/assets/10ba7d2f-0e1b-4ab7-b9cf-67651ec335e0)
![Image](https://github.com/user-attachments/assets/9ebeed0c-5727-48f7-8be7-302d1f1d7b1c)
---

## 📝 Text Overlay (Experimental)

Add custom text overlays with template variables:

### Features
- 🎯 **Template variables** — Use `{title}` and `{year}` in custom text
- 🎨 **Full customization** — Font family, size, weight, color
- 📍 **Precise positioning** — X/Y offset controls
- 🌈 **Shadow & outline** — Text effects for readability
- ⚠️ **Experimental** — Feature is still in development

### Example
```
{title} ({year})
```
Renders as: `Movie Title (2024)`

---

## 💾 Template-Based Presets

Stored per-template in:

```
/config/settings/presets.json
```

Includes save, delete, JSON import/export.

UI settings live alongside presets:

```
/config/settings/ui_settings.json
```

---

## 📂 Output

```
/config/output/Movie Title (Year)/poster.jpg
```

---

## 📝 Logs

```
/config/logs/simposter.log
```

Log preferences are stored in the database (auto-migrated from `/config/settings/log_config.json` if present).

![Image](https://github.com/user-attachments/assets/2e7b7b23-770e-463e-91e6-62f0d061fff1)

---

## 📜 History View

Track all generated posters with comprehensive filtering and preview capabilities.

### Features
- **Complete history** — Every poster generation is logged with timestamp, template, preset, and source
- **Filtering** — Filter by library, template, action (sent to Plex, saved locally), and source (manual, batch, webhook, auto-generate)
- **Preview on hover** — Hover over the "View" button to see a popup preview of the generated poster
- **Fallback tracking** — See which posters used template fallback due to missing logos/posters

### Preview Sources
- **Locally saved posters** — Preview from saved file on disk
- **Sent to Plex** — Preview fetches current poster from Plex

### Columns
| Column | Description |
|--------|-------------|
| Preview | Hover to see poster thumbnail |
| Date & Time | When the poster was generated |
| Title | Movie or TV show title |
| Year | Release year |
| Library | Which Plex library |
| Template | Template used |
| Preset | Preset applied |
| Source | manual, batch, webhook, auto_generate |
| Action | sent_to_plex or saved |
| Fallback | Shows if template fallback was used |
| Path | Local save path (if saved) |

---

## 📡 Plex Upload

- Upload poster  
- Remove labels  
- Auto-refresh existing poster  

---

## 📦 Batch Mode

**Full-page interface** with advanced features:

### Selection & Filtering
- 📋 **Grid view** — Visual movie selection with thumbnails
- 🔍 **Search & filter** — Find movies by title, year, or label
- ✅ **Select all/deselect** — Bulk selection controls
- 🏷️ **Label-based filtering** — Filter by existing Plex labels

### Preview & Validation
- 👁️ **Live preview sidebar** — Real-time rendering with selected template + preset
- 🔄 **Navigate previews** — Cycle through selected movies before processing
- 📝 **Movie list** — Quick jump to any movie's preview
- ✨ **TMDB assets** — Preview uses TMDB posters based on preset (textless, text, any)

### Processing
- 🎯 **Template + preset required** — Ensures consistent output
- 📤 **Send to Plex** — Upload directly to your Plex server
- 💾 **Save locally** — Export to `/config/output/`
- 🏷️ **Smart label removal** — Select specific labels to remove (cached from Plex)
- 📊 **Progress tracking** — Visual progress bar during batch processing

### Caching
- ⚡ **Fast loading** — Posters and labels cached in sessionStorage
- 🔄 **Shared cache** — Cache shared between main view and batch edit
- 🚀 **Lazy loading** — Assets load on-demand

![Image](https://github.com/user-attachments/assets/e6e60d93-5913-4054-aa47-b38a04bd5435)
---

## 🎙️ Tautulli Webhook Configuration

Tautulli can automatically trigger poster generation when Plex events occur (new media added, watched, etc.). Configure a webhook in Tautulli to send events to Simposter.

### Setup Steps

1. **In Simposter Settings** (Performance Tab):
   - Enable "Automatically Send to Plex" if you want webhooks to automatically upload posters
   - Configure "Default Labels for Webhook Posters" (e.g., "Overlay, Auto")
   - Save your settings

2. **In Tautulli Settings** > **Notification Agents** > **Add a new notification agent** > **Webhook**:

### Webhook URL Format

```
http://your-server:8686/api/webhook/tautulli?template_id=TEMPLATE_ID&preset_id=PRESET_ID&event_types=added
```

**Query Parameters:**
- `template_id` — Your template ID (required)
- `preset_id` — Your preset ID (required)
- `event_types` — Comma-separated list: `added`, `updated`, `watched` (default: `added`)
- `test=true` — Optional: dry-run mode with detailed logging (no actual poster generation)

**Example URLs:**
```
# Generate posters for newly added content only
http://localhost:8686/api/webhook/tautulli?template_id=universal&preset_id=my-preset&event_types=added

# Test mode (dry-run with logging)
http://localhost:8686/api/webhook/tautulli?template_id=universal&preset_id=my-preset&event_types=added&test=true

# Multiple event types
http://localhost:8686/api/webhook/tautulli?template_id=universal&preset_id=my-preset&event_types=added,watched
```

### Webhook Configuration (Movies)

**Webhook Method:** `POST`

**JSON Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**JSON Data:**
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

**Triggers:** Configure which events to trigger on (e.g., "Recently Added")

### Webhook Configuration (TV Shows)

**Webhook Method:** `POST`

**JSON Headers:**
```json
{
  "Content-Type": "application/json"
}
```

**JSON Data:**
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

**Triggers:** Configure which events to trigger on (e.g., "Recently Added")

**Important for TV Shows:**
- **Episode events are automatically ignored** for the `added` category to prevent duplicate processing
- Configure Tautulli to send **show-level or season-level** events, not episode-level events
- When a new episode is added, Tautulli may send an event for each episode, but Simposter will skip these to avoid regenerating the same show poster multiple times
- Use library scan notifications (show/season level) instead of episode notifications for best results

### Supported Event Types

Tautulli sends various event types that Simposter maps automatically:

| Tautulli Event | Simposter Category | Description |
|---------------|-------------------|-------------|
| `library.new` | `added` | New media added to library |
| `created` | `added` | Alternative event for new media |
| `library.update` | `updated` | Media metadata updated |
| `playback.stop` | `watched` | Media finished playing |

Configure `event_types` in the URL to control which events trigger poster generation.

### Testing Your Webhook

1. **Use Test Mode**: Add `&test=true` to your webhook URL for dry-run testing
2. **Check Logs**: Monitor `/config/logs/simposter.log` for webhook events
3. **Manual Test**: Use Tautulli's "Test Notification" button to send a test event

**Example Test Payload** (for manual API testing):
```bash
curl -X POST "http://localhost:8686/api/webhook/tautulli?template_id=universal&preset_id=my-preset&event_types=added&test=true" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "created",
    "media_type": "movie",
    "title": "Catch Me If You Can",
    "year": "2002",
    "rating_key": "60996",
    "tmdb_id": "640",
    "thetvdb_id": ""
  }'
```

### Troubleshooting

**No poster generated for TV shows?**
- **Episode events are ignored by design** - Configure Tautulli to send show-level events instead
- Check that your notification trigger is set to "Recently Added" for shows, not episodes
- Review logs for `[TAUTULLI_WEBHOOK] Skipping episode` messages
- Verify template_id and preset_id exist in your settings

**No poster generated for movies?**
- Check that `event_types` parameter includes the event category (e.g., `added`)
- Verify template_id and preset_id exist in your settings
- Review logs for errors: `[TAUTULLI_WEBHOOK]` prefix

**Duplicate processing?**
- For movies: Tautulli may send multiple events for the same item, which is normal
- For TV shows: Episode events are automatically skipped to prevent duplicates

**Event not recognized?**
- Check logs to see what event type Tautulli is sending
- Verify the event maps to a supported category (see table above)

---

## 🏷️ Webhook Ignore Labels

Skip automatic poster generation for specific items by assigning Plex labels. This feature works with both webhooks (Radarr, Sonarr, Tautulli) and auto-generate during library scans.

### Use Cases
- **Preserve custom artwork** — Mark items with labels like "AURA" or "Custom" to keep their existing posters
- **Exclude collections** — Use labels to prevent poster generation for specific collections
- **Temporary exclusions** — Add labels to skip items during bulk processing

### Configuration

1. **In Plex** — Add labels to movies/TV shows you want to exclude (e.g., "NoOverlay", "Custom", "Manual")

2. **In Simposter Settings** (Libraries Tab):
   - Expand the library card (Movie or TV Show library)
   - Find the "Webhook Ignore Labels" section
   - Check the labels that should skip poster generation
   - Save settings

### How It Works

| Trigger | Behavior |
|---------|----------|
| **Webhook (Radarr/Sonarr/Tautulli)** | Checks item labels before processing; skips if ignore label found |
| **Auto-Generate (Library Scan)** | Checks item labels before processing; item is still scanned/added to database, but poster generation is skipped |
| **Manual Batch** | Ignore labels do NOT apply; you have full control |

### Notes
- Label matching is **case-insensitive** ("AURA" matches "aura", "Aura", etc.)
- Items with ignore labels are still scanned into Simposter's database
- Only poster generation is skipped — metadata is still tracked
- Configure different ignore labels per library (movies vs TV shows)

---

# 📁 Project Structure

```
simposter/
├── backend/
│   ├── main.py
│   ├── rendering.py
│   ├── config.py
│   ├── tmdb_client.py
│   ├── assets/
│   │   └── selection.py         # Poster/logo picking logic
│   ├── templates/
│   │   ├── universal.py         # Shared rendering utilities
│   │   └── uniformlogo.py       # Main template (bounding box logo placement)
│   └── api/
│       ├── preview.py           # Enhanced with TMDB integration (v1.4)
│       ├── save.py
│       ├── plexsend.py
│       ├── batch.py
│       ├── movies.py
│       ├── presets.py
│       ├── templates.py         # Template listing (v1.4)
│       ├── uploads.py
│       └── ui_settings.py
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── MoviesView.vue
│   │   │   └── BatchEditView.vue    # New in v1.4
│   │   ├── components/
│   │   │   ├── editor/
│   │   │   │   ├── EditorPane.vue
│   │   │   │   └── TextOverlayPanel.vue  # New in v1.4
│   │   │   └── layout/
│   │   │       └── Sidebar.vue
│   │   └── stores/
│   │       └── ui.ts             # SessionStorage caching (v1.4)
│   └── index.html
├── config/
│   ├── settings/
│   │   ├── presets.json         # User presets
│   │   └── ui_settings.json     # UI configuration
│   ├── logs/
│   │   └── simposter.log
│   └── output/                  # Saved posters
└── Dockerfile
```

---

## 🎯 Settings Guide

Simposter settings are organized into 5 tabs for easy navigation:

### **🏠 General Tab**
- Theme selection (Light/Dark mode)
- Poster display density (Grid view)
- Library refresh interval

### **📚 Libraries Tab**
- **Plex Connection** — Server URL, API token, SSL verification
- **Library Configuration** — Enable/disable per-library processing, set output folders
- **Auto-Generate** — Enable automatic poster generation for new content with template/preset selection
- **Webhook Ignore Labels** — Skip poster generation for items with specific labels (webhooks & auto-generate)
- **Label Removal** — Choose which Plex labels to remove per library (checkboxes)
- **Scheduled Scans** — Configure cron schedule for automatic library scanning

### **💾 Save Locations Tab**
- **Movie Output** — Where to save generated posters (default: Plex poster folder)
- **TV Show Output** — Separate folder for TV posters
- **Batch Subfolder** — Organize batch-generated posters in subfolders

### **⚡ Performance Tab**
- **Image Quality** — Choose output format (JPEG/PNG/WebP) with per-format quality sliders
  - JPEG quality: 0-100%
  - PNG compression: 0-9 (0=no compression, 9=best)
  - WebP quality: 0-100%
- **Rendering Performance**
  - Concurrent renders: 1-4 (balance speed vs memory)
  - Memory limit: 512MB-4GB
  - Overlay cache: Pre-generate overlays for faster rendering
- **API Rate Limiting** — Configure request limits per API (5-100 requests/10 seconds)
  - TMDb rate limit
  - TVDB rate limit
- **Cache Management** — Clear application cache, image cache, or database

### **🔧 Advanced Tab**
- **API Source Priority** — Drag to reorder (TMDb, TVDB, Fanart)
  - Lock/unlock sources to prevent reordering
  - Set which source takes priority for artwork lookup
- **Database Management**
  - Export settings database
  - Import settings from backup

---

# ⚙️ Configuration

Simposter supports **two configuration methods**:

1. **GUI Settings (Recommended for most users)** - Configure via the Settings page in the web UI
2. **Environment Variables** - Set via `.env` file or docker-compose (useful for automation)

**Priority order**: Environment variables override GUI settings

| Variable | Required |  Purpose | Example |
|----------|----------|-------------|---------|
| `PLEX_URL` | * | Base Plex URL | `http://myplex:32400` |
| `PLEX_TOKEN` | * | Plex token | `xxxyyyzzz` |
| `PLEX_MOVIE_LIBRARY_NAME` | * | Movie library | `Movies` |
| `PLEX_TV_LIBRARY_NAME` |  | TV show library | `TV Shows` |
| `TMDB_API_KEY` | * | TMDb key |  `abcd1234` |
| `TVDB_API_KEY` |  | TVDB key (for TV shows) |  `efgh5678` |
| `FANART_API_KEY` |  | Fanart.tv key (for logos) |  `ijkl9012` |
| `CONFIG_DIR` |  | Config path (Docker only) | `/config` |

\* Can be set via GUI Settings OR environment variables

---

# 🐳 Docker Deployment

## Method 1: Simple Docker Run (GUI Configuration)

**Easiest for most users** - Configure Plex/TMDB credentials via the Settings page after starting:

```bash
docker run -d \
  --name simposter \
  -p 8003:8003 \
  -e CONFIG_DIR=/config \
  -v /path/to/config:/config \
  simposter:latest
```

Then visit `http://localhost:8003` and configure your Plex/TMDB settings in the GUI.

## Method 2: Docker Compose (Environment Variables)

**Best for automation** - Credentials set in `.env` file or docker-compose:

```bash
docker-compose up -d
```

Example `docker-compose.yml`:
```yaml
services:
  simposter:
    image: simposter:latest
    ports:
      - "8003:8003"
    volumes:
      - ./config:/config
```

## Build Image

```bash
docker build -t simposter:latest .
```

---

# 🖥 Local Dev

```bash
uvicorn backend.main:app --reload --port 8003
```

---

# 🧩 Workflow

## Single Movie
1. **Select movie** — Choose from Plex library
2. **Load TMDb assets** — Automatic fetch of posters and logos
3. **Choose template + preset** — Select from saved presets
4. **Adjust controls** — Fine-tune settings (optional)
5. **Preview** — Real-time preview with changes
6. **Save / Send to Plex** — Export or upload

## Batch Mode (New!)
1. **Navigate to Batch Edit** — Access from Movies submenu
2. **Select movies** — Use grid view with search/filter
3. **Choose template + preset** — Both required for consistency
4. **Preview renders** — Navigate through selected movies
5. **Select labels to remove** — Choose specific labels (optional)
6. **Process batch** — Send to Plex and/or save locally

## Automation
- **Scheduled scans** — Configure cron schedule in Settings to automatically scan your Plex library

---

# 💡 Tips

## General
- **Use textless posters** — Best for matte/fade effects
- **Uniform Logo template** — Ideal for set-wide consistency
- **Save presets** — Speed up library-wide creation
- **Use logs modal** — Debug API issues

## Batch Edit (v1.4)
- **Preview before processing** — Navigate through all selected movies to verify
- **Filter by labels** — Quickly find movies with specific labels
- **Use sessionStorage cache** — Posters load instantly on subsequent visits
- **Select specific labels to remove** — More control than auto-remove
- **TMDB integration** — Preview shows actual TMDB poster (textless/text) based on preset

## Performance
- **Smart cache management** — LRU eviction prevents quota errors, maintains fast performance
- **Indexed database queries** — 5-10x faster lookups for movies, TV shows, and history
- **Debounced editor** — Reduced UI operations during slider adjustments
- **Lazy loading** — Images load as you scroll
- **Shared cache** — Cache persists between main view and batch edit
- **Memory leak protection** — Automatic cleanup on navigation
- **Template + preset required** — Ensures consistent bulk processing

---

# 📜 License
MIT License.
