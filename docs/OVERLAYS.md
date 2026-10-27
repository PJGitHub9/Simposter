# Overlays

Overlays are badges, images and text drawn on top of a poster: a 4K or Dolby Vision badge, the audience rating, a "NEW SEASON" ribbon, a frame. Simposter draws them into the poster it renders, so whatever server receives the poster (Plex, Jellyfin, Emby) shows them.

This guide covers building overlays, the rules that decide which posters get which layers, importing Kometa overlay files, ratings and lists from MDBList, and keeping posters up to date when their overlay would change.

- [What overlays can do](#what-overlays-can-do)
- [How overlays fit in](#how-overlays-fit-in)
- [Building an overlay](#building-an-overlay)
- [Show when: rules](#show-when-rules)
- [Text with values](#text-with-values)
- [Badge sets and hide rules](#badge-sets-and-hide-rules)
- [Importing Kometa overlays](#importing-kometa-overlays)
- [MDBList ratings and lists](#mdblist-ratings-and-lists)
- [Lists from WeTrakr, SIMKL and Floppy](#lists-from-wetrakr-simkl-and-floppy)
- [Scheduler](#scheduler)
- [Overlay Refresh](#overlay-refresh)
- [Live Kometa files](#live-kometa-files)
- [Sharing overlays](#sharing-overlays)
- [Reading the overlay log](#reading-the-overlay-log)
- [Limits](#limits)

---

## What overlays can do

**Show information about the item**
- Quality badges: resolution (4K, 1080p…), HDR/Dolby Vision (from the file name), video codec, audio codec, channels and language, with a different image or text per value.
- Edition (Director's Cut, Extended, IMAX…), studio or TV network logo, and where the title streams.
- Ratings from IMDb, Rotten Tomatoes, Metacritic, TMDb, Trakt, Letterboxd, MyAnimeList and the MDBList score, as a number on the poster or as a rule (e.g. a frame only above 8.5). Needs an MDBList key.
- Any text, with values filled in per item: `{title}`, `{year}`, `{audience_rating}`, `{resolution}`…

**Decide which posters get which layers**
- Rules on resolution, codecs, audio, file name (patterns), edition, labels, year, title, studio, streaming service, ratings, days since added, show status, TMDb/TVDB ID lists, and membership of lists on MDBList, WeTrakr, SIMKL or Floppy.
- Badge sets: show only the best match of several (e.g. "4K DV" over "4K HDR" over "4K").
- Hide rules: one layer hides others when it's drawn.
- Rules for a whole overlay (e.g. only for 4K items).

**Work with movies, TV shows and seasons**
- TV shows and seasons use their best episode's quality: a show with any 4K episode counts as 4K, as in Kometa, and each season poster uses its own episodes. Run a TV scan to fill this in.

**Look the way you want**
- Your own images, image links, full-poster frames, text in any font (yours, Simposter's font collection, or Kometa's), background boxes with rounded corners and borders, outlines, blur, and Kometa-style positions and queues.

**Reuse what you have**
- Import Kometa overlay files (including Kometa's own default templates, UMTK and TSSK), or keep an overlay in step with a file another tool rewrites daily.
- Share a preset together with its overlays and images as a single file.

**Stay current**
- Overlay Refresh finds posters whose overlay would now look different (a new rating, a list, an upgrade, an edited overlay) and re-sends them, on a schedule or right after you edit an overlay, and says what changed.

Works with Plex, Jellyfin and Emby. Labels and editions come from Plex only; see [Limits](#limits).

---

## How overlays fit in

- An **overlay** is a named set of **layers**. You build overlays in **📐 Overlays** (sidebar).
- An overlay does nothing until it's turned on in a **preset** (Template Manager) or in the poster editor (**Extras → Overlays**). A preset can use several overlays.
- Each overlay sits **above** the logo and text by default; tick **Place below logo & text** next to it in the editor's Extras → Overlays to draw it underneath.
- Overlays apply wherever that preset renders: the manual editor, Batch Edit, webhooks, auto-generate and the retry queue.
- The Uniform Logo template supports overlays. The Kometa collection template doesn't.

Simposter renders the poster from the original artwork with the overlay baked in. It doesn't stack badges on top of whatever poster is currently on your server, so a poster never collects two copies of the same badge.

---

## Building an overlay

Open **📐 Overlays** and create an overlay. The editor has a preview on the right and three tabs on the left:

1. **Layers**: the layers, top of the list = drawn on top. Drag on the preview to move a layer; use the ↑ ↓ buttons to change its order.
2. **Badge sets**: groups of layers where only one is shown (see [below](#badge-sets-and-hide-rules)).
3. **Show overlay when**: rules for the whole overlay. When they don't match an item, none of its layers are drawn.

### Layer types

**+ Add layer** offers:

| Layer | What it shows |
|-------|---------------|
| **Video** | Resolution or video codec, with a different image or text per value |
| **Audio** | Audio codec, channels or language, per value |
| **Edition** | Director's Cut, Extended, IMAX… (Plex editions) |
| **Streaming** | Where the title streams, from TMDb, for the region you pick |
| **Studio** | The studio or TV network logo |
| **Image** | One of your images, or an image link |
| **Text** | Any text, with [values](#text-with-values) like `{audience_rating}` |
| **Full-poster image** | An image stretched over the whole poster, e.g. a frame (use a PNG with a see-through middle) |

Imported Kometa files can also create **background box** layers (a coloured box with no image or text).

For the badge layers, each value gets its own setting: **None** (draw nothing), **Text**, **Image** (one of your images), **URL** (an image link), or **Simposter Asset** (a logo from the Simposter assets repo, e.g. studio and streaming logos).

### Each layer's tabs

- **Look**: the layer's own settings (image, text, font, colours), plus an optional **background box** and **outline** (text).
- **Position**: a 3×3 **Pin to** grid and distances from that edge in pixels of the finished 2000×3000 poster.
- **Show when**: the layer's own rules (see below).

A ⚠ on a layer's header means something is incomplete, for example an image layer with no image, empty text, or a rule with no value. Hover it for the reason.

### Preview

- **Preview with: Example values** lets you set test values (resolution, codecs, ratings…) and see which layers appear. Only the fields your overlay uses are listed; **More values** shows the rest.
- **Preview with: A real movie or show** uses a real item's data from your library, including its MDBList ratings.
- **Compare on several posters** shows small previews for three example items plus any real items you add, so you can check a rule set at a glance.
- Layers that won't be drawn for the current values show faded in the main preview.

The editor asks before closing with unsaved changes.

### Your images

**Your images** (collapsed at the bottom of the layer list) holds uploaded overlay images. Images from imported Kometa files land here too.

---

## Show when: rules

Every layer, and every overlay as a whole, can have rules. All of a layer's rules have to match for it to be drawn. Pick a **field**, an **operator** and a **value**:

| Group | Fields |
|-------|--------|
| **Video** | Resolution (4K / 1080p / 720p / SD), video codec |
| **Audio** | Audio codec, audio channels, audio language |
| **File** | File path / name (pattern match on the file name, e.g. TRaSH naming, CAM/TS, `{edition-…}` tags), edition (Plex only) |
| **Ratings** | Audience rating (0–10), critic rating (0–10), MDBList score, IMDb, Rotten Tomatoes (critics and audience), Metacritic, TMDb, Trakt, Letterboxd. All need an [MDBList key](#mdblist-ratings-and-lists). |
| **Lists** | On a list from MDBList, WeTrakr, SIMKL or Floppy (see [Lists from other services](#lists-from-wetrakr-simkl-and-floppy)) |
| **Item** | Label (Plex only), movie or show, year, days since added, show status (TV), TMDb ID, TVDB ID, title, studio, streaming platform |

Operators depend on the field:

- **Text and choice fields**: is, is not, is any of, is none of, contains, matches pattern, is set, is empty.
- **Numbers**: is at least, is above, is at most, is below, is exactly, is known, is unknown.
- **Lists**: is on, is on any of, is not on.

Notes on some fields:

- **Days since added** counts from the date your last library scan recorded. Use "is at most 7" for a "NEW" badge.
- **Show status** is continuing, ended, canceled or upcoming, from TMDb. TV shows only.
- **TMDb ID / TVDB ID** with "is any of" takes a list of IDs. This is how tools like UMTK and TSSK pick items.
- **Label** and **edition** come from Plex only. On Jellyfin/Emby, match the file name instead (most edition tags are in the file name).
- Rating fields only appear once an MDBList key is set in Settings → General; "On a list" appears once any list service is set up there.
- A rule that can't be checked (missing data) doesn't match, so the layer stays off.
- **TV shows and seasons**: a show or season has no file of its own, so resolution, codec and audio come from its best episode (highest resolution, then most audio channels). A show with one 4K episode counts as 4K, matching Kometa; each season uses its own episodes. These values are read during a TV scan (one extra request per show), so scan once after updating. On Plex, audio language isn't available this way. File-name rules on a show check the show's folder.

---

## Text with values

A **Text** layer can include values that are filled in per item. Use **+ Insert value…** in the Text box, or type them in curly braces:

| Group | Values |
|-------|--------|
| Item | `{title}`, `{year}`, `{edition}` (Plex only), `{studio}` |
| Video | `{resolution}`, `{video_codec}` |
| Audio | `{audio_codec}`, `{audio_channels}`, `{audio_language}` |
| Ratings (MDBList) | `{audience_rating}`, `{critic_rating}`, `{mdb_rating}`, `{mdb_imdb_rating}`, `{mdb_tomatoes_rating}`, `{mdb_tomatoesaudience_rating}`, `{mdb_metacritic_rating}`, `{mdb_metacriticuser_rating}`, `{mdb_tmdb_rating}`, `{mdb_trakt_rating}`, `{mdb_letterboxd_rating}`, `{mdb_myanimelist_rating}`, `{mdb_average_rating}` |

If a value is missing for an item (no rating yet, no MDBList key), the layer isn't drawn at all rather than showing an empty or literal `{…}` text.

---

## Badge sets and hide rules

- **Badge sets** (left tab 2): put layers in a set and order them; only the first one whose rules match is drawn. For example, a set of "Ultra HD Dolby Vision", "Ultra HD HDR", "Ultra HD", "1080p" badges shows only the best match. Sets work across all the overlays a preset uses.
- **Hide rules**: a layer can hide other named layers when it's drawn (e.g. a combined "DV + Atmos" badge hides the separate DV and Atmos badges). These mostly come from Kometa imports (`suppress_overlays`); they're shown when a layer has them.

Rename a layer with the pencil icon or by double-clicking its name. Hide rules follow the rename.

---

## Importing Kometa overlays

**📐 Overlays → Import Kometa** turns Kometa overlay files into Simposter overlays (one overlay per file).

> **Beta.** Kometa import and live Kometa files work, but Kometa files vary a lot and some may still import slightly differently than Kometa draws them. Please report anything that looks off.

1. Add the overlay `.yml` files, or **Paste YAML** to paste one in. Add the images and fonts they use alongside: loose files, a folder, or a zip.
2. Pick the library type the files are for: **Movies**, **TV Shows**, or **Movies and TV Shows** (one overlay for both kinds of library, like a Kometa file both libraries use; layers that only apply to one kind, or look different, get a movie/show rule so they only show there). Also add the images the files use, unless they're already in Your images from an earlier import: an image with the same file name is reused.
3. **Check** shows a report per file and per overlay: what imported, what was skipped and why, and which images weren't found.
4. **Import** saves the overlays. Re-importing a file updates the same overlay instead of creating a copy.

Then turn the overlays on in a preset (or the editor's Extras → Overlays).

### What carries over

- Kometa's own templates, including `default: templates`, variables, defaults, conditionals and optional values. Simposter expands them the way Kometa does.
- Images from files, links (`url:`, `git:`) and Kometa's defaults (`default:`/`pmm:`). Linked images are downloaded into **Your images**.
- Positions (`horizontal_align`/`vertical_align` and offsets), background boxes (`back_color`, size, radius, padding, border), text with `text(…)` and variables, fonts, outlines.
- `group`/`weight` (as badge sets) and `suppress_overlays` (as hide rules).
- `queues` (layers fill a list of positions, highest weight first), `blur`, images next to text (addon images) and `font_style` for variable fonts.
- Filters: resolution, codecs, channels, language, file path, edition, labels, year, title, studio, ratings, `added`, `tvdb_status`/`tmdb_status`, and the usual modifiers (`.not`, `.regex`, `.gte`, `.lte`, …). Comma-separated values (`label.not: Coming Soon, RequestNeeded`) are split, as in Kometa.
- Builders: `tmdb_movie`, `tmdb_show` and `tvdb_show` ID lists, and `mdblist_list`.

### What doesn't

These are listed in the import report:

- builders other than the ID lists and MDBList lists (Trakt, Plex searches, other list sources). Those layers are imported but hidden, so you can see and edit them.
- unknown filters (imported but hidden, with a note on the rule)
- text overlays with no `horizontal_offset`/`vertical_offset` (Kometa rejects these too)
- `text()` with nothing inside (Kometa draws nothing for it either)

An ID list (`tmdb_movie: 123, 456`) is copied at import time. If another tool rewrites the file regularly, use [Live Kometa files](#live-kometa-files) so the list stays current.

### Fonts

Kometa overlay files name font files, and Kometa's default is `Roboto-Medium.ttf`. Fonts you add with the import are used first. Otherwise Simposter downloads the font the first time it's needed: from its own font collection (24 open-source families such as Roboto, Oswald, Poppins, Bebas Neue and Playfair Display, in every weight), then from Kometa's, so imported text looks the same as in Kometa. A font it can't find anywhere falls back to a regular-weight system font. Your own fonts go in `config/fonts`.

### UMTK and TSSK

Overlay files from [UMTK](https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa) (upcoming movies/shows, top 10) and TSSK (TV show status) import as described above. Their item lists change daily, so they work best as live Kometa files. TSSK's status overlays use the **Show status** field (from TMDb, so very rarely it can differ from TVDB). An empty TSSK file (nothing to show yet) imports as an overlay with no layers.

---

## MDBList ratings and lists

[MDBList](https://mdblist.com) provides ratings from many sources and user-made lists. Add a free API key in **Settings → General → MDBList** (get one at mdblist.com/preferences, API section; the free tier has a daily request limit). Then:

- **Audience rating comes from** / **Critic rating comes from**: which source fills `audience_rating` and `critic_rating` (IMDb, Rotten Tomatoes critics or audience, TMDb, Trakt, Metacritic, Letterboxd, MyAnimeList, or the MDBList score). Both are scaled to 0–10.

Simposter only contacts MDBList when an overlay actually uses a rating or list, and remembers the results; how often they are fetched again is set in [Scheduler](#scheduler). If MDBList is unreachable, the render still happens; layers that needed the missing value are left off.

For a list rule, choose **On a list** and paste the list's URL (`https://mdblist.com/lists/user/list-name`).

### Lists from WeTrakr, SIMKL and Floppy

"On a list" also works with these services. Set them up in **Settings → General**:

- **WeTrakr**: the **Client ID** of an app you create at wetrakr.com → Settings → API (not the client secret; the redirect URL isn't used). Public lists work with just the Client ID. To use your own private lists and your tracking lists (Watchlist, Watching, Watched, On hold, Dropped), click **Connect account**: Simposter shows a code to enter at wetrakr.com/activate.
- **SIMKL**: a client ID from an app registered at simkl.com/settings/developer as **TV, devices & command line**, then **Connect account** (approve the code on simkl.com). Every SIMKL list needs the connection. Plan to Watch, Watching, Completed, On Hold and Dropped work on a free account; custom lists need SIMKL PRO or VIP.
- **Floppy**: your server's address (e.g. `http://192.168.1.10:8000`) and an app token from Floppy's Settings → Integrations → App tokens, with the `lists:read` scope.

In the rule, the dropdown lists your own lists from every connected service, grouped by service. To use someone else's public list, choose **Paste a list link…** and paste its link. Lists are matched by TMDb ID and re-fetched as often as [Scheduler](#scheduler) says; until then the stored copy is used, so a render never waits on a list service. If a service can't be reached, layers that need its list stay off and the overlay log says why.

---

## Scheduler

Overlay Manager → **Scheduler** sets how often the outside data overlays use is fetched again. These are the only settings that cost API calls:

- **Re-check ratings every N days** (default 45, or your old MDBList setting if you'd changed it): a rating older than this is fetched again, 100 items per request, only for items whose overlay uses a rating.
- **Re-check lists every N hours** (default 24): a list older than this is downloaded again. That's one request per page of the list (100 to 1,000 items a page depending on the service), not one per item, and only for lists an overlay uses. It applies to MDBList, WeTrakr, SIMKL and Floppy lists.

A file name, quality or edition doesn't need this: a library scan or webhook picks up those changes. Labels come from your last library scan.

The section also lists every library group's **Overlay Refresh** schedule (below), with a link to each. Example: lists every 3 hours, ratings every 7 days and an hourly Overlay Refresh means lists are downloaded every 3 hours and each rating once a week, and the hourly run uses the stored values, fetching whatever is due first, so it makes no other API calls.

## Overlay Refresh

A poster's overlay can change after it's been sent: a better rating, a new list membership, a 4K upgrade, an edited overlay. **Overlay Refresh** (🔁, in each library's sidebar menu) finds posters whose overlay would now come out differently and re-renders them.

- **Check for changes** lists the posters that would change, with the reason: what changed in the item's data, then the layers, e.g. "now on list Trending: added Trending frame" or "Audience rating 8.4 → 8.7: added High score". Only data that crossed one of the overlay's rules is named, so a rating moving from 8.4 to 8.5 without crossing a threshold isn't a change. It doesn't send anything.
- **Refresh changed posters** re-renders and sends those posters. **Re-send all** re-sends every tracked poster.
- **Schedule** runs it automatically (e.g. nightly). A scheduled run that changes nothing sends no notification.
- **Plex label**: posters refreshed on Plex get this label (default `Simposter-Overlay`), like Kometa's `Overlay` label.
- **Tracked posters** lists every poster Simposter is tracking, with the overlays each was sent with. Filter by an overlay to re-send just the posters that use it, or re-send one poster.
- **After editing an overlay**: when you save a changed overlay in the Overlay Manager, Simposter lists the tracked posters sent with it, per library, and offers to refresh them. Only posters whose overlay now looks different are re-sent.

How it works and its limits:

- Only posters sent by Simposter since this feature existed are tracked. A poster is re-rendered from the artwork it was originally rendered from, not from what's on the server now.
- A poster keeps the overlays it was sent with. Turning an overlay on or off in a preset reaches already-sent posters the next time they're sent (use Re-send in Tracked posters).
- New data (resolution, file name, date added) arrives with library scans; ratings and lists arrive from MDBList.
- Runs are logged and send a summary notification (toggle "Overlay Refresh" in Settings → Notifications). A poster sent to several servers is listed once, with the servers.

---

## Live Kometa files

Some tools rewrite their Kometa overlay files every day (UMTK and TSSK update their item lists). **📐 Overlays → Advanced → Live Kometa files** (beta) keeps an overlay in step with such a file:

- **File path on the Simposter server**: the `.yml` file. **Browse…** lists the folders on the Simposter server so you can pick it. In Docker, mount the folder with the file into the Simposter container (for example `- /mnt/user/appdata/kometa/config:/kometa/config:ro`) and use the path inside the container.
- **Overlay name** (optional), **Library type** (Movies / TV shows / Movies and TV shows), and **Check the file** (every hour to once a day).
- **When it changes, re-render posters whose overlay now looks different**: runs Overlay Refresh for every library of that type after the file changes.

Each entry shows when it was last checked and last changed, with **Check now**, **Open overlay**, **Edit**, **Pause/Resume** and **Remove** (removing keeps the overlay it made). Images and fonts the file uses are looked for next to the file and in the folders above it, as Kometa's own paths are relative to its config folder.

Rules you add to the whole overlay ("Show overlay when") are kept when the file is re-imported. Edits to individual layers are replaced by the file's content on the next change.

---

## Sharing overlays

To give someone a preset with its overlays, use the **share** button on the preset in Template Manager (or **Share selected** for several). Tick **Include overlays** and download:

- a **.zip** when the overlays use images or fonts Simposter can't download by itself: `presets.json`, the images, and the fonts from your `config/fonts`;
- a **.json** when nothing else is needed.

The other install imports it with Template Manager → Import / Export → **Open file**. Overlays already there with identical layers are reused; a different overlay with the same id is imported under a new id, so nothing of theirs is overwritten. Fonts with a name they already have are kept as they are. Without "Include overlays", the shared preset has its overlays turned off.

---

## Reading the overlay log

Each poster rendered with overlays writes one block to the log (Settings → Logs), for example:

```
[OVERLAY] Dune (2021): overlays 'Media Info' (81 layers); drew 3 of 81 layers
[OVERLAY]   Data: 4K, HEVC, TRUEHD, 8ch, TMDb ID 438631, file Dune (2021) {edition-IMAX} ... .mkv, ratings: none found
[OVERLAY]   Drew: Ultra-HD; IMAX; DV-HDR-TrueHD-Atmos
[OVERLAY]   Skipped 1080P: Resolution is 4k; needs: is 1080p
[OVERLAY]   Skipped Dolby Vision: hidden by DV-HDR-TrueHD-Atmos
```

- **Data** shows what the rules were checked against, and why something is missing (no MDBList key, no TMDb ID, no date added yet, "scan the library").
- **Skipped** lines give the first rule that didn't match with the item's actual value, another layer winning its badge set, or a hide rule. Up to 8 are listed; set the log level to DEBUG to see the rest.

If a layer you expect isn't drawn, this is the first place to look.

---

## Limits

- **Labels and editions** come from Plex only. On Jellyfin/Emby, use file-name rules (edition tags are usually in the file name).
- **HDR and Dolby Vision** are read from the file name, as in Kometa's default overlays.
- **Square Art and Thumb Art** use the preset's overlays too, but layers are placed for a 2:3 poster, so check how they sit on the square or wide image. Overlay Refresh only tracks posters. The Kometa collection template doesn't support overlays.
- **Kometa builders** other than TMDb/TVDB ID lists and MDBList lists (Trakt, Plex searches, IMDb lists…) aren't supported; those layers import hidden.
- **Overlay Refresh** only tracks posters sent since it existed, and re-renders from the artwork they were rendered from.
- **Preview**: the Overlay Manager preview draws a variable font at its default weight; the real render uses the weight you picked.
