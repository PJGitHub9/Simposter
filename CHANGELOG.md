# Changelog

## v1.6.17 (2026-07-31)
### Bug Fixes
- **Uploading a custom poster (or a custom background from the editor) failed with `API preview failed (400): Private/internal network URLs are not allowed for this host`**: the upload endpoint (`POST /api/upload/background`) serves files back from `GET /api/uploaded/{filename}`, but the SSRF allowlist that grants an exception for the app's own known-safe local endpoints still listed a stale `/uploads/` path that has never actually existed as a route — so as soon as the frontend built the full URL (`http://<your-host>:8003/api/uploaded/...`) and the backend tried to fetch it for preview/save/send, it got flagged as an unrecognized private-network host and rejected. This affected every self-hosted deployment, since the app is always reached over a LAN/localhost address. Allowlist corrected to the real `/api/uploaded/` path — uploaded posters and backgrounds now preview, save, and send normally again.
### Documentation
- **README Quick Start rewritten**: previously showed `docker run ... simposter:latest` and a Docker Compose example with `image: simposter:latest` as the primary paths — both implied there's a published image to pull, but Simposter has never been published to a registry; the shipped `docker-compose.yml` builds locally (`build: .`). Quick Start now leads with `docker-compose up -d --build` (matches the shipped compose file exactly), explains updating is `git pull` + rebuild, and moves the `docker run` + build-script flow to a clearly-labeled alternative for people managing the container manually. Settings tab table also updated to match the v1.6.13 Output/Automation reorg (was still describing the old Save Locations/Performance split).
- **`build-docker.sh` fixed to match `build-docker.bat`**: the Linux/Mac script only ever passed `--build-arg GIT_BRANCH=...`, which the Dockerfile doesn't declare or use (branch is auto-detected via `git` inside the build) — and never passed `DOCKER_TAG`, so Mac/Linux-built images always reported `docker_tag: unknown` and silently never showed the "unmaintained tag" warning banner that Windows builds (via the `.bat` script) do. Now accepts the same optional tag argument and passes `DOCKER_TAG` the same way.

## v1.6.15 (2026-07-27)
### Bug Fixes
- **Library scan progress looked stuck at 0 for movie libraries**: `POST /api/scan-library` only updated its progress counter in the final "assemble the cache" loop — but that loop runs after labels, posters, and logos have already been fetched (sequentially for labels, in parallel via a thread pool for posters/logos), which is where nearly all of a scan's time is actually spent. The progress counter (and the polling endpoint the UI reads every few seconds) never moved during that real work, so the UI sat at "0/N" for the whole scan and then jumped to done almost instantly once the slow phase finished. Progress now updates live as each label fetch and each poster/logo download completes, so the counter climbs smoothly through the whole scan instead of appearing frozen. TV show scanning was unaffected (it was already sequential and already reported per-item progress).

## v1.6.14 (2026-07-23)
### Bug Fixes
- **Local Assets was slow to refresh**: `GET /api/local-assets` re-opened and re-parsed every single saved poster file on every single request (list or resend) — on network-backed storage (NFS/SMB volumes, common for these self-hosted setups) this made "Refresh" visibly slow, worse the more posters you have saved. Metadata reads are now cached in memory per file, keyed by the file's modified time and size, so unchanged files are served instantly on repeat requests instead of being re-opened — automatically invalidated the moment a file actually changes (re-saved, edited, replaced). In local testing this cut a 20-file repeat listing from ~290ms to ~10ms; the effect scales with library size.

## v1.6.13 (2026-07-23)
### Improvements
- **Settings reorganized**: related settings that had drifted across tabs are now grouped together. New **Output** tab combines Save Locations with Image Quality (both are "what gets written to disk" concerns). New **Automation** tab combines the Webhook URL Generator (previously in Libraries) with Automatic Poster Generation (previously in Performance) — everything about webhooks and auto-generation now lives in one place instead of three. Performance is trimmed down to rendering concurrency, memory, API rate limits, and cache management. No settings were removed or reset — this only changes which tab each control lives in.
- Fixed a small existing bug where the "save to asset folder on send" toggle (added in v1.6.12) wasn't included in the Output tab's unsaved-changes detection — changing only that field wouldn't highlight the tab as dirty (the Save button still worked correctly).

## v1.6.12 (2026-07-23)
### New Features
- **Kometa-compatible save presets**: Settings → Save Locations now has four quick-select presets — Default, Flat (Kometa), Asset folders (Kometa), and Custom. The two Kometa presets produce `Movie Name (Year)/poster.ext` and `Show Name (Year)/SeasonNN.ext`, matching Kometa's asset-folder convention exactly, via a new `{filename}` template token. Custom keeps full manual control of the template strings.
- **Save to asset folder on send**: new toggle (Settings → Save Locations) that makes "Send to Plex" also write the render to your configured save-location template, instead of (or in addition to, previously) an internal-only cache — so tools like Kometa can pick up the file, and "save now, push to Plex later with something else" becomes a real workflow. When enabled, the asset-folder file becomes the resend source directly.
- **Resend confirmation preview**: clicking resend on a movie/TV card now shows a small popup comparing the saved poster against what's currently live in Plex before anything is sent, instead of sending immediately.
- **Bulk resend from Local Assets**: Local Assets now supports selecting multiple saved posters (checkbox per card, "select all resendable") and resending them to Plex in one action, with a per-item success/skipped/failed summary. Only files saved after this release carry the Plex reference needed to resend — older files are reported as skipped rather than guessed at.

### Improvements
- **Consolidated save-path resolution**: the save-location template logic that had drifted into four separate, slightly different copies (manual save, movie batch, TV batch, Local Assets browsing) is now one shared resolver. Along the way this fixed: TV batch saves silently missing the `/output`↔`/config` path remapping and the path-traversal safety check that manual save already had; Local Assets browsing/deleting from a stale legacy settings field even when the newer per-media-type fields were set; and `saveBatchInSubfolder` not working for TV batches and not actually being timestamped despite the UI saying so (now genuinely one shared `batch-<timestamp>` folder per run, movies and TV alike).
- **Fixed TV save-path ordering bug**: the default TV template produced `"Show - series (2008).jpg"` instead of the documented `"Show (2008) - series.jpg"` because the season/series suffix was baked into the `{title}` substitution. Existing templates are unaffected (still resolve exactly as before); the new `{filename}` token-based presets don't have this issue.
- **JPEG local assets for TV/season batch saves now carry embedded metadata**: previously only PNG output embedded library/title metadata for this render path — JPEG (the default output format) silently saved with none, which also broke Local Assets library filtering for those files.

## v1.6.11 (2026-07-14)
### Bug Fixes
- **Numeric-looking secret values broke settings entirely**: `get_ui_settings()` guessed a stored value's type from its shape (all-digits → `int`), which is correct for genuine numeric settings but wrong for string fields that happen to be all-digits — e.g. a webhook secret of `"123"`. That silently turned it into an `int`, which then failed `UISettings` validation on every single settings read, breaking any endpoint that touches settings, including the scheduler (`POST /api/scheduler/library-scan` would 500). Known string-only fields (Plex token, TMDb/TVDB/Fanart keys, webhook secret, webhook labels, Discord webhook URL) are now always read back as strings regardless of their content. Fixes itself on restart — no manual database edit needed.
- **Webhook secret setup instructions were wrong for Radarr/Sonarr**: the in-app help text (added in v1.6.10) suggested adding the secret as a custom header in Radarr/Sonarr, but their webhook connection UI has no custom-header field — only URL, method, and optional basic auth. Corrected to point at the actually-supported method: append `?secret=your-secret` (or `&secret=...` if the URL already has a `?`) to the webhook URL configured in each app.

## v1.6.10 (2026-07-14)
### Security
- **SSRF hardening**: URL-fetching endpoints (poster/logo render pipeline, badge image proxy, Plex logo upload) now resolve the target host and block private/internal/link-local ranges — including the `169.254.169.254`-style cloud metadata range, which was previously unrestricted everywhere. A private-network exception remains for the configured Plex server and the app's own local-asset paths; the image-proxy endpoint (which reflects fetched bytes back to the caller) allows no private-network exception at all. Closes a bypass where a crafted URL could smuggle an allowed substring (e.g. `/library/metadata/`) past the old regex-based check while actually pointing at an arbitrary internal host.
- **Path traversal fix in `/api/save`**: the save-path sanitizer allow-listed `.` and `/`, so a crafted movie title could escape the intended output directory once `..` components were resolved by the filesystem. The final resolved path is now required to stay within the configured output/config roots, matching the containment check already used by local-assets and backup file serving.
- **Webhook shared secret is now enforced**: `WEBHOOK_SECRET` existed as a config field but was never actually checked by the Radarr/Sonarr/Tautulli webhook endpoints. It's now enforced when set (via `X-Webhook-Secret` header or `?secret=` query param), configurable from Settings → Performance → Automatic Poster Generation → Webhook Secret. Off by default to preserve existing webhook configs.
- **Rate limiting enabled**: the per-endpoint sliding-window rate limiter existed but was commented out. Now active (e.g. batch render initiation: 5/min, webhooks: 10/min, preview: 120/min). Frequently-polled status endpoints (`/api/batch-progress`, `/api/scan-progress` — polled every 200ms/3s while a job runs) are exempted; also fixed a matching bug where those same endpoints would have inherited the much stricter `/api/batch` limit due to a shared text prefix (`batch-progress` starts with `batch`), which would have broken the live batch progress bar within a couple seconds of starting any batch job.
- **CORS**: disabled `allow_credentials` on the wildcard-origin CORS policy — removes a dangerous wildcard-origin-plus-credentials combination flagged by security review. No functional change since the app doesn't use cookie/session auth.
- **Secrets no longer returned in plaintext**: `GET /api/ui-settings` previously returned the raw Plex token and TMDb/TVDB/Fanart API keys to any caller. It now returns a masked placeholder, and saving only overwrites a credential field if it was actually changed (the "Test API Key" and "Test Plex Connection" buttons resolve the placeholder back to the real stored key server-side). `GET /api/database/export` now excludes credentials by default, with an explicit "Include API keys and tokens" checkbox in Settings → Advanced for full-migration backups. `test-tmdb`/`test-tvdb` moved from GET query-parameter to POST body so keys stop appearing in access logs (matching the existing `test-fanart` pattern).
- Note: Simposter still has no authentication gate on the API itself — this release closes concrete SSRF/traversal/secret-exposure/webhook-trust bugs, but anyone who can reach the configured port still has full read/write access to the app. Keep it behind your own network boundary (VPN, reverse-proxy auth, firewall) if it's reachable beyond a trusted LAN.

## v1.6.09 (2026-07-08)
### Improvements
- **Retry queue only sends when the poster is actually ready**: Previously, every retry attempt re-uploaded a poster to Plex regardless of whether the new render still needed a fallback (missing logo, poster fallback, etc.) — so items stuck in the queue got re-sent unnecessarily on every pass. The retry job now renders and checks whether the ideal template conditions are met *before* uploading, and only sends to Plex if they are. Items that still don't meet spec are left pending for the next retry without an upload. For TV shows this is evaluated per season/series poster, so a show with some seasons ready and some not will only send the ready ones.

## v1.6.08 (2026-07-06)
### New Features
- **Resend cached poster to Plex**: Hover any movie or TV show card to reveal a send button (bottom-left of the poster). Movies resend immediately; TV shows prompt whether to include cached season posters. No re-render — uses the previously saved render.
- **"Cached only" filter**: New toggle button in the Movies and TV Shows toolbars filters the grid to items with a locally cached render. Shows a live count while active and stacks with the existing label and search filters.

### Bug Fixes
- **Resend removes labels**: Cached-poster resend now removes configured auto-labels (e.g. Simposter, Overlay) from Plex and updates the label cache, matching the full render pipeline. Applies to card resend, webhook resend, scheduler resend, and auto-generate resend paths.
- **Resend refreshes thumbnail**: After a successful resend the grid card fetches the updated poster thumbnail from Plex automatically.

## v1.6.07 (2026-06-30)
### Bug Fixes
- **Retry queue did not remove labels on success**: When the retry job resolved an item (e.g. a logo became available after several attempts), it uploaded the poster to Plex but never removed the configured labels. Labels (`Simposter`, `Overlay`, etc.) are now removed and the label cache is updated, matching the behaviour of auto-generate and webhook renders.
- **Resend mode did not remove labels**: When `existingContentMode=resend` was active and a cached poster was re-uploaded, the webhook handler, scheduled scan movie path, and scheduled scan TV path all returned/continued before the label removal block could run. All three paths now remove labels after a successful resend.

## v1.6.06 (2026-06-26)
### New Features
- **Preset duplication**: Click the ⎘ button on any preset card to create a copy with all options preserved.
- **Preset rename**: Click the pencil icon on a preset card to rename it inline. The internal ID never changes so history records, webhook configs, and settings stay linked correctly. Rename is instant (optimistic update).
- **History search box**: Filter the history table by title in real time without triggering a new API request.
- **Retry queue thumbnail**: Hover or click View on any retry queue item to preview the current Plex poster for that title.
- **Compact preset export**: "Copy compact" button in Template Manager → Import/Export copies a minified preset JSON to the clipboard with all default values stripped (typically 80–90% smaller). Designed for sharing presets with others.
- **Preset name in History/Retry Queue**: The Preset column now shows the display name instead of the internal ID. Renames are reflected in past records.

### Improvements
- **Export never includes internal IDs**: Both regular and compact exports now omit the internal preset ID entirely. On import, Simposter always generates a fresh ID from the preset name — imported presets can never conflict with or silently overwrite existing ones.
- **History resolves preset names at render time**: Fetches the current presets list on load and maps IDs to display names, so renamed presets show the new name everywhere.

## v1.6.05 (2026-06-24)
### New Features
- **Clickable titles in History and Retry Queue**: Movie and TV show titles are now links — clicking one navigates directly to that item's editor, bypassing the library grid search entirely.

### Bug Fixes
- **Retry queue not populated after logo fallback**: When auto-generate or a scheduled scan found no logo and switched to a fallback preset, the item was not enqueued for retry. Fixed in both movie and TV render paths.

## v1.6.02 (2026-06-22)
### Bug Fixes
- **Retry queue not populated after logo fallback**: When auto-generate or a scheduled scan found no logo and switched to a fallback preset (e.g. `stock-poster`), the fallback preset's `logo_mode: none` overwrote the original mode — causing `logo_was_expected` to evaluate `False` and `needs_retry` to remain `False`. Items using a logo or poster fallback are now correctly enqueued for retry.

## v1.6.01 (2026-06-19)
### Bug Fixes
- **Timezone blank after onboarding**: Settings timezone dropdown now includes the full timezone list from the onboarding wizard, and any saved or browser-detected timezone not in the standard list is prepended automatically so the select never appears blank
- **Kometa label not auto-applied**: Default Labels to Remove was saved with a `"default"` key instead of per-library IDs — fixed to use actual library IDs so the "Overlay" label appears correctly in Settings after setup
- **Scheduled scan no libraries selected**: Onboarding now saves all configured library IDs into `scheduler.libraryIds` so the scan schedule covers all selected libraries from the start
- **Retry not enabled by default**: New installs now have "Retry Until Template Is Met" enabled by default (set during onboarding's settings save)

## v1.6 (2026-06-19)
### New Features
- **Onboarding wizard**: First-run setup modal walks new users through Plex connection, library selection, API keys (TMDb/TVDb/Fanart with inline test buttons), automation preferences (Kometa compatibility, scan schedule, timezone, label tracking), performance defaults (concurrent renders, output format/quality), and Apprise notifications — all in one guided flow
  - Library scan starts immediately after the libraries step so content is ready by the time setup finishes
  - Default preset (Uniformlogo) is automatically imported on completion — no manual step needed
  - Existing users are detected via DB flag and skip the wizard entirely
- **Quick start guide**: Post-onboarding feature overview showing all key areas of the app (Libraries, Batch Edit, Template Manager, Overlay Manager, Local Assets, Backup & Restore) as a scannable card grid

## v1.5.998 (2026-06-18)
### Bug Fixes
- **existingContentMode not saving**: `AutomationSettings` Pydantic schema was missing `existingContentMode`, `retryUntilTemplateMet`, `retryIntervalHours`, and `retryMaxAttempts` fields. Pydantic silently stripped them on every POST, so the setting always reverted to `regenerate` after a page refresh.
- **Batch runs not enqueuing retries**: When a batch run used a fallback preset, the item was never added to the retry queue. Batch results are now evaluated for retry eligibility (matching webhook and auto-generate behaviour).
- **Resend not tracked in History**: Resent posters were logged to the application log file but never written to the history database. They now appear in History with a "Resent to Plex" action badge and hover thumbnail preview, and can be filtered via the Action dropdown.

## v1.5.997 (2026-06-17)
### New Features
- **Retry Until Template Is Met**: New automation setting that queues items for automatic retry when the ideal poster can't be generated (no logo found, or no textless poster available). Items retry on a configurable interval until the ideal poster is produced, then are saved, uploaded to Plex, and removed from the queue. Toggle, retry interval (hours), and max attempts (0 = unlimited) configurable in Settings → Performance.
- **Retry Queue in History**: New "Retry Queue" tab in the History page shows all pending retries with reason, attempt count, last tried time, and per-item Retry Now / Dismiss actions.
- **Manual send clears retry queue**: Sending a poster manually (from the editor, batch, or via direct Plex send) automatically removes the item from the retry queue — the manual poster takes precedence.
### Diagnostics
- Added `[AUTO_GEN] sendLogosToPlex=` log line on each auto-generate run to help diagnose why logos may not be sent with auto-generated posters.
- Added `[BATCH] Logo upload check:` info log in both movie and TV logo upload paths to surface whether `send_logos_to_plex` or `logo_url` is the failing condition.

## v1.5.996 (2026-06-11)
### New Features
- **Resend existing poster setting**: New automation setting "Existing Content — Poster Behaviour" (Settings → Performance → Automatic Poster Generation)
  - `Regenerate` (default): always creates a new poster — existing behaviour unchanged
  - `Resend`: when a webhook or scan fires for a title that already has a Simposter-generated poster, the cached render is pushed straight back to Plex without regenerating. Protects manually tuned posters from being overwritten by future Radarr/Sonarr events.
- **Poster render cache**: Every poster sent to Plex (manual, batch, webhook, auto-scan) is now cached to `/config/cache/poster_renders/{rating_key}.jpg`. Cached in `/config/cache/` so clearing the cache directory gracefully falls back to full regeneration.

## v1.5.995 (2026-05-08)
### New Features
- **Logo send wired into all paths**: "Send logos to Plex by default" setting now applies to webhook triggers and automatic scan sends, not just manual/batch
- **Current Plex Logo in editors**: Both movie and TV show manual editors now show the current Plex clearlogo below the poster preview, with a refresh button
- **Logos page improvements**: Sort (title A–Z, title Z–A, year), filter (all / has logo / missing), and search box

### Bug Fixes
- **Custom text font rendering**: Font picker now shows actually available fonts; Liberation Sans/Serif/Mono and DejaVu fonts are bundled in Docker so selections render correctly

## v1.5.991 (2026-05-01)
### New Features
- **Logo Editor**: New dedicated Logos page (Movies & TV Shows) showing all library clearlogos in a grid
  - Cards display the cached clearlogo, or a placeholder for items missing a logo
  - Toggle to show/hide items with missing logos
  - Click any card to open the Logo Editor — browse TMDb/Fanart.tv logos or upload a custom PNG/JPG
  - Send selected or uploaded logo directly to Plex's clearLogo slot
  - UI updates immediately after send (no full page reload required)
- **Send Logo to Plex — Manual Editor**: Both movie and TV show editors now have a standalone **Send Logo** button
  - Sends the currently selected logo to Plex independently of poster send
  - Separate loading/success state from the poster send flow
- **Send Logo with Poster**: New "Send logo" checkbox modifier in both manual editors
  - When checked, the selected logo is sent to Plex automatically after each poster send
- **Batch Logo Send**: "Send logos to Plex" checkbox in both Batch Edit views
  - Sends each item's rendered logo to Plex alongside its poster in the same batch run
- **Global Logo Default**: New "Send logos to Plex by default" toggle in Settings → Libraries
  - Pre-populates the batch and manual editor checkboxes on load

### Bug Fixes
- **Movie logos not showing in Logos view**: FastAPI `response_model` was stripping `logo_url` from movie responses because the `Movie` schema was missing the field
- **Plex clearlogo fetch**: Fixed `fetch_and_cache_logo` which was using XML parsing on a JSON endpoint — now correctly requests `Accept: application/json` and parses `MediaContainer.Image[]`
- **Logo cache stale after send**: After uploading a logo to Plex, the uploaded bytes are now written directly to the local cache file so the UI reflects the new logo immediately (no delay waiting for Plex to process the upload)
- **Logo Editor modal positioning**: Fixed modal appearing halfway down the page — wrapped in `<Teleport to="body">` to escape ancestor CSS transforms

## v1.5.72 (2026-03-18)
### New Features
- **Apprise Notifications**: Send poster generation events to 70+ services (Slack, Telegram, Pushover, Gotify, ntfy, email, and more) via Apprise URL schemes
  - Configured in Settings → Notifications alongside existing Discord integration
  - Multiple URLs supported — all services notified simultaneously
  - Per-library and per-event-type filtering (batch, manual, webhook, auto-generate)
  - Test button fires to all configured URLs
  - Discord and Apprise fire independently — both can be enabled at the same time
### Bug Fixes
- **Text Shadow Default**: "Enable Text Shadow" no longer defaults to on when enabling the custom text overlay

## v1.5.71 (2026-03-14)
### Bug Fixes
- **Manual Editor Fallback**: Movie editor and Template Manager previews no longer apply logo/poster fallback logic — the selected preset always renders as-is, even when no logo is available
  - Previously, fallback could silently switch to an alternate preset (e.g. a text-only fallback), overwriting the user's selected options and rendering the wrong result
  - Added `skip_fallback` flag to manual editor preview requests
- **Text Shadow Default**: "Enable Text Shadow" no longer turns on by default when enabling the text overlay

## v1.5.7 (2026-03-13)
### New Features
- **Streaming Platform Badge**: New overlay element type that auto-detects the streaming platform from TMDb watch providers
  - Supports Netflix, Prime Video, Disney+, Max, Hulu, Apple TV+, Paramount+, Peacock, Tubi, Crunchyroll, Shudder, MUBI
  - Per-platform badge modes: None, Text, Image (Simposter Asset), or URL
  - Region selector on overlay config (US, GB, CA, AU, DE, FR, ES, IT, JP, KR, BR, MX)
  - Watch provider results cached in DB for 7 days to avoid redundant API calls
- **Studio Badge**: New overlay element type that shows the primary production studio / network
  - Auto-detected from TMDb production_companies (movies) or networks (TV shows)
  - Same per-value badge modes as streaming badge
- **Simposter Asset Badge Mode**: New `asset` mode for badge elements that pulls logos directly from the simposter-assets GitHub repo
  - Live `logos.json` index refreshed hourly with 60-second retry cooldown on failure
  - TMDb company ID column (`tmdb_production_company_id`) in logos.json for reliable studio matching regardless of name variations
  - Slug alias system: per-element mappings for edge cases where TMDb returns an unexpected company name
  - Thread-safe cache with double-checked locking to prevent race conditions during prewarm
- **Unmaintained Branch Warning**: Logo in the top-left turns amber/red and shows a pulsing warning badge when running a Docker tag that is not `latest` or `webui-overhaul-dev`
  - Docker tag is baked into `build-info.json` at build time via `--build-arg DOCKER_TAG=...`
  - Can also be set at runtime via `DOCKER_TAG` environment variable

### Improvements
- `/api/version-info` now includes `docker_tag` field
- Studio company ID cached alongside studio name so asset lookup by TMDb ID works immediately on subsequent renders
- Stale studio cache entries (pre-dating company ID tracking) are automatically re-fetched from TMDb on next render

## v1.5.51 (2026-03-01)
### Bug Fixes
- **Version API Docker Fix**: Fixed API crash in Docker containers due to incorrect subprocess exception handling
  - Changed `subprocess.SubprocessTimeoutExpired` to `subprocess.TimeoutExpired` (correct Python stdlib name)
- **Branch Detection in Containers**: Fixed git branch detection failing when `.git` directory is not present
  - Added build-time branch capture via Docker build args
  - Creates `build-info.json` file in image with git branch information
  - Backend now falls back to `build-info.json` when git commands fail
  - Added `build-docker.sh` and `build-docker.bat` scripts to automate branch capture

## v1.5.5 (2026-03-01)
### UI Improvements
- **Navigation Emoji Icons**: Added emojis to all page headings and navigation items for better visual distinction
  - Movies 🎬, TV Shows 📺, Batch Edit ✏️, Template Manager 🎨, Overlay Manager 📐
  - Local Assets 🗂️, History 📜, Logs 📝, Collections 📚, Settings ⚙️, Backup/Restore 💾
  - Removed duplicate SVG + emoji icons from sidebar (was rendering both)

### Overlay System Enhancements
- **Overlay Element Type Refactor**: Reorganized element types for clearer metadata organization
  - **New types**: `video_badge` (resolution, codec), `audio_badge` (codec, channels, language), `edition_badge` (theatrical, extended, etc.)
  - **Legacy support**: `resolution_badge` and `codec_badge` still work (aliased to new types)
  - **Removed from UI**: `label_badge` (still renders for backwards compatibility)
  - **Metadata field dropdowns**: Now restricted to relevant fields per badge type
    - Video badges: video_resolution, video_codec only
    - Audio badges: audio_codec, audio_channels, audio_language only
    - Edition badges: fixed to edition field (theatrical, extended, director's cut, unrated, imax)
  - **Case-insensitive label matching**: `show_if_label` and `hide_if_label` now case-insensitive
  - **Consolidated rendering**: Backend uses unified `_apply_metadata_badge` function for all badge types

### Technical Improvements
- Simplified overlay badge rendering pipeline with type-to-defaults mapping
- Canvas preview rendering now uses lookup table for badge colors (blue for video, purple for audio, amber for edition)
- Updated schema documentation with new element types

## v1.5.4 (2026-02-27)
### Bug Fixes
- **Fallback Settings Reset Fix**: Fixed fallback preset settings being reset to blank after v1.5.3 template consolidation
  - `fallbackPosterTemplate` and `fallbackLogoTemplate` references to removed 'default'/'universal' templates now automatically migrate to 'uniformlogo' on startup
  - Applies to both main preset options and season-specific options
- **Overlay badge rendering fixes**: Fixed multiple issues preventing overlay badges from appearing on posters
  - Fixed metadata not being injected when background URL was a direct TMDB link (rating_key now sent explicitly from frontend)
  - Fixed overlay badges not rendering in Send to Plex, Save, and Batch paths — all render paths now inject preset_id and Plex media metadata
  - Fixed resolution value mismatch: frontend badge values now match Plex's actual `videoResolution` format (e.g., `1080` instead of `1080p`)

### New Features
- **Overlay Config Manager**: Create reusable overlay templates with draggable elements (early testing)
  - Resolution badges, codec badges, custom images, text labels, and label badges
  - Overlay asset library — upload and manage badge images (4K, Atmos, etc.)
  - Live canvas preview with drag-to-position, poster search, and value switcher
  - Badge per-value mode selector: None (skip), Text (with custom display text and font settings), or Image (from asset library)
  - Percentage-based and pixel-based sizing for overlay elements
- **Dynamic Plex media metadata**: Overlay badges use real media info (resolution, codec, channels) fetched from Plex instead of hardcoded values
  - Media info is cached in the database for fast subsequent lookups
  - Cached automatically during library scans and label fetches

### Improvements
- Increased logo bounding box max height (thanks chadwpalm)
- Detailed overlay rendering logs for easier debugging

## v1.5.0 (2026-01-11)
### Major Features
- **Poster Generation History Tracking**: Complete audit log of all poster operations
  - New History page with filterable table view
  - Tracks manual and batch poster generations
  - Source column distinguishes between manual/batch operations
  - Color-coded badges (purple=batch, gray=manual)
  - Library-aware filtering with display name resolution
  - Template, preset, and action filtering capabilities
  - Records save path and timestamps for all operations

### Removed Features
- **Radarr/Sonarr Integration Polling** (removed in v1.6.0): Integration polling and webhooks have been removed
  - Simposter now focuses on core poster generation with scheduled Plex library scans
  - Use scheduled scans in Settings → Automation for keeping poster library in sync
  - Manual batch processing remains the primary workflow

- **Automatic Cache Cleanup** (`backend/database.py`):
  - Orphaned entries are automatically removed when items are deleted from Plex/Radarr/Sonarr
  - Cleans up database cache (`movie_cache`, `tv_cache`, `collection_cache`)
  - Removes orphaned label cache entries (`label_cache`, `tv_label_cache`)
  - Deletes orphaned poster files from disk
  - Triggered automatically during library scans and cache refreshes
  - Prevents stale data from showing in the UI

- **Database Schema Updates**:
  - Added `source` column to `poster_history` table (manual/batch/auto)
  - Automatic migration for existing databases
  - Integration settings stored in UI settings
  - Last poll timestamps stored per integration instance

- **History API** (`backend/api/history.py`):
  - Enhanced filtering by library, template, and action
  - Pagination support (up to 2000 records)
  - Status endpoint for bulk poster status queries

### Frontend Enhancements
- **UI Polish & Modern Interactions** (`frontend/src/assets/main.css`):
  - Smooth transitions on all interactive elements (buttons, inputs, panels)
  - Enhanced button hover effects with lift animations
  - Improved input focus states with accent-colored glow
  - Refined glass panel hover effects
  - Better disabled states with visual feedback
  - Card hover animations with shadow depth
  - Accessibility improvements (focus-visible outlines)
  - Custom scrollbar styling across all themes
  - Loading and badge pulse animations
  - Smooth scroll behavior

- **History View** (`frontend/src/views/HistoryView.vue`):
  - Full-featured history table with sortable columns
  - Multi-filter support (library, template, action)
  - Library name resolution from settings
  - Real-time refresh capability
  - Clear filters button
  - Results count display
  - Clock icon in sidebar navigation

### Technical Improvements
- Batch operations record source='batch' in history
- Manual operations record source='manual' (default)
- Settings store exports LibraryMapping type for reuse
- Router includes /history route with component import
- Sidebar icon system extended with clock SVG

## v1.4.9 (2026-01-07)
### Major Features
- **Separate Save Locations for Movies and TV Shows**: Enhanced local asset saving with media-type-specific save locations
  - Split single save location into `movieSaveLocation` and `tvShowSaveLocation` settings
  - Movie save location supports variables: `{library}`, `{title}`, `{year}`, `{key}`
  - TV show save location adds `{season}` variable for season-specific saving (formats as `s01`, `s02`, etc.)
  - Automatic cleanup of empty variables to prevent dangling punctuation in filenames
  - Library folder names now use display names instead of numeric IDs
  - Full backwards compatibility with legacy `saveLocation` field
  - Settings UI shows separate inputs with available variable hints

### Bug Fixes
- **TV Show Save to Disk**: Fixed critical issue where `/api/save` endpoint didn't support TV shows properly
  - Updated SaveRequest schema to include `season_index` and `is_tv` fields
  - `/api/save` now uses correct media type and passes season to path variables
  - `/api/save` now loads preset season_options for season-specific rendering (matching preview behavior)
  - Frontend render service updated to pass library_id and season_index
  - TV show editor builds season-specific options for each season (poster, logo, text overlay)
  - TV show editor correctly retrieves library_id from route and passes season index
  - Fixes "wrong library", "Season X.jpg" filename, and "all seasons same poster" issues

- **Library Cache Contamination (FIXED)**: Resolved persistent issue where movies/shows from one library appeared in another
  - Root cause: `hydratePostersFromSession()` was loading from hardcoded global cache key instead of library-specific keys
  - Removed composable's `hydratePostersFromSession` calls, using library-specific poster cache directly
  - Fixed poster hydration to only apply posters from the current library's cache

- **Library Parameter Loss**: Fixed critical bug where library parameter was removed from URL when applying filters/sorting
  - URL sync watcher now preserves the `library` query parameter
  - Prevents switching to "all libraries" view when changing sort order or filters
  - Applied to both MoviesView and TvShowsView

- **Save Location Settings Change Detection**: Fixed unsaved changes indicator not showing when editing save location text fields
  - Added proper event handlers to trigger change detection on input

### UX Improvements
- **Browser Navigation Support**: Added URL state management for filters, sorting, pagination, and edit mode
  - Browser back/forward buttons now work correctly when editing items
  - Filters, sort order, and page number preserved in URL
  - Edit mode includes item ID in URL (e.g., `?edit=12345&library=1`)
  - URL state restored when using browser navigation

- **Conditional Navigation**: Navigation sidebar now adapts to Plex configuration state
  - Only Settings shown when Plex not configured
  - Full navigation restored once Plex configured
  - Automatic redirect to Settings on fresh instances

### Technical Improvements
- Added comprehensive debug logging to track cache operations and library switches
- Added `library_id` field to Movie type definition
- Removed unused `hydratePostersFromSession` imports from both view components
- Settings page now checks Plex configuration before attempting to load labels
- Enhanced `resolve_library_label()` to load from database instead of settings module
- Updated `apply_save_location_variables()` with regex-based cleanup for empty variables
- Improved `get_save_location_template()` to accept media_type parameter
- Enhanced batch save logging with absolute paths for better file location visibility

## v1.4.8 (2026-01-06)
### Bug Fixes
- **Library Switching Cache Contamination**: Fixed critical issue where items from one library appeared in another
  - Deferred initial cache load until route is fully ready
  - Added immediate display clear when switching libraries (`movies.value = []`, `tvShows.value = []`)
  - Strengthened library ID validation to strictly filter by current library
  - Eliminated race conditions between cache loading and route resolution

- **Settings Labels Not Populating**: Fixed inconsistent label loading in Settings
  - Added loading state with spinner indicator
  - Made label fetching properly await completion before displaying
  - Added "Refresh Labels" button when no labels found
  - Better error logging and empty result caching
  - Shows clear "Loading labels..." state during fetch

### UX Improvements
- **Template Manager Fallback Clarity**: Improved wording and added visual fallback chain
  - Changed "If X logo missing" to "If X logo not found" for clarity
  - Added numbered fallback priority chain showing exact order of operations
  - Clarified that global white logo fallback applies between preset preference and preset fallback
  - Better explanation of when fallback settings apply (batch edit mode only)

### Performance & Reliability
- Strict library filtering prevents cross-contamination in multi-library setups
- Cached empty label results prevent repeated failed API calls
- Improved timing of cache operations for more reliable data display

## v1.4.7 (2026-01-06)
### Major Features
- **TV Show Seasons Support**: Enhanced TV show rendering with season-specific poster generation
  - Season suffixes in local asset filenames (e.g., `Show Name_s01.jpg` for Season 1)
  - Season metadata passed through rendering pipeline with proper schema validation
  - Settings checkbox for season-specific local asset saving
  - "Coming Soon" badge support for unreleased seasons via TVDB integration

- **Scheduled Library Scans**: Automatic cron-based library scanning to keep Simposter synced with Plex
  - Configure cron schedule in Settings (e.g., "0 2 * * *" for daily 2 AM scans)
  - Optional library-specific scans or scan all libraries
  - APScheduler background daemon with proper initialization and restoration
  - Schedule status and next run time visible in Settings
  - Comprehensive cron validation (supports wildcards, ranges, steps, lists)

### Performance Optimizations
- **Database Indexing**: Added 6 new database indexes for 5-10x faster queries
  - `idx_movie_cache_tmdb`, `idx_movie_cache_composite` (library + rating_key)
  - `idx_tv_cache_tmdb`, `idx_tv_cache_tvdb`, `idx_tv_cache_composite`
  - `idx_poster_history_template_preset` for faster history filtering

- **Smart SessionStorage Caching**: LRU eviction system prevents quota errors
  - 4MB cache limit with automatic eviction of least-recently-used items
  - Access time tracking for intelligent cache management
  - Graceful QuotaExceededError handling
  - Cache statistics API (`getCacheStats()`)
  - Integrated in SettingsView with plans for full rollout

- **Debounced Editor Saves**: 300ms debounce on localStorage writes
  - 60-80% reduction in storage operations during slider adjustments
  - Eliminates UI stuttering when dragging sliders
  - Applied to both MovieEditorPane and TvShowEditorPane

- **Memory Leak Fixes**: Eliminated interval/timer memory leaks
  - Fixed scanPoller leak in SettingsView (interval continued after navigation)
  - Added proper cleanup in `onBeforeUnmount` hooks

### API & Security
- **Enhanced Rate Limiting**: Added rate limits for scheduler endpoints
  - `/api/scheduler/*` limited to 10 req/60s
  - Updated API_SECURITY.md documentation with scheduler endpoints

- **Improved Error Handling**: More specific network error handling
  - Separate handlers for `ConnectionError`, `RequestException`, and `Timeout`
  - Better logging with stack traces for unexpected errors

- **Cron Expression Validation**: Comprehensive validation for scheduler
  - Validates individual fields (minute: 0-59, hour: 0-23, etc.)
  - Supports wildcards (*), ranges (1-5), steps (*/5), lists (1,3,5)
  - Clear error messages for invalid expressions

### Technical Improvements
- **Simplified Library ID Handling**: Reduced complexity in scheduler API
  - Single-line normalization instead of verbose type checking
  - Pydantic already ensures correct types

- **Settings Architecture**: Unified scheduler settings persistence
  - Scheduler settings integrated into main settings store
  - Proper change detection with unsaved changes indicator
  - Settings snapshot system tracks all scheduler fields

### Documentation
- **Updated README**: Performance & Caching section highlights all optimizations
  - Smart caching, indexed database, debounced saves, memory leak protection
  - Updated Performance tips section with new best practices

- **Architecture Documentation**: Added scheduler initialization flow
  - Scheduler startup process documented
  - API router descriptions for all scheduler endpoints

- **PRD Updates**: APScheduler added to tech stack and architecture diagrams

### Bug Fixes
- Scheduler settings now persist correctly across page refreshes
- Scheduler shows unsaved changes indicator when modified
- SessionStorage operations no longer throw uncaught errors
- Scan polling properly stops when navigating away from Settings

## v1.4.6
### Major Features
- **Overlay Caching for Fast Rendering**: Pre-generated template effect overlays (matte, fade, vignette, grain, wash) for rapid batch poster generation
  - Composites cached PNG overlays with posters instead of rendering effects from scratch
  - 3-5x speed improvement for `uniformlogo` templates with or without logos
  - Configurable via "Use Overlay Cache" toggle in Performance settings (enabled by default)
  - Full uniformlogo support: logo positioning, text overlays, and borders all work in fast path
  - Other templates fall back to full render when logos present (future enhancement)

### Performance
- **Logo Selection Optimization**: Drastically faster logo selection in preview and batch operations
  - Analyzes only top 6 logo candidates (sorted by size/source priority) instead of all logos
  - Uses TMDb thumbnail images (w300) instead of full-resolution downloads
  - Concurrent color analysis via ThreadPoolExecutor instead of serial processing
  - Batch logo selection now completes in seconds instead of 20+ seconds
  - Batch rendering speed improvements: 3-5x faster with overlay cache, 2-3x faster logo selection

### Improvements
- **Batch Edit Fallback Logic**: Batch now correctly re-selects posters/logos after applying template fallback (matches preview behavior)
  - Respects fallback template and preset options in correct order
  - Re-picks logo after fallback to ensure compatibility with new template
- **Settings Labels UI Consolidation**: Unified "Default Labels to Remove" section displays both movie and TV libraries with type badges
  - Type badges (Movies/TV) clearly distinguish library type
  - Single organized section instead of separate movie/TV sections
  - Labels auto-refresh after library scan without manual "Refresh Cache" click

### Technical
- Added `useOverlayCache` field to PerformanceSettings schema (default: true)
- New `generate_overlay()` function in `rendering.py` extracts effect pipeline
- Optimized `pick_logo()` and `analyze_logo_color()` with thumbnail-based concurrent analysis
- Preset save endpoint generates and caches overlay PNG automatically
- Batch rendering checks overlay cache before falling back to standard render

## v1.4.5
### Major Features
- **TV Show Library Support**: Full TV show library integration with TVDB as metadata source, poster rendering, and library management
- **TVDB Integration**: Added TVDB API client for TV show metadata, logos, and poster fetching with language preference support
- **Fanart.tv Logo Fallback**: Enhanced logo source selection with TMDB/Fanart priority modes and automatic fallback when logos are missing
- **Preset Fallback System**: Template/preset fallback logic for missing posters and logos (e.g., switch to text-based template when logo unavailable)

### Improvements
- **Cache Reliability**: Fixed stale poster cache on app startup after inactivity; movies now refresh properly without manual cache clear
- **Library Switching**: Improved library switching to prevent cross-library contamination; display clears immediately when changing libraries
- **Library ID Handling**: Fixed "default" library errors; backend now correctly handles empty/default library IDs
- **Preview Rendering**: Preview endpoint now respects fallback templates and preset options (text overlay, logo mode) matching batch behavior
- **Settings UI**: Reorganized performance/quality settings; concurrent rendering functional (JPEG quality setting currently unused)

### Testing & In Progress
- **Batch Edit**: Continued refinements and testing for bulk poster operations

## v1.4.4
- **Database Tweaks**: Optimized the SQLite settings/presets path (initial migration landed in 1.4.2) for smoother reads/writes.
- **Template Manager**: New UI to manage presets plus poster/logo fallback logic (currently in testing).
- **Fanart Integration**: Added Fanart.tv logo source option and merge/fallback behavior alongside TMDB logos.
- **Batch Edit History**: Recorded actions/history groundwork to surface within batch edit (iterating on UI merge next).
- **Settings UI Cleanup**: Reorganized sections, clearer controls, better state handling.
- **Logo Selection Tweaks**: Improved white-logo preference and selection heuristics for clearer marks.

## v1.4.3
- **Multiple Library Support**: Enhanced UI with separate movie libraries subsection in Settings, improved library mapping management
- **Scanning Improvements**: Added 10-second cooldown to prevent multiple scan button clicks, backend protection against duplicate simultaneous scans
- **Cache Management**: Added "Clear Backend Cache" button with proper scan state protection, improved cache clearing UX
- **Docker Environment**: Environment variables now copy to database on container startup for initial setup, users can modify via UI afterwards
- **Performance**: Bulk API optimization for movie labels (50% reduction in API calls), better session storage caching
- **UI Polish**: Reorganized Settings page structure, improved button disable states, better visual feedback during operations

## v1.4.2
- Added SQLite-backed cache for Plex movies (labels/tmdb/poster metadata) with new `/api/cache/*` endpoints and incremental updates from live calls.
- Improved concurrency by pooling Plex HTTP connections (faster label/poster fetches on unRAID).
- Batch edit tab updates and local asset tab improvements.
- Settings persistence now centralized in the SQL db (legacy JSON migrated automatically).
- Version badge bumped to v1.4.2.

## v1.4.1
- Added visible version badge (top nav and Settings) and centralized version constant.
- Fixed presets: text overlay state and fields now reset/apply correctly; reload pulls fresh values.
- Preview/batch rendering now merges preset options with live slider values so UI tweaks reflect in renders.
- Batch mode improvements: preview caching when cycling movies; status overlay while batch runs; saves honor `saveLocation` and optional batch subfolder.
- Save-to-disk fixes: paths mapped under `/config/output`, template filename respected, frontend shows saved path.
- Settings: new “save batch runs into subfolder” toggle; scan library overlay shows progress/items.
