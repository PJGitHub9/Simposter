# Simposter — How It Works

Every poster goes through the same rendering pipeline regardless of how it's triggered. The differences are only in **how the request arrives** and **what happens with the result**.

```
Input (movie + options) → Fetch assets (poster, logo) → Render (PIL) → Output (preview / disk / Plex)
```

---

## 1. Manual Editor (Movies View)

**You pick a movie, adjust sliders, click Preview.**

1. **Frontend** (`EditorPane.vue`) reads the current slider values and builds an `options` payload — things like `poster_zoom`, `logo_scale`, `matte_height_ratio`, `text_overlay_enabled`, etc.

2. `render.preview()` in `services/render.ts` POSTs to `/api/preview` with:
   - `template_id`, `preset_id` — which template and preset to use
   - `options` — the live slider values (override the saved preset)
   - `background_url` — the poster URL already shown in the editor
   - `rating_key` — Plex item ID (needed for media metadata)
   - `skip_fallback: true` — never switch to a fallback preset mid-render

3. **Backend** (`preview.py`):
   - Loads the saved preset from DB, merges with the incoming `options` (request options win, so sliders work live)
   - Since `background_url` is a pre-selected TMDb URL, skips re-fetching poster
   - Fetches logos from TMDb/Fanart based on `logo_preference`
   - If no logo found: `skip_fallback=True` so it renders without a logo rather than switching presets
   - Fetches Plex media metadata via `rating_key` → `video_resolution`, `audio_codec`, `edition`, etc.
   - Calls `render_poster()` which runs the full PIL pipeline
   - Returns base64 JPEG → displayed in editor

4. **You click Save / Send to Plex** → POSTs to `/api/save` or `/api/plex/send` with the same payload → same render pipeline, no fallback applied, result is written to disk and/or uploaded to Plex via `PUT /library/metadata/{rating_key}/posters`

---

## 2. Batch Render

**You select 50 movies in BatchEditView, click Render All.**

1. Frontend POSTs to `/api/batch/render` with a list of movies + template/preset + options

2. **Backend** (`batch.py`):
   - Creates a `ThreadPoolExecutor` with `concurrentRenders` workers (default 2)
   - For each movie, `_process_single_movie()` runs the full render pipeline:
     - Fetches poster/logo from TMDb/Fanart
     - **Fallback IS active here** — if no logo, switches to fallback preset (e.g. text-only)
     - Fetches Plex media metadata for overlay badges
     - Renders poster
     - Saves to disk and/or uploads to Plex
     - Records a history entry with `source='batch'`
   - Streams progress back to frontend as each movie completes

The key difference from manual: **fallback is intentional in batch** — you want it to handle logoless movies gracefully without stopping.

---

## 3. Webhook (Tautulli / Radarr / Sonarr)

**A new movie is added to Plex → Tautulli fires a webhook.**

1. Tautulli POSTs to `POST /api/webhook/tautulli` with event data (rating_key, event type)

2. **Backend** (`webhooks.py`):
   - Checks event type (`library.new`, `media.scrobble`, etc.)
   - Looks up the item in Plex using `rating_key` to get title, TMDb ID, etc.
   - Reads the auto-generate settings from DB (which preset, which library, whether to auto-send)
   - Runs the full render pipeline (same as batch for that single item)
   - If "Automatically Send to Plex" is enabled → uploads to Plex
   - Records history entry with `source='webhook'`

---

## 4. Scheduled Scan (Auto-Generate)

**Cron fires at 2 AM → scan library → generate new posters.**

1. **APScheduler** triggers `run_scheduled_scan()` in `scheduler.py`
2. Calls `api_scan_library()` which walks the Plex library, detects new/changed items
3. For items marked for auto-generation, runs the same render pipeline as batch
4. Records history with `source='scheduled'`

---

## How Overlays Get Applied

Overlays are the badge system (resolution, studio, streaming platform, etc.). They run **after** the base poster is composed.

```
Base poster render (matte + fade + vignette + logo)
  ↓
Overlay pass (universal.py)
```

**Step by step in `backend/templates/universal.py`:**

1. **Load overlay config** — reads from DB using `overlayConfigId` from the preset

2. **Pre-pass** (resolves dynamic fields before the element loop):
   - If any element is `studio_badge` + `tmdb_id` available → calls `get_studio_name()` + `get_studio_company_id()` → injects `metadata["studio"]` and `metadata["studio_company_id"]`
   - If any element is `streaming_platform_badge` → calls `get_watch_providers(tmdb_id, media_type, region)` → picks highest-priority `flatrate` provider → injects `metadata["streaming_platform"]`

3. **Element loop** — for each element in the config:
   - Check `show_if_label` / `hide_if_label` against Plex labels → skip if condition not met
   - Get the metadata value for this element type (e.g. `metadata["video_resolution"]` → `"4k"`)
   - Look up `badge_modes[value]` — what should happen for this specific value?
     - `"none"` → skip, render nothing
     - `"text"` → draw text directly onto poster with configured font/color/size
     - `"image"` → composite a user-uploaded PNG from the `overlay_assets` DB table
     - `"asset"` → call `get_asset_url(slug, company_id)` → fetch PNG from simposter-assets GitHub repo → composite it
   - Position the badge at `(position_x * poster_width, position_y * poster_height)`

4. **Overlay cache** — the base template effects (matte/fade/vignette layers) are cached as a PNG per `template/preset`. On cache hit, the base render is skipped and only the dynamic parts (logo, badges) are recomposed. This gives 3-5x speedup in batch mode.

---

## The Fallback System

When a movie has no logo available:

- **Manual editor**: `skip_fallback=True` → renders without a logo (blank logo area), preserves your selected preset
- **Batch / webhook / scheduled**: Fallback IS applied
  - Checks `fallbackLogoAction` in the preset (`"continue"`, `"template"`, or `"skip"`)
  - If `"template"` → switches to the configured fallback template/preset (e.g. a text-only preset that renders the movie title instead of a logo)
  - The fallback preset's full options override the current ones — so the text overlay, font, etc. from the fallback preset all take effect

---

## Summary

| Trigger | Fallback? | Output | History source |
|---|---|---|---|
| Manual editor preview | No | base64 preview | — |
| Manual save/send | No | disk + Plex | `manual` |
| Batch render | Yes | disk + Plex | `batch` |
| Webhook | Yes | Plex | `webhook` |
| Scheduled scan | Yes | Plex | `scheduled` |

---

**Last Updated**: 2026-03-16
**Current Version**: v1.5.71
