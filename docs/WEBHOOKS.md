# Webhooks

Simposter can generate and send a poster automatically the moment new media is imported, without you ever opening the app. Three sources are supported: **Radarr** (movies), **Sonarr** (TV), and **Tautulli** (either, event-driven off Plex activity instead of the *arr apps).

All three URLs are also generated for you in **Settings → Automation** — you don't have to hand-build them, but this page explains what each part means and covers a couple of things the generator doesn't show (dry-run testing, ignore labels).

---

## Shared setup

**Webhook secret** (optional, recommended if Simposter is reachable from outside your LAN): set one in **Settings → Automation → Webhook Secret**. Once set, every webhook call must include it, either as a query param (`?secret=yoursecret`, works with all three below) or an `X-Webhook-Secret` header (if the sending app supports custom headers). Leaving it unset preserves the old trusted-network behavior — no secret required.

**Ignore labels**: in **Settings → Libraries → Webhook Ignore Labels**, list Plex labels that should skip automatic poster generation entirely (e.g. `Custom`, `NoOverlay`) — useful for titles you've hand-tuned and don't want a webhook silently overwriting. Case-insensitive, applies to all three webhook sources.

**Existing content mode** (**Settings → Automation**): controls what happens when a webhook fires for something that already has a poster.
- `Regenerate` *(default)* — always creates a fresh poster
- `Resend` — if a Simposter poster was already sent for this item, just re-pushes the cached render instead of re-rendering. Also protects manually tuned posters from being overwritten by an automated re-trigger.

**Smart retry**: if a webhook-triggered render doesn't meet the ideal template conditions (no clearlogo found, no textless poster available), the item is queued and retried automatically on the interval configured in Settings → Automation, instead of leaving a permanently-imperfect poster. See **Smart Retry Queue** in [COLLECTIONS_AND_POSTERS.md](COLLECTIONS_AND_POSTERS.md).

**Label to Add After Sending** (**Settings → Automation**, optional): if set, every item a webhook successfully sends a poster for also gets tagged with this label — handy for filtering/smart-collections on what Simposter has touched. Separate from the per-library "Default Labels to Remove" above.

---

## Radarr

**URL:**
```
http://your-server:8003/api/webhook/radarr/{template_id}/{preset_id}
```
Template and preset are part of the URL path, not query params — e.g. `.../api/webhook/radarr/uniformlogo/default`.

**Radarr setup:** Settings → Connect → add a Webhook connection.
- **Trigger on:** On Import, On Upgrade
- **Method:** POST
- **URL:** the path above (add `?secret=yoursecret` if you've set a webhook secret)

Radarr sends its own fixed payload shape (no template configuration needed on Radarr's side) — Simposter reads `movie.tmdbId`, `movie.title`, `movie.year` from it and looks up the matching Plex item by TMDb ID. The match is exact, not a substring check — a webhook for TMDb ID `58` won't accidentally match an unrelated item whose ID happens to start with those digits (e.g. `5825`).

**Test/dry-run:** append `&test=true` to the URL. Logs the event and what *would* happen, without generating or sending a poster.

---

## Sonarr

**URL:**
```
http://your-server:8003/api/webhook/sonarr/{template_id}/{preset_id}
```

**Sonarr setup:** Settings → Connect → add a Webhook connection.
- **Trigger on:** On Import, On Upgrade
- **Method:** POST
- **URL:** the path above (`?secret=yoursecret` if applicable)

Optional query param:
- `include_seasons` (default `true`) — when true, generates posters for all seasons in addition to the series poster; set to `false` for series-poster-only.

Matches the Plex show by TVDb ID (exact match). A newly-added show generates both the series poster and every season poster in one run; an episode import for an existing show only regenerates the affected season.

**Test/dry-run:** append `&test=true`.

---

## Tautulli

**URL:**
```
http://your-server:8003/api/webhook/tautulli?template_id=uniformlogo&preset_id=default&event_types=added
```
Unlike Radarr/Sonarr, Tautulli's template/preset are query params, not path segments — because Tautulli's payload is fully custom (you define the JSON body yourself), so Simposter can't infer anything from Tautulli's side.

**Method:** POST
**Trigger:** Recently Added (or whichever notification agent event you want to map — see Event Types below)

**JSON Payload — Movies:**
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

**JSON Payload — TV Shows:**
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

**Event Types** (`event_types` query param — comma-separate multiple):

| Tautulli Event | Simposter value | Fires when |
|----------------|-----------------|------------|
| `library.new` / `created` | `added` | New media added |
| `library.update` | `updated` | Metadata updated |
| `playback.stop` | `watched` | Playback finished |

**Test/dry-run:** append `&test=true` — logs the event without generating a poster.

---

## Debugging a webhook that isn't firing

1. Check **Settings → Logs** — every webhook call is logged with the media title and how long it took (`[RADARR_WEBHOOK]`/`[SONARR_WEBHOOK]`/`[TAUTULLI_WEBHOOK]` prefixes).
2. Try the `test=true` dry-run first — it tells you whether the event even reached Simposter and what it parsed out of the payload, without touching Plex.
3. Confirm the item isn't hitting a Webhook Ignore Label.
4. If you've set a webhook secret, double check it's actually being sent — a mismatched or missing secret is a silent rejection (403), not an error dialog.
5. `GET /api/webhook/test` is a plain connectivity check — hit it directly in a browser to confirm the server is reachable at all before troubleshooting further.
