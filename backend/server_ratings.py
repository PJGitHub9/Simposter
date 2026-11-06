"""Ratings the media servers already have, for overlay rules and text.

Kometa's audience_rating/critic_rating are Plex's own audienceRating/rating
attributes (modules/plex.py), so they need no outside service. Scans store
them here: Plex audienceRating/rating, Jellyfin/Emby CommunityRating and
CriticRating (0-100, stored /10). All values are 0-10.

Settings > Ratings & Lists picks one source per field: "server" (the default:
the first enabled media server in Settings > Media Servers that has a rating
for the item), "plex", "jellyfin" (Jellyfin or Emby) or an MDBList source. When an MDBList source is picked but there is
no MDBList key, the media server's value is used instead, so overlays that
use a rating still work out of the box.

Rows are keyed by (server_id, rating_key) and looked up by TMDb id, so a
rating stored from the Plex copy also applies to the Jellyfin copy.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

SERVER_SOURCES = ("server", "plex", "jellyfin")


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
    for field, source in _sources().items():
        if ctx.get(field) not in (None, ""):
            continue
        if source == "server":
            order = server_order()
        elif source in SERVER_SOURCES:
            order = [source]
        elif not mdblist_ready:
            order = server_order()  # MDBList source without a key: the servers instead
        else:
            continue
        for src in order:
            if src not in cache:
                cache[src] = lookup(src, media_type, tmdb_id, rating_key)
            value = cache[src].get(field)
            if value is not None:
                ctx[field] = value
                used[field] = "Plex" if src == "plex" else "Jellyfin/Emby"
                break
    return used


def mdblist_fields_wanted() -> set:
    """Which of audience/critic rating should still come from MDBList."""
    return {f for f, s in _sources().items() if s not in SERVER_SOURCES}
