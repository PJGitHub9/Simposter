# Poster API

Simposter can serve posters to other apps by TMDb id. An app such as Ether asks for a poster by URL, and Simposter answers with your pinned poster, the one already on your media server, or a fresh render from your Uniform Logo preset. It also works with no media server at all.

## Enable it

Open **🔌 Poster API** in the sidebar.

1. Tick **Enable**.
2. Click **Generate** next to the key field, copy the key and **Save**. The key is shown in full only once; after that the page shows a masked value.
3. Pick a **default movie preset** and **default TV preset** (Uniform Logo presets only). Left on "simposter-main (default)", Simposter uses the `simposter-main` starter preset (or the first Uniform Logo preset if that one was deleted).
4. **Wait seconds** (2-30, default 10) is how long a request waits for a render before it is sent to stock TMDb art instead.

The key is optional, but without one anyone who can reach Simposter can use your TMDb quota through this API. The page warns you about this.

**The key travels in the URL** (`?key=...`). Reverse proxies and Simposter's own web server (uvicorn) can record it in access logs. Simposter never writes the key to its own log, but treat it like a password in a URL: use a key you don't reuse anywhere else.

## URLs

Three equivalent forms. Replace `603` with a TMDb id and `YOUR_KEY` with your key (leave `&key=...` off if you have no key). The **Copy** buttons on the Poster API page copy these URLs with your real key already filled in.

```
# Query form
http://simposter:8003/api/poster?tmdb_id=603&type=movie&key=YOUR_KEY

# Path form
http://simposter:8003/api/poster/movie/603?key=YOUR_KEY

# Root alias
http://simposter:8003/poster?tmdb_id=603&type=movie&key=YOUR_KEY
```

TV shows use `type=tv` (also accepted: `series`, `show`, `tv-show`). Add `season=2` for a season poster; without it you get the series poster. `season` is ignored for movies.

```
http://simposter:8003/api/poster?tmdb_id=1396&type=tv&season=2&key=YOUR_KEY
```

The Poster API page shows these templates with your host filled in, and a Copy button for each.

### `preset=` override

`preset=<id>` renders with that Uniform Logo preset instead of the default. Preset ids may contain letters, digits, `_` and `-`. An unknown id, or a Kometa preset, returns 404. Each preset is cached separately.

## Responses

| Status | Meaning |
|---|---|
| `200` | The poster (JPEG, or PNG for a library poster). `Cache-Control: public, max-age=86400`. |
| `302` | The render took longer than **Wait seconds**. You are redirected to the stock TMDb poster (`image.tmdb.org`). The render keeps going, so a later request gets `200`. |
| `404` | The API is disabled, the id is unknown or has no poster art (remembered for 10 minutes), the preset is unknown, or there is nothing cached and no TMDb key to render with. |
| `401` | A key is set and the request's `key=` is missing or wrong. |
| `400` | The request is malformed (bad `type`, `tmdb_id` not a positive number, bad `preset`, negative `season`). |

## Lookup order

Without `preset=`, Simposter looks in this order and serves the first hit:

1. **Pinned**: a poster you pinned from the editor (see below). Never expires and never overwritten.
2. **Library**: the poster Simposter already sent to your media server for that title.
3. **Rendered**: a render cached by the API itself. If you edit the preset afterwards, the old render is served once while a new one is built in the background.

If none exist, Simposter renders one from TMDb art with your default preset. Many requests for the same id at once cause one render, and all of them get the same answer.

With `preset=`, pinned and library posters are skipped and the render for that preset is used.

Cached files (pinned, library, rendered) are served even with no TMDb key; only a new render needs one.

## Regenerate, pin, clear

On the Poster API page every cached poster is a tile.

- **Regenerate** re-renders a rendered poster now. It does not touch pinned or library posters.
- **Clear** deletes that tile's cached entry only (it never deletes a pinned poster when you clear a rendered tile).
- **Open in editor** opens the title in the normal editor in API mode.
- **Pin**: in API mode the editor shows a Pin button instead of Save/Send. Pinning stores the poster you see in the preview and serves it from then on. For TV, pin the focused season or the series. Pinning also removes the old rendered copy for that title (or that season), since the pin is served instead; renders for an explicit `preset=` are kept.
- **Select several**: tick the box on each tile (or click its image), or use **Select page** / **Select all**, then **Regenerate** or **Clear** them in one go. Regenerate only applies to rendered posters; Clear removes each tile's own entry, same as the single button.

Rendered posters that haven't been served for **retention days** (default 90) are removed by Cleanup (Settings → Cleanup, "Poster API renders"). Pinned posters are included in database export/import.

## Running without a media server

On first launch the setup wizard asks whether to connect a media server. Choose **No media server - use Simposter as a poster provider**. The wizard then:

1. asks for your TMDb key (TVDB and Fanart.tv are optional),
2. imports the starter presets,
3. asks you to enable the Poster API, generate a key and pick default presets,
4. lands you on the Poster API page.

In this mode the sidebar shows only Poster API, Template Manager, Overlays, Logs and Settings (Settings hides Libraries, Output and Automation). Back up presets, overlays, settings and pinned posters from Settings → Advanced. Template Manager and Overlay Manager previews use TMDb titles (trending and search) instead of your library, and the global search finds TMDb titles. Connect a server later in Settings → Media Servers and the full navigation appears; remove the last one and you are back in this mode.

## Ether and other clients

Ether's exact poster-URL template syntax has not been verified against a real Ether install. The three URL forms above are meant to cover the common styles; if Ether wants a different placeholder format, use whichever form fits and substitute its id placeholder for the `603`.
