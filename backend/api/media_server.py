"""Real, permanent media-server endpoints backing the Settings UI's Media
Servers section (Jellyfin-integration plan Phase 5 -- CLAUDE.md Quirk #60).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import SECRET_MASK

router = APIRouter(prefix="/media-server", tags=["media-server"])


@router.delete("/{server_id}/cache")
def api_purge_media_server_cache(server_id: str):
    """Purge everything cached for a media server that's been removed in
    Settings → Media Servers: its movie/TV/collection DB cache rows, label
    cache, retry-queue entries, Media Mirror sync state, and the on-disk
    poster/logo/backdrop/square-art files (plus thumbnails and the resend
    render cache) for each of its items.

    Called by the frontend only AFTER the settings save that removes the
    server has succeeded, mirroring DELETE /api/library/{id}. Deliberately
    leaves poster_history and the user's saved output files untouched.
    """
    from pathlib import Path
    from .. import database as db
    from ..config import (
        logger, settings, POSTER_CACHE_DIR, LOGO_CACHE_DIR, ART_CACHE_DIR, SQUARE_ART_CACHE_DIR,
    )

    if not server_id or "/" in server_id or "\\" in server_id:
        raise HTTPException(status_code=400, detail="Invalid server id")

    # Refuse to purge a server that's still configured -- this endpoint is only
    # for cleaning up after a removal has actually been saved.
    from ..media_server.registry import _load_media_servers
    still_configured = any(
        isinstance(s, dict) and s.get("id") == server_id
        and (server_id != "plex-1" or bool(settings.PLEX_URL and settings.PLEX_TOKEN))
        for s in _load_media_servers()
    )
    if still_configured:
        raise HTTPException(status_code=409, detail=f"Server {server_id} is still configured -- remove it and save first")

    try:
        result = db.purge_server_cache(server_id)
    except Exception as e:
        logger.error("[MEDIA_SERVER] Failed to purge DB cache for %s: %s", server_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to purge cache: {e}")

    cache_dirs = [Path(d) for d in (POSTER_CACHE_DIR, LOGO_CACHE_DIR, ART_CACHE_DIR, SQUARE_ART_CACHE_DIR)]
    render_dir = Path(settings.CONFIG_DIR) / "cache" / "poster_renders"
    removed_files = 0
    for rk in result["rating_keys"]:
        candidates = [render_dir / f"{rk}.jpg"]
        for d in cache_dirs:
            candidates.append(d / "thumbs" / f"{rk}.jpg")
            for ext in ("jpg", "jpeg", "png", "webp"):
                candidates.append(d / f"{rk}.{ext}")
                candidates.append(d / f"tv_{rk}.{ext}")
        for p in candidates:
            try:
                if p.is_file():
                    p.unlink()
                    removed_files += 1
            except OSError as e:
                logger.warning("[MEDIA_SERVER] Couldn't remove cached file %s: %s", p, e)

    logger.info(
        "[MEDIA_SERVER] Removed server %s: %d items, %d cache files deleted",
        server_id, len(result["rating_keys"]), removed_files,
    )
    return {
        "status": "ok",
        "server_id": server_id,
        "items_removed": len(result["rating_keys"]),
        "cache_files_removed": removed_files,
        "rows_removed": result["counts"],
    }


class MediaServerTestRequest(BaseModel):
    type: str  # "plex" | "jellyfin" | "emby"
    url: str
    token: Optional[str] = None    # Plex
    apiKey: Optional[str] = None   # Jellyfin/Emby
    # The id of the already-saved mediaServers entry being (re-)tested, if any --
    # needed so a masked credential (see below) can be resolved back to its real
    # stored value. Omitted/blank for a brand-new, not-yet-saved server.
    server_id: Optional[str] = None


@router.post("/test-connection")
def api_test_media_server_connection(payload: MediaServerTestRequest):
    """Tests a server BEFORE it's saved -- takes url/credentials directly in
    the body rather than reading a configured mediaServers entry, mirroring
    how test_plex_connection() already lets Settings validate a URL/token the
    user is still typing.

    Credential resolution: GET /api/ui-settings never returns a real
    Jellyfin/Emby apiKey -- it comes back as the literal SECRET_MASK
    placeholder ("********", see ui_settings.py's _mask_media_server_secrets).
    Testing an ALREADY-SAVED server (e.g. right after a page reload/backend
    restart, before the user has re-typed anything) would otherwise send that
    literal placeholder string as the real API key and always fail to
    connect -- a real bug reported directly by the user ("it could connect
    before restart"). test_plex_connection() already resolves this correctly
    for Plex by falling back to settings.PLEX_TOKEN; this mirrors that same
    pattern for Jellyfin/Emby by resolving the mask back to the real stored
    credential for `server_id`, when one is given."""
    token = payload.token
    api_key = payload.apiKey
    if payload.server_id and (token == SECRET_MASK or api_key == SECRET_MASK):
        from .. import database as db
        stored = next(
            (s for s in (db.get_ui_settings() or {}).get("mediaServers") or []
             if isinstance(s, dict) and s.get("id") == payload.server_id),
            None,
        )
        if stored:
            if token == SECRET_MASK:
                token = stored.get("token") or ""
            if api_key == SECRET_MASK:
                api_key = stored.get("apiKey") or ""

    if payload.type == "plex":
        # PlexClient.test_connection() reads the global settings.PLEX_URL/
        # PLEX_TOKEN, not the url/token passed to its constructor (a known,
        # documented Phase 2 limitation -- CLAUDE.md Quirk #58) -- so testing
        # a not-yet-saved Plex URL has to go through the endpoint already
        # built for exactly this pre-save-test case instead.
        from .movies import test_plex_connection
        result = test_plex_connection(plex_url=payload.url, plex_token=token)
        # test_plex_connection() already returns a "sections" list on success --
        # passed straight through so this endpoint's response shape (used for
        # any additional Plex entry beyond the primary connection) matches the
        # Jellyfin/Emby branch below exactly, letting the frontend build the
        # same "✓ Connected! Found N movie libraries: ..." message either way.
        return {"connected": result.get("status") == "ok", "sections": result.get("sections") or []}

    if payload.type in ("jellyfin", "emby"):
        from ..media_server import JellyfinClient
        client = JellyfinClient(
            "test", url=payload.url,
            api_key=api_key or token or "",
            is_emby=(payload.type == "emby"),
        )
        connected = client.test_connection()
        # Same "sections" shape test_plex_connection() already returns (a
        # plain title/key/type list), so the frontend can build the identical
        # "✓ Connected! Found N movie libraries: ..." message for Jellyfin/
        # Emby instead of a bare boolean -- previously this endpoint only
        # ever returned {"connected": true/false}, giving no confirmation of
        # what was actually found, unlike Plex's test button. Best-effort:
        # a listing failure doesn't turn a genuinely successful connection
        # test into a failure, it just omits the library detail.
        sections = []
        if connected:
            try:
                sections = [
                    {"title": lib.name, "key": lib.id, "type": "movie" if lib.media_type == "movie" else "show"}
                    for lib in client.list_libraries()
                ]
            except Exception:
                sections = []
        return {"connected": connected, "sections": sections}

    raise HTTPException(400, f"Unknown server type: {payload.type}")


@router.get("/libraries")
def api_list_all_libraries():
    """Every library across every enabled, connected media server -- backs the
    Library Groups UI's 'pick libraries for this group' picker (Settings ->
    Library Groups), so the user never has to hand-type a server id/library id
    pair. Best-effort per server: one server being unreachable doesn't fail
    the whole listing, it just contributes zero libraries for that server_id
    (reported in `errors`) so the picker can still show every other server's
    libraries.
    """
    from ..media_server import get_enabled_clients

    libraries = []
    errors = []
    for client in get_enabled_clients():
        try:
            for lib in client.list_libraries():
                libraries.append({
                    "serverId": client.server_id,
                    "serverType": type(client).__name__.replace("Client", "").lower(),
                    "libraryId": lib.id,
                    "libraryName": lib.name,
                    "mediaType": lib.media_type,
                })
        except Exception as e:
            errors.append({"serverId": client.server_id, "error": str(e)})

    return {"libraries": libraries, "errors": errors}


def _update_scan_status(message: str) -> None:
    """Best-effort write into the SAME shared scan_status dict movies.py's own
    Plex scan already writes "current" into -- lets a Jellyfin/Emby linked-
    library scan (which runs synchronously right after the Plex scan, inside
    the same /api/scan-library request, see api_scan_library()'s own call to
    scan_all_linked_plex_libraries()) show up in the one scan-progress overlay
    the frontend already polls, instead of that phase running completely
    invisibly. A plain dict mutation (matching movies.py's own `scan_status.update(...)`
    pattern -- no lock there either), imported lazily to avoid a module-load-time
    circular import between movies.py and media_server.py. Never raises --
    a status-display failure must never be allowed to fail the actual scan."""
    try:
        from .movies import scan_status
        scan_status.update({"current": message})
    except Exception:
        pass


def _scan_one_library(client, server_id: str, library_id: str, media_type: str, library_name: str = "") -> dict:
    """Scan exactly one library on one non-Plex server and upsert its items.
    The shared building block for both the per-library scan (the normal UI
    path, per CLAUDE.md's Quirk about not scanning a whole server
    unconditionally) and scan-linked's per-member loop below."""
    from .. import database as db

    items = client.list_items(library_id, media_type)
    rows = [
        {"rating_key": i.id, "title": i.title, "year": i.year, "added_at": i.added_at, "tmdb_id": i.tmdb_id, "tvdb_id": i.tvdb_id}
        for i in items
    ]
    if media_type == "movie":
        counts = db.upsert_media_server_movies(server_id, library_id, rows)
    else:
        counts = db.upsert_media_server_tv_shows(server_id, library_id, rows)

    # Fetch poster/logo/backdrop art + video/audio media info for every
    # scanned item -- deliberately a SECOND pass, after the identity rows
    # above already exist (fetch_and_cache_poster()/etc route to the right
    # server via db.get_server_id_for_rating_key(), which needs the row
    # upserted first). Closes the gap Quirk #61's own docstring explicitly
    # deferred ("No poster/logo/backdrop/square_art fetching here -- that's
    # separate, later work") -- user-reported directly, after checking the DB
    # by hand and finding poster_url/logo_url/art_url/video_resolution/
    # audio_codec/audio_channels/video_codec/audio_language all null for
    # every Jellyfin-scanned row. Square art and labels are deliberately
    # skipped here, per the user's own confirmation: Jellyfin has no
    # square-art concept at all (Quirk #59), and this app's label-based
    # dedup/removal mechanism doesn't apply to non-Plex items either
    # (Quirk #59's remove_label()/add_label() no-ops).
    if items:
        _fetch_art_and_media_info_for_scan(items, media_type, client)

    return {
        "library_id": library_id,
        "library_name": library_name,
        "media_type": media_type,
        "item_count": len(items),
        **counts,
    }


def _scan_one_collection_library(client, server_id: str, library_id: str, library_name: str = "") -> dict:
    """Collections mirror of _scan_one_library() above -- a genuinely separate
    function rather than a media_type="collection" branch inside it, since
    list_items()/upsert_media_server_movies()/_tv_shows() all have no concept
    of a collection at all (Collections is a movie-only Plex concept, Quirk
    #21/#128 -- JellyfinClient.list_collections() is its own method, not a
    list_items() filter). Was missing entirely until now: Quirk #128 built
    Jellyfin collection listing + a real upsert_media_server_collections()
    writer, but only ever wired them into the on-demand /api/collections
    endpoint (fired when a user actually visits the Collections page) -- this
    is the scan path itself, called from api_scan_linked_libraries()/
    scan_all_linked_plex_libraries() so a group's "Scan" click populates
    collection_cache the same way it already populates movie_cache/tv_cache,
    instead of only ever getting collections on first page visit.
    User-reported directly: "it did not scan jellyfins collections when i
    scanned a group." No art-fetching here (Collections' own poster/logo come
    from TMDb/Fanart via the Simposter/Kometa Creator editors, not from the
    source server itself, unlike movies/TV -- see Quirk #128)."""
    if not hasattr(client, "list_collections"):
        return {"library_id": library_id, "library_name": library_name, "media_type": "collection", "item_count": 0}
    from .. import database as db

    items = client.list_collections(library_id)
    rows = [
        {
            "rating_key": i["key"], "title": i.get("title") or "", "year": i.get("year"),
            "added_at": i.get("addedAt"), "poster_url": i.get("poster"),
        }
        for i in items
    ]
    counts = db.upsert_media_server_collections(server_id, library_id, rows)
    return {
        "library_id": library_id,
        "library_name": library_name,
        "media_type": "collection",
        "item_count": len(items),
        **counts,
    }


def _fetch_art_and_media_info_for_scan(items, media_type: str, client) -> None:
    """Concurrently fetches poster/logo/backdrop + video/audio media info for
    a just-upserted batch of Jellyfin/Emby items, mirroring the exact
    concurrent-fetch pattern movies.py's Plex scan already uses (same
    ThreadPoolExecutor shape) -- just wiring the ALREADY server-aware fetch
    functions (Quirk #65) into the one scan path that never called them.
    Poster/logo/backdrop use the same disk-cache functions the live serve
    endpoints use (no new "download this asset" logic); media info comes
    from MediaServerClient.get_item_metadata(), already built in Phase 3
    (CLAUDE.md Quirk #59)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .. import database as db
    from ..config import logger
    from .movies import (
        fetch_and_cache_poster, fetch_and_cache_logo, fetch_and_cache_backdrop,
        _poster_cache_url as _movie_poster_cache_url, _logo_cache_url, _art_cache_url,
    )

    is_tv = media_type != "movie"
    if is_tv:
        from .tv_shows import fetch_and_cache_tv_poster, _poster_cache_url as _tv_poster_cache_url
        update_poster = db.update_tv_poster
        update_logo = db.update_tv_logo_url
        update_art = db.update_tv_art_url
        update_media_info = db.update_tv_media_info
    else:
        update_poster = db.update_movie_poster
        update_logo = db.update_movie_logo_url
        update_art = db.update_movie_art_url
        update_media_info = db.update_movie_media_info

    def _one(item) -> None:
        rating_key = item.id
        try:
            if is_tv:
                poster_path = fetch_and_cache_tv_poster(rating_key)
                if poster_path:
                    update_poster(rating_key, _tv_poster_cache_url(rating_key, poster_path), item.library_id or "default")
            else:
                poster_path = fetch_and_cache_poster(rating_key)
                if poster_path:
                    update_poster(rating_key, _movie_poster_cache_url(rating_key, poster_path), item.library_id or "default")
        except Exception as e:
            logger.debug("[MEDIA_SERVER_SCAN] Poster fetch failed for %s: %s", rating_key, e)
        try:
            logo_path = fetch_and_cache_logo(rating_key)
            if logo_path:
                update_logo(rating_key, _logo_cache_url(rating_key, logo_path))
        except Exception as e:
            logger.debug("[MEDIA_SERVER_SCAN] Logo fetch failed for %s: %s", rating_key, e)
        try:
            art_path = fetch_and_cache_backdrop(rating_key)
            if art_path:
                update_art(rating_key, _art_cache_url(rating_key, art_path))
        except Exception as e:
            logger.debug("[MEDIA_SERVER_SCAN] Backdrop fetch failed for %s: %s", rating_key, e)
        try:
            meta = client.get_item_metadata(rating_key)
            update_media_info(
                rating_key,
                video_resolution=meta.video_resolution,
                audio_codec=meta.audio_codec,
                audio_channels=meta.audio_channels,
                video_codec=meta.video_codec,
                audio_language=meta.audio_language,
                edition=meta.edition,
            )
        except Exception as e:
            logger.debug("[MEDIA_SERVER_SCAN] Media-info fetch failed for %s: %s", rating_key, e)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_one, item) for item in items]
        for _ in as_completed(futures):
            pass

    logger.info("[MEDIA_SERVER_SCAN] Fetched art + media info for %d %s item(s)", len(items), media_type)


@router.post("/{server_id}/scan")
def api_scan_media_server(server_id: str, library_id: Optional[str] = None, media_type: Optional[str] = None, library_name: Optional[str] = None):
    """Pull item data into movie_cache/tv_cache, tagged with this server's own
    server_id -- via upsert_media_server_movies()/_tv_shows() (database.py),
    deliberately separate from the existing Plex scan path
    (bulk_refresh_cache()/bulk_refresh_tv_cache(), used by /api/scan-library)
    so this can never risk mislabeling or orphaning real Plex data.

    Deliberately scoped to ONE library when `library_id`+`media_type` are
    given -- the real, always-used UI path is now the "Scan" button on a
    Plex library's row in Settings -> Libraries, which only ever scans
    libraries the user has actually linked (see scan-linked below and
    CLAUDE.md's Quirk on this). Scanning a whole server unconditionally
    (every library it has, whether tracked or not) would silently import and
    cache content the user never asked to track -- a real "clogs the DB with
    things I don't want" complaint raised directly by the user, which is why
    this is no longer the default/only mode. The whole-server mode is kept
    (no `library_id` given) purely for the temporary debug tooling / a
    deliberate manual re-sync -- it is NOT wired to any button in the real UI
    anymore.

    Plex is intentionally rejected here -- it already has its own scan flow
    (Settings -> Libraries -> Scan, /api/scan-library) which this does not
    replace or duplicate.

    `library_name` (optional): a display name for the shared scan-progress
    overlay (_update_scan_status()) -- the frontend already has this (the
    group member's own LibraryGroupMember.libraryName) and passing it through
    avoids a second, redundant client.list_libraries() call here just to look
    one up. Falls back to the bare library_id when omitted, which is still
    informative, just less friendly.
    """
    from ..media_server import get_client, PlexClient, get_server_label

    client = get_client(server_id)
    if not client:
        raise HTTPException(404, f"No mediaServers entry with id='{server_id}', or its type isn't supported yet")
    if isinstance(client, PlexClient):
        raise HTTPException(400, "Plex libraries already scan via Settings -> Libraries -- this endpoint is for Jellyfin/Emby only")

    if library_id:
        if not media_type:
            raise HTTPException(400, "media_type is required when library_id is given")
        display_name = library_name or library_id
        server_label = get_server_label(server_id)
        # Drives the SAME shared scan-progress overlay the Plex scan uses
        # (previously this standalone/Plex-less path had no connection to it
        # at all -- a Jellyfin/Emby-only group's "Scan" click showed nothing
        # globally, only LibraryGroupCard.vue's own local busy state). Guarded
        # against a concurrent Plex scan the same way movies.py's own
        # api_scan_library() guards against a concurrent run of itself.
        from .movies import scan_status
        from datetime import datetime, timezone
        if scan_status.get("state") == "running":
            raise HTTPException(409, "A scan is already in progress")
        total_steps = 2 if media_type == "movie" else 1
        scan_status.update({
            "state": "running", "total": total_steps, "processed": 0,
            "current": f"Scanning {server_label}: {display_name} ({'TV shows' if media_type == 'tv' else 'movies'})",
            "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None, "error": None,
        })
        try:
            result = _scan_one_library(client, server_id, library_id, media_type, display_name)
            results = [result]
            scan_status.update({"processed": 1})
            # Collections have no media_type of their own in this app's model
            # (Quirk #21) -- scan them alongside a movie library, same as
            # api_scan_linked_libraries() does for a Plex-anchored group. Was
            # missing entirely here too, the same "on-demand endpoint built,
            # scan path never wired up" gap -- user-reported directly for a
            # Plex-less (standalone) movie group specifically.
            if media_type == "movie":
                _update_scan_status(f"Scanning {server_label}: {display_name} (collections)")
                results.append(_scan_one_collection_library(client, server_id, library_id, display_name))
                scan_status.update({"processed": 2})
            scan_status.update({"state": "done", "finished_at": datetime.now(timezone.utc).isoformat()})
        except Exception as e:
            scan_status.update({"state": "error", "error": str(e), "finished_at": datetime.now(timezone.utc).isoformat()})
            raise
        return {
            "server_id": server_id,
            "libraries": results,
            "total_movies_found": result["item_count"] if media_type == "movie" else 0,
            "total_shows_found": result["item_count"] if media_type == "tv" else 0,
        }

    libraries = client.list_libraries()
    library_results = []
    total_movies = 0
    total_shows = 0

    for lib in libraries:
        result = _scan_one_library(client, server_id, lib.id, lib.media_type, lib.name)
        library_results.append(result)
        if lib.media_type == "movie":
            total_movies += result["item_count"]
            library_results.append(_scan_one_collection_library(client, server_id, lib.id, lib.name))
        else:
            total_shows += result["item_count"]

    return {
        "server_id": server_id,
        "libraries": library_results,
        "total_movies_found": total_movies,
        "total_shows_found": total_shows,
    }


@router.get("/status")
def api_media_server_status():
    """Lightweight, per-server reachability check for a TopNav status badge --
    mirrors /api/plex-status's own design (movies.py: cheap, polled
    periodically, never raises, "down" on any failure) but for every
    configured Jellyfin/Emby server. Plex is deliberately excluded here --
    it already has its own dedicated badge/endpoint; this is additive, not a
    replacement, and stays empty (so the frontend renders nothing extra) for
    any install with no non-Plex server configured.
    """
    from ..media_server import get_enabled_clients, PlexClient
    from .. import database as db

    # Name lookup for the badge label (Quirk on naming servers to disambiguate
    # e.g. two Jellyfin instances) -- fetched once, not per-client.
    settings_row = db.get_ui_settings() or {}
    names = {s.get("id"): s.get("name") for s in (settings_row.get("mediaServers") or [])}

    results = []
    for client in get_enabled_clients():
        if isinstance(client, PlexClient):
            continue
        try:
            up = client.test_connection()
        except Exception:
            up = False
        results.append({
            "server_id": client.server_id,
            "type": type(client).__name__.replace("Client", "").lower(),
            "name": names.get(client.server_id),
            "status": "up" if up else "down",
        })
    return {"servers": results}


@router.post("/scan-linked")
def api_scan_linked_libraries(server_id: str, library_id: str):
    """The real scan trigger for the merged-grid feature (Quirk #65): given a
    Plex library that was just scanned normally (the existing /api/scan-library
    flow), find its LibraryGroup (if any -- Quirk #62/#64) and scan every OTHER
    member (Jellyfin/Emby) too, so a single "Scan" click on a linked Plex
    library's row covers all its linked servers. A library with no group, or
    a group with no other members, is a silent no-op -- most libraries have
    neither, so this must never surface as an error for the common case.

    Deliberately does not scan the `server_id`/`library_id` pair passed in --
    that's assumed to be the Plex side, already scanned by the caller via the
    existing /api/scan-library flow, immediately before this is called.

    Updates the same shared scan_status dict movies.py's own Plex scan writes
    to, with the member's own library name (from the group's stored
    LibraryGroupMember.libraryName snapshot -- Quirk #62) and server label
    (get_server_label(), honors a custom Settings name) plus which content
    type is currently being fetched -- previously this whole phase ran
    completely silently, so the scan overlay looked frozen/finished the
    instant the Plex portion ended even though a real, sometimes lengthy
    Jellyfin/Emby scan was still running in the background. User-reported
    directly: "it did not scan jellyfins collections when i scanned a group
    (seemed to only scan plex's library)" -- partly a real gap (collections
    genuinely weren't scanned, fixed above) and partly this exact invisibility
    making a real, working Jellyfin movie/TV scan look like it never ran."""
    from ..config import get_library_group_for
    from ..media_server import get_client, get_server_label

    scanned = []
    errors = []
    for media_type in ("movie", "tv"):
        group = get_library_group_for(server_id, library_id, media_type)
        members = group.get("members") if group else None
        if not members or len(members) <= 1:
            continue
        for member in members:
            member_server_id = member.get("serverId")
            member_library_id = member.get("libraryId")
            member_library_name = member.get("libraryName") or member_library_id
            if member_server_id == server_id and member_library_id == library_id:
                continue
            client = get_client(member_server_id)
            if not client:
                errors.append({"server_id": member_server_id, "library_id": member_library_id, "error": "server not configured or unsupported"})
                continue
            server_label = get_server_label(member_server_id)
            try:
                _update_scan_status(f"Scanning {server_label}: {member_library_name} ({'TV shows' if media_type == 'tv' else 'movies'})")
                result = _scan_one_library(client, member_server_id, member_library_id, media_type, member_library_name)
                scanned.append({"server_id": member_server_id, **result})
            except Exception as e:
                errors.append({"server_id": member_server_id, "library_id": member_library_id, "error": str(e)})
            # Collections are a movie-only Plex concept (Quirk #21) with no
            # media_type of their own in the Library Group model -- scan them
            # alongside a linked member's movie library, not as a separate
            # loop iteration. See _scan_one_collection_library()'s own
            # docstring for why this was missing entirely until now.
            if media_type == "movie":
                try:
                    _update_scan_status(f"Scanning {server_label}: {member_library_name} (collections)")
                    coll_result = _scan_one_collection_library(client, member_server_id, member_library_id, member_library_name)
                    scanned.append({"server_id": member_server_id, **coll_result})
                except Exception as e:
                    errors.append({"server_id": member_server_id, "library_id": member_library_id, "media_type": "collection", "error": str(e)})
        # A Plex library_id only ever belongs to one media type's groups (movie
        # libraries and TV libraries are tracked in separate lists) -- once a
        # match is found, the other media_type has nothing left to check.
        break

    return {"scanned": scanned, "errors": errors}


def scan_all_linked_plex_libraries(library_id: Optional[str] = None) -> dict:
    """Runs api_scan_linked_libraries() for every Plex library that has a
    LibraryGroup, or just ONE specific library_id when given. The single
    source of truth for "also scan whatever's linked" -- used by:
    (1) api_scan_library() (movies.py) after ANY Plex scan, single-library OR
        "Scan All Libraries" -- previously only the single-library UI path
        (SettingsView.vue's scanLibrary(), via its own frontend-side
        scan-linked fetch, gated on `if (libraryId)`) ever triggered this;
        "Scan All Libraries" scanned every Plex library but never called
        scan-linked for ANY of them, so a linked Jellyfin/Emby library never
        got refreshed at all when a user scanned that way -- a real,
        reported gap ("its also only scanning plex?").
    (2) _scan_linked_libraries_for_scheduled_scan() (scheduler.py), which now
        delegates here instead of duplicating this same iteration itself.
    Reads `libraryGroups` fresh from the DB, the same way every other
    settings-reading helper in this app does. A no-op (empty result) for an
    install with no groups at all, or none linking a Jellyfin/Emby library --
    the common case, so this must never be treated as an error."""
    from .. import database as db

    ui_settings = db.get_ui_settings() or {}
    groups = ui_settings.get("libraryGroups") or []
    plex_library_ids = set()
    for group in groups:
        for member in group.get("members") or []:
            if member.get("serverId") == "plex-1" and member.get("libraryId"):
                if library_id is None or str(member["libraryId"]) == str(library_id):
                    plex_library_ids.add(str(member["libraryId"]))

    all_scanned = []
    all_errors = []
    for lib_id in plex_library_ids:
        try:
            result = api_scan_linked_libraries(server_id="plex-1", library_id=lib_id)
            all_scanned.extend(result.get("scanned") or [])
            all_errors.extend(result.get("errors") or [])
        except Exception as e:
            all_errors.append({"server_id": "plex-1", "library_id": lib_id, "error": str(e)})

    return {"scanned": all_scanned, "errors": all_errors}


@router.get("/library-group")
def api_get_library_group(server_id: str, library_id: str, media_type: str):
    """Backs the Movies/TV grid toolbar's live "prefer" dropdown (Quirk #85) --
    returns the whole Library Group a (server_id, library_id) pair belongs to
    (members + its current preferredServerId), or {"group": null} when it's
    in no group at all, in which case the toolbar shows nothing."""
    from ..config import get_library_group_for
    return {"group": get_library_group_for(server_id, library_id, media_type)}


class PreferredServerUpdate(BaseModel):
    server_id: str
    library_id: str
    media_type: str
    preferred_server_id: str


@router.post("/library-group/preferred-server")
def api_set_library_group_preferred_server(payload: PreferredServerUpdate):
    """The write side of the toolbar dropdown above -- persists immediately
    on every change (like the grid's other toolbar controls), not gated
    behind Settings -> Libraries' own Save button, since this is edited from
    a different page now (Quirk #85 moved it out of Settings entirely)."""
    from .. import database as db
    updated = db.set_library_group_preferred_server(
        payload.server_id, payload.library_id, payload.media_type, payload.preferred_server_id
    )
    if updated is None:
        raise HTTPException(404, "No Library Group found for this library")
    return {"group": updated}


class MergeItemsUpdate(BaseModel):
    server_id: str
    library_id: str
    media_type: str
    merge_items: bool


@router.post("/library-group/merge-items")
def api_set_library_group_merge_items(payload: MergeItemsUpdate):
    """The write side of the Merge Items checkbox (Settings -> Libraries) --
    persists immediately on every change instead of waiting for Settings'
    own page-wide Save button, matching the preferred-server endpoint above.
    Added specifically to remove any dependency on remembering to click Save
    (or on correctly navigating the "unsaved changes" confirm dialog) before
    the toggle can take effect for the Movies/TV grid's own merge-aware
    fetch."""
    from .. import database as db
    updated = db.set_library_group_merge_items(
        payload.server_id, payload.library_id, payload.media_type, payload.merge_items
    )
    if updated is None:
        raise HTTPException(404, "No Library Group found for this library")
    return {"group": updated}
