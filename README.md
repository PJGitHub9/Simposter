# **Simposter 🎬🖼️ — Template-Based Poster Builder with TMDb + Plex + Radarr Automation**

> **Simposter** is a fast, modern poster-generation tool for Plex users who want **clean, consistent, template-driven artwork** — now with a **completely redesigned UI**, **enhanced batch editing**, **real-time preview**, **TMDB-integrated rendering**, and **intelligent caching**.

![Image](https://github.com/user-attachments/assets/bc31ee99-0d68-4ba0-a54f-d6b4a1b119b7)
---

## ✨ What’s New in v1.4.1

### 🎨 **Complete UI Overhaul**
- 🖥️ **New full-page batch edit interface** — Grid view with movie selection
- 👁️ **Real-time preview sidebar** — See rendered output with template + preset applied
- 🔄 **Preview navigation** — Cycle through selected movies with prev/next controls
- 📋 **Quick movie list** — Jump to any selected movie instantly
- 🏷️ **Smart label selector** — Choose specific labels to remove (replaces auto-remove)

### ⚡ **Performance & Caching**
- 💾 **SessionStorage caching** — Posters and labels cached across views
- 🚀 **Lazy loading** — Images load on-demand for better performance
- 🔍 **Label filtering** — Filter movies by existing labels in batch edit

### 🎬 **Enhanced Preview System**
- 🖼️ **TMDB integration** — Preview uses TMDB posters based on preset filter (textless, text, any)
- 🎭 **Logo mode support** — Respects 'none' setting (no logo fetch when disabled)
- 📐 **Accurate rendering** — Preview shows exact output with all preset options applied

### 🧪 **Experimental Features**
- 📝 **Custom text overlay** — Add template variables like {title} and {year} (experimental)

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

## 🖼 TMDb Artwork Integration

Simposter pulls:

- Posters  
- Textless variants  
- High-resolution logos  

UI includes:

- Thumbnail strips  
- “View All” modal  
- Filters: **all**, **textless**, **text**

---

## 🧩 Templates (Universal + UniformLogo)

### 1️⃣ Universal Template  (better for manual control)
Full creative controls for cinematic posters.

### 2️⃣ Uniform Logo Template (better for bulk edits/consistent logo placement)
Precise bounding-box placement for ultra-clean minimalist sets.

---

## 🔣 Logo System

Modes:

- **Stock** — Keep logo as-is
- **Match** — Color match logo to poster
- **Hex** — Custom color (works best with white logos)
- **None** — No logo rendering

Preference:
- **White** or **Color** — Preferred logo type for bulk edits

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

## 🔗 Radarr Webhook

```
POST /api/webhook/radarr/{template_id}/{preset_id}
```

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
│   │   ├── universal.py         # Default template
│   │   └── uniformlogo.py       # Uniform logo template
│   └── api/
│       ├── preview.py           # Enhanced with TMDB integration (v1.4)
│       ├── save.py
│       ├── plexsend.py
│       ├── batch.py
│       ├── movies.py
│       ├── presets.py
│       ├── templates.py         # Template listing (v1.4)
│       ├── uploads.py
│       └── webhooks.py
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
| `TMDB_API_KEY` | * | TMDb key |  `abcd1234` |
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
- **Radarr webhook** — Automatic poster generation on import

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
- **Lazy loading** — Images load as you scroll
- **Shared cache** — Cache persists between main view and batch edit
- **Template + preset required** — Ensures consistent bulk processing

---

# 📜 License
MIT License.
