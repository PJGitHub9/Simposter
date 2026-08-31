# Simposter — How It Works

Every poster goes through the same rendering pipeline regardless of how it's triggered. The differences are only in **how the request arrives**, **whether fallback is applied**, and **what happens with the result**.

```
Input (movie/show/collection + options) → Fetch assets (poster, logo) → Render (PIL) → Output (preview / disk / Plex)
```

---

## 1. Manual Editor (Movies / TV / Collections)

**You pick an item, adjust sliders, click Preview.**

1. **Frontend** (`EditorPane.vue` / `TvShowEditorPane.vue` / `KometaCreatorPane.vue`) reads the current slider values and builds an `options` payload — `poster_zoom`, `logo_scale`, `matte_height_ratio`, `text_overlay_enabled`, etc.

2. `render.preview()` in `services/render.ts` POSTs to `/api/preview` with:
   - `template_id`, `preset_id` — which template and preset to use
   - `options` — the live slider values (override the saved preset)
   - `background_url` — the poster URL already shown in the editor
   - `rating_key` — Plex item ID (needed for media metadata)
   - `skip_fallback: true` — never switch to a fallback preset mid-render, so what you're editing is always exactly what you asked for

3. **Backend** (`preview.py`):
   - Loads the saved preset from DB, merges with the incoming `options` (request options win, so sliders work live)
   - Since `background_url` is a pre-selected TMDb URL, skips re-fetching poster
   - Fetches logos from TMDb/Fanart based on `logo_preference` (recent lookups are cached briefly — see Performance below)
   - If no logo found: `skip_fallback=True` so it renders without a logo rather than switching presets
   - Fetches Plex media metadata via `rating_key` → `video_resolution`, `audio_codec`, `edition`, etc. (skipped for collections — they have none)
   - Calls `render_poster_image()`, which runs the full PIL pipeline **without** the overlay cache — every preview is a from-scratch render, which is what keeps slider changes live-accurate instead of showing a stale cached effect layer
   - Returns base64 JPEG → displayed in editor

4. **You click Save / Send to Plex** → POSTs to `/api/save` or `/api/plex/send` with the same payload → same uncached render pipeline, no fallback applied, result is written to disk and/or uploaded to Plex (`POST /library/metadata/{rating_key}/posters`, or `/library/collections/{id}/posters` for a collection).

Collections route through the same manual-editor pipeline, just with a different template (`kometa` instead of `uniformlogo` if you use the Kometa Creator — see below) and no Plex media-metadata step.

---

## 2. Batch Render

**You select a chunk of your library in Batch Edit, click Render All.**

1. Frontend POSTs to `/api/batch-movies` or `/api/batch-tv-shows` (the legacy combined `/api/batch` endpoint still exists for backward compatibility) with a list of items + template/preset + options

2. **Backend** (`batch.py`):
   - Creates a `ThreadPoolExecutor` with `concurrentRenders` workers (default 2, configurable up to 10 in Settings → Performance)
   - For each item, `_process_single_movie()` / `_process_single_tv_show()` runs the full render pipeline:
     - Fetches poster/logo from TMDb/Fanart
     - **Fallback IS active here** — if no logo, switches to the configured fallback preset (e.g. text-only)
     - Fetches Plex media metadata for overlay badges
     - Renders via `render_with_overlay_cache()` — reuses the pre-rendered matte/fade/vignette/grain layer for that template+preset when the overlay cache is enabled, which is what makes batch rendering 3-5x faster than the manual editor's per-item uncached render
     - Saves to disk and/or uploads to Plex (see [WEBHOOKS.md](docs/WEBHOOKS.md) and [COLLECTIONS_AND_POSTERS.md](docs/COLLECTIONS_AND_POSTERS.md) for what "uploads" involves — connection-pooled, tiered PNG encode)
     - Records a history entry with `source='batch'`
   - Streams progress back to frontend as each item completes (polled via `/api/batch-progress`)

The key difference from manual: **fallback is intentional in batch** — you want it to handle logoless movies gracefully without stopping the whole run, and you want the speed of the overlay cache since you're rendering many items, not tuning one.

---

## 3. Webhook (Radarr / Sonarr / Tautulli)

**A movie is imported by Radarr → Radarr fires a webhook.**

1. Radarr/Sonarr POST to `/api/webhook/radarr/{template_id}/{preset_id}` or `/api/webhook/sonarr/{template_id}/{preset_id}`; Tautulli POSTs to `/api/webhook/tautulli?template_id=...&preset_id=...&event_types=...` (see [WEBHOOKS.md](docs/WEBHOOKS.md) for the full setup and payload shapes for all three)

2. **Backend** (`webhooks.py`):
   - Validates the shared webhook secret if one is configured
   - Filters by event type (only import/upgrade-type events actually trigger a render)
   - Matches the payload's TMDb/TVDb ID against Plex by **exact GUID match** to find the `rating_key`
   - Checks the item isn't hitting a configured Webhook Ignore Label
   - Runs the same render pipeline as batch for that single item (fallback active, overlay cache used) via `process_webhook_poster_generation()`
   - If **Existing Content Mode** is set to `Resend` and a cached render already exists, skips regeneration entirely and just re-pushes the cached bytes
   - If "Automatically Send to Plex" is enabled → uploads to Plex, removes configured labels, and applies **Label to Add After Sending** (Settings → Automation) if one is set
   - If the result doesn't meet ideal template conditions and retry-until-met is on → adds it to the retry queue (see below)
   - Records history entry with `source='webhook'`

---

## 4. Scheduled Scan (Auto-Generate)

**Cron fires → scan library → generate posters for new/changed items.**

1. **APScheduler** triggers the scheduled scan job in `scheduler.py`
2. Walks the configured Plex library/libraries, detects new or changed items since the last scan
3. For items marked for auto-generation, runs the same render pipeline as batch (fallback active, overlay cache used)
4. Records history with `source='auto_generate'`

---

## 5. Retry Queue

**A render didn't meet the ideal template (no clearlogo found, no textless poster) → queued instead of left imperfect forever.**

This isn't a trigger in the same sense as the four above — it's a follow-up pass over items that batch/webhook/scheduled runs already flagged as `needs_retry`.

1. `_run_poster_retry()` (`scheduler.py`) runs on the configured interval, pulling pending items from the retry queue
2. For each item, re-runs the exact same render pipeline as batch/webhook, but with `send_only_if_ideal=True`
3. **Critically**: the Plex upload only happens if the fresh render actually meets ideal conditions this time (real logo found, no fallback needed) — a retry that still doesn't meet spec updates the attempt count and leaves the item queued, it never re-uploads a still-imperfect result on top of nothing having changed
4. On success, the item is marked resolved and removed from the queue; if `retryMaxAttempts` is exceeded, or if the source Plex item is confirmed deleted (a definitive 404, not a network blip), the item is abandoned instead of retrying forever
5. The manual **Retry Now** button (History → Retry Queue) runs the identical single-item logic on demand

---

## Collections & the Kometa Template

Collections have no TMDb/TVDB entry of their own, so they skip the metadata-lookup and Plex-media-info steps every other item goes through. Two things distinguish their pipeline:

- **Logo source**: TMDb has no artwork endpoint for collections at all. Fanart.tv does have franchise-wide logos, just filed under the TMDb collection ID inside its regular movie-artwork namespace — `get_logos_for_movie()` works unmodified when called with a collection ID.
- **Template**: the **Kometa** template (`render_kometa()` in `backend/templates/kometa.py`) is a separate, smaller renderer from Uniform Logo — flat/gradient background, centered logo (width-only resize, vertical-offset-only positioning — no bounding-box concept), optional text/border. It shares only the generic low-level effect helpers (matte/fade/vignette/grain) with Uniform Logo, not its full option surface.

See [COLLECTIONS_AND_POSTERS.md](docs/COLLECTIONS_AND_POSTERS.md) for the two creators (Simposter Creator vs. Kometa Creator) and how they differ from a UX standpoint.

---

## How Overlays Get Applied

Overlays are the badge system (resolution, studio, streaming platform, etc.). They run **after** the base poster is composed, for the Uniform Logo template only — Kometa/collection posters have no badge metadata to apply.

```
Base poster render (matte + fade + vignette + logo)
  ↓
Overlay pass (universal.py)
```

**Step by step in `backend/templates/universal.py`:**

1. **Load overlay config(s)** — reads from DB using `overlay_config_ids` (and `overlay_config_ids_below`, for elements placed under the logo/text instead of over it) from the preset

2. **Pre-pass** (resolves dynamic fields before the element loop):
   - If any element is `studio_badge` + `tmdb_id` available → calls `get_studio_name()` + `get_studio_company_id()` → injects `metadata["studio"]` / `metadata["studio_company_id"]`
   - If any element is `streaming_platform_badge` → calls `get_watch_providers(tmdb_id, media_type, region)` → picks highest-priority `flatrate` provider → injects `metadata["streaming_platform"]`

3. **Element loop** — for each element in the config:
   - Check `show_if_label` / `hide_if_label` against Plex labels → skip if condition not met
   - Get the metadata value for this element type (e.g. `metadata["video_resolution"]` → `"4k"`)
   - Look up `badge_modes[value]` — what should happen for this specific value?
     - `"none"` → skip, render nothing
     - `"text"` → draw text directly onto poster with configured font/color/size
     - `"image"` → composite a user-uploaded PNG from the `overlay_assets` DB table
     - `"asset"` → call `get_asset_url(slug, company_id)` → fetch PNG from the simposter-assets GitHub repo → composite it
   - Position the badge at `(position_x * poster_width, position_y * poster_height)`

4. **Overlay cache** — the base template effects (matte/fade/top-matte/top-fade/vignette layers) are cached as a PNG per template/preset. On cache hit, the base render is skipped and only the dynamic parts (logo, badges) are recomposed. This is what gives batch mode its 3-5x speedup over the manual editor's uncached render.

---

## The Fallback System

When a movie/show has no logo available:

- **Manual editor**: `skip_fallback=True` → renders without a logo (blank logo area), preserves your selected preset exactly
- **Batch / webhook / scheduled**: fallback IS applied
  - Checks `fallbackLogoAction` in the preset (`"continue"`, `"template"`, or `"skip"`)
  - If `"template"` → switches to the configured fallback template/preset (e.g. a text-only preset that renders the title instead of a logo)
  - The fallback preset's full options override the current ones — so the text overlay, font, etc. from the fallback preset all take effect
  - The render is also flagged `needs_retry` so it lands in the retry queue instead of being treated as a final, ideal result

---

## Summary

| Trigger | Fallback? | Overlay cache? | Output | History source |
|---|---|---|---|---|
| Manual editor preview | No | No | base64 preview | — |
| Manual save/send | No | No | disk + Plex | `manual` |
| Batch render | Yes | Yes | disk + Plex | `batch` |
| Webhook (Radarr/Sonarr/Tautulli) | Yes | Yes | Plex | `webhook` |
| Scheduled scan | Yes | Yes | Plex | `auto_generate` |
| Retry queue (auto or manual) | Yes | Yes | Plex, only if ideal | `auto_generate` |

---

**Last Updated**: 2026-08-31
**Current Version**: v1.6.79
