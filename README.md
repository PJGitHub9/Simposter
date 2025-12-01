# **Simposter v1.3.1 🎬🖼️ — Template-Based Poster Builder with TMDb + Plex + Radarr Automation**

> **Simposter** is a fast, modern poster-generation tool for Plex users who want **clean, consistent, template-driven artwork** — now with **multiple templates**, **TMDb integration**, **batch automation**, **Radarr webhook support**, **uniform logo alignment**, and **full preset control**.

![Image](https://github.com/user-attachments/assets/cc986a6c-5177-4820-b418-b035b10af26f)
---

## ✨ What’s New in v1.3.1

- 🔷 **Uniform Logo Template** with precise bounding-box alignment  
- 🖼 **Improved poster/logo auto-selection logic**  
- 🔗 **Radarr webhook support** (`/api/webhook/radarr/<template>/<preset>`)  
- 📦 **Batch mode fixed & improved** — auto-selects unique TMDb assets  
- 💾 **Presets reorganized** (now template-scoped: `default`, `uniformlogo`)  
- 🎛 Cleaner UI + fixed preset loading  
- 📡 More reliable Plex uploads + label removal  
- 🧩 Modular code (selection engine, templates, assets folder)
- 📒 Better logging (I hope)

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

- Stock - Keep logo as it is
- Match - Color match logo to poster color
- Hex - Custom color (works much better with white logos)

 Preference:
- Preferred white or color logos for easier bulk edits  

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

Log configuration: `/config/settings/log_config.json`.

---

## 📡 Plex Upload

- Upload poster  
- Remove labels  
- Auto-refresh existing poster  
![Image](https://github.com/user-attachments/assets/a7a2fcb5-da02-4d30-8373-deedb237b441)
---

## 📦 Batch Mode

- Uses template and preset  
- Unique TMDb assets  
- Optional Plex upload  
- Optional label removal  

![Image](https://github.com/user-attachments/assets/533217dc-3879-43c8-b3f9-2dafb0e18667)
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
│   │   ├── selection.py
│   ├── templates/
│   │   ├── universal.py
│   │   ├── uniformlogo.py
│   └── api/
│       ├── preview.py
│       ├── save.py
│       ├── plexsend.py
│       ├── batch.py
│       ├── movies.py
│       ├── presets.py
│       ├── uploads.py
│       └── webhooks.py
├── frontend/
│   └── index.html
└── Dockerfile
```

---

# ⚙️ Environment Variables

| Variable | Required |  Purpose | Example |
|----------|----------|-------------|---------|
| `PLEX_URL` | ✔ | Base Plex URL | `http://myplex:32400` |
| `PLEX_TOKEN` | ✔ | Plex token | `xxxyyyzzz` |
| `PLEX_MOVIE_LIBRARY_NAME` | ✔ | Movie library | `Movies` |
| `TMDB_API_KEY` | ✔ | TMDb key |  `abcd1234` |
| `CONFIG_DIR` | ✔ | Paths | `/config` |

---

# 🐳 Docker

## Build
```bash
docker build -t simposter:latest .
```

## Run
```bash
docker run -d   --name simposter   -p 8003:8003   -e PLEX_URL="http://<plex-ip>:32400"   -e PLEX_TOKEN="xxxx"   -e PLEX_MOVIE_LIBRARY_NAME="Movies"   -e TMDB_API_KEY="your_tmdb_key"   -v /mnt/user/appdata/simposter/config:/config   simposter:latest
```

---

# 🖥 Local Dev

```bash
uvicorn backend.main:app --reload --port 8003
```

---

# 🧩 Workflow

1. Select movie  
2. Load TMDb assets  
3. Choose template + preset  
4. Adjust controls  
5. Preview  
6. Save / Send to Plex  
7. Batch mode (optional)  
8. Radarr automation (optional)

---

# 💡 Tips

- Use textless posters for best matte/fade combos  
- Uniform Logo template is ideal for set-wide consistency  
- Use logs modal to debug API issues  
- Presets speed up library-wide creation  

---

# 📜 License
MIT License.
