"""Radarr/Sonarr tags, read only, for poster mode rules (backend/poster_mode.py).

Two requests per instance: /api/v3/tag (id -> label) and /api/v3/movie
(Radarr, keyed by TMDb id) or /api/v3/series (Sonarr, keyed by TVDB id and,
when Sonarr has one, TMDb id). The v3 API is served by Radarr, Sonarr v4 and
Sonarr v5. Nothing is ever written to Radarr or Sonarr.

A successful fetch replaces the instance's rows in arr_tags; a failed one
leaves them and records the error, and callers must then treat the tags as
unknown (sync_ok() False), not as "no tags".
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from . import database as db
from .config import api_user_agent, redact_secrets

logger = logging.getLogger("simposter")

TYPES = ("radarr", "sonarr")
_ID_MAP_DAYS = 30

Key = Tuple[str, str]


class ArrError(Exception):
    pass


def _instances() -> List[Dict[str, Any]]:
    try:
        ui = db.get_ui_settings() or {}
    except Exception:
        return []
    return [i for i in (ui.get("arrInstances") or []) if isinstance(i, dict)]


def get_instance(instance_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not instance_id:
        return None
    for i in _instances():
        if str(i.get("id")) == str(instance_id):
            return i
    return None


def _get(url: str, api_key: str, path: str, timeout: int) -> Any:
    base = str(url or "").strip().rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        raise ArrError("The address must start with http:// or https://")
    try:
        r = requests.get(f"{base}{path}", headers={"X-Api-Key": str(api_key or ""), "User-Agent": api_user_agent()},
                         timeout=timeout, allow_redirects=False)
    except requests.RequestException as e:
        raise ArrError(redact_secrets(f"Couldn't reach {base}: {e}"))
    if r.status_code in (401, 403):
        raise ArrError("The API key was rejected")
    if 300 <= r.status_code < 400:
        raise ArrError("The address redirects somewhere else; use the direct address (including any URL base)")
    if r.status_code >= 400:
        raise ArrError(f"The server answered {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise ArrError("The answer wasn't JSON; check the address (including any URL base)")


def test_connection(type: str, url: str, api_key: str) -> Dict[str, Any]:
    out = {"ok": False, "app": "", "version": "", "error": ""}
    if type not in TYPES:
        out["error"] = "Unknown type"
        return out
    try:
        data = _get(url, api_key, "/api/v3/system/status", 10)
    except ArrError as e:
        out["error"] = str(e)
        return out
    if not isinstance(data, dict):
        out["error"] = "Unexpected answer from the server"
        return out
    out["app"], out["version"] = str(data.get("appName") or ""), str(data.get("version") or "")
    if out["app"].lower() != type:
        out["error"] = f"This address is {out['app'] or 'another app'}, not {type.capitalize()}"
        return out
    out["ok"] = True
    return out


def fetch_tags(instance: Dict[str, Any]) -> Dict[Key, List[str]]:
    """{(id_type, id): [tag labels]} for every tagged title. Raises ArrError."""
    kind = instance.get("type")
    if kind not in TYPES:
        raise ArrError("Unknown type")
    url, key = instance.get("url"), instance.get("apiKey")
    tags = _get(url, key, "/api/v3/tag", 30)
    items = _get(url, key, "/api/v3/movie" if kind == "radarr" else "/api/v3/series", 30)
    if not isinstance(tags, list) or not isinstance(items, list):
        raise ArrError("Unexpected answer from the server")
    labels = {t.get("id"): str(t.get("label") or "").strip() for t in tags if isinstance(t, dict)}
    out: Dict[Key, List[str]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        names = [labels[t] for t in (it.get("tags") or []) if labels.get(t)]
        if not names:
            continue
        ids = [("tmdb", it.get("tmdbId"))] if kind == "radarr" else [("tvdb", it.get("tvdbId")), ("tmdb", it.get("tmdbId"))]
        for id_type, value in ids:
            try:
                n = int(value or 0)
            except (TypeError, ValueError):
                n = 0
            if n > 0:
                out[(id_type, str(n))] = names
    return out


def _sync_row(instance_id: str):
    with db.get_db() as conn:
        return conn.execute("SELECT * FROM arr_tag_sync WHERE instance_id = ?", (str(instance_id),)).fetchone()


def sync_ok(instance_id: Optional[str]) -> bool:
    """True when the stored tags come from a successful sync and the last attempt didn't fail."""
    if not instance_id:
        return False
    row = _sync_row(instance_id)
    return bool(row and row["synced_at"] and not row["error"])


def last_error(instance_id: str) -> str:
    row = _sync_row(instance_id)
    return (row["error"] or "") if row else ""


def refresh(instance_id: Optional[str], max_age_seconds: int = 60) -> bool:
    """Fetch the instance's tags unless they were fetched within max_age_seconds.
    Returns whether the stored tags can be trusted. Never raises."""
    try:
        inst = get_instance(instance_id)
        if not inst or inst.get("enabled") is False:
            return False
        iid = str(inst["id"])
        row = _sync_row(iid)
        now = time.time()
        if row and row["attempted_at"] and now - float(row["attempted_at"]) < max_age_seconds:
            return bool(row["synced_at"] and not row["error"])
        try:
            tags = fetch_tags(inst)
        except Exception as e:  # ArrError, or an answer in a shape fetch_tags() didn't expect
            msg = redact_secrets(str(e))
            with db.get_db() as conn:
                conn.execute(
                    "INSERT INTO arr_tag_sync (instance_id, synced_at, attempted_at, error) VALUES (?, NULL, ?, ?) "
                    "ON CONFLICT(instance_id) DO UPDATE SET attempted_at = excluded.attempted_at, error = excluded.error",
                    (iid, now, msg))
            logger.warning("[ARR] Couldn't read tags from %s (%s): %s. Poster modes set by its tags are kept as they are.",
                           inst.get("name") or iid, inst.get("type"), msg)
            return False
        with db.get_db() as conn:
            conn.execute("DELETE FROM arr_tags WHERE instance_id = ?", (iid,))
            conn.executemany("INSERT INTO arr_tags (instance_id, id_type, item_id, tags_json) VALUES (?,?,?,?)",
                             [(iid, k[0], k[1], json.dumps(v)) for k, v in tags.items()])
            conn.execute(
                "INSERT INTO arr_tag_sync (instance_id, synced_at, attempted_at, error) VALUES (?, ?, ?, '') "
                "ON CONFLICT(instance_id) DO UPDATE SET synced_at = excluded.synced_at, "
                "attempted_at = excluded.attempted_at, error = ''", (iid, now, now))
        logger.debug("[ARR] %s: %d tagged title id(s)", inst.get("name") or iid, len(tags))
        return True
    except Exception as e:
        logger.warning("[ARR] Tag refresh failed for %s: %s", instance_id, redact_secrets(str(e)))
        return False


def tags_for(instance_id: Optional[str]) -> Dict[Key, List[str]]:
    if not instance_id:
        return {}
    out: Dict[Key, List[str]] = {}
    with db.get_db() as conn:
        for r in conn.execute("SELECT id_type, item_id, tags_json FROM arr_tags WHERE instance_id = ?",
                              (str(instance_id),)).fetchall():
            try:
                v = json.loads(r["tags_json"] or "[]")
            except ValueError:
                v = []
            out[(r["id_type"], r["item_id"])] = [str(t) for t in v] if isinstance(v, list) else []
    return out


def tags_of(instance_id: Optional[str], key: Key) -> Optional[List[str]]:
    """One title's tags; None when the instance has no row for it."""
    if not instance_id:
        return None
    with db.get_db() as conn:
        r = conn.execute("SELECT tags_json FROM arr_tags WHERE instance_id = ? AND id_type = ? AND item_id = ?",
                         (str(instance_id), key[0], str(key[1]))).fetchone()
    if r is None:
        return None
    try:
        v = json.loads(r["tags_json"] or "[]")
    except ValueError:
        return []
    return [str(t) for t in v] if isinstance(v, list) else []


def known_tags(instance_id: Optional[str]) -> List[str]:
    seen = {t for tags in tags_for(instance_id).values() for t in tags if t}
    return sorted(seen, key=str.lower)


def tvdb_for_tmdb(tmdb_id) -> Optional[str]:
    """A show's TVDB id from its TMDb id (TMDb external ids), remembered for
    30 days including "none". A failed lookup is not remembered."""
    key = str(tmdb_id or "").strip()
    if not key:
        return None
    now = time.time()
    with db.get_db() as conn:
        row = conn.execute("SELECT tvdb_id, checked_at FROM arr_id_map WHERE tmdb_id = ?", (key,)).fetchone()
    if row and now - float(row["checked_at"] or 0) < _ID_MAP_DAYS * 86400:
        return row["tvdb_id"] or None
    try:
        from . import tmdb_client
        ext = tmdb_client.get_tv_external_ids(int(key)) or {}
    except Exception as e:
        logger.debug("[ARR] TVDB id lookup for TMDb %s failed: %s", key, redact_secrets(str(e)))
        return None
    tvdb = str(ext.get("tvdb_id")) if ext.get("tvdb_id") else None
    with db.get_db() as conn:
        conn.execute("INSERT INTO arr_id_map (tmdb_id, tvdb_id, checked_at) VALUES (?,?,?) "
                     "ON CONFLICT(tmdb_id) DO UPDATE SET tvdb_id = excluded.tvdb_id, checked_at = excluded.checked_at",
                     (key, tvdb, now))
    return tvdb


def delete_instance_data(instance_id: str) -> None:
    with db.get_db() as conn:
        conn.execute("DELETE FROM arr_tags WHERE instance_id = ?", (str(instance_id),))
        conn.execute("DELETE FROM arr_tag_sync WHERE instance_id = ?", (str(instance_id),))
