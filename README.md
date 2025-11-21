# Simposter 🎬🖼️

> **Simposter** – a simple, opinionated, TMDb‑powered poster builder with live preview, Plex integration, and one‑click uploads.

Simposter is a small FastAPI + HTML/JS app that helps you generate clean, vertical (2:3) artwork for your media library.  
It talks to **Plex** for your movie list, **TMDb** for posters/logos, and renders final images via **Pillow** – with sliders for zoom, matte, fade, vignette, grain, and logo controls.

<img width="2476" height="1241" alt="Image" src="https://github.com/user-attachments/assets/2ffe0dd7-ba1f-4c6e-aebb-84f213100aed" />

---

## ✨ Features

- 🎞 **Plex‑aware movie picker**  
  - Reads your Plex movie library via `PLEX_URL`, `PLEX_TOKEN`, and `PLEX_MOVIE_LIB_ID`.
  - Movie dropdown is sorted with **most recently added first**.

- 🖼 **TMDb artwork browser**
  - Fetches **posters + logos** from TMDb for the selected movie.
  - Filter posters by:
    - `All`
    - `Textless`
    - `With Text`
  - Thumbnail strips for quick selection, plus a “View All” modal grid.

- 🎚 **Full‑control rendering**
  - Vertical 2:3 canvas (TMdb‑friendly).
  - Sliders for:
    - Poster zoom
    - Poster vertical shift
    - Matte height
    - Fade height
    - Vignette strength
    - Grain amount
    - Logo scale
    - Logo vertical position (0–100% of canvas height)
  - Live auto‑preview as you tweak sliders and URLs.

- 🔣 **Logo modes**
  - **Keep Original** – use the TMDb logo as‑is.
  - **Color Match Poster** – tint based on the average poster color.
  - **Custom Hex Color** – colorize the logo with a chosen hex value.

- 💾 **Presets JSON**
  - `presets.json` holds template presets (e.g. “DarkMatte”, “Clean”).
  - UI supports:
    - Loading presets.
    - Copying your current settings as JSON.
    - Applying JSON back into the UI.
    - **Save / Overwrite Preset** via `/api/presets/save`.

- 📂 **File output**
  - Saves posters as `poster.jpg` under:
    ```text
    /poster-outputs/Movie Title (Year)/poster.jpg
    ```
  - Output root is configurable via `OUTPUT_ROOT`.

- 📡 **Plex artwork update + label cleanup**
  - A **Send to Plex** action:
    - Uploads the rendered poster to Plex as the movie’s artwork.
    - Removes the `overlay` label from that movie (to play nice with Kometa overlays).

> Right now, Simposter focuses on movies; shows/collections could be added later.

---

## 🧱 Tech Stack

- **Backend**
  - Python 3.11
  - FastAPI
  - Uvicorn
  - Requests
  - Pillow (PIL) for image processing
- **Frontend**
  - Vanilla HTML/JS + a small amount of CSS
  - Fetch‑based API calls to the backend
- **Integrations**
  - Plex HTTP API
  - TMDb API (via `tmdb_client.py`)

---

## 📁 Project Structure

```text
.
├─ backend/
│  ├─ main.py           # FastAPI app + Plex/TMDb endpoints, preview/save/send-to-plex
│  ├─ tmdb_client.py    # TMDb API client + image helpers
│  ├─ templates/
│  │  ├─ __init__.py    # Template registry (universal renderer wired as "default")
│  │  └─ universal.py   # Single universal renderer (matte, fade, vignette, grain, logo)
│  ├─ presets.json      # Template defaults + presets for the UI
│
├─ frontend/
│  └─ index.html        # Single-page UI + JS logic for sliders, presets, posters/logos
│
├─ Dockerfile           # Container image for Simposter
├─ requirements.txt     # Python dependencies
└─ README.md
```

---

## ⚙️ Environment Variables

Simposter expects a few environment variables (especially in Docker):

| Variable           | Required | Description                                             | Default                      |
|--------------------|----------|---------------------------------------------------------|------------------------------|
| `PLEX_URL`         | ✅       | Plex base URL (e.g. `http://host.docker.internal:32400`) | `http://localhost:32400`    |
| `PLEX_TOKEN`       | ✅       | Plex API token                                          | _empty_                      |
| `PLEX_MOVIE_LIB_ID`| ✅       | Plex library section ID for movies                      | `1`                          |
| `OUTPUT_ROOT`      | ⚪       | Where posters are written inside the container          | `/poster-outputs`           |
| `TMDB_API_KEY`     | ✅       | TMDb API key (used by `tmdb_client.py`)                 | _none_                       |

You can override `OUTPUT_ROOT` to map into a persistent volume so your generated posters survive container restarts.

---

## 🐳 Running with Docker

### 1. Build the image

From the root of the repo:

```bash
docker build -t simposter:latest .
```

### 2. Run the container

Example:

```bash
docker run -d \
  --name simposter \
  -p 8000:8000 \
  -e PLEX_URL="http://your-plex-host:32400" \
  -e PLEX_TOKEN="your_plex_token_here" \
  -e PLEX_MOVIE_LIB_ID="1" \
  -e TMDB_API_KEY="your_tmdb_api_key" \
  -e OUTPUT_ROOT="/poster-outputs" \
  -v /path/on/host/poster-outputs:/poster-outputs \
  simposter:latest
```

Then open:

```text
http://localhost:8000
```

---

## 🖥 Running Locally (without Docker)

1. **Create and activate a virtualenv** (optional but recommended):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables** (at minimum):

   ```bash
   export PLEX_URL="http://your-plex-host:32400"
   export PLEX_TOKEN="your_plex_token_here"
   export PLEX_MOVIE_LIB_ID="1"
   export TMDB_API_KEY="your_tmdb_api_key"
   export OUTPUT_ROOT="/poster-outputs"
   ```

4. **Run Uvicorn** from the project root:

   ```bash
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. Open the UI at:

   ```text
   http://localhost:8000
   ```

---

## 🧩 Usage Workflow

1. **Pick a movie**  
   - The “Movie (from Plex)” dropdown is populated from your Plex movie library.

2. **Pick posters + logos from TMDb**
   - Simposter uses the movie’s Plex metadata to look up its TMDb ID.
   - It fetches posters/logos and shows them as thumbnail strips.
   - Use the `Poster Filter` (all / textless / text) to narrow options.
   - Click a thumb to select it, or use “View All” to open a grid picker.

3. **Tune your look**
   - Choose a **Preset** to load base settings (e.g. a DarkMatte or Clean look).
   - Adjust sliders:
     - Zoom, shift, matte height, fade, vignette, grain.
     - Logo scale and position (0–100% down the canvas).
   - Choose a **Logo Mode**:
     - Stock, matched, or custom hex.
   - The preview automatically re-renders as you tweak controls.

4. **Presets / JSON**
   - Hit **Copy JSON** to get your current template + slider config.
   - Paste JSON back and **Apply** to restore or share settings.
   - Use **Save / Overwrite Preset** to persist your current options into `presets.json`.

5. **Save locally**
   - Click **Save** to render and write to:
     ```text
     /poster-outputs/Movie Title (Year)/poster.jpg
     ```

6. **Send to Plex**
   - (From the UI) click **Send to Plex**:
     - Renders using your current settings.
     - Uploads the artwork directly to the movie in Plex.
     - Removes the Plex label `overlay` for that movie (so Kometa doesn’t re‑overlay it).

---

## 🧪 Tips & Gotchas

- If you see `Error: Invalid background image`, the TMDb image URL might have failed to download or is not a valid image. Try another poster or logo.
- If logos appear oddly colored:
  - Ensure **Logo Mode** is set to **Keep Original**.
  - For `match`/`hex` modes, keep in mind they re‑tint the logo based on the average color or your chosen hex.
- For best results, use **textless posters** when building matte‑heavy or logo‑focused layouts.

---

## 🗺 Roadmap / Ideas

- TV show & collection support.
- Additional template “styles” built on top of the same universal renderer.
- Export presets per‑template.
- Batch “auto‑generate & send to Plex” API for unattended runs.
- Optional Kometa/TMdb glue logic.

---

## 🤝 Contributing

This is a small, niche tool built for smoothing Plex/Kometa/TMdb workflows, but PRs and ideas are welcome.

If you’d like to:
- Add a new preset style,
- Improve the front‑end UX,
- Wire up batch APIs,

…feel free to open an issue or a pull request.

---

## 📜 License

MIT – do whatever, just don’t blame Simposter when you spend three hours perfecting a single poster. 😄
