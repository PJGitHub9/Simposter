"""
Poster drift detection: notice when a poster Simposter sent was changed on the
server by something else (Kometa overlays, a manual edit, another tool).

How it works:
  * Every successful poster send stores a small fingerprint of the sent image
    (a 16x24 RGB thumbnail, base64) per (server_id, rating_key).
  * Scans already re-download a poster only when the server reports a new
    poster version (Quirk #152). Right after that download, the new poster is
    fingerprinted and compared with the stored one.
  * A difference beyond normal re-encoding/resizing noise marks the item as
    drifted. What happens next is the user's choice (get_action()):
      off     - nothing is checked
      list    - shown under History -> Changed Outside Simposter
      notify  - listed, plus one Discord/Apprise summary per scan
      resend  - listed, and the last poster Simposter sent is uploaded again

Items Simposter never sent a poster to have no fingerprint and are never
reported.

Logos and backdrops work the same way (asset_type "logo"/"backdrop"). Their
sent bytes are also kept in config/cache/drift_sent/ so "put back" can upload
them again (posters use the existing resend cache instead).
"""
from __future__ import annotations

import base64
import io
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from . import database as db
from .config import logger

ACTIONS = ("off", "list", "notify", "resend")
ASSET_TYPES = ("poster", "logo", "backdrop")
DEFAULT_ACTION = "list"
_GRID = (16, 24)  # width x height of the fingerprint thumbnail

# Thresholds, from comparing renders against JPEG-recompressed, Plex-sized
# copies (noise) and against copies with a small corner badge (a change).
_CELL_DELTA = 40     # a cell this different (0-255, any channel) counts as changed
_CHANGED_CELLS = 2   # this many changed cells = drift
_MEAN_DELTA = 10.0   # or an average difference this large = drift

_pending_lock = threading.Lock()
_pending: List[Dict[str, Any]] = []
# Every drift found since the last flush, for one summary log line per scan.
_scan_found: List[str] = []


# --------------------------------------------------------------------------
# Settings (own table, so a Settings page save can't reset it)
# --------------------------------------------------------------------------

def _ensure_config_table(cursor) -> None:
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS poster_drift_config (id INTEGER PRIMARY KEY CHECK (id = 1), action TEXT NOT NULL)"
    )


def get_action() -> str:
    try:
        with db.get_db() as conn:
            cur = conn.cursor()
            _ensure_config_table(cur)
            cur.execute("SELECT action FROM poster_drift_config WHERE id = 1")
            row = cur.fetchone()
        action = row[0] if row else DEFAULT_ACTION
        return action if action in ACTIONS else DEFAULT_ACTION
    except Exception:
        return DEFAULT_ACTION


def set_action(action: str) -> str:
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    with db.get_db() as conn:
        cur = conn.cursor()
        _ensure_config_table(cur)
        cur.execute(
            "INSERT INTO poster_drift_config (id, action) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET action = excluded.action",
            (action,),
        )
    return action


# --------------------------------------------------------------------------
# Fingerprints
# --------------------------------------------------------------------------

def fingerprint(image: Any) -> Optional[str]:
    """bytes / path / PIL image -> base64 of a 16x24 RGB thumbnail."""
    try:
        if isinstance(image, Image.Image):
            img = image
        elif isinstance(image, (bytes, bytearray)):
            img = Image.open(io.BytesIO(image))
        else:
            img = Image.open(str(image))
        img = _flatten(img).resize(_GRID, Image.BOX)
        return base64.b64encode(img.tobytes()).decode("ascii")
    except Exception as e:
        logger.debug("[DRIFT] Couldn't fingerprint image: %s", e)
        return None


def _flatten(img: Image.Image) -> Image.Image:
    """RGB as the image looks: a transparent image (logos) is drawn on black.
    convert("RGB") alone keeps the hidden colour under transparent pixels,
    which any resize or re-save can change while the logo looks the same."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (0, 0, 0))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB")


def recheck_art_fingerprints(force: bool = False) -> Dict[str, int]:
    """Once after fingerprints started ignoring the colour under transparent
    pixels: recompute stored logo/backdrop fingerprints from the kept sent
    copies, and clear drift marks that no longer hold against the cached image.
    (Shrinking the cache had made every logo look changed.)"""
    marker = "drift_fp_alpha_v1"
    out = {"recomputed": 0, "cleared": 0}
    try:
        with db.get_db() as conn:
            cur = conn.cursor()
            if not force and cur.execute("SELECT 1 FROM applied_migrations WHERE name = ?", (marker,)).fetchone():
                return out
            rows = cur.execute(
                "SELECT server_id, rating_key, asset_type, fingerprint, drift_detected_at FROM poster_fingerprints "
                "WHERE asset_type IN ('logo', 'backdrop')"
            ).fetchall()
        from .api import movies as m
        for server_id, rating_key, asset_type, old_fp, drifted in rows:
            fp = old_fp
            sent = sent_copy_path(server_id, rating_key, asset_type)
            if sent.exists():
                new_fp = fingerprint(sent.read_bytes())
                if new_fp and new_fp != old_fp:
                    fp = new_fp
                    out["recomputed"] += 1
            clear = False
            if drifted:
                cached = m._logo_cache_path(rating_key) if asset_type == "logo" else m._art_cache_path(rating_key)
                current = fingerprint(cached) if cached else None
                clear = bool(current) and not compare(fp, current)["drift"]
            if fp != old_fp or clear:
                with db.get_db() as conn:
                    if clear:
                        conn.cursor().execute(
                            """UPDATE poster_fingerprints SET fingerprint = ?, drift_detected_at = NULL, drift_score = NULL,
                                 drift_action = NULL WHERE server_id = ? AND rating_key = ? AND asset_type = ?""",
                            (fp, server_id, rating_key, asset_type))
                        out["cleared"] += 1
                    else:
                        conn.cursor().execute(
                            "UPDATE poster_fingerprints SET fingerprint = ? WHERE server_id = ? AND rating_key = ? AND asset_type = ?",
                            (fp, server_id, rating_key, asset_type))
        with db.get_db() as conn:
            conn.cursor().execute("INSERT OR IGNORE INTO applied_migrations (name) VALUES (?)", (marker,))
        if out["recomputed"] or out["cleared"]:
            logger.info("[DRIFT] Logo/backdrop fingerprints updated: %d recomputed, %d false 'changed' marks cleared",
                        out["recomputed"], out["cleared"])
    except Exception as e:
        logger.warning("[DRIFT] Couldn't recheck logo/backdrop fingerprints: %s", e)
    return out


def compare(a: str, b: str) -> Dict[str, Any]:
    """{"drift": bool, "score": mean difference, "changed_cells": n}."""
    pa = base64.b64decode(a)
    pb = base64.b64decode(b)
    if len(pa) != len(pb) or not pa:
        return {"drift": True, "score": 255.0, "changed_cells": -1}
    changed = 0
    total = 0
    for i in range(0, len(pa), 3):
        d = max(abs(pa[i] - pb[i]), abs(pa[i + 1] - pb[i + 1]), abs(pa[i + 2] - pb[i + 2]))
        total += d
        if d > _CELL_DELTA:
            changed += 1
    mean = total / (len(pa) / 3)
    return {"drift": changed >= _CHANGED_CELLS or mean > _MEAN_DELTA,
            "score": round(mean, 2), "changed_cells": changed}


def _sent_dir() -> Path:
    from .config import settings
    d = Path(settings.CONFIG_DIR) / "cache" / "drift_sent"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(part))


def sent_copy_path(server_id: str, rating_key: str, asset_type: str) -> Path:
    """Where the last logo/backdrop Simposter sent to this item is kept."""
    return _sent_dir() / f"{_safe(server_id)}__{_safe(rating_key)}.{asset_type}"


def remove_sent_copies(server_id: str) -> None:
    """Drop the kept logo/backdrop copies of a removed media server."""
    try:
        for f in _sent_dir().glob(f"{_safe(server_id)}__*"):
            f.unlink(missing_ok=True)
    except OSError:
        pass


def record_sent(server_id: Optional[str], rating_key: Optional[str], image: Any, asset_type: str = "poster") -> None:
    """Remember what Simposter just sent to this item (clears any drift mark).
    Never raises: a fingerprint failure must not fail a send."""
    if not rating_key or image is None or asset_type not in ASSET_TYPES:
        return
    fp = fingerprint(image)
    if not fp:
        return
    server_id = server_id or "plex-1"
    try:
        with db.get_db() as conn:
            conn.cursor().execute(
                """INSERT INTO poster_fingerprints (server_id, rating_key, asset_type, fingerprint, sent_at,
                                                    drift_detected_at, drift_score, drift_action)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, NULL, NULL, NULL)
                   ON CONFLICT(server_id, rating_key, asset_type) DO UPDATE SET
                     fingerprint = excluded.fingerprint, sent_at = CURRENT_TIMESTAMP,
                     drift_detected_at = NULL, drift_score = NULL, drift_action = NULL""",
                (server_id, str(rating_key), asset_type, fp),
            )
        if asset_type != "poster" and isinstance(image, (bytes, bytearray)):
            sent_copy_path(server_id, str(rating_key), asset_type).write_bytes(bytes(image))
    except Exception as e:
        logger.debug("[DRIFT] Couldn't store %s fingerprint for %s: %s", asset_type, rating_key, e)


def matches_sent(server_id: Optional[str], rating_key: Optional[str], image: Any,
                 asset_type: str = "poster") -> Optional[bool]:
    """Is this image what Simposter last sent to the item? True if it matches
    the stored fingerprint (within re-encoding noise), False if it differs,
    None when nothing was ever sent (no fingerprint) or the image can't be read.
    Used by the overlay-only path (backend/overlay_only.py) so a poster
    Simposter sent itself is never kept as the other app's clean copy."""
    if not rating_key:
        return None
    try:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM poster_fingerprints WHERE server_id = ? AND rating_key = ? AND asset_type = ?",
                (server_id or "plex-1", str(rating_key), asset_type),
            ).fetchone()
        if not row or not row[0]:
            return None
        current = fingerprint(image)
        if not current:
            return None
        return not compare(row[0], current)["drift"]
    except Exception as e:
        logger.debug("[DRIFT] matches_sent failed for %s: %s", rating_key, e)
        return None


# --------------------------------------------------------------------------
# Checking after a scan
# --------------------------------------------------------------------------

def _clear_mark(server_id: str, rating_key: str, asset_type: str = "poster") -> None:
    with db.get_db() as conn:
        conn.execute("UPDATE poster_fingerprints SET drift_detected_at = NULL, drift_score = NULL, drift_action = NULL "
                     "WHERE server_id = ? AND rating_key = ? AND asset_type = ?",
                     (server_id, str(rating_key), asset_type))


def poster_mode_for(server_id: str, rating_key: str) -> Tuple[str, Optional[int]]:
    """(poster mode, season index) for a drift-tracked item. The season index
    comes from Overlay Refresh tracking (None for a movie or show poster)."""
    from . import poster_mode
    season_index = None
    try:
        with db.get_db() as conn:
            row = conn.execute("SELECT season_index FROM overlay_state WHERE server_id = ? AND rating_key = ? LIMIT 1",
                               (server_id, str(rating_key))).fetchone()
        if row and row[0] is not None and int(row[0]) >= 0:
            season_index = int(row[0])
    except Exception:
        pass
    mode = poster_mode.gate(server_id, str(rating_key), None, poster_mode.infer_is_tv(rating_key))
    return mode, season_index


def check_after_download(server_id: Optional[str], rating_key: str, poster_path: Any,
                         asset_type: str = "poster") -> Optional[Dict[str, Any]]:
    """Called by a scan right after it re-downloaded a poster/logo/backdrop
    whose version changed. Compares it with what Simposter last sent; marks
    and handles a drift. Returns the drift info, or None.

    Poster modes (posters only): leave_alone is never compared (and an old
    mark is cleared); for overlay_only a difference is the other app's new
    poster, so the overlays go back on it (overlay_only.on_external_poster)
    instead of the configured action -- no mark, list entry or notification."""
    server_id = server_id or "plex-1"
    try:
        poster_mode, season_index = ("full", None)
        if asset_type == "poster":
            poster_mode, season_index = poster_mode_for(server_id, rating_key)
            if poster_mode == "leave_alone":
                _clear_mark(server_id, rating_key)
                return None
        action = get_action()
        # Overlay-only titles are checked even with the drift action off: it's
        # how the other app's new poster gets its overlays back.
        if action == "off" and poster_mode != "overlay_only":
            return None
        with db.get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT fingerprint, drift_detected_at FROM poster_fingerprints "
                "WHERE server_id = ? AND rating_key = ? AND asset_type = ?",
                (server_id, str(rating_key), asset_type),
            )
            row = cur.fetchone()
        if not row:
            return None
        current = fingerprint(poster_path)
        if not current:
            return None
        result = compare(row[0], current)
        if not result["drift"]:
            return None
        if poster_mode == "overlay_only":
            from . import overlay_only
            _clear_mark(server_id, rating_key)
            overlay_only.on_external_poster(server_id, str(rating_key), season_index)
            return None
        title = _title(rating_key)
        logger.debug("[DRIFT] %s for %s on %s was changed outside Simposter (difference %.1f, %d areas)",
                     asset_type.capitalize(), title, server_id, result["score"], result["changed_cells"])
        try:
            from .media_server import get_server_label
            where = get_server_label(server_id)
        except Exception:
            where = server_id
        with _pending_lock:
            _scan_found.append(f"{title} ({where}{'' if asset_type == 'poster' else ', ' + asset_type})")
        already = row[1] is not None
        with db.get_db() as conn:
            conn.cursor().execute(
                """UPDATE poster_fingerprints SET drift_detected_at = CURRENT_TIMESTAMP, drift_score = ?,
                     drift_action = ? WHERE server_id = ? AND rating_key = ? AND asset_type = ?""",
                (result["score"], action, server_id, str(rating_key), asset_type),
            )
        info = {"server_id": server_id, "rating_key": str(rating_key), "asset_type": asset_type, "title": title, **result}
        if action == "resend":
            info["resent"] = resend(server_id, str(rating_key), asset_type)
        if action in ("notify", "resend") and not already:
            with _pending_lock:
                _pending.append(info)
        return info
    except Exception as e:
        logger.debug("[DRIFT] Check failed for %s: %s", rating_key, e)
        return None


def _title(rating_key: str) -> str:
    try:
        title, year = db.get_title_for_rating_key(str(rating_key))
        if title:
            return f"{title} ({year})" if year else str(title)
    except Exception:
        pass
    return f"item {rating_key}"


def resend(server_id: str, rating_key: str, asset_type: str = "poster") -> bool:
    """Upload the last poster Simposter sent again (the resend cache), the same
    way the grid's resend button does. Logos/backdrops: the kept copy."""
    if asset_type != "poster":
        return _resend_art(server_id, rating_key, asset_type)
    try:
        from .api.plexsend import api_render_cache_resend, ResendCachedRequest, ResendTarget
        is_tv = _is_tv(rating_key)
        api_render_cache_resend(
            rating_key,
            ResendCachedRequest(is_tv=is_tv, targets=[ResendTarget(server_id=server_id, rating_key=rating_key)]),
        )
        logger.info("[DRIFT] Re-sent Simposter's poster for %s to %s", _title(rating_key), server_id)
        return True
    except Exception as e:
        logger.warning("[DRIFT] Couldn't re-send the poster for %s: %s", _title(rating_key), getattr(e, "detail", e))
        return False


def _resend_art(server_id: str, rating_key: str, asset_type: str) -> bool:
    path = sent_copy_path(server_id, rating_key, asset_type)
    if not path.exists():
        logger.warning("[DRIFT] No saved %s for %s; send it again from Simposter instead", asset_type, _title(rating_key))
        return False
    try:
        from .media_server.base import ImageType
        from .media_server.registry import get_client
        client = get_client(server_id)
        if client is None:
            raise RuntimeError(f"server {server_id} isn't configured")
        data = path.read_bytes()
        content_type = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
        image_type = ImageType.LOGO if asset_type == "logo" else ImageType.BACKDROP
        # upload_image() records the fingerprint again, which clears the mark.
        client.upload_image(rating_key, image_type, data, content_type)
        try:
            from .api import movies as m
            if asset_type == "logo":
                m._save_logo_cache(rating_key, data, content_type)
            else:
                saved = m._save_art_cache(rating_key, data, content_type)
                if saved:
                    m._art_thumbnail(rating_key, saved)
        except Exception:
            pass
        logger.info("[DRIFT] Re-sent Simposter's %s for %s to %s", asset_type, _title(rating_key), server_id)
        return True
    except Exception as e:
        logger.warning("[DRIFT] Couldn't re-send the %s for %s: %s", asset_type, _title(rating_key), e)
        return False


def _is_tv(rating_key: str) -> bool:
    try:
        return db.get_cached_tv_show(str(rating_key)) is not None
    except Exception:
        return False


def dismiss(server_id: str, rating_key: str, poster_path: Any = None, asset_type: str = "poster") -> None:
    """Keep the server's poster: clear the drift mark, and if the current
    poster is available, adopt it as the new baseline so it isn't reported again."""
    fp = fingerprint(poster_path) if poster_path else None
    with db.get_db() as conn:
        if fp:
            conn.cursor().execute(
                """UPDATE poster_fingerprints SET fingerprint = ?, drift_detected_at = NULL, drift_score = NULL,
                     drift_action = NULL WHERE server_id = ? AND rating_key = ? AND asset_type = ?""",
                (fp, server_id, rating_key, asset_type),
            )
        else:
            conn.cursor().execute(
                """UPDATE poster_fingerprints SET drift_detected_at = NULL, drift_score = NULL, drift_action = NULL
                   WHERE server_id = ? AND rating_key = ? AND asset_type = ?""",
                (server_id, rating_key, asset_type),
            )


def list_drifted() -> List[Dict[str, Any]]:
    with db.get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT server_id, rating_key, asset_type, sent_at, drift_detected_at, drift_score, drift_action
               FROM poster_fingerprints WHERE drift_detected_at IS NOT NULL ORDER BY drift_detected_at DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["title"] = _title(r["rating_key"])
        r["is_tv"] = _is_tv(r["rating_key"])
        # For grouping by library group in History (a season maps to its show's library).
        try:
            r["library_id"] = db.get_library_id_for_rating_key(str(r["rating_key"]))
        except Exception:
            r["library_id"] = None
    return rows


def drifted_keys() -> List[Dict[str, str]]:
    """[{server_id, rating_key, asset_type}] currently marked as changed, for grid badges."""
    with db.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT server_id, rating_key, asset_type FROM poster_fingerprints WHERE drift_detected_at IS NOT NULL")
        return [dict(r) for r in cur.fetchall()]


def tracked_count() -> int:
    with db.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM poster_fingerprints")
        return int(cur.fetchone()[0])


def flush_notifications() -> None:
    """Send one summary for the drifts found since the last flush (end of a scan)."""
    with _pending_lock:
        items = list(_pending)
        _pending.clear()
        found = list(_scan_found)
        _scan_found.clear()
    if found:
        shown = ", ".join(found[:10]) + (f" and {len(found) - 10} more" if len(found) > 10 else "")
        logger.info("[DRIFT] %d changed outside Simposter this scan: %s (History → Changed Outside Simposter)",
                    len(found), shown)
    if not items:
        return
    try:
        from .api.notifications import send_poster_drift_notification
        send_poster_drift_notification(items)
    except Exception as e:
        logger.warning("[DRIFT] Notification failed: %s", e)
