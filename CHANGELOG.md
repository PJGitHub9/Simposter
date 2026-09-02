# Changelog

## v1.6.86 (2026-09-02)
### Bug Fixes
- **Webhook-triggered TV season renders could report "FAILED" in History even when nothing was actually wrong** — reproduced from a real production log: a Sonarr episode-import webhook for a season whose poster had *already been sent* correctly determined there was nothing to do ("Season poster already sent for X - Season N, skipping"), then crashed on its own final summary log line with `NameError: name '_show_start' is not defined`, which the webhook handler reported up as a failed action. Root cause: `_render_all_tv_seasons()` (`backend/api/batch.py`) referenced `_show_start` in its closing `logger.info(...)` call, but that variable is only ever defined inside a *different* function, `_process_single_tv_show()` — leftover from a refactor that split that function's logic out into helper functions (`_render_tv_series_poster()`, `_render_all_tv_seasons()`) without carrying the timer variable along. Any call into `_render_all_tv_seasons()` that reached its final log line hit this unconditionally; it only surfaced as a *user-visible* problem on the "already sent, skip everything" path specifically, since that's the one path with no earlier exception/return to short-circuit past the broken log line first.
- **Fix**: `_render_all_tv_seasons()` now sets its own `_seasons_start = time.time()` at the top and uses that in its closing log line, instead of reaching into a sibling function's local variable. Also removed the now-fully-dead `_show_start` from `_process_single_tv_show()` — confirmed via a full search of the function body that it was never actually read there either, since that function just tail-returns whatever `_render_all_tv_seasons()`/`_render_tv_series_poster()` produces rather than doing its own timing.
- **If you split a function into helpers, grep the original function's local variables for any that only make sense at the very end (timers, accumulators) and make sure they either move with the logic that uses them or get re-declared in the new function** — this is exactly the kind of gap a refactor leaves behind, and it can sit invisible until a specific, less-common code path exercises the exact line that references the now-out-of-scope variable.

## v1.6.85 (2026-09-01)
### Bug Fixes
- **A movie/show removed from Plex could retry forever in the background, generating a fresh "failed" History row every retry cycle indefinitely.** This was previously fixed once already (a `_plex_item_exists()` existence check in `_run_poster_retry()`, `backend/scheduler.py`), but the fix only ran inside the `except Exception as retry_err:` branch — i.e. only if the render call itself raised an exception up to the scheduler. The actual real-world failure mode ("No TMDb ID found," which is what happens when a Plex item's rating_key 404s) is caught *internally* by `_process_single_movie()`/`_process_single_tv_show()`'s own broad `try/except` and returned as a normal `{"status": "error", ...}` dict — it never raises past that point, so the existence check built to catch exactly this case was never reached for it. User-reported ("what are all these in the history?") after noticing a specific movie repeating in History every 6 hours; confirmed directly from `config/logs/simposter.log`: a real `404 Client Error: Not Found` from Plex, immediately followed by `No TMDb ID found`, immediately followed by `still pending ... will retry again` (never `Error retrying...`, the log line the existence check is gated behind) — at **attempt #72**, roughly 18 days of retrying a permanently-deleted item every 6 hours.
- **Fix**: added a second check for this in `_run_poster_retry()`, alongside the existing one — when the render result is a dict with `status: "error"` (a hard failure, not just "needs a better logo/poster match," which is expected and should keep retrying under "retry until template met"), the existence check now also runs there before falling back to "still pending." A `None` result from the existence check (network blip, timeout) still correctly leaves the item pending rather than abandoning it.
- **Immediate relief for anyone hitting this today, no code change needed**: History → Retry Queue has a per-item **Dismiss** button (already existed) — use it to remove a specific stuck entry right away rather than waiting for the fix to reach a running deployment.
- **If you add another place that decides whether a background job "gives up" based on a render result**, check whether that call's failure mode returns a normal-looking error dict instead of raising — an `except Exception` handler alone won't see it, exactly as this gap demonstrated.

## v1.6.84 (2026-09-01)
### Bug Fixes
- **The browser tab icon (and any other file dropped directly in `frontend/public/`) never loaded when running Simposter in Docker, despite working fine with `npm run dev` locally.** `backend/main.py`'s catch-all SPA route (`serve_spa()`, registered as `@app.get("/{full_path:path}")`) unconditionally returned `index.html` for every request that wasn't under the explicitly-mounted `/assets` path — including `/favicon.svg` and `/favicon.ico`. A browser request for the favicon got `index.html`'s HTML bytes back (with `Content-Type: text/html`) instead of the actual image, so it silently failed to render — no error, no 404, just no icon. This backend code only runs in the built/Docker app (`if (frontend_path / "index.html").exists()`); running the Vite dev server locally serves `frontend/public/*` directly and never touches this route at all, which is exactly why it "worked locally."
- **Fix**: `serve_spa()` now checks whether the requested path resolves to a real file under `frontend_path` first (resolved and verified to still be inside `frontend_path` — traversal attempts like `../../etc/passwd` fall through safely to the existing `index.html` fallback, not the requested file) and serves it directly if so; only a path with no matching file falls back to `index.html`, which is the correct behavior for genuine Vue Router routes (`/movies`, `/settings/output`, etc.). Verified against a simulated `dist/`-shaped directory: `favicon.svg`/`favicon.ico`/`assets/app.js` all now resolve to the real file, `/movies`/`/settings/output` still correctly fall back to `index.html`, and a traversal attempt is blocked.
- **If you add another file to `frontend/public/`** (a `robots.txt`, a `manifest.json`, etc.), this fix means it'll now be served correctly in Docker without needing its own dedicated backend route — the same `frontend_path`-relative file check picks it up automatically.

## v1.6.83 (2026-08-31)
### Bug Fixes
- **The browser tab icon (`favicon.svg`) showed up completely blank.** User-reported immediately after v1.6.82's fix added an embedded `<style>` block with an `@media (prefers-color-scheme: dark)` rule (to keep the sparkle accent visible against a light tab bar). A favicon is rendered through a separate, more restrictive code path than a normal embedded page image in a number of browsers — it's a known, if inconsistently-documented, gap that embedded `<style>`/CSS (including media queries) in an SVG favicon isn't reliably honored there the way it is for an `<img>`/inline SVG on a page, and the safest assumption is that it can silently fail to render at all rather than gracefully falling back.
- **Fix**: removed the `<style>` block and the sparkle accent entirely from `favicon.svg` (the one element the styling existed to fix) rather than trying to route around the rendering gap — the remaining fanned poster-cards are all mid-tone colors (slate/blue) with no light/dark contrast problem in the first place, so nothing else needed the same treatment. `Sidebar.vue`/`TopNav.vue`'s icons (real DOM SVG, not a favicon) are unaffected — they keep the `var(--text-primary)` sparkle fix from v1.6.82, since that's a completely different rendering context without this restriction. `.github/logo.svg` (used in the README, rendered via a normal `<img>` tag by GitHub, not as a favicon) also keeps its `prefers-color-scheme` version for the same reason.

## v1.6.82 (2026-08-31)
### Bug Fixes
- **The v1.6.81 logo mark looked wrong in light theme.** User-reported with a screenshot: the icon's dark `#0F172A` rounded-square background sat as a harsh, disconnected block next to the wordmark, and (found while investigating) the sparkle accent — the one detail element that sits directly on the surrounding nav background rather than on one of the colored poster-cards — was a fixed near-white (`#F8FAFC`), which goes invisible against light theme's light background. The other near-white elements (the text-bar lines, the mini art-scene highlight circle) were unaffected, since those always sit on top of the icon's own blue front card, not the page background.
- **Fix**: dropped the background rect from `Sidebar.vue`/`TopNav.vue`'s inline icon SVGs entirely — just the floating poster-cards now, no square behind them. The sparkle's fill was changed to `var(--text-primary, #F8FAFC)`, so it automatically tracks whichever of the app's 6 themes is active (all of which already define `--text-primary` with real light/dark contrast against their own `--bg-primary`) instead of a value hardcoded for the dark themes only.
- **The two static SVG files** (`frontend/public/favicon.svg`, `.github/logo.svg` — outside the Vue app, so no CSS custom properties available) got the equivalent fix via an embedded `<style>` block using `@media (prefers-color-scheme: dark)`: the sparkle defaults to a dark fill (safe for the common light-mode case — a browser tab bar or GitHub README on light) and only switches to near-white when the OS/browser is actually in dark mode. `.github/logo.svg`'s background square was dropped too, matching the app icons.

## v1.6.81 (2026-08-31)
### New Features
- **Added a real logo mark to the brand** — `TopNav.vue`'s header logo and `Sidebar.vue`'s header (expanded state only) now show a small inline SVG icon (dark rounded-square badge, layered poster-stack + film-strip motif) next to the "Simposter" wordmark, replacing plain text alone. Inlined directly as SVG markup in both components (no new asset file/network request) — same icon reused in both places for consistency, sized 24px in the top bar and 28px in the sidebar. Collapsed-sidebar behavior is unchanged (icon and text both stay hidden there, matching the pre-existing collapsed-state design); mobile's existing `.logo-text { display: none }` breakpoint also unchanged, so the icon alone becomes the compact mobile brand mark there.

## v1.6.80 (2026-08-31)
### Bug Fixes
- **"Test Connection" (Settings → Libraries and the setup wizard's Plex step) failed with a trailing slash on the Plex URL.** `test_plex_connection()` (`backend/api/movies.py`) builds `f"{test_url}/library/sections"` from whatever `plex_url` query param the caller sends — both `SettingsView.vue`'s `testPlexConnection()` and `OnboardingModal.vue`'s `testPlex()` pass the live, currently-typed field value straight through, with no normalization. A URL with a trailing slash (e.g. `https://.../32400/`, easy to end up with from copy-pasting a Plex remote-access URL) produced a double-slash path (`.../32400//library/sections`) that Plex rejects — while the *initial* connection during setup could still succeed depending on whether that specific attempt happened to go through a path that stripped it (`_apply_runtime_settings()` already `.rstrip("/")`s the value it copies into the runtime `settings.PLEX_URL`, but that's a separate in-memory copy from the raw value this endpoint's query param uses), which is what made it look like it "connects fine" initially but fails on a later re-test.
- **Fix, two layers**: (1) `test_plex_connection()` now strips a trailing slash from `test_url` itself before building the path, fixing the immediate symptom regardless of caller. (2) `_normalize_plex_payload()` (`backend/api/ui_settings.py`) now also strips it from the *saved* `plex.url` value on every settings save — previously only the separate runtime `settings.PLEX_URL` copy was ever cleaned, so the raw DB-stored value (and whatever `GET /api/ui-settings` echoes back into the Settings field on every page load) kept the trailing slash indefinitely, silently re-feeding it into anything that reads the raw value directly instead of `settings.PLEX_URL`.

## v1.6.79 (2026-08-31) — Docs
- **`docs/GETTING_STARTED.md` incorrectly said "Simposter isn't published to a container registry"** — stale as of the `.github/workflows/publish-ghcr.yml` CI (added earlier, alongside the repo-hygiene pass in v1.6.44) that's been publishing images to `ghcr.io/pjgithub9/simposter` on every push all along, tagged both by branch name and `latest` (main only). The Docker Compose section now documents both real options: pulling the pre-built GHCR image (a ready-to-use `docker-compose.yml` snippet, no clone/build required) as Option A, and building from source (the existing instructions, and what the repo's own shipped `docker-compose.yml` does by default) as Option B — including how to pin to a non-`main` branch's image tag if that branch is ahead. `README.md`'s Quick Start got a one-line pointer to the same GHCR image for anyone who'd rather skip building locally.

## v1.6.78 (2026-08-31)
### Bug Fixes
- **`plex_add_label()` still didn't actually apply the label, even after v1.6.77's verification logic caught and reported the failure.** Live-tested log confirmed the real root cause: both PUT attempts using `label[].tag.tag+` (the syntax used for the whole feature, mirroring `plex_remove_label()`'s working `tag.tag-`) returned a clean `200`, but the label never actually attached — and `PUT /library/metadata/{id}/labels` (the endpoint that supports `DELETE` for removal) returned a flat `404`, confirming it has no PUT/add equivalent. Plex's tag-diff query syntax turns out to only support *removing* a value this way; there's no matching "append one value" operator on the real API, despite `-` implying `+` should exist symmetrically.
- **Fix**: `plex_add_label()` no longer tries to diff-append a single label. It now fetches the item's current `<Label>` tags first, and — only if the target label isn't already present — PUTs back the **complete** list (existing + new) as indexed params (`label[0].tag.tag=A&label[1].tag.tag=B&...`) plus `label.locked=1`, matching the pattern python-plexapi's own `_edit_tags()` uses for non-remove edits. Sending only the new label (without the existing ones) would have silently wiped out anything else on the item (a personal rating tag, `4k`, etc.) — the fetch-then-full-write approach was mandatory, not just a nicety. Still verifies the result by re-fetching afterward (kept from v1.6.77, now actually confirms real success instead of catching a real failure every time).

## v1.6.77 (2026-08-31)
### Bug Fixes
- **`plex_add_label()` (v1.6.74) could report success without the label actually being applied.** User reported "Label to Add After Sending" set to "Simposter" and confirmed saved (verified directly against the live DB — `automation.labelToAdd` was correctly persisted, ruling out a settings-plumbing bug), but the label never showed up on the sent item in Plex, with no error in the logs. Root cause: unlike `plex_remove_label()` (where trusting a bare `200`/`204` status is safe — removing something already absent is harmless either way), `plex_add_label()` trusted the same bare status for an *add*, and Plex can return a success status for one of the three fallback PUT endpoints without the label actually ending up attached (the exact mechanism is still unconfirmed — plausibly the bulk `/library/sections/{id}/all` "multi-edit" endpoint, method 1, silently no-opping for a single-item field-diff edit it wasn't really designed for). Since method 1 "succeeded" by status code, the function returned immediately and never tried methods 2/3, which might have actually worked.
- **Fix**: `plex_add_label()` now re-fetches the item after each attempt that returns a success status and checks whether the label genuinely appears in its `<Label>` tags before considering it done; if verification comes back `False` (confirmed not present), it moves on to the next fallback method instead of stopping. A verification fetch that itself fails (network hiccup, not a real signal) doesn't count against the attempt — the success status is trusted in that specific case, same as before. Also elevated all attempt/result logging from `debug` to `info` so a future report like this is diagnosable straight from the normal log level instead of requiring code changes just to see what happened.
- **The user's own live `budget-daps` preset was separately cleaned up** (local DB, not a code change) — it held a leftover `overlay_config_ids: ["overlay-1773153797981"]` reference to an overlay config that no longer exists in their `overlay_configs` table at all (confirmed empty), which is what caused the recurring `[OVERLAY] Overlay config overlay-1773153797981 not found` warning on every render. Anyone else hitting this warning should check their preset's Overlay Config selection in Template Manager and clear any config that no longer exists.

### Improvements
- **Removed the redundant "Labels to Remove After Sending" field from Settings → Automation** (`AutomationTab.vue`) — duplicated Settings → Libraries' per-library "Default Labels to Remove," which is more precise (scoped per library) and is what's actually relied on. The underlying `webhookAutoLabels` setting and its backend merge logic are untouched for any install that already has a value stored there — it's just no longer editable from this tab.

## v1.6.76 (2026-08-31)
### New Features
- **Added "Kometa Compatibility" (Settings → Libraries, in the "Default Labels to Remove" section).** The startup wizard's "Using Kometa?" toggle only ever auto-checked "Overlay" for the libraries selected *at that moment* during onboarding (`labelsToRemove` written once into `defaultLabelsToRemove` for `allLibIds`) — a library added afterward through Settings never got it, with no way to apply it after the fact short of manually re-checking the box per library. New `automation.kometaCompatibility` setting (persisted from onboarding's `usingKometa` toggle too, so it carries forward automatically for existing "Using Kometa" users) drives new logic in `SettingsView.vue`'s `saveSettings()`: right before the save request, any library present now but absent from the last-saved `savedLibraryIds`/`savedTvShowLibraryIds` gets "Overlay" appended to its `defaultLabelsToRemove`/`defaultTvLabelsToRemove` entry (only if not already present) when the setting is on — reusing the exact same newly-added-library detection the v1.6.69 auto-scan-on-save feature already computes.

### Improvements
- **Refreshed the "budget-daps" starter preset.** `_DEFAULT_PRESETS_TEMPLATE` (`backend/api/presets.py`): `vignette_strength` 0.25→0.1, `uniform_logo_max_h` 461→360, `uniform_logo_offset_y` 0.85→0.91. Deliberately did **not** carry over the source preset's `overlay_config_ids: ["overlay-1773153797981"]` — that references a specific overlay config from the requesting user's own install (which their own logs show as already-deleted/not-found on their end), and baking a dangling overlay-config reference into a preset every new install imports would reproduce that same "Overlay config not found" warning for everyone, not just them.

## v1.6.75 (2026-08-31)
### New Features
- **Added "textless-border" and refreshed "budget-daps" in the starter-preset bundle.** `_DEFAULT_PRESETS_TEMPLATE` (`backend/api/presets.py`) now has 4 Uniform Logo presets (`simposter-main`, `budget-daps`, `textless-border`, `stock-poster`) instead of 3 — `textless-border` is a plain white-border textless-poster look with no logo. `budget-daps`'s options were overwritten with an updated look (Comfortaa-Medium font, uppercase text, a text bounding box, top matte/fade, a thicker stroke, and a larger/repositioned logo box) — same name/id, so existing installs that already imported the old version keep it until they re-import via Settings → Advanced → onboarding rerun or Template Manager's "Import Simposter defaults" button.

## v1.6.74 (2026-08-31)
### New Features
- **Simposter can now actually add a label to Plex items after sending a poster.** Previously the only label-related feature was removal (`defaultLabelsToRemove`/`webhookAutoLabels` — strips a label an external tool like Kometa/Radarr/Sonarr applies beforehand to mark "needs a poster"); there was no way to tag an item *after* Simposter successfully sends its own poster, despite the onboarding wizard's UI implying this already existed (see Bug Fixes below). New `plex_add_label()` (`backend/config.py`) mirrors `plex_remove_label()`'s 3-method-fallback shape, using Plex's append syntax (`label[].tag.tag+`) instead of its remove syntax (`tag.tag-`). New `automation.labelToAdd` setting (Settings → Automation → "Label to Add After Sending", blank = disabled) drives it, read fresh from the DB via a new `get_label_to_add()` helper (not the possibly-stale pydantic `settings.*` object — same "read fresh from DB" pattern `plexsend.py`/`scheduler.py` already use for `webhookAutoLabels`, deliberately not the stale one `webhooks.py`'s own handlers use).
- **Wired into every place a poster actually gets sent to Plex**, mirroring the existing `plex_remove_label()` call sites one-for-one: `backend/api/batch.py` (`_process_single_movie`/`_render_and_save_poster` — covers manual batch, webhook-triggered generation, auto-generate, scheduled retry, and manual "Retry Now", since all of these funnel through these two shared functions), `backend/api/plexsend.py` (manual Send to Plex, plus all three resend paths — single resend, TV season resend, and bulk Local Assets resend, via a new shared `_add_label_for_key()` helper alongside the existing `_remove_labels_for_key()`), `backend/api/webhooks.py` (the webhook handlers' own "resend cached poster" fast path, before falling through to `batch.py`), and `backend/auto_generate.py` (its own separate "resend cached poster" fast path, movie and TV loops both).

### Bug Fixes
- **The onboarding wizard's "Apply a label after sending a poster?" toggle did nothing.** `OnboardingModal.vue` wrote `sendLabel`/`labelName` into `webhookAutoLabels` — the label-*removal* setting — instead of a real "add a label" field, which didn't exist until this release. Since most users never had that label already applied, "removing" it was a silent no-op: the toggle looked like it worked (no error) but never tagged anything. Now writes to the new `labelToAdd` setting instead, matching what the toggle's own description always said it would do.
- **Settings → Automation's "Default Labels for Webhook Posters" field was misleadingly named** — same root confusion as the wizard bug above, just in the always-visible Settings UI rather than a one-time wizard step. Relabeled to "Labels to Remove After Sending" with a description that explicitly says it strips labels rather than applying them, and points to the new "Label to Add After Sending" field for the feature users were probably expecting.

## v1.6.73 (2026-08-31)
### New Features
- **Added a "Run Startup Wizard" button to Settings → Advanced.** Onboarding (`OnboardingModal.vue`) was previously only reachable automatically, gated on `settings.onboardingCompleted` being `false` (`App.vue`'s `onMounted`) — a user who skipped it, or wants to redo Plex/library setup or re-import the starter presets, had no way back in short of manually clearing that DB flag. Since `OnboardingModal` is mounted at the `App.vue` level (outside `<router-view>`, so it can float above any page) but the new button lives in a routed view (`Settings → Advanced`, several component layers deep), added a tiny shared counter ref (`frontend/src/composables/useOnboardingLauncher.ts`) instead of threading a prop/emit chain through `SettingsView.vue` → `AdvancedTab.vue` and back up — `App.vue` watches it and flips `showOnboarding` on any increment. Existing settings aren't cleared; the wizard already prefills Plex URL/token from `settings.plex.value` on mount (`OnboardingModal.vue`'s own `onMounted`), so reopening it is a genuine "redo the same screens," not a wipe.

## v1.6.72 (2026-08-31)
### New Features
- **Added an "Import Simposter defaults" button to Template Manager's Import/Export section.** Previously the 5 starter presets added in v1.6.71 (`_DEFAULT_PRESETS_TEMPLATE`, `backend/api/presets.py`) were only reachable via onboarding's fire-and-forget finish-step import — no way to pull them back in later (e.g. after deleting one, or if onboarding was skipped/failed for an existing install). New `handleImportDefaults()` (`TemplateManagerView.vue`) calls the exact same `GET /api/presets/default-template` → `POST /api/presets/import` pair onboarding uses; import is a merge (`db.merge_presets`), so clicking it more than once is safe — it re-applies the same content rather than duplicating.

## v1.6.71 (2026-08-31)
### New Features
- **Onboarding's default-preset import now ships 5 starter presets instead of 1.** `GET /api/presets/default-template` (`backend/api/presets.py`) previously returned a single hardcoded `uniformlogo`/`default` preset; replaced with a `_DEFAULT_PRESETS_TEMPLATE` dict covering both `uniformlogo` (`simposter-main` — this project's own reference look, previously developed under the name "pj"; `budget-daps`; `stock-poster`, used as the fallback target for the other two's `fallbackPosterPreset`/`fallbackLogoPreset`) and `kometa` (`Plex-Requests`, `LEAVING-SOON` — Kometa Creator presets for the two most common Overlay-collection use cases). Preset IDs are generated from each display name via a new `_slugify_preset_name()` helper rather than hardcoded, so the data only needs a name. Onboarding's finish-step import remains fire-and-forget and is never triggered for an existing install — same mechanism as before, just more content.

### Bug Fixes
- **"Copy Compact" (Template Manager) and the webhook URL copy button (Settings → Automation) threw "Cannot read properties of undefined (reading 'writeText')" instead of copying.** `navigator.clipboard` is only defined in secure contexts (HTTPS, or `localhost`) — both call sites accessed it directly, which fails immediately on the plain-HTTP LAN address most self-hosted users reach this app through. Added a shared `copyToClipboard()` helper (`frontend/src/services/clipboard.ts`) that checks `window.isSecureContext` first and falls back to the legacy `document.execCommand('copy')` (via a temporary offscreen textarea) when the modern API isn't available, returning `true`/`false` instead of throwing so callers can show their own error toast. Both call sites now route through it.

## v1.6.70 (2026-08-28)
### Bug Fixes
- **TV editor's "Save As" (create new preset) always failed with "Cannot save season options as new preset" whenever attempted while viewing a season poster, not just when actually trying to save it as a season-specific override.** `saveAsNewPreset()` (`TvShowEditorPane.vue`) unconditionally blocked the season case with an error toast instead of following the same pattern already used for "Save Preset" (overwrite): a *new* preset has no `season_options` of its own to diff against yet, so there was never a real reason to block this — the currently-focused season's fully-resolved effective options (already what's displayed while viewing a season, via the same `resolve_season_options()` merge the backend uses for reads) are a perfectly valid base `options` payload for a brand-new preset. Fixed by removing the block; saving as new from a season tab now creates the new preset using that season's effective settings as its base template, with a toast clarifying that's what happened (rather than creating a season-specific override, which isn't possible for a preset that doesn't exist yet).

## v1.6.69 (2026-08-28)
### Bug Fixes
- **TV editor's `doSave()` was missing the `saveCurrentSettings()` call every other save/switch path in the file already has.** Saving right after a live change (e.g. setting Logo Mode to "No Logo") without navigating away first used stale cached settings, since the currently-focused season/series' live UI state was never flushed into `settingsCache` before `doSave()` read from it.
- **The series poster's own edits were never detected as "modified" at all.** `markFieldModified()` (`TvShowEditorPane.vue`) only ever tracks changes for actual seasons (`isSeason` check) — `userModifiedFields` is deliberately empty for the series key. `doSave()`'s and the background renderer's `hasUserModifications` check read that same tracking Set for the series too, so it was always `false` regardless of what was changed, silently discarding live series edits (including Logo Mode) in favor of the saved preset's defaults. Fixed by special-casing the series: since `saveCurrentSettings()` already caches its full live state unconditionally (no preset-field stripping, unlike seasons), whether cached data exists at all is now the correct signal for the series, instead of the field-level tracking Set that was never populated for it.
- **The real root cause of both bugs above, and a wider class of bug: `seasonOptions` was built from the currently-focused item's full live options, not the target season's own state.** `doSave()`'s and `renderAllSelectedSeasons()`'s season loops both started `seasonOptions` as a copy of whatever the *currently-focused* season/series showed (`{...optionsPayload.value}`), then patched only a hand-picked handful of fields per season (`logo_mode`, `text_overlay_enabled`, `custom_text`, `font_size`, `font_family`). Every other season-customizable field — text color, position, letter spacing, per-season matte/fade/vignette/grain overrides, logo drop shadow — silently leaked through from whatever the currently-focused item happened to show, meaning editing Series could appear to also change a season's rendered poster in unrelated ways. Fixed with a new shared `applyCachedPresetFields()` helper that applies the *complete* set of season-customizable fields (matching `saveCurrentSettings()`'s own `presetFields` list, the same set the backend's season_options diffing already tracks) instead of the narrow hand-picked subset, used consistently in both functions.
- **The "Rendered Posters" strip could show a stale thumbnail indefinitely.** `renderAllSelectedSeasons()`'s "already rendered, skip" check only tested whether *any* preview existed for a season key, not whether it matched the *current* poster/logo/options — so once a season had been rendered once, later settings changes for it never showed up in the strip until you manually clicked into that season. Fixed to check against the actual settings-aware cache key instead.
- **Adding or removing a Plex library in Settings silently didn't save.** `localLibraries`/`localTvShowLibraries` (`LibrariesTab.vue`) are writable `computed()`s whose getter returns freshly-spread copies of the props on every read — `v-model="lib.id"` on the Library ID dropdown (and the Display Name input) mutated a throwaway clone that was discarded on the next re-render, never reaching the parent's state or the save payload. The `autoGenerateEnabled`/`autoGeneratePresetId` fields in the same component already had an explicit `@change="updateLibraries"` workaround for this exact gotcha (force-reassigns the array to trigger the computed setter) — the two fields that actually matter for adding a library just never got it. Added the same trigger to both.
- **The TV "Flat" save layout put every show in its own subfolder instead of being genuinely flat.** `OutputTab.vue`'s "Flat" and "Asset folders (Kometa)" presets used the *identical* TV template (`{title} ({year})/{filename}.jpg`), by design — the code comment even said "Kometa has no flat season-poster naming, so Flat and Asset folders necessarily produce the same TV layout." Renamed "Flat (Kometa)" to "Flat" (it was never actually a Kometa convention) and gave it a real flat template (`{title} ({year}) {filename}.jpg`, space instead of `/` before `{filename}`) producing `Show Name (Year) poster.jpg` / `Show Name (Year) SeasonNN.jpg` with no subfolder. "Asset folders (Kometa)" is unchanged.
- **Season posters could save with the season's own display label (e.g. "Season 1") instead of the show's name, in both save modes.** `TvShowEditorPane.vue`'s `doSave()` and `doSend()` both built a temporary movie object for each season using `season.title` (a UI display label) as the `title` sent to the backend — `doSave()` only for non-series entries, `doSend()` unconditionally. Since the season itself is already conveyed separately via `seasonIndex`, and the save-path template's `{title}` substitution has no other source, this meant the "folder"/filename portion of Flat and Asset-folder templates showed the season's own label instead of the real show name. Fixed to always use `props.movie.title` (the real show name) in both functions.

### New Features
- **Removing a library actually works now, with confirmation and cache cleanup.** New `DELETE /api/library/{library_id}` (`backend/api/movies.py`) purges `movie_cache`/`tv_cache`/`collection_cache` rows for that library, deletes the on-disk poster/logo cache files for every item that was cached there, and clears pending retry-queue entries (new `db.clear_retry_queue_for_library()`). Deliberately leaves `poster_history` and on-disk saved output files untouched — History stays as a record of past activity, and output files are the user's actual exported posters, a different and more destructive thing to delete than "cache". The Library ID dropdown itself is still locked once saved (unchanged) — only the Remove button's `disabled` restriction was lifted. Clicking it shows a `window.confirm()` (matching this app's existing confirmation style elsewhere in Settings) explaining what will happen; the actual purge is deferred until the page's Save button succeeds, so a removal isn't "final" until saved, consistent with every other change on this page.
- **Adding a library now auto-scans it on save.** `saveSettings()` (`SettingsView.vue`) captures which library IDs are newly-added (present now, weren't in the last-saved set) before saving, and after a successful save, sequentially scans each one via the existing `scanLibrary()` — the same call an individual library's Scan button already makes — instead of leaving a freshly-added library empty until the next scheduled scan or a manual click.
- **Settings' "unsaved changes" highlight is now per-section, not one shared flag.** The single `sectionsWithChanges.connections` flag (Plex URL/token *and* both library lists all bundled together) is now three independent flags — `plexConnection`, `movieLibraries`, `tvLibraries` — computed separately in `checkForChanges()` and passed as separate props, so each section only highlights when its own data actually changed instead of all three highlighting together for any one of them changing.

## v1.6.68 (2026-08-27)
### Bug Fixes
- **Logo thumbnail tiles could show up blank in the logo picker, in all three places it appears (`EditorPane.vue`, `TvShowEditorPane.vue`, `LogoEditorModal.vue`).** Every logo `<img>` rendered `l.thumb || l.url` with no error handling. `tmdb_client.py`'s `_build_image_entry()` sets `thumb` to a resized `w300` PNG and `url` to the `original` file — for SVG-sourced or newly-added logos, the resized variant can 404 (a known TMDb CDN propagation quirk) even though the original loads fine, and with no fallback the tile just stayed permanently blank. Flagged as a secondary, lower-confidence note in the same bug report as the v1.6.67 fix below ("not sure if related") — traced separately through `tmdb_client.py` and confirmed unrelated. Fixed by adding a shared `failedLogoThumbs` tracking ref + `@error` handler to all three files that falls back to the full-size `url` once a thumb fails to load. `EditorOverlay.vue` has the identical unfixed pattern but is dead code (not imported anywhere) and was deliberately left alone. See CLAUDE.md Quirk #29.
- **Logo tiles in the "🖼️ Logos" tab could also show up blank, for a completely different reason.** After applying the fix above, the user asked whether the bug might actually be in the Logos tab (`LogosView.vue`) rather than the editor — a genuinely different feature (one cached clearlogo tile per library item, not a picker of candidates). It was: `batch.py`'s batch/webhook/auto-generate logo-upload path (`_process_single_movie()`/`_render_and_save_poster()`) cached the raw external TMDb/Fanart source URL in the DB's `logo_url` field instead of a locally-cached copy — unlike a fresh library scan or the standalone "Send Logo to Plex" button, both of which correctly save the uploaded bytes locally and serve them via `/api/logo/{rating_key}`. Since batch/webhook/auto-generate is the primary way most users' logos get sent, this was the more consequential of the two bugs. Fixed by caching the just-uploaded bytes locally (no extra fetch — they're already in hand from the upload) instead of the external URL, via a new `logo_url_for_cache` variable. Deliberately does not re-fetch from Plex to get this URL, matching an existing comment in `plexsend.py` explaining why that would be unsafe ("Plex may not have processed the upload yet, so re-fetching would return the old logo"). See CLAUDE.md Quirk #30.
- **A fourth `<img>` with the identical no-fallback gap, in the same modal as the first fix above.** `LogoEditorModal.vue`'s "Current Logo" preview at the top of the modal (distinct from the "Select Logo" candidate grid below it, which the first fix already covers) also rendered `item.logo_url` with no `@error` handler. Caught after the user pointed out that clicking a Logos-tab tile opens this modal to change the logo — prompting a check of every `<img>` in the modal, not just the one already found. Fixed with a `currentLogoFailed` ref that swaps to the existing "No logo cached yet" placeholder on failure, matching `LogosView.vue`'s own grid.

## v1.6.67 (2026-08-27)
### Bug Fixes
- **"No Logo" mode was ignored when using Save to Disk for TV show posters (fixes #37).** `doSave()`'s per-season loop in `TvShowEditorPane.vue` is the one save/send path in this file that never switches the live editing context per season the way `doSend()` does via `restoreSettingsForKey()` — instead it hand-derives each season's logo URL as `cachedSettings?.selectedLogo || logoUrl.value`. When a season's Logo Mode was explicitly set to "No Logo" but the user hadn't separately picked a specific logo file (the normal case — there's no dedicated "no logo" value for `selectedLogo`, it's simply left unset), this fell through to `logoUrl.value`, the *live* computed logo for whatever season currently has editor focus, not the season actually being saved in that loop iteration — so a logo could get added back in despite "No Logo" being selected. Reported by an external user with a clean repro; movies are unaffected (no per-season loop exists there), and Send to Plex was never affected, since it always sent an empty logo URL for a no-logo season and so never exercised whether the backend would incorrectly honor a stale one. Fixed by checking `cachedSettings?.logoMode === 'none'` first and forcing `seasonLogoUrl = null` in that case, matching what the live `logoUrl` computed already does elsewhere in the file. See CLAUDE.md Quirk #13 for the general pattern this bug follows.

## v1.6.66 (2026-08-27)
### Performance
- **PNG encoding for Plex uploads (manual send and batch) now tries a fast pass before paying for a slow one.** `encode_poster_for_plex()` (`backend/api/save.py`) previously always encoded at `compress_level=9` (max effort) to keep grain/matte-heavy posters under Plex's ~10MB upload cap — measured taking up to ~5 seconds on its own in a real production trace, the single largest chunk of a ~9s "Send to Plex" click. Since PNG compression level is a pure lossless effort/size tradeoff (never a pixel/quality difference), it now tries `compress_level=6` first (same default the save-to-disk path already uses) and only escalates to `compress_level=9` if that fast attempt doesn't already fit under the size cap — which the overwhelming majority of posters do. The JPEG fallback (the one genuinely lossy step, used only as a last resort) is unchanged. Measured effect on a real send: encode dropped from ~5s to ~1s, cutting total send time from ~9.2s to ~4.85s.
- **Trimmed a redundant Plex round-trip after every send.** Both manual editors (`EditorPane.vue`/`TvShowEditorPane.vue`) were calling `fetchExistingPoster(true)` right after a send completed, forcing a second fresh Plex poster fetch on top of the one `/api/plex/send` already does internally as part of the send itself. Now reuses the already-fresh cache instead (`fetchExistingPoster()`, no force).
- **Plex upload/download calls were bypassing the app's own connection pool.** The poster and clearLogo upload calls in `backend/api/plexsend.py` and `backend/api/batch.py` used a bare `requests.post()`/`requests.get()` instead of the shared, pooled `plex_session` — meaning the single most expensive, most frequent Plex call (the actual poster upload) paid for a fresh TCP+TLS handshake every time instead of reusing an open connection. Switched every Plex-URL-targeted call in both files to `plex_session`.
- **Label removal no longer re-fetches metadata it just fetched moments earlier.** `plex_remove_label()` (`backend/config.py`) always did its own `/library/metadata/{rating_key}` fetch just to detect movie/show/season/episode type — even when the caller (manual send, or the movie-batch path, which is always type "movie" by construction) already knew or had just parsed that. Added an optional `content_type` parameter so those callers skip the redundant round-trip; every other caller keeps the original auto-detection behavior unchanged.
### Improvements
- **Backend logs across the send/batch/webhook/retry pipeline now show real movie/show titles and per-item timing instead of just a bare rating_key.** `preview.py`, `plexsend.py`, `batch.py` (both the movie and TV batch paths), `webhooks.py`, `scheduler.py`'s automatic retry job, and `history.py`'s manual "Retry Now" button all now resolve a display title (via a cheap local DB cache lookup — never an extra network call, same helper `get_title_for_rating_key()` already used for History's fallback titles) and log it alongside the rating_key, plus a `done in X.Xs` summary line per item/send. This was a direct, real debugging need — tracing a single item through interleaved concurrent batch log output was previously only possible by rating_key, which made it hard to follow multiple items rendering at once.
- **Plex server status indicator** (see v1.6.65) and this release's logging work together surfaced a stale doc: CLAUDE.md's FAQ claimed `concurrentRenders` caps at 4, but the actual UI slider (`PerformanceTab.vue`) goes up to 10 with no backend-enforced ceiling at all. Confirmed via real before/after batch logs that raising it from 2→~9 cut a 9-movie batch's total wall-clock time roughly in half (~27s → ~12s), at the cost of higher per-item latency from CPU/network contention — a good trade for total throughput. Doc corrected.

## v1.6.65 (2026-08-27)
### New Features
- **Plex status indicator in the top bar.** New `GET /api/plex-status` (`backend/api/movies.py`) pings Plex's cheap `/identity` endpoint (not the heavier `/library/sections` `test-plex-connection` uses) with a 5s timeout, polled every 30s by `TopNav.vue`. Shows a small colored dot + label (green/pulsing red/gray) with a tooltip, collapsing to just the dot on mobile — so a downed Plex server shows up immediately instead of surfacing as a string of confusing failures elsewhere in the app.
- **Fanart.tv API key now explicitly called out as needed for Collection logos**, in both Settings → General and the onboarding wizard's Fanart step — TMDb has no artwork endpoint for Collections at all (see CLAUDE.md Quirk #21), so without a Fanart key, Collection posters can't auto-find a logo.
- **A "major release" highlight-reel modal** for big version jumps. New `frontend/src/majorReleases.ts` holds curated big-picture highlights, separate from the granular per-version `releaseNotes.ts`; `UpdateAnnouncementModal.vue` shows this instead of a huge per-version bullet dump whenever a user's last-seen version predates a listed milestone (fresh installs skip it — onboarding already covers their intro). First entry covers the `webui-overhaul-dev` → `main` merge.
### Performance
- **Plex uploads (poster + clearLogo) were opening a brand-new connection for every single request** instead of reusing the app's existing pooled `requests.Session` (`plex_session`, already used elsewhere in the codebase) — meaning every manual send and batch item paid for a fresh TCP+TLS handshake to the Plex server on top of the actual upload. Fixed in `backend/api/plexsend.py` and `backend/api/batch.py`.
- **Label removal re-fetched metadata it had often just fetched moments earlier.** `plex_remove_label()` (`backend/config.py`) always did its own `/library/metadata/{rating_key}` fetch to detect movie/show/season/episode type — even when the caller (manual send, or the movie-batch path, which is always type "movie" by construction) already knew or had just parsed this. Added an optional `content_type` parameter so those callers can skip the redundant round-trip; unaffected callers keep the existing auto-detection behavior unchanged.

## v1.6.64 (2026-08-24)
### Bug Fixes
- **The manual "Retry Now" button (History → Retry Queue) always re-uploaded a poster to Plex, even when the render still didn't meet the template.** `POST /api/retry-queue/{rating_key}/retry-now` (`backend/api/history.py`) called `process_single_movie_poster()`/`process_single_tv_show_poster()` without passing `send_only_if_ideal=True` — both default that parameter to `False`, so a manual retry unconditionally uploaded whatever it rendered (missing logo, poster/logo fallback used, etc.), stripping labels and recording a "sent to Plex" history entry regardless of whether ideal template conditions were actually met. The automatic background retry job (`scheduler.py`'s `_run_poster_retry()`) already passed this flag correctly since v1.6.09 — this manual, one-off retry path was simply never updated to match. Fixed by adding `send_only_if_ideal=True` to both calls in `api_retry_now()`. A manual retry now behaves identically to the automatic one: it re-renders and checks whether the template is actually met, and only uploads if so — otherwise it just records the attempt and leaves the item pending in the queue.

## v1.6.63 (2026-08-24)
### Bug Fixes
- **Cycling through library pages could rate-limit poster loading, leaving posters stuck failing to load.** Per-item endpoints (`/api/movie/{id}/poster`, `/api/tv-show/{id}/poster`, `/api/logo/{id}`) had no entry in the rate limiter's `endpoint_limits` (`backend/middleware/rate_limit.py`), so they fell through to the low `default_limit` (300 requests/60s) meant for unlisted, mostly-expensive endpoints. Each visible grid card fires two poster requests (`?meta=1` + `?raw=1`), and "Poster Density" (Settings → General) allows up to 100 items per page — a single max-density page already uses roughly two-thirds of that 300 budget, so flipping through more than one page inside a minute tripped the limit and every subsequent poster 429'd. Added explicit, much higher limits for `/api/movie` (2000/60s), `/api/tv-show` (2000/60s), and `/api/logo` (1500/60s) — safe to raise generously since these mostly serve already-disk-cached files, not external API calls; `/api/movie` still isn't fully exempted, since it also covers `/api/movie/{id}/tmdb`, which does hit TMDb.

## v1.6.62 (2026-08-24)
### Performance
- **Live preview and rendering could take anywhere from ~300ms to over 10 seconds for what looked like identical requests — root-caused to two compounding issues, neither about the render itself.** (1) Every `/api/preview` call re-fetched movie/show details, images, and Fanart logos from TMDb/Fanart.tv from scratch, even when nothing but a slider value had changed since the last request for the same item — Fanart.tv's own latency alone was observed spiking to 4+ seconds per call in production logs. (2) That redundant call volume was enough to trip TMDb's own client-side rate limiter (`_apply_rate_limit()`, default 40 requests/10s), which sleeps *synchronously* inside the request when the window fills — so a burst of slider changes during active editing could turn into several seconds of blocked rendering, compounding with the first issue. Added a short-lived (5 minute) in-memory response cache to `tmdb_client.py`'s `_tmdb_get()` and `fanart_client.py`'s `_fanart_get()` — the two low-level functions all TMDb/Fanart lookups funnel through — so repeated requests for the same item reuse the already-fetched data instead of hitting the network (or the rate limiter) again. A "no artwork found" (404) result is cached too, since that's one of the most common Fanart responses and was being re-fetched just as wastefully as a hit; genuine transient failures (timeouts, connection errors) are deliberately never cached, so those still get a real retry. This is purely an I/O-timing change — no rendered pixel, encoding, or quality setting is touched (see CLAUDE.md Quirk #17's hard boundary on this).

## v1.6.61 (2026-08-24)
### Bug Fixes
- **Fixed the movie/collection manual editor (`EditorPane.vue`) showing a stale preview render** in two related ways: (1) switching to a different movie/collection while a preview was still rendering could let that slower, now-stale response land after the switch and overwrite the new item's preview with the previous item's poster; (2) rapidly changing slider values could fire several overlapping preview requests, and an older, slower response landing after a newer one would visually "jump" the preview back to an earlier slider state. `doPreview()` now captures the target item's identity and a monotonically-increasing request sequence number before each render, and only applies a response if both are still current when it resolves — matching the identical protection `TvShowEditorPane.vue` already had for switching seasons (see CLAUDE.md Quirk #13, fixed v1.6.31), which was never applied to the movie/collection editor. The TV editor's existing season-identity guard also got the same request-sequence check added, since it only protected against switching seasons, not against two overlapping renders *for the same season* resolving out of order (the identical rapid-slider-jumping symptom, just not yet reported for TV specifically).

## v1.6.60 (2026-08-24)
### Bug Fixes
- **Fixed Radarr/Sonarr/Tautulli webhooks matching the wrong Plex item when one TMDb/TVDb ID is a numeric prefix of another.** `find_plex_movie_by_tmdb_id()`/`find_plex_show_by_tvdb_id()` (`backend/api/webhooks.py`) matched Plex's GUID with `f"tmdb://{tmdb_id}" in guid_id` — a substring check, not an exact match. Since `"tmdb://58"` is a literal string prefix of `"tmdb://5825"`, a Radarr webhook for TMDb ID 58 ("Pirates of the Caribbean: Dead Man's Chest") matched and needlessly reprocessed a completely unrelated movie whose real TMDb ID was 5825 ("Christmas Vacation") — stripping its labels and re-sending it to Plex — while the actual target movie was never touched, since the loop returns on first match and stops searching. (The wrongly-matched movie's own poster/logo artwork came out correct, since the render pipeline re-resolves TMDb data from the matched rating_key rather than trusting the webhook's original ID — the real damage is the pointless reprocessing and the intended movie being silently skipped.) Root-caused directly from a user's production log showing the payload's TMDb ID (58) and the subsequently-fetched TMDb ID (5825) disagreeing. Fixed both functions to require an exact GUID match (`guid_id == f"tmdb://{tmdb_id}"` / `f"tvdb://{tvdb_id}"`). Any Plex library where one TMDb or TVDb ID happens to be a numeric prefix of another was exposed to this on every matching webhook call.

## v1.6.59 (2026-08-23)
### Bug Fixes
- **Kometa Creator gave no confirmation when a preset was saved.** `saveCurrentPreset()`/`saveAsNewPreset()` (`KometaCreatorPane.vue`) called `presetService.savePreset()`/`savePresetAs()` but never checked the result or showed a toast, unlike the matching functions in the movie/TV editors. Added the same `success('Preset saved!')` / `notifyError(...)` pattern already used there.
- **Kometa Creator presets didn't save the selected logo at all** — reselecting or reloading a preset never restored its logo, since `optionsPayload` (what actually gets written to a preset's `options_json`) never included the logo URL in the first place; `applyPresetOptions()` had nothing to read it back from either. Unlike the movie/TV editors, where a preset is a reusable style applied across many different items (so the item-specific logo is deliberately *not* saved into the preset), a Kometa preset is normally built for one specific collection — its logo is part of that poster's design. New `kometa_logo_url` option key (same explicit-`''`-on-clear pattern already used for `kometa_texture_url`, so clearing the logo and re-saving actually clears it in a preset too, rather than silently keeping the old value via the backend's options merge).

## v1.6.58 (2026-08-23)
### New Features
- **`{folder}` save-path variable now works for TV shows**, not just movies — resolves to the real on-disk show folder name (e.g. from `/data/tv/Fallout (2024)/Season 01/ep.mkv`, resolves to `Fallout (2024)`), independent of Plex's display-language title. Show-level only, not per-season (a season's episodes always live under the same one show folder, so resolving it once per show — not once per season — avoids redundant Plex lookups for an identical value). New `get_show_folder_name()`/`extract_show_folder_name_from_episode_metadata()` in `backend/config.py`, handling both `Show/Season NN/episode.ext` and flat `Show/episode.ext` layouts, unified behind a new `get_media_folder_name(rating_key, is_tv)` entry point that's byte-identical to the existing movie behavior when `is_tv=False`. Wired into `save.py`, all five `SaveContext` sites in `plexsend.py`, and (as a follow-up fix beyond the original PR's scope) `batch.py`'s shared movie/TV/season renderer, so batch and webhook-triggered TV renders get it too, not just manual Save/Send. Contributed by romquenin (PR #36) — thank you!
### Bug Fixes
- **Fixed TV series-level saves including a stray "(Series)" in the `{title}` variable.** `TvShowEditorPane.vue` builds the series tab's display object with `` `${title} (Series)` `` for the season list UI, but `doSave()` was reusing that decorated title directly when saving — producing filenames like `Show Name (Series).jpg` instead of `Show Name.jpg`. Fixed to use the real show title for the actual save request, keeping the "(Series)" suffix only where it's meant to be (the tab label). Contributed by romquenin (PR #36) — thank you!

## v1.6.57 (2026-08-21)
### Bug Fixes
- **Retry queue items whose Plex item had been deleted/reorganized retried forever**, generating a fresh "failed" History entry every retry cycle indefinitely (worse when `retryMaxAttempts` is 0/unlimited, since the built-in abandon-after-N-attempts logic never kicked in). Root-caused via a live production log: the failure was `get_movie_tmdb_id()` returning `None` after Plex genuinely 404'd on `/library/metadata/{rating_key}` — confirmed directly against the reporting user's own server that both stuck rating keys return a real `404 Not Found` from Plex (not a network/auth issue; `/identity` on the same server responds normally). New `_plex_item_exists()` (`backend/scheduler.py`) does a definitive existence check — `True`/`False` on a clear answer, `None` on any network hiccup so a transient failure is never mistaken for a deletion — and `_run_poster_retry()`'s exception handler now calls it after any retry error, immediately abandoning the queue entry (`db.resolve_retry_queue_item(rating_key, "abandoned")`) when Plex confirms the item is gone, instead of waiting on `retryMaxAttempts` (which may never trigger).
- **Failed History entries for early-failing items (e.g. "No TMDb ID found") showed an opaque `(rating key 12345)` instead of the actual title**, since `title_hint` only ever advanced past the raw rating key after a successful TMDb lookup — exactly the case that doesn't happen when the failure *is* the TMDb/Plex lookup itself. `_process_single_movie`/`_process_single_tv_show` (`backend/api/batch.py`) now fall back to the already-existing `db.get_title_for_rating_key()` (reads the last scan's cached Plex title from `movie_cache`/`tv_cache`, independent of any TMDb match) before falling back to the bare rating key placeholder.

## v1.6.56 (2026-08-21)
### New Features
- **Kometa Creator now has full logo parity with the Simposter Creator.** Added a "Current Plex Logo" panel (same `/api/logo/{rating_key}` endpoint the movie/TV editors use — reads a collection's clearLogo via Plex's generic `/library/metadata/{id}` JSON metadata, which works identically for a collection's rating key), a "Send logo" toggle, and a standalone "Send Logo" button (`/api/plex/send-logo`, no `is_collection` handling needed — verified empirically that Plex's `/library/metadata/{id}/clearLogos` upload path already works for a collection rating key the same as a movie's). Also fixed `doSend()` silently hardcoding the send-logo flag to `false`, meaning the combined "Send to Plex" action could never send a logo even with the toggle on.
### Bug Fixes
- **The Collections "Choose your creator" popup could land off-screen, requiring a scroll to find it**, if you'd scrolled down a sufficiently long collections list before clicking one. Root cause: the popup's `.view` ancestor has the shared `.glass` class, whose `backdrop-filter` creates a new CSS containing block for `position: fixed` descendants — so the popup's "fixed, centered" positioning was actually centering itself relative to `.view`'s entire (page-length) box, not the true viewport. Fixed by wrapping the popup in `<Teleport to="body">`, escaping the containing-block issue entirely. The same `.modal-backdrop`-inside-a-`.glass`-container pattern exists in several other views' modals in this app — not touched here, but worth knowing if the same symptom shows up elsewhere.
- **API rate-limiting returned a generic `500 Internal Server Error` instead of the intended `429 Too Many Requests`** when a client exceeded its limit. `RateLimitMiddleware.dispatch()` (`backend/middleware/rate_limit.py`) `raise`d an `HTTPException` on the over-limit path, but that code runs inside Starlette's `BaseHTTPMiddleware`, which executes `dispatch()` in its own `anyio` task group *outside* FastAPI's normal exception-handling layer — a raised `HTTPException` there never reaches the handler that converts it into a proper response, it just becomes an unhandled exception, and Starlette reports a generic 500. This wasn't specific to any one endpoint — any endpoint hitting its configured rate limit anywhere in the app would have hit this; caught via a real production log showing it for `/api/logo`. Fixed by `return`-ing a `JSONResponse(429, ...)` directly instead of raising, preserving the same status code, body, and `Retry-After` header the client should have gotten all along.

## v1.6.55 (2026-08-21)
### New Features
- **Collections gained two dedicated poster creators**, replacing what was previously an accidental fallback (selecting a collection opened the plain movie editor because `App.vue` ignored the emitted media type, not by design). Choosing a collection now shows a creator picker:
  - **Simposter Creator** — the existing manual editor, now genuinely collection-aware: pulls real poster/backdrop candidates from TMDb's `/collection/{id}/images` endpoint (resolved via a one-time title search cached in `collection_cache.tmdb_collection_id`, since Plex collections carry no TMDb ID of their own), and sources a logo two ways (see below).
  - **Kometa Creator** — a new, independent template (`backend/templates/kometa.py`, registered as `"kometa"`) modeled on bullmoose00's `create_poster.ps1` / Kometa-Team's `Defaults-Image-Creation` conventions: flat color or a background texture (referenced live from Kometa-Team's GitHub repo, not vendored), a 5-style gradient-fade dropdown, a centered logo (upload, Kometa's categorized logo library — also live-referenced — or a Fanart franchise logo), text, and a border. Deliberately **not** a wrapper around `uniformlogo` — its own small option-key surface (`kometa_base_color`, `kometa_white_wash`, `kometa_logo_width`, `kometa_logo_offset_y`, `kometa_texture_url`, `kometa_center_fade_strength`, plus the generic text/border/matte/fade/vignette/grain options already shared with `uniformlogo`), so a Kometa preset's stored JSON stays small and self-describing instead of silently carrying ~45 unrelated uniformlogo fields. Fonts referenced by the Kometa repo's own defaults are fetched-and-cached-on-first-use (`config/fonts_cache/`, gitignored) since PIL needs a real file on disk, not a URL.
- **Collection logos, without any manual upload needed in the common case**: TMDb's collection API has posters/backdrops but no logos at all — however, Fanart.tv's contributor community tags franchise-wide art (logo, clearart, background, banner, poster, thumb) under the **TMDb collection ID itself**, retrievable through the same `/v3/movies/{id}` endpoint used for individual films (Fanart's API doesn't care what kind of TMDb ID it's given). Verified live against the LOTR collection (TMDb id 119): 12 `hdmovielogo` + 3 `hdmovieclearart` entries, none belonging to any single film. New `GET /api/tmdb/collection/{collection_id}/fanart-logos` calls the *already-existing* `get_logos_for_movie()` unmodified — no new Fanart client code needed. Both creators load these automatically; if a collection has none (studio/curated collections with no representative single logo), a fallback lets you import a logo from any individual movie in the collection instead (new `GET /api/collection/{rating_key}/movies`, listing members via Plex's `/library/metadata/{id}/children`, same pattern already used for TV seasons).
- **Collections gained their own Save Location** (Settings → Output → `collectionSaveLocation`), Send-to-Plex support (`/library/collections/{id}/posters` instead of `/library/metadata/`, via a new `is_collection` flag threaded through `PreviewRequest`/`PlexSendRequest`/`SaveContext`), a "Refresh Cache" button, and a working per-card refresh button (previously never wired to an event handler at all — clicking it silently did nothing).
### Bug Fixes
- **Collection cache could accumulate duplicate/zombie entries with a `NULL` rating_key.** `bulk_refresh_collection_cache()`'s orphan-cleanup query used a plain `WHERE rating_key NOT IN (...)`, and SQL's three-valued logic means `NULL NOT IN (...)` is neither true nor false — so a previously-corrupted `NULL` row could never be matched and deleted by that query, regardless of how many times a good row was re-inserted alongside it. Fixed the query (`WHERE rating_key IS NULL OR rating_key NOT IN (...)`) in both the SELECT and DELETE, and added a defensive insert-time filter dropping any collection with no `rating_key` before it reaches the DB.
- **Some collections resolved to the wrong TMDb collection** — e.g. a documentary ("The Making of The Lord of the Rings Collection") instead of the real trilogy. TMDb's collection search ranking isn't franchise-priority, and every real match's title always has "Collection" appended by TMDb's own naming convention, so a naive exact-match-or-first-result approach failed. New `_best_collection_match()` (`backend/api/movies.py`) normalizes away the "Collection" suffix and prefers the shortest starts-with/contains match.

See CLAUDE.md Quirk #21 for the full Collections architecture writeup, including why the Kometa template is fully independent rather than a uniformlogo variant, and the Fanart franchise-logo mechanism.

## v1.6.54 (2026-08-20)
### Bug Fixes
- **Onboarding wizard's TMDb/TVDB "Test" buttons failed with a generic error instead of validating the key.** `testTmdb()`/`testTvdb()` in `OnboardingModal.vue` were still sending GET requests with the key in the query string, left over from before the v1.6.10 security pass made `/api/test-tmdb` and `/api/test-tvdb` POST-only with the key in the request body. `testFanart()` in the same file was already correct; its two siblings were missed. Settings page key tests were unaffected (already used the correct pattern).

## v1.6.53 (2026-08-19)
### Improvements
- **Logo drop shadow's Size/Blur slider max raised from 150px to 250px.** The backend (`add_drop_shadow()`) never had an upper bound on this value — the 150 cap was frontend-only — so this is a pure UI change, no backend clamp to touch.
### New Features
- **New Custom Text template variable: `{season number}`** — resolves to just the season's number (e.g. `3`), separate from the existing `{season}` variable which always resolves to the full English phrase (`Season 3`, `Specials`). Lets users write season text in other languages or formats — e.g. `Temporada {season number}`, `S{season number}`, or a bare `{season number}` with no "Season" word at all. Empty for series-level posters, same as `{season}`. Wired through every place `season_text` already flows (live preview, batch/webhook renders, background season pre-rendering) — see CLAUDE.md Quirk #13 for why this file has so many separate call sites that all needed the same treatment.

## v1.6.52 (2026-08-19)
### Improvements
- **Moved the logo Drop Shadow controls from the Bounding Box section into the Logo section** (both editors) — the shadow only ever applies to the logo (never Custom Text, which also uses the Bounding Box section for its optional fit-to-box mode), so it belongs with the other logo controls rather than the shared geometry section. Still gated to Uniform Logo templates only; no functional change, UI placement only.

## v1.6.51 (2026-08-19)
### Bug Fixes
- **Movie editor never saved overlay config selections into presets.** `TvShowEditorPane.vue`'s `saveCurrentPreset()`/`saveAsNewPreset()` already included `overlay_config_ids`/`overlay_config_ids_below` when writing a preset, but `EditorPane.vue`'s (movie) equivalent two functions never did — enabling an overlay config and saving a preset from the movie editor silently didn't persist that selection at all, so reloading the preset (or triggering a batch/webhook render from it) never applied the overlay. Fixed by adding the same two fields to both functions, matching the pattern already used everywhere else in both files.
### New Features
- **Deleting an overlay config now warns which presets use it, by name**, instead of a generic "this will unlink it from any presets" message regardless of actual usage. New `GET /api/overlay-configs/{id}/usage` endpoint (`db.get_presets_using_overlay_config()`) checks presets' live `overlay_config_ids`/`overlay_config_ids_below` selections (plus the legacy singular `presets.overlay_config_id` column for older data) and lists the actual preset names in the confirmation dialog. `delete_overlay_config()` was also fixed to actually strip the deleted id out of every preset's saved `overlay_config_ids`/`overlay_config_ids_below` arrays — previously it only nulled a legacy column with no live write path, leaving deleted ids to linger silently in every preset that had used them (harmless at render time — a missing config is already skipped with a warning — but confusing stale state with no way for a user to know).

## v1.6.50 (2026-08-19)
### New Features
- **Full Cover overlay image type.** A new `full_cover_image` overlay element (Overlay Manager) stretches an uploaded asset to fill the entire poster canvas — no position/scale/anchor controls, unlike the existing Custom Image type — for pre-made gradient/vignette PNGs that don't need Kometa or other external processing to apply.
- **"Place below logo & text" per overlay config.** Each overlay config selected in the manual editor's "Overlay & Border" section can now be individually flagged to render *below* the logo and custom text instead of above (the previous, still-default behavior). Implemented as a two-bucket split in the render pipeline — below-flagged overlays render right after the base poster (matte/fade/vignette/grain), everything else renders in its original position (last, after logo/text/border) — rather than three independently-orderable stages. Mirrored in both the live render path (`uniformlogo.py`) and the cached-overlay batch-render path (`rendering.py`), which reimplement logo/text compositing independently and have to be kept in sync by hand.
- **Logo drop shadow.** A Photoshop-style drop shadow (Color/Opacity/Angle/Distance/Size) for the rendered logo itself, in the Bounding Box section of both editors. New `backend/drop_shadow.py` blurs and offsets the logo's own alpha silhouette behind the sharp logo. No "Spread" control — found to cause multi-second/timeout-length renders on poster-sized images with no fast PIL alternative.
- These three features originated from an external contributor's PR (#35) — reimplemented against the current codebase (the PR was based on a commit from months earlier and wasn't mergeable as-is) with one deliberate design change from the original: the "place below" flag is relative to the logo *and* text as one group, not the logo alone, so text's position in the pipeline can't end up ignoring the flag the way it did in the original PR.

## v1.6.49 (2026-08-18)
### Improvements
- **Manual editor decluttering pass** (movie and TV editors), following up on user feedback that the editor felt "overwhelming":
  - **Renamed the Logo "Preference" dropdown to "Logo Style"** — it sat right below "Logo Mode" (whose options include "Color Match Poster"), and "Preference"/"Colored Logos" echoed that wording for an unrelated setting (which logo variant to preview vs. an automated recolor). "Manual Selection" is now "Preview Logo (Manual Selection)". An earlier draft of this change also added a hint claiming Logo Mode's recolor options "don't affect this preview" — that turned out to be incorrect (choosing Color Match Poster does recolor the logo actually shown/sent), so that hint and the "Recolor for Batch/Webhook" heading text were reverted; only the "Preference" → "Logo Style" rename shipped.
  - **Preset section now starts collapsed** by default (Poster and Logo stay open, since they're used almost every session) — cuts the default-visible control count on a fresh session. Existing users' own open/closed state (saved to localStorage) is unaffected.
  - **Poster section's asset-selection controls are now sub-grouped** ("Source", "Upload & Selection") to match the existing slider sub-groups (Position/Top Fade/Bottom Fade/Effects), instead of sitting flat above them.
  - **Fixed a real TV editor bug**: clicking a season row you were already viewing silently removed it from the render batch instead of doing nothing — a previously-reported, unfixed issue. Re-clicking the focused season is now a no-op; deselecting a focused season requires its checkbox, which already did the right thing. The season-selection function was renamed `toggleSeasonSelection` → `focusSeason` to match its narrower, clearer responsibility. A dashed/dimmed style was added for the one remaining "focused but deselected" state (only reachable via the checkbox now).
  - TV editor: "None" (season selection) renamed to "Series Only" — it never actually cleared the selection to zero, it reset to the series poster; the season-navigation arrows' tooltips now say "Previous/Next selected season" since they only cycle the selected subset, not every season in the list; TVDB source checkboxes get a tooltip clarifying they're TV-specific.
  - **"Rendered Posters" strip is no longer clickable.** Its "active" highlight didn't reliably track which season/series was actually focused in the left panel (screenshotted by the user — the strip highlighted "Season 2" while the banner and preview showed "Series"), so clicking a thumbnail could jump to a different poster than expected. Rather than chase that sync bug, the strip is now a read-only "what's been rendered this session" reference — removed the click handler, the now-dead `switchToRenderedPreview`/`cycleRenderedPreviews`/`onPreviewWheel` functions, the hover/pointer-cursor affordance, and the stale "Click to load • Scroll to cycle" hint text (the scroll-to-cycle half was already dead code, never actually wired to a wheel event).
- **Deliberately out of scope this pass**: `posterZoom` (has no UI control despite being used by the render pipeline) and `overlayFile`/`overlayOpacity`/`overlayMode` (confirmed dead — only appear in preset defaults, never read by the render pipeline) are untouched. The user wants to build real UI for the overlay-image feature separately rather than adding a slider for zoom or removing the dead fields as part of a cleanup pass.

## v1.6.48 (2026-08-18)
### Bug Fixes
- **"Save As" preset names containing spaces (or other non-slug characters) saved successfully but then permanently 400'd on every subsequent preview/render.** `POST /api/presets/save` never validated `preset_id` before writing it to the database and using it in a filesystem path (`overlays/{template_id}/{preset_id}.png`) — but `/api/preview` and other render/save paths validate it against `^[a-zA-Z0-9_-]+$` (no spaces) via `validate_preset_id()`. A preset saved as e.g. `"top overlay"` would save without error, then fail every preview afterward with a 400 that had no server-side logging (the validator raises `HTTPException` directly, which the preview route's `except HTTPException: raise` re-throws silently) — making it look broken with no visible cause.
- Fixed at the source: `api_save_preset()` (`backend/api/presets.py`) now calls `validate_preset_id()` itself, so an invalid ID is rejected immediately with a clear error instead of silently succeeding and breaking later. The "Save As" input in both editors (`EditorPane.vue`, `TvShowEditorPane.vue`) now also slugifies the entered name client-side (spaces → hyphens, other invalid characters stripped) before submitting, with a toast telling the user if their input was changed — so a natural-language name like "Top Overlay" just becomes `Top-Overlay` instead of failing later with no explanation. `/api/presets/delete` deliberately keeps accepting any `preset_id` unvalidated, so a preset already saved with an invalid legacy ID can still be deleted through the UI.

## v1.6.47 (2026-08-18)
### New Features
- **Top Matte + Fade** — a mirrored, fully independent counterpart to the existing bottom matte/fade effect. New `top_matte_height_ratio`/`top_fade_height_ratio` options (same 0–0.5/0–1 ranges and clamps as their bottom counterparts) darken the top of the poster instead of, or in addition to, the bottom. Both are `0.0` by default, so no existing preset or saved poster changes appearance unless a user explicitly turns it on.
- Implemented in lockstep in both places the matte/fade math lives: `build_base_poster()` (`backend/templates/universal.py`, the live vectorized-numpy render path used by every actual render) and `generate_overlay()` (`backend/rendering.py`, the cached-overlay path baked on preset save for fast batch rendering). Both combine their bottom and top alpha contributions via `max()` per row rather than addition, so a poster with both sliders cranked high never exceeds full black in the overlap region and the two sliders behave independently of each other's value.
- Manual editor: the "Poster" section's previously-flat "Adjustments" group (Poster Shift Y, Matte Height, Fade Height, Vignette, Grain, all undifferentiated) is now split into four labeled sub-groups — Position, Top Fade, Bottom Fade, Effects — using the same `sub-section-title` pattern already used in the Logo section. The existing bottom sliders are relabeled "Bottom Matte Height %"/"Bottom Fade Height %" for clarity now that a top counterpart exists. Applied to both `EditorPane.vue` (movies) and `TvShowEditorPane.vue` (TV shows); the two new fields are also wired into the TV editor's per-season field-modification-tracking system (`markFieldModified`/`presetFields`) so a season's top-matte/fade value correctly falls back to the preset's saved value when untouched, rather than freezing at whatever was last on screen (the same mechanism documented in CLAUDE.md's TV editor season-state notes).

## v1.6.46 (2026-08-18)
### Bug Fixes
- **`{folder}` never resolved on any "Send to Plex" path — always fell back to the plain, possibly Plex-localized, title with no year.** Reported by an external contributor (PR #28/#29) with two clean repro cases: a same-title movie losing its year ("Toy Story 5" instead of "Toy Story 5 (2026)"), and a French-localized title resolving to the Plex display title ("L'impasse") instead of the real on-disk folder name ("Carlito's Way (1993)"). Root cause: `backend/api/save.py` (manual Save to Disk) and `backend/api/batch.py` (batch/webhook save *and* send) both correctly resolve the real on-disk folder name via `get_movie_folder_name()` before building a `SaveContext`, but `backend/api/plexsend.py` (manual Send to Plex, and the resend/preview endpoints that need to find a file saved that way later) had six separate `SaveContext` constructions that never called it at all — not gated behind a setting, just entirely missing.
- Fixed by resolving `folder_name` in all six, matching `batch.py`'s existing gating exactly (movies only; only when "save to asset folder on send" is enabled, since that's the only thing that reads it — the setting is off by default, so this doesn't add a Plex round-trip to a plain Plex send for most users). The one bulk-lookup site (`/api/render-cache/cached-keys`, which checks every cached movie for a resendable file) additionally only pays for the per-movie Plex fetch when the user's actual save template contains `{folder}` at all, checked once up front — otherwise a large library would mean one live Plex call per movie on every page load for no reason.
- Verified directly against both of the reporter's repro cases: `{folder}` now resolves to `Toy Story 5 (2026)` and `Carlito's Way (1993)` respectively, matching what Save to Disk already produced.

## v1.6.45 (2026-08-17)
### New Features
- **Local Assets: bulk delete.** The multi-select checkboxes (previously limited to resendable posters, for bulk-resend) now work on any asset, and a "Delete N" button sits next to "Resend N to Plex" in the selection bar. New `POST /api/local-assets/delete-bulk` endpoint, sharing the same per-file delete + empty-folder-cleanup logic as the existing single-file `DELETE` endpoint (extracted into `_delete_local_asset_file()`).

### Performance
- **Two render-pipeline speedups, both purely about I/O timing — no change to rendered pixels, encoding, or quality settings:**
  - `render_with_overlay_cache()` (the batch/webhook render path when the overlay cache is enabled) had its own bespoke image downloader instead of reusing the shared `_download_image()` helper — meaning it got none of that helper's LRU byte cache, retry/backoff on slow connections, SSRF validation, or SVG logo support. Switched it over: same decode, same bytes, but repeated renders of the same poster/logo now skip the network entirely after the first fetch, and SVG logos (previously a latent crash in this specific path) now work correctly too.
  - `render_poster_image()` (the path live preview always uses) downloaded the poster and logo **sequentially** instead of in parallel, unlike the batch path which already fetched both at once. Parallelized it the same way — measured 4.4x faster on a cold cache (no visible poster/logo yet fetched this session), which is exactly the "opening the editor for a new movie" moment most likely to feel slow. Once both are cached from the first fetch, this made no difference either way.

## v1.6.44 (2026-08-13)
### Security
- **Follow-up dependency audit**, triggered by GitHub Dependabot alerts after enabling dependency graph/security scanning on the repo. Applied what actually had a fix available:
  - Backend: `requests` 2.32.5 → 2.34.2.
  - Frontend: `npm audit fix` (no `--force`) resolved `js-yaml` (quadratic CPU consumption in `!!omap` resolution) and `nanoid` (non-terminating loop with negative/zero size) — both down to 0 vulnerabilities per `npm audit`.
- **Not fixed, no action available yet**: `pillow` (12.3.0), `cairosvg` (2.9.0), and `python-multipart` (0.0.32) are already pinned at the newest version published on PyPI for each — the GitHub alert doesn't have a fixed version to move to yet. Nothing to do but wait for upstream.
- **Still deliberately deferred**: the `starlette` CVEs (pulled in transitively via FastAPI) still have no fix within FastAPI 0.122.0's allowed range — same root cause documented in v1.6.23, unchanged. Fixing requires bumping FastAPI to 0.141.1+, a large jump that needs its own dedicated testing pass.
- **Discrepancy worth noting**: GitHub's alert list also flagged `shell-quote`, `postcss`, `brace-expansion`, `vite`, `flatted`, `minimatch`, and `rollup` in `frontend/package-lock.json` — a fresh `npm ci` + `npm audit` against the exact committed lockfile shows none of these as vulnerable at their current pinned versions. GitHub's Advisory Database and npm's own audit registry don't have full parity in coverage; this isn't a contradiction so much as two different databases disagreeing. All of these are frontend *build tooling* (not shipped in the built bundle users' browsers load), so real-world exposure is limited to the dev/CI environment even if the alerts turn out to be accurate — worth revisiting via the specific GHSA advisory IDs if they don't clear on their own after GitHub's next scan.

## v1.6.43 (2026-08-13)
### New Features
- **Added a `{folder}` save-path variable** (Settings → Output) that resolves to the real on-disk folder name Plex knows for a movie — parsed from Plex's own file path, not derived from the display-language title — for save-location templates that need to match folder names created by Radarr/Sonarr/Kometa rather than Plex's metadata title. Falls back to `{title}` for TV shows/seasons or whenever it can't be resolved. Thank you romquenin for the suggestion!

### Bug Fixes
- **Fixed the filename sanitizer stripping valid punctuation** (commas, apostrophes, ampersands, etc.) from saved poster filenames, causing them to drift from the real on-disk names Radarr/Sonarr/Kometa use — e.g. "Widow's Bay" was being saved as "Widows Bay". The sanitizer now only strips characters that are actually illegal in Windows/Linux filenames instead of whitelisting a narrow allowed set.

### Other
- Docker builds no longer need `.git` in the build context — the branch name is now passed in explicitly as a `GIT_BRANCH` build-arg instead of being detected via `git rev-parse` at build time (which required copying `.git` into the image and installing/removing `git`+`jq`). Local build scripts and the GHCR CI workflow were updated to pass it.

## v1.6.42 (2026-08-13)
### Improvements
- **Changing the preset in the TV show editor now refreshes every other selected season/series, not just the one you're currently viewing.** `watch(selectedPreset, ...)` previously only applied the new preset to the currently-focused poster — every other season/series kept its `settingsCache` entry (and rendered preview thumbnail) from whatever preset was selected before, so switching to one of them showed stale settings until something else happened to trigger a fresh render. It now clears all cached settings and rendered previews (except the one you're actively viewing, which the normal preview flow already handles) and triggers a background re-render of everything else, matching how "Select All Seasons" already works.

## v1.6.41 (2026-08-13)
### Bug Fixes
- **"Restrict Custom Text to this box" could silently ignore a season's saved preset value.** `TvShowEditorPane.vue` tracks which season-specific fields the user has explicitly customized (`userModifiedFields`) so an untouched field falls back to the preset's own saved value instead of whatever happens to be on screen — `textBboxEnabled` was never added to that tracking (or to its `presetFields` allowlist) when the bbox feature shipped, so it was always treated as "explicitly modified," meaning a season's local session cache permanently froze whatever bbox state was on screen the first time you viewed that season, silently overriding the preset's actual saved value on every subsequent visit or save. Also missing from the two (duplicated) `fieldsToRemove` lists used when background-rendering other selected seasons, which had the same effect for seasons you hadn't directly opened in the current session. Fixed by adding `textBboxEnabled` to all three lists, matching how `textOverlayEnabled`/`logoMode`/etc. already work.

## v1.6.40 (2026-08-13)
### Bug Fixes
- **Text could render outside the bounding box when top/bottom-aligned.** `_render_text_overlay()` (`backend/templates/universal.py`) measured each line's height/position using PIL's *tight* glyph bounding box, but drew the text using PIL's default anchor, which positions relative to the font's ascender line — a gap that varies with content (~18px for all-caps text, ~38px+ with descenders, at 100px Arial Bold). That gap barely showed with the old always-centered behavior (slack on both sides absorbed it), but v1.6.39's top/bottom alignment has zero slack on the aligned edge, so the text visibly overflowed past the box. Fixed by measuring and compensating for each line's actual top offset at draw time, so the real rendered pixels land where the box-fit math intends. Verified: bottom/top-aligned text (including a case with descenders) now stops exactly at the box edge instead of overflowing, and center alignment is now slightly more precisely centered too (same fix, just less visually obvious there since it was smaller before).

## v1.6.39 (2026-08-13)
### Bug Fixes
- **The Bounding Box section's Horizontal/Vertical Align buttons had no effect on Custom Text.** They were only ever consumed by the logo renderer (`backend/templates/uniformlogo.py`) — `_render_text_overlay()`'s bbox mode (`backend/templates/universal.py`) always centered the text block on the box's center point regardless of what those buttons were set to. Fixed by positioning the text block (using its actual measured size, which is often smaller than the box after the auto-shrink-to-fit font search) within the box the same way the logo already does, only when Horizontal/Vertical Align isn't left at "center" — `text_align` (left/center/right per-line justification) continues to work exactly as before within whatever width that leaves. Verified against all 9 alignment combinations and confirmed no change to existing center-aligned or non-bbox rendering.

## v1.6.38 (2026-08-13)
### Improvements
- **"Show bounding box" moved from the preview toolbar into the new Bounding Box section** (movie and TV editor), alongside "Restrict Custom Text to this box" and the box's geometry sliders — everything about the bounding box now lives in one place instead of being split between the preview toolbar and an accordion section.

## v1.6.37 (2026-08-13)
### Bug Fixes
- **TV show editor: settings (bounding box and everything else) didn't update when navigating between series/seasons with the ‹ › arrow buttons.** Every other way of switching focus (clicking a season in the list, clicking a thumbnail in the rendered-posters strip) flushes the outgoing target's edits and loads the incoming target's cached settings — `nextSeason()`/`prevSeason()` (the arrow buttons) did neither, just changing `currentSeasonIndex` directly. Fixed by having both call `saveCurrentSettings()` before switching, and adding `restoreSettingsForCurrent()` to the shared `watch(currentSeason, ...)` handler so any path that changes the current season — including these two — reliably loads the right settings, rather than requiring every switch function to remember to do it itself.

## v1.6.36 (2026-08-13)
### Improvements
- **"Bounding Box" is now its own accordion section** in the manual editor (movie and TV), between Custom Text and Overlay & Border, instead of living inside Logo. Direct follow-up to v1.6.35: that fix kept the box's Position & Size sliders visible regardless of Logo Mode, but they still lived under the Logo heading, which was a confusing home for something that's really shared geometry between Logo and Custom Text, not a logo-only setting. The section (Max Width/Height, Box X/Y%, alignment, plus the "Restrict Custom Text to this box" toggle — moved out of the Custom Text panel) only appears for Uniform Logo templates, since the box concept doesn't apply otherwise. `TextOverlayPanel.vue`'s `bboxEnabled` prop/emit was removed since the toggle no longer lives inside it.

## v1.6.35 (2026-08-13)
### Bug Fixes
- **Enabling "Restrict to Logo Bounding Box" on Custom Text left you with no way to adjust the box.** The Logo section's "Position & Size" controls (Max Width, Max Height, Logo Box X/Y%, alignment) were wrapped in the same `v-if` as the logo picker (preference, source filters, upload, thumbnails) — all of it hidden whenever Logo Mode is set to "No Logo". But that's exactly the setup text-bbox mode is meant for (text taking the place of a logo), so turning it on made the very sliders that define the box disappear along with the logo picker. Moved "Position & Size" out from under that condition in both `EditorPane.vue` and `TvShowEditorPane.vue` — it now stays visible for Uniform Logo templates regardless of Logo Mode, since it's shared, dual-purpose geometry (logo box when there's a logo, text box when there isn't).

## v1.6.34 (2026-08-13)
### Bug Fixes
- **Editing a season poster's settings (e.g. the logo bounding box) could bleed into the series poster too, permanently.** `selectedPosterType` (`frontend/src/components/editor/TvShowEditorPane.vue`), the flag that decides whether "Save Preset" writes into the series' base `options` or the season's `season_options`, was a `ref` kept in sync with `currentSeason` by a separate `watch()` callback rather than being derived synchronously. That left a window where code could read a stale `selectedPosterType` right after switching between series and a season but before the watcher had actually run — and if a save happened to land in that window, a season-specific edit (like a custom bounding box) could get written into the series' shared base `options` instead of the season's own diff, corrupting the series poster's settings too, not just that season's.
- Fixed by making `selectedPosterType` a `computed()` derived directly from `currentSeason` instead of a separately-synced `ref` — it's now always correct at the instant it's read, with no window where it can lag behind which poster is actually in focus.

## v1.6.33 (2026-08-13)
### Bug Fixes
- **TV show editor: the rendered-posters strip could highlight the wrong thumbnail.** Clicking a season in the left season list that was already selected and already had a cached render (e.g. switching between Series and Season 2 after both had been previewed) correctly swapped the big preview image, but left the highlighted thumbnail in the "Rendered Posters" strip below pointing at whichever season was rendered most recently rather than the one now actually being viewed. `toggleSeasonSelection()` (`frontend/src/components/editor/TvShowEditorPane.vue`) now updates `activePreviewIndex` alongside `lastPreview` when switching to an already-rendered season.

## v1.6.32 (2026-08-12)
### Improvements
- **TV preset ("template") bloat fix — second of the season-poster improvements from Quirk #13.** TV presets store two option blobs, `options` (series) and `season_options` (seasons), and `season_options` was always saved as a full duplicate of every field (~45 keys) even though only ~8 typically ever differ from the series preset (`logo_mode`, `text_overlay_enabled`, `custom_text`, `font_size`, `letter_spacing`, `position_y`, `shadow_enabled`, `shadow_blur`). This roughly doubled preset size for no reason, and that duplication propagated through every duplicate/rename/export of a TV preset — the exact "templates get way too large to copy/move" complaint.
- `season_options` is now stored as a **diff** — only the fields that actually differ from `options` — reconstructed via a new `resolve_season_options()` merge wherever season posters are actually rendered or displayed (batch rendering, live preview, the manual editor, and the Template Manager's season tab). All four of those consumers previously picked `season_options` *wholesale* instead of merging it with `options`, which would have silently broken season rendering once storage went sparse — fixed as part of this change, not left as a follow-up risk.
- **Existing presets are migrated automatically on startup** — a preset saved before this release with a full-copy `season_options` gets shrunk in place to a diff the first time the app starts on v1.6.32, with no change in rendered output (verified: merging the new diff back onto `options` reconstructs the exact original season values). The migration is idempotent, so it's safe to run on every startup.
- `GET /api/presets/export-compact` (used by "Copy Compact" in Template Manager) now exports `season_options` as a true diff against `options` instead of the previous "include the whole block unless byte-identical" check — compact exports of TV presets are substantially smaller.
- No frontend save-path changes were needed — the diffing is centralized server-side (`db.diff_season_options()`, called from every write path: `/presets/save`, `/presets/save-season-options`, import/merge, and the startup migration), so any caller sending a full options blob gets it reduced automatically before it touches the database.

## v1.6.31 (2026-08-07)
### Bug Fixes
- **TV show manual editor: a stale season preview could land on the wrong season.** Switching seasons while a preview render was still in flight — e.g. the "delayed render" case where a slow response arrives after you've already moved on — could cause that response to overwrite whatever season you'd since switched to, since the result was attributed to "whatever season is currently focused when the response arrives" rather than "the season the request was actually for." `doPreview()` (`frontend/src/components/editor/TvShowEditorPane.vue`) now captures the season at request time and, once the response arrives, only updates the visible preview if that season is still the one in focus — otherwise the result is still cached (so it's instant if you click back to it) but doesn't clobber the currently-displayed poster. This is the first of a few season-poster UX improvements planned — see CLAUDE.md Quirk #13 for the full mechanism and what's still on deck (the season-selection click/checkbox behavior, and preset bloat from duplicated season options).

## v1.6.30 (2026-08-07)
### Bug Fixes
- **"Simposter Asset" studio/streaming badges (`badge_mode: "asset"`) failed to render in the Overlay Manager preview** with a `502` and a log line like `[OVERLAY] Refused to fetch URL badge: Refusing to fetch URL (Private/internal network URLs are not allowed): http://<host>:8003/api/asset-image?slug=a24`. The preview canvas (`OverlayConfigManagerView.vue`) built the correct, same-origin `/api/asset-image?slug=...` URL, then unnecessarily routed it through `/api/proxy-image` — a generic CORS-relay endpoint meant for genuinely external URLs (`badge_mode: "url"`). That endpoint's SSRF guard (`assert_external_fetch_safe`, strict mode, no private-network exceptions) correctly refused to fetch a URL pointing back at the app's own LAN address. This only started failing after v1.6.10's SSRF hardening closed the private-IP loophole the double-proxy had been silently relying on since the "asset" preview mode was added — actual poster rendering (`backend/templates/universal.py`) was never affected, since it resolves and fetches the real `raw.githubusercontent.com` asset URL directly, with no proxy involved. Fixed by loading the same-origin `/api/asset-image` URL directly in the preview (new `loadDirectImage()` helper), skipping the proxy relay entirely — it was never needed for a same-origin request.

## v1.6.29 (2026-08-07)
### Bug Fixes
- **The retry queue could silently empty itself on a transient failure** — e.g. a brief TMDb DNS/network blip during a scheduled retry pass. `_run_poster_retry()` (`backend/scheduler.py`) determined whether an item still needed retrying by reading a `needs_retry` key off the render result, but when `process_single_movie_poster()`/`process_single_tv_show_poster()` catch an internal exception they return an error dict with no such key (or, for TV, no populated `results` list) — `.get("needs_retry", False)` then defaulted to "doesn't need retry," so the item was marked resolved and removed from the queue even though nothing was actually fixed. A single bad retry pass (e.g. one DNS lookup failure affecting every pending item at once) could wipe the whole queue in one run. Fixed by defaulting to "still needs retry" when the result doesn't clearly say otherwise, matching the already-correct logic in the manual "Retry Now" button (`backend/api/history.py`).
- **"Unknown"-titled FAILED entries in History** were a symptom of the same class of failure: when a render errors out before the movie/show title is ever fetched from TMDb (e.g. that same network blip, on the very first API call), the history entry was recorded with `title=None`, which the History table renders as the generic "Unknown" — with no way to tell which library item it was. Both `_process_single_movie` and `_process_single_tv_show` (`backend/api/batch.py`) now fall back to `(rating key {rating_key})` instead, so a failed entry with no title is still identifiable.

## v1.6.28 (2026-08-05)
### Bug Fixes
- **v1.6.26's logo-cropping fix only covered the standalone "Send Logo to Plex" button** (`POST /api/plex/send-logo`) — the same raw-passthrough bug (fetched logo bytes uploaded to Plex's `clearLogos` endpoint completely untouched, no PIL re-encode) was independently duplicated in `backend/api/batch.py`'s logo-upload logic, which is what actually runs for batch renders, webhooks, the retry queue, and auto-generate — i.e. the "Also send logos to Plex" checkbox in day-to-day use, not just the standalone button. That path was untouched by v1.6.26 and would still have produced cropped-looking logos in Plex.
- Extracted the normalization into a shared `normalize_logo_for_plex()` helper (`backend/api/save.py`) and routed both of `batch.py`'s duplicated logo-upload blocks (movie batch and TV/season batch — same code, verified byte-identical between the two) through it, alongside the already-fixed standalone endpoint. All logo-to-Plex paths now go through one function. Verified directly: a synthetic indexed-palette PNG normalizes correctly to clean RGBA, and unparseable bytes fall back to the original bytes/content-type rather than failing the upload.

## v1.6.27 (2026-08-04)
### New Features
- **Text overlay bounding box**: custom text overlays can now be restricted to a bounding box, so font size automatically shrinks (down to a configurable floor, default 20px) instead of overflowing. Rather than adding a new, separate box size/position setting, "Restrict to Logo Bounding Box" reuses the *same* box the Uniform Logo template already reserves for the logo (Logo section → Max Width/Height/Position) — no new parameters to configure. This is deliberately convenient for the common case of a season poster or similar with Logo Mode set to "No Logo" and text taking its place: the text now fills exactly the space the logo would have used. The existing "Show bounding box" preview toggle (previously nested inside the Logo section, only relevant to the logo) moved out to the preview toolbar next to "Send logo," since it's now equally relevant whichever content — logo or text — currently occupies the box. Off by default; existing presets/text overlays are unaffected. Implemented as a binary search over candidate font sizes in `_render_text_overlay()` (`backend/templates/universal.py`), re-using the existing line-wrap/measure logic at each candidate size so it fits the *actual* wrapped line count rather than assuming a linear relationship between font size and block height.

### Documentation
- **Clarified the scope of Settings → Output → Image Quality**: these settings (format, JPEG/PNG/WebP quality) only govern the live Preview and "Save to Disk" — they were easy to mistake for also controlling Send-to-Plex quality. A fresh "Send to Plex" always uses the best quality that fits regardless of this setting (PNG when it's under Plex's upload size limit, otherwise a high-quality JPEG — see `encode_poster_for_plex()`, v1.6.19–v1.6.24). The one exception is *resending* an already-saved file (e.g. bulk resend from Local Assets), which reuses that file's original on-disk bytes as-is — so a file saved at a lower quality here will still resend at that lower quality later. Added this explanation directly into the Image Quality section (`OutputTab.vue`).

## v1.6.26 (2026-08-04)
### Bug Fixes
- **Standalone "Send Logo to Plex" could appear cropped once uploaded**, even though the same logo looked correct in preview and when composited into the poster. Traced to the standalone send path forwarding the raw source bytes (from TMDb/Fanart/upload) completely untouched, unlike every other image path in the app which always re-encodes through PIL. `POST /api/plex/send-logo` now normalizes the logo through PIL (decode → convert to clean RGBA → re-encode as PNG) before upload, ruling out source format quirks (indexed/palette color, ICC profiles, interlacing, unusual bit depth) without touching dimensions or aspect ratio at all. Verified against a synthetic indexed-palette PNG with transparency — correctly normalizes to clean RGBA, preserving both opaque content and transparent regions.

## v1.6.25 (2026-08-04)
### Bug Fixes
- **Selecting an item from the global search bar while already editing something could silently bounce back to the library grid** instead of opening the newly selected item, or intermittently fail to navigate at all. Root cause: `handleSearchSelect()` (`App.vue`) navigated via `router.push({ name: ... })` without setting the `edit` query param that a separate `watch(() => route.query.edit, ...)` watcher depends on to know whether the editor should be open — when that watcher saw the param disappear (dropped by the incomplete navigation), it treated it as "user closed the editor" and cleared the selection right after search had just set it. Fixed to build the same `{ ...route.query, edit: itemId }` navigation that the normal grid-click handler already uses correctly.

## v1.6.24 (2026-07-31)
### Bug Fixes
- **Root cause found for the `500 Internal Server Error` some users hit when sending to Plex after v1.6.22's always-PNG change: Plex's `/posters` endpoint rejects uploads over roughly 10MB.** At the app's fixed 2000x3000 render canvas, a PNG (lossless) encode of a poster with a lot of fine detail or heavy grain can cross that threshold, and Plex responds with a bare 500 rather than a clear "too large" error — which is exactly why it could work fine on one server/poster and fail on another with the same code: it depends on how large that specific poster's PNG happens to be, not on the Plex server itself.
- **Fix**: `encode_poster_for_plex()` (`backend/api/save.py`) now encodes PNG at maximum compression and checks the actual output size — if it's still over the limit (leaving headroom under Plex's real cap), it automatically falls back to a high-quality JPEG (quality floor 98, no chroma subsampling) for that poster instead of sending something Plex will reject. Most posters stay PNG (verified: a synthetic poster using this app's actual max-intensity grain effect at full 2000x3000 resolution encoded to ~3.75MB, well under the limit); only unusually large/detailed ones fall back automatically. Also flattens to RGB before encoding either way, dropping a functionally-meaningless alpha channel that the render pipeline leaves in.
- Bulk resend from Local Assets gets the same size-aware fallback: an on-disk PNG over the limit re-encodes as JPEG at upload time instead of failing; on-disk JPEG files are unaffected (JPEG file sizes were never the problem) and still upload as-is with zero extra generation loss.
- Verified: backend imports cleanly; a pure-noise pathological test image (PNG far over the limit) correctly triggers the JPEG fallback; a realistic max-grain poster stays PNG and well under budget.

## v1.6.23 (2026-07-31)
### Security
- **Dependency audit and patch**: ran `pip-audit` against `requirements.txt` and `npm audit` against the frontend. Applied all low-risk, same-major-version fixes and verified them (package imports, JPEG/PNG encode round-trip, full backend import):
  - Backend: `requests` 2.32.3→2.32.5, `python-dotenv` 1.0.1→1.2.2, `python-multipart` 0.0.20→0.0.32, `pillow` 12.0.0→12.3.0, `cairosvg` 2.7.1→2.9.0.
  - Frontend: `npm audit fix` (no `--force`) resolved the critical (shell-quote) and moderate (ajv) findings plus most highs (vite, rollup, postcss, @babel/core) — all devDependencies (build tooling), none shipped to end users.
- **Two findings deliberately deferred, not fixed in this release**:
  - **Starlette** (pulled in transitively via FastAPI) has several known CVEs, but none are patched within FastAPI 0.122.0's allowed range (`starlette<0.51.0`) — the fixes only exist in starlette 1.x. Getting them requires bumping FastAPI itself to 0.141.1 (a 19 minor-version jump), which touches routing/middleware behavior across every API router in the app. This needs its own dedicated testing pass, not a same-session bundle with five other fixes.
  - **ESLint 9.x's dependency tree** has a `minimatch` ReDoS (15 "high" npm audit findings, all inside eslint/typescript-eslint/eslint-plugin-vue). Pure lint tooling, never shipped to users, low real-world exploit risk. Fixing requires forcing ESLint to a major version bump (9→10) with config/plugin compatibility risk — deferred until a deliberate ESLint 10 upgrade.

## v1.6.22 (2026-07-31)
### Improvements
- **Send-to-Plex now always uploads a lossless PNG, regardless of the configured local save format** — a direct follow-up to v1.6.21, after a user confirmed they could still see faint artifacts on a sent poster even with that fix in place. Rather than continuing to chase the "right" JPEG quality/subsampling combination, `encode_poster_for_plex()` (`backend/api/save.py`) now skips JPEG entirely for freshly-rendered Plex uploads (manual send, batch, and the two batch send paths) — a Plex upload is a one-time transfer, not a disk-space-constrained archive copy, so there's no good reason to introduce any lossy generation there at all. Bulk resend from Local Assets is unchanged (still uploads the exact bytes already on disk — if that file was originally saved as JPEG, converting it to PNG post-hoc wouldn't recover any lost quality, so it stays as-is).
- **Still experimental**: as with v1.6.21, it's unconfirmed whether all Plex Media Server versions handle PNG poster uploads without issue. If this introduces new problems (upload rejections, broken thumbnails), the fix is reverting `encode_poster_for_plex()` to a JPEG encode again.

## v1.6.21 (2026-07-31)
### Bug Fixes / Improvements
- **Send-to-Plex could still show visible JPEG artifacts even after the v1.6.19 chroma-subsampling fix**, for users comparing against manually re-uploading their saved poster through Plex's own UI. Root cause: every Plex-upload code path unconditionally force-converted the render to JPEG, regardless of the user's configured local save format — so a user saving as PNG (lossless) and manually uploading that file to Plex themselves got a genuinely lossless poster, while Simposter's own "Send to Plex" always introduced a fresh lossy JPEG generation on top, even at high quality. Send-to-Plex (manual send, batch, and bulk resend from Local Assets) now uploads PNG when the user's output format is set to PNG, matching what a manual re-upload already produced. WEBP has no native Plex poster support, so WEBP-configured users still get JPEG, same as before. For users staying on JPEG, the Plex-bound copy's quality now floors at 98 (previously tied 1:1 to the local-save quality setting, which some users have lower for disk-space reasons) since this copy also goes through Plex's own thumbnail generation — a second lossy pass on top of ours. Bulk resend from Local Assets now uploads the exact bytes already on disk instead of re-encoding them at all, for zero additional generation loss on either format.
- New shared `encode_poster_for_plex()` helper (`backend/api/save.py`) replaces four separate, slightly-diverged inline JPEG-encode blocks across `plexsend.py` and `batch.py`.
- **This is a partial-confidence fix, not a guaranteed one** — Plex uploads were locked to JPEG-only in an earlier version for a reason that wasn't clearly documented, so it's possible (though unconfirmed) that some Plex Media Server versions handle PNG poster uploads worse than JPEG. Worth confirming with affected users that PNG sends actually look correct in their Plex library before considering this fully closed.

## v1.6.20 (2026-07-31)
### Bug Fixes
- **Docker build could fail with `Unable to connect to deb.debian.org` / `E: Unable to locate package fonts-dejavu-core`**: the Dockerfile ran two separate `apt-get update && apt-get install` passes (one for `git`/`jq`, a later one for `fonts-dejavu-core`/`fonts-liberation`/`gosu`), each a fresh opportunity for a transient DNS/connection blip to Debian's mirror network to hard-fail the whole build. Merged into a single `apt-get update`/`install` pass covering all five packages, and added `-o Acquire::Retries=5` so a transient blip retries within the build instead of failing it outright. Verified with a full local `docker build` — image builds successfully, fonts/gosu install correctly, and `git`/`jq` are still purged afterward as before (they're only needed transiently to detect the git branch and generate `build-info.json`).

## v1.6.19 (2026-07-31)
### Bug Fixes
- **Visible artifacts (color bleeding/blockiness) appeared on posters only after sending to Plex, not in the preview or a local save**: every JPEG encode in the render pipeline (`preview`, `save`, `batch`, `send-to-Plex`) relied on Pillow's default JPEG chroma subsampling (4:2:0 — halves color resolution), which is normally not very noticeable but becomes visible as color bleeding around saturated edges (colored clearlogos, badges, title text) and interacts badly with this app's grain/noise effects. Because posters sent to Plex are *always* re-encoded as JPEG regardless of your configured local save format (a deliberate, pre-existing choice — Plex's poster upload endpoint is JPEG-only in practice), anyone saving locally as PNG (lossless) would only ever see the subsampling artifact on the copy that actually reaches Plex, never in preview or on disk. All JPEG encodes now use full 4:4:4 chroma (no subsampling); measured on a synthetic saturated-edge test image, this cut average color error at a hard color boundary by ~60% (mean abs error 7.3 → 2.8, max 45 → 16) at the cost of roughly 2x JPEG file size — a reasonable tradeoff for final poster artwork. No settings changed; this applies automatically to all future sends/saves.

## v1.6.18 (2026-07-31)
### New Features
- **Logo upload**: the manual editor's Logo section (movies and TV shows) now has a drag-and-drop / click-to-upload zone, matching the existing custom poster upload. Uploaded logos can be selected, replaced, or removed just like an uploaded poster, and are sent through the same preview/save/send pipeline as any TMDb/Fanart-sourced logo. The shared upload endpoint (`POST /api/upload/background`) now takes an optional `kind` field so uploaded logos are saved with a `logo_` filename prefix instead of `bg_`, purely for readability if you ever browse the `uploads/` folder directly — existing callers are unaffected.

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
