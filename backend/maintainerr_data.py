# backend/maintainerr_data.py
"""Snapshot of Maintainerr's collections and "when does this item leave".

One fetch per media type (movie, show, season) replaces the whole snapshot in
`maintainerr_items`. It's used for an hour; a stale snapshot is still used
while a background sync runs, and Overlay Refresh forces a sync before it
checks posters. An item's removal date is the earliest
addDate + deleteAfterDays of the collections it's in, as in Maintainerr.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional

from . import database as db

logger = logging.getLogger("simposter")

STALE_SECONDS = 3600
# After a failed fetch, renders wait this long before trying again (Overlay
# Refresh, which forces a sync, still tries every run).
RETRY_AFTER_FAILURE_SECONDS = 300
TYPES = ("movie", "show", "season")

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_sync_lock = threading.Lock()
_bg_running = threading.Event()


def _parse_add_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _rows_from(type_id: str, collections: List[Dict[str, Any]]) -> List[tuple]:
    rows = []
    for c in collections:
        if c.get("isActive") is False:
            continue
        days = c.get("deleteAfterDays")
        for m in c.get("media") or []:
            added = _parse_add_date(m.get("addDate"))
            sid = m.get("mediaServerId")
            if added is None or sid in (None, ""):
                continue
            deletion = added + timedelta(milliseconds=float(days) * 86_400_000) if days not in (None, "") else added
            rows.append((type_id, str(sid), _to_int(m.get("tmdbId")), _to_int(m.get("tvdbId")),
                         _to_int(c.get("id")), str(c.get("title") or ""), _to_int(c.get("arrAction")),
                         deletion.astimezone(timezone.utc).isoformat(),
                         str(c.get("mediaServerType") or "").lower() or None))
    return rows


def status() -> Dict[str, Any]:
    with db.get_db() as conn:
        row = conn.execute("SELECT fetched_at, last_error, last_attempt_at FROM maintainerr_sync WHERE id = 1").fetchone()
        items = conn.execute("SELECT COUNT(*) FROM maintainerr_items").fetchone()[0]
    return {"fetched_at": row[0] if row else None, "last_error": row[1] if row else None,
            "last_attempt_at": row[2] if row else None, "items": items}


def clear() -> None:
    with db.get_db() as conn:
        conn.execute("DELETE FROM maintainerr_items")
        conn.execute("DELETE FROM maintainerr_sync")


def sync(force: bool = False) -> bool:
    """Fetch every type and replace the snapshot. Only a complete fetch replaces
    it; on failure the old rows stay and the error is recorded. Without force,
    a fresh snapshot or a failed attempt in the last 5 minutes means no fetch
    (threads waiting on the lock reuse the fetch that just finished)."""
    from . import maintainerr_client as mc
    if not mc.is_configured():
        return False
    with _sync_lock:
        if not force:
            st = status()
            fetched, attempted = st["fetched_at"], st["last_attempt_at"]
            if fetched and time.time() - fetched < STALE_SECONDS:
                return True
            last_failed = bool(attempted) and (not fetched or fetched < attempted)
            if last_failed and time.time() - attempted < RETRY_AFTER_FAILURE_SECONDS:
                return False
        attempt_at = time.time()
        try:
            rows: List[tuple] = []
            for type_id in TYPES:
                rows.extend(_rows_from(type_id, mc.fetch_overlay_data(type_id)))
        except mc.MaintainerrError as e:
            with db.get_db() as conn:
                conn.execute("INSERT INTO maintainerr_sync (id, fetched_at, last_error, last_attempt_at) VALUES (1, "
                             "(SELECT fetched_at FROM maintainerr_sync WHERE id = 1), ?, ?) "
                             "ON CONFLICT(id) DO UPDATE SET last_error = excluded.last_error, "
                             "last_attempt_at = excluded.last_attempt_at", (str(e), attempt_at))
            logger.info("[MAINTAINERR] Couldn't update the removal dates: %s", e)
            return False
        with db.get_db() as conn:
            conn.execute("DELETE FROM maintainerr_items")
            conn.executemany("INSERT INTO maintainerr_items (media_type, media_server_id, tmdb_id, tvdb_id, "
                             "collection_id, collection_name, arr_action, deletion_date, media_server_type) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            now = time.time()
            conn.execute("INSERT INTO maintainerr_sync (id, fetched_at, last_error, last_attempt_at) "
                         "VALUES (1, ?, NULL, ?) ON CONFLICT(id) DO UPDATE SET fetched_at = excluded.fetched_at, "
                         "last_error = NULL, last_attempt_at = excluded.last_attempt_at", (now, now))
        logger.info("[MAINTAINERR] Updated removal dates: %d item(s) in Maintainerr collections", len(rows))
        return True


def _background_sync() -> None:
    try:
        sync()
    except Exception as e:
        logger.info("[MAINTAINERR] Background update failed: %s", e)
    finally:
        _bg_running.clear()


def ensure_fresh(background: bool = True) -> None:
    """Never fetched: fetch now. Stale: use it and update in the background
    (one at a time). Fresh: nothing."""
    from . import maintainerr_client as mc
    if not mc.is_configured():
        return
    fetched = status()["fetched_at"]
    if not fetched:
        sync()
        return
    if time.time() - fetched < STALE_SECONDS:
        return
    if not background:
        sync()
        return
    if _bg_running.is_set():
        return
    _bg_running.set()
    threading.Thread(target=_background_sync, name="maintainerr-sync", daemon=True).start()


def lookup(rating_key: Optional[str], tmdb_id: Any, tvdb_id: Any, media_type: str) -> Optional[Dict[str, Any]]:
    """The item's removal date (earliest of its collections) and collection
    names, or None. Matches the item's own id first, then TMDb/TVDB ids, so
    every server's copy of a title gets the same date. For TV the own id is
    checked against show and season rows (a season render carries the
    season's id and the show's TMDb/TVDB ids), and the id fallback only uses
    show rows: a season of a leaving show gets the show's date, a show never
    gets one of its seasons' dates."""
    kind = "show" if str(media_type).lower() in ("show", "tv", "tv-show") else "movie"
    kinds = ("show", "season") if kind == "show" else ("movie",)
    tmdb, tvdb = _to_int(tmdb_id), _to_int(tvdb_id)
    rows = []
    if rating_key not in (None, ""):
        # Maintainerr's ids belong to the one server it manages; an Emby id can
        # equal an unrelated Plex rating key, so ids are only compared within the
        # same server type (an item not in the scan cache counts as Plex).
        try:
            item_type = str(db.get_server_id_for_rating_key(str(rating_key)) or "plex-1").split("-")[0].lower()
        except Exception:
            item_type = "plex"
        with db.get_db() as conn:
            rows = conn.execute("SELECT collection_name, deletion_date FROM maintainerr_items WHERE media_type IN (%s) "
                                "AND media_server_id = ? AND (media_server_type IS NULL OR media_server_type = ?)"
                                % ",".join("?" * len(kinds)), (*kinds, str(rating_key), item_type)).fetchall()
    with db.get_db() as conn:
        if not rows and kind == "movie" and tmdb:
            rows = conn.execute("SELECT collection_name, deletion_date FROM maintainerr_items "
                                "WHERE media_type = 'movie' AND tmdb_id = ?", (tmdb,)).fetchall()
        if not rows and kind == "show" and tvdb:
            rows = conn.execute("SELECT collection_name, deletion_date FROM maintainerr_items "
                                "WHERE media_type = 'show' AND tvdb_id = ?", (tvdb,)).fetchall()
        if not rows and kind == "show" and tmdb:
            rows = conn.execute("SELECT collection_name, deletion_date FROM maintainerr_items "
                                "WHERE media_type = 'show' AND tmdb_id = ?", (tmdb,)).fetchall()
    if not rows:
        return None
    dates = [d for d in (_parse_add_date(r[1]) for r in rows) if d]
    if not dates:
        return None
    names: List[str] = []
    for r in rows:
        if r[0] and r[0] not in names:
            names.append(r[0])
    return {"deletion": min(dates), "collections": names}


def local_date(deletion: datetime, tz: Optional[tzinfo] = None) -> date:
    """The calendar day of a removal instant in the server's time zone (or tz)."""
    return deletion.astimezone(tz).date()


def format_leaving(removal: date, today: date) -> Dict[str, Any]:
    days = max(0, (removal - today).days)
    short = f"{_MONTHS[removal.month - 1]} {removal.day}"
    weekday = _DAYS[removal.weekday()]
    if days == 0:
        leaving = "today"
    elif days == 1:
        leaving = "tomorrow"
    elif days <= 6:
        leaving = weekday
    else:
        leaving = short
    return {"removal_date": removal.isoformat(), "days_until_removal": days, "leaving": leaving,
            "leaving_date": short, "leaving_day": weekday, "leaving_days": str(days)}


def collection_names() -> List[str]:
    with db.get_db() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT collection_name FROM maintainerr_items "
                                           "WHERE collection_name != '' ORDER BY collection_name").fetchall()]
