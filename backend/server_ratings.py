"""Ratings the media servers already have, for overlay rules and text.

Kometa's audience_rating/critic_rating are Plex's own audienceRating/rating
attributes (modules/plex.py), so they need no outside service. Scans store
them here: Plex audienceRating/rating, Jellyfin/Emby CommunityRating and
CriticRating (0-100, stored /10). All values are 0-10.

Settings > Ratings & Lists picks one source per field: "server" (the default:
the first enabled media server in Settings > Media Servers that has a rating
for the item), "plex", "jellyfin" (Jellyfin or Emby), "tmdb" or an MDBList
source. When an MDBList source is picked but there is no MDBList key, the
media server's value is used instead, so overlays that use a rating still work
out of the box. When a media-server source has no value (no server, or none
for this item), MDBList is used if there is a key (IMDb for audience, Rotten
Tomatoes for critic), then TMDb (audience only).

Rows are keyed by (server_id, rating_key) and looked up by TMDb id, so a
rating stored from the Plex copy also applies to the Jellyfin copy.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

SERVER_SOURCES = ("server", "plex", "jellyfin")
# Sources that need no MDBList key: the media servers, plus TMDb's own user
# score (audience only -- TMDb has no critic score). TMDb is also the fallback
# for audience_rating whenever no server has a value, which is always the case
# on an install with no media server (Poster API / server-less mode).
TMDB_SOURCE = "tmdb"
LOCAL_SOURCES = SERVER_SOURCES + (TMDB_SOURCE,)
# When a media-server source has no value (no server, or the server has no
# rating for the item) and there is an MDBList key, these MDBList sources are
# used instead, then TMDb (audience only).
MDBLIST_FALLBACK = {"audience_rating": "imdb", "critic_rating": "tomatoes"}
_FALLBACK_LABELS = {"imdb": "MDBList (IMDb)", "tomatoes": "MDBList (Rotten Tomatoes)"}


# A title with no TMDb votes yet is checked again after a day, so its badge
# appears once it has a score instead of waiting the full ratings interval.
_TMDB_UNRATED_MAX_AGE = 86400


def _tmdb_score_key(media_type: str, tmdb_id: Any) -> str:
    # Its own prefix in item_ratings: MDBList's keys are "<type>:<provider>:<id>".
    return f"tmdbscore:{'tv' if media_type in ('tv', 'show') else 'movie'}:{tmdb_id}"


def _fetch_tmdb_score(media_type: str, tmdb_id: Any) -> Optional[Dict[str, Any]]:
    """{"score": x} or {} (no votes yet); None when TMDb couldn't be asked."""
    try:
        from .tmdb_client import get_movie_details, get_tv_show_details
        details = get_movie_details(int(tmdb_id)) if media_type == "movie" else get_tv_show_details(int(tmdb_id))
    except Exception:
        return None
    if not details:
        return None
    if not details.get("vote_count"):
        return {}  # no votes yet: TMDb reports 0.0, which isn't a real score
    value = _num(details.get("vote_average"))
    return {"score": round(value, 1)} if value is not None else {}


def tmdb_audience_rating(media_type: str, tmdb_id: Any) -> Optional[float]:
    """TMDb's user score (vote_average, 0-10) for the item. None when unknown
    or unrated. Stored and reused like MDBList's ratings (Overlays > Scheduler,
    "ratings every N days"), so a score that moves a little each day doesn't
    re-send the poster on every Overlay Refresh run."""
    if tmdb_id in (None, ""):
        return None
    import time
    from . import database as db
    key = _tmdb_score_key(media_type, tmdb_id)
    stale: Optional[Dict[str, Any]] = None
    try:
        cached = db.get_item_ratings(key)
    except Exception:
        cached = None
    if cached:
        data, fetched_at = cached
        try:
            from .list_sources import ratings_max_age
            max_age = ratings_max_age()
        except Exception:
            max_age = 45 * 86400
        if "score" not in data:
            max_age = min(max_age, _TMDB_UNRATED_MAX_AGE)
        if time.time() - fetched_at < max_age:
            return data.get("score")
        stale = data
    fresh = _fetch_tmdb_score(media_type, tmdb_id)
    if fresh is None:
        return (stale or {}).get("score")
    try:
        db.save_item_ratings(key, fresh, time.time())
    except Exception:
        pass
    return fresh.get("score")


def forget_tmdb_scores(media_type: str, tmdb_ids: List[Any]) -> int:
    """Drop stored TMDb scores so the next render reads them again (Refresh now)."""
    from . import database as db
    keys = [_tmdb_score_key(media_type, t) for t in tmdb_ids if t not in (None, "")]
    if not keys:
        return 0
    with db.get_db() as conn:
        cur = conn.executemany("DELETE FROM item_ratings WHERE cache_key = ?", [(k,) for k in keys])
        conn.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def _num(value: Any, scale: float = 1.0) -> Optional[float]:
    try:
        v = float(value) / scale
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    return round(min(v, 10.0), 1)


def from_plex_element(el) -> Tuple[Optional[float], Optional[float]]:
    """(audience, critic) from a Plex <Video>/<Directory> element."""
    if el is None:
        return None, None
    return _num(el.get("audienceRating")), _num(el.get("rating"))


def from_plex_xml(xml_text: str) -> Tuple[Optional[float], Optional[float]]:
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None, None
    el = root.find(".//Video")
    if el is None:
        el = root.find(".//Directory")
    return from_plex_element(el)


def from_jellyfin_item(item: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """(audience, critic) from a Jellyfin/Emby item: CommunityRating 0-10,
    CriticRating 0-100."""
    return _num(item.get("CommunityRating")), _num(item.get("CriticRating"), 10.0)


def store(server_id: str, server_type: str, media_type: str,
          rows: Iterable[Tuple[str, Any, Optional[float], Optional[float]]]) -> int:
    """rows: (rating_key, tmdb_id, audience, critic). media_type "movie"/"tv".
    Never raises."""
    data = []
    for rating_key, tmdb_id, audience, critic in rows:
        if not rating_key:
            continue
        try:
            tmdb = int(tmdb_id) if tmdb_id not in (None, "") else None
        except (TypeError, ValueError):
            tmdb = None
        data.append((server_id, str(rating_key), server_type, media_type, tmdb, audience, critic))
    if not data:
        return 0
    try:
        from . import database as db
        with db.get_db() as conn:
            conn.executemany(
            """INSERT INTO server_ratings (server_id, rating_key, server_type, media_type, tmdb_id,
                   audience_rating, critic_rating, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(server_id, rating_key) DO UPDATE SET
                   server_type=excluded.server_type, media_type=excluded.media_type,
                   tmdb_id=excluded.tmdb_id, audience_rating=excluded.audience_rating,
                   critic_rating=excluded.critic_rating, updated_at=CURRENT_TIMESTAMP""",
            data,
            )
        return len(data)
    except Exception as e:
        from .config import logger
        logger.debug("[RATINGS] Couldn't store server ratings: %s", e)
        return 0


def _types_for(source: str) -> Tuple[str, ...]:
    return ("plex",) if source == "plex" else ("jellyfin", "emby")


def lookup(source: str, media_type: str, tmdb_id: Any = None, rating_key: Any = None) -> Dict[str, Optional[float]]:
    """{"audience_rating", "critic_rating"} from one server type ("plex" or
    "jellyfin", which includes Emby), matched by TMDb id, else rating key."""
    out: Dict[str, Optional[float]] = {"audience_rating": None, "critic_rating": None}
    types = _types_for(source)
    marks = ",".join("?" * len(types))
    mt = "movie" if media_type == "movie" else "tv"
    try:
        from . import database as db
        with db.get_db() as conn:
            row = _find_row(conn, mt, tmdb_id, rating_key, types, marks)
        if row is not None:
            out["audience_rating"], out["critic_rating"] = row[0], row[1]
    except Exception:
        pass
    return out


def _find_row(conn, mt, tmdb_id, rating_key, types, marks):
    row = None
    if tmdb_id not in (None, ""):
        row = conn.execute(
            f"""SELECT audience_rating, critic_rating FROM server_ratings
                WHERE media_type = ? AND tmdb_id = ? AND server_type IN ({marks})
                  AND (audience_rating IS NOT NULL OR critic_rating IS NOT NULL)
                ORDER BY updated_at DESC LIMIT 1""",
            (mt, int(tmdb_id), *types),
        ).fetchone()
    if row is None and rating_key not in (None, ""):
        row = conn.execute(
            f"""SELECT audience_rating, critic_rating FROM server_ratings
                WHERE rating_key = ? AND server_type IN ({marks})""",
            (str(rating_key), *types),
        ).fetchone()
    return row


def _sources() -> Dict[str, str]:
    from . import database as db
    try:
        cfg = (db.get_ui_settings() or {}).get("mdblist") or {}
    except Exception:
        cfg = {}
    return {
        "audience_rating": str(cfg.get("audienceRatingSource") or "server").lower(),
        "critic_rating": str(cfg.get("criticRatingSource") or "server").lower(),
    }


def server_order() -> List[str]:
    """"plex"/"jellyfin" in the order the enabled servers are listed in
    Settings > Media Servers (Emby counts as "jellyfin"). Both, Plex first,
    when nothing is configured."""
    from . import database as db
    try:
        servers = (db.get_ui_settings() or {}).get("mediaServers") or []
    except Exception:
        servers = []
    order: List[str] = []
    for srv in servers:
        if not isinstance(srv, dict) or srv.get("enabled") is False:
            continue
        kind = "plex" if srv.get("type") == "plex" else "jellyfin" if srv.get("type") in ("jellyfin", "emby") else None
        if kind and kind not in order:
            order.append(kind)
    return order or ["plex", "jellyfin"]


def fill(ctx: Dict[str, Any], media_type: str, tmdb_id: Any, mdblist_ready: bool) -> Dict[str, str]:
    """Put audience_rating/critic_rating in ctx from the media servers when the
    chosen source is a server, or when it's an MDBList source but MDBList can't
    be used. Returns {field: where it came from} for the render log."""
    used: Dict[str, str] = {}
    rating_key = ctx.get("rating_key")
    cache: Dict[str, Dict[str, Optional[float]]] = {}
    tmdb_value: List[Optional[float]] = []  # fetched at most once

    def _tmdb() -> Optional[float]:
        if not tmdb_value:
            tmdb_value.append(tmdb_audience_rating(media_type, tmdb_id))
        return tmdb_value[0]

    for field, source in _sources().items():
        if ctx.get(field) not in (None, ""):
            continue
        if source == TMDB_SOURCE:
            order: List[str] = [TMDB_SOURCE]
        elif source in SERVER_SOURCES:
            # The server(s) first. With an MDBList key, MDBList comes next
            # (fill_after_mdblist() then tries TMDb); without one, TMDb now.
            order = server_order() if source == "server" else [source]
            if not mdblist_ready:
                order = order + [TMDB_SOURCE]
        elif not mdblist_ready:
            # MDBList source without a key: the servers instead, then TMDb.
            order = server_order() + [TMDB_SOURCE]
        else:
            continue
        for src in order:
            if src == TMDB_SOURCE:
                # TMDb only has an audience score.
                value = _tmdb() if field == "audience_rating" else None
                label = "TMDb"
            else:
                if src not in cache:
                    cache[src] = lookup(src, media_type, tmdb_id, rating_key)
                value = cache[src].get(field)
                label = "Plex" if src == "plex" else "Jellyfin/Emby"
            if value is not None:
                ctx[field] = value
                used[field] = label
                break
    return used


def mdblist_fallback_source(field: str, source: str) -> Optional[str]:
    """The MDBList source to use for a field whose chosen source is a media
    server, or None when the chosen source isn't a media server."""
    return MDBLIST_FALLBACK.get(field) if source in SERVER_SOURCES else None


def fallback_label(field: str) -> str:
    return _FALLBACK_LABELS.get(MDBLIST_FALLBACK.get(field, ""), "MDBList")


def fill_after_mdblist(ctx: Dict[str, Any], media_type: str, tmdb_id: Any) -> Dict[str, str]:
    """TMDb's audience score for a media-server source that neither a server
    nor MDBList had a value for (used when an MDBList key is set; without one
    fill() already tried TMDb)."""
    used: Dict[str, str] = {}
    if ctx.get("audience_rating") in (None, "") and _sources()["audience_rating"] in SERVER_SOURCES:
        value = tmdb_audience_rating(media_type, tmdb_id)
        if value is not None:
            ctx["audience_rating"] = value
            used["audience_rating"] = "TMDb"
    return used


def _any_server_enabled() -> bool:
    from . import database as db
    try:
        servers = (db.get_ui_settings() or {}).get("mediaServers") or []
    except Exception:
        servers = []
    return any(isinstance(s, dict) and s.get("enabled") is not False and s.get("type") in ("plex", "jellyfin", "emby")
               for s in servers)


def mdblist_fields_wanted() -> set:
    """Which of audience/critic rating should still come from MDBList (used to
    decide whether to batch-fetch MDBList ratings before a render). A media-
    server source counts only when no media server is enabled; otherwise the
    server normally has the value and MDBList is asked per item only when it
    doesn't."""
    no_server = None
    out = set()
    for f, s in _sources().items():
        if s not in LOCAL_SOURCES:
            out.add(f)
        elif s in SERVER_SOURCES:
            if no_server is None:
                no_server = not _any_server_enabled()
            if no_server:
                out.add(f)
    return out
