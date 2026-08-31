# Collections & Poster Guide

How templates, presets, logos, and badges fit together, how batch processing works, and how Plex Collection posters work specifically (they're a different beast — no TMDb/TVDB entry, no built-in artwork source). If you haven't installed Simposter yet, start with [GETTING_STARTED.md](GETTING_STARTED.md).

---

## Templates & Presets

**Templates** define the rendering logic. There are two:
- **Uniform Logo** — the main template for movies and TV shows: places the clearlogo inside a configurable bounding box zone, with matte, fade, top-matte/top-fade, vignette, grain, and wash effects, plus optional overlay badges.
- **Kometa** — for Collections specifically (see below): flat/gradient background, centered logo, optional text and border. Deliberately simpler — collections have no resolution/codec/edition metadata to badge.

**Presets** store a named snapshot of template settings — logo zone, effect intensities, text overlays (with `{title}`/`{year}`/`{season}` variables), linked overlay badge configuration, and fallback rules (switch templates/presets when a logo or textless poster is missing). Presets can be exported and imported as JSON, and shared between installs. A small set of starter presets ships with Simposter (a few Uniform Logo looks plus Kometa Creator presets) — imported automatically at the end of the setup wizard, or pull them in any time via **Import Simposter defaults** in Template Manager's Import/Export section.

<!-- SCREENSHOT SUGGESTION: Template Manager page showing a preset list on the left and
     the options panel on the right, with logo zone and effects visible -->

---

## Logo System

Logos are sourced from TMDb, Fanart.tv, and TVDB, then merged with priority/fallback logic.

| Mode | Behaviour |
|------|-----------|
| Original | Logo's real colors, untouched |
| Match | Tints logo to match the poster's dominant color |
| Hex | Custom hex color (best with white/monochrome logos) |
| None | No logo rendered (e.g. for a text-only season poster) |

| Preference | Picks |
|------------|-------|
| White | Lowest saturation logo |
| Color | Highest saturation logo |
| First | First available |

**Fallback options when no logo is found:**
- Continue without logo
- Skip rendering entirely
- Switch to a different template/preset (e.g. a text-only fallback)

A logo drop shadow (Photoshop-style — angle, distance, size, opacity) is also available in the Logo section for the Uniform Logo template.

<!-- SCREENSHOT SUGGESTION: Side-by-side showing the same poster with white logo, color logo,
     and the hex-tinted variant -->

---

## Overlay Badges

Badges pull live metadata from Plex (resolution, codec, audio channels, edition title) or TMDb (studio, streaming platform) and render on top of the poster:

- **Video** — Resolution (4K, 1080p, 720p) and codec (HEVC, AV1, H.264)
- **Audio** — Codec (Atmos, DTS-X, TrueHD), channels, language
- **Edition** — Theatrical, Extended, Director's Cut, IMAX, Unrated
- **Studio / Streaming platform** — Auto-detected
- **Custom images** — Your own badge assets (4K logo, Dolby Vision seal, etc.)
- **Text labels** — Custom text with full font/size/color control
- **Full-cover images** — An image that stretches to fill the whole canvas, placed below or above the logo/text

Each badge value can be individually set to **None**, **Text**, or **Image** mode — so you can show 4K as a badge image but render Dolby Atmos as text, for example. Every overlay element can also be placed **below** the logo/text instead of the default above.

Badge visibility can be controlled with Plex labels: `show_if_label` / `hide_if_label`.

<!-- SCREENSHOT SUGGESTION: Overlay Config Manager showing a configured badge set on the left
     and a rendered poster preview with badges visible on the right -->

---

## Collections

Plex Collections don't have their own TMDb/TVDB entry — there's no built-in metadata match, and critically, **no built-in logo source at all**. Selecting a collection opens a picker between two creators:

### Simposter Creator
The same manual editor used for movies/TV, made collection-aware — upload your own poster/logo, or let it pull one in automatically (see Fanart.tv below). Good if you want full manual control per collection.

### Kometa Creator
A dedicated creator modeled on the Kometa community's poster conventions (flat color or a live-referenced background texture, a 5-style gradient dropdown, centered logo, text, border) — pulls its background textures and a categorized logo library (aspect ratio, award, franchise, genre, streaming platform, studio, etc.) live from the [Kometa-Team/Defaults-Image-Creation](https://github.com/Kometa-Team/Defaults-Image-Creation) repo, so new textures/logos there show up automatically with no update needed on your end.

Both creators support Save Location and Send-to-Plex, same as movies/TV.

### Fanart.tv and Collections

This is the one non-obvious part: TMDb has **no artwork endpoint for Collections at all** — but Fanart.tv's contributor community tags franchise-wide logos under the TMDb collection's own ID (inside its regular movie-artwork namespace). Both creators fetch this automatically. **Without a Fanart.tv API key, Collection posters have no automatic logo source** — you'd be uploading every collection logo by hand. Set one in Settings → General or during onboarding; it's free at [fanart.tv/get-an-api-key](https://fanart.tv/get-an-api-key/).

For collections Fanart has no art for (studio/curated/genre collections with no single representative franchise, e.g. "Christmas Movies"), the Simposter Creator's Logo section has an **"Import Logo From Movie"** picker — pulls in a member movie's own logo instead.

---

## Batch Processing

1. Go to **Batch Edit** (Movies or TV)
2. Select items — search, label filters, or select all
3. Choose template + preset
4. **Preview** — step through selected items to spot-check renders before committing
5. Set labels to remove (optional)
6. Run the batch — progress tracked live, results summary shown when complete

If Settings → Automation's **Label to Add After Sending** is set, every successfully-sent item in the batch gets tagged with it too — that's a global setting, not something you configure per batch run.

<!-- SCREENSHOT SUGGESTION: Batch Edit page with several items selected (checkboxes visible)
     and the batch results panel open at the bottom showing succeeded/fallback counts -->

Batch rendering uses the **overlay cache** (pre-rendered effect layers) for a 3-5x speedup over a from-scratch render, and runs multiple items concurrently — see the concurrency tip in [Getting Started → Settings Reference](GETTING_STARTED.md#settings-reference) if a batch feels slow.

---

## Smart Retry Queue

When a poster is generated via batch, webhook, or auto-scan and the ideal template conditions aren't met (no clearlogo found, or no textless poster available), Simposter adds the item to a retry queue instead of leaving a compromise poster in place forever. A background job periodically re-attempts it and only re-sends to Plex once the ideal result is actually achieved — a retry that still doesn't meet spec updates the attempt count and leaves it queued, it never re-sends a worse result on top of nothing changing.

- **Toggle** on/off in Settings → Automation
- **Retry interval** — configurable in hours
- **Max attempts** — 0 = unlimited, or set a cap
- **Manual override** — sending a poster manually removes it from the queue immediately

Visible in **History → Retry Queue tab**, with per-item reason badges (*No Logo*, *Poster Fallback*, or *Both*), attempt count, and per-item **Retry Now**/**Dismiss** actions.

<!-- SCREENSHOT SUGGESTION: History page with the Retry Queue tab active, showing a handful
     of items with their reason badges and action buttons -->

---

## History

Every poster generation is logged in the **History** tab:
- Timestamp, template, preset, source (manual / batch / webhook / auto-generate)
- Whether a fallback template was used
- Hover "View" to preview the poster thumbnail
- Filter by library, template, action

![History](https://github.com/user-attachments/assets/2e7b7b23-770e-463e-91e6-62f0d061fff1)

<!-- SCREENSHOT SUGGESTION: Replace the above with a shot showing both History and Retry Queue
     tabs — ideally with Retry Queue active and 2-3 items visible -->

---

## Tips

- **Textless posters** look best with matte and fade effects — filter for them in the poster picker
- **Save presets** before running a batch so you can reproduce the same look later
- **Overlay cache** gives the biggest batch speed boost — keep it on (Settings → Performance)
- **Concurrent Rendering** can go much higher than you'd expect (up to 10) — see the tip in [Getting Started](GETTING_STARTED.md#settings-reference)
- **Retry queue** means a missing logo today won't be missing forever — Fanart.tv gets new logos regularly
- **A Fanart.tv key matters more than it looks like** if you make Collection posters — it's the only automatic logo source for them
- **Check logs** in Settings → Logs to diagnose webhook or API key issues — every send/batch item now logs its name and how long it took, not just an internal ID
