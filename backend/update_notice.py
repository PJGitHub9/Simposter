"""Notify when a newer Simposter version is available on the running branch.

Uses the same per-branch check as the version badge (api/version_info.py:
APP_VERSION on the branch on GitHub), then reads that branch's
frontend/src/releaseNotes.ts to list what the newer versions include. Sends
one Discord/Apprise notification per new version (Settings -> Notifications,
"App updates"); the version already announced is kept in its own table, not
the settings table, which every Settings save rebuilds (Quirk #60).
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from .config import logger
from . import database as db

CHECK_INTERVAL_HOURS = 6
MAX_HIGHLIGHTS = 6
_ITEM_MAX_CHARS = 160


def _short(item: str) -> str:
    """First sentence of a release-note item, at most _ITEM_MAX_CHARS."""
    m = re.search(r"[.!?](\s|$)", item)
    text = item[:m.start() + 1] if m and m.start() < _ITEM_MAX_CHARS else item
    if len(text) > _ITEM_MAX_CHARS:
        text = text[:_ITEM_MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def _ensure_table() -> None:
    with db.get_db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_update_notice ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), version TEXT, notified_at TIMESTAMP)"
        )


def _last_notified() -> Optional[str]:
    _ensure_table()
    with db.get_db() as conn:
        row = conn.execute("SELECT version FROM app_update_notice WHERE id = 1").fetchone()
    return row["version"] if row else None


def _set_notified(version: str) -> None:
    _ensure_table()
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO app_update_notice (id, version, notified_at) VALUES (1, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET version = excluded.version, notified_at = excluded.notified_at",
            (version,),
        )


def _js_string(raw: str) -> str:
    """Decode the body of a single-quoted JS string ('\\'' and \\uXXXX escapes)."""
    try:
        return json.loads('"' + raw.replace('"', '\\"').replace("\\'", "'") + '"')
    except Exception:
        return raw.replace("\\'", "'")


def parse_release_notes(text: str) -> List[Dict]:
    """[{"version", "sections": [{"title", "items": [...]}]}] from the
    releaseNotes.ts source, newest first (the file's own order)."""
    out: List[Dict] = []
    for block in re.split(r"\n\s*\{\s*\n\s*version:", text)[1:]:
        m = re.match(r"\s*'([^']+)'", block)
        if not m:
            continue
        sections = []
        for sec in re.finditer(r"title:\s*'((?:[^'\\]|\\.)*)'\s*,\s*items:\s*\[(.*?)\]", block, re.S):
            items = [_js_string(i) for i in re.findall(r"'((?:[^'\\]|\\.)*)'", sec.group(2))]
            sections.append({"title": _js_string(sec.group(1)), "items": items})
        out.append({"version": m.group(1), "sections": sections})
    return out


def highlights_between(notes: List[Dict], current: str, latest: str) -> Tuple[List[str], int, List[str]]:
    """(highlights, how many more items, versions covered) for versions newer
    than `current` up to `latest`. New features first, then improvements, then
    fixes, newest version first within each."""
    from .api.version_info import parse_version
    cur, top = parse_version(current), parse_version(latest)
    newer = [n for n in notes if cur < parse_version(n["version"]) <= top]
    order = {"new features": 0, "improvements": 1, "bug fixes": 2}
    items: List[Tuple[int, int, str]] = []
    for vi, note in enumerate(newer):
        for sec in note["sections"]:
            rank = order.get(sec["title"].strip().lower(), 3)
            for item in sec["items"]:
                items.append((rank, vi, item))
    items.sort(key=lambda x: (x[0], x[1]))
    picked = [_short(item) for _r, _v, item in items[:MAX_HIGHLIGHTS]]
    return picked, max(0, len(items) - MAX_HIGHLIGHTS), [n["version"] for n in newer]


def check_and_notify(force: bool = False) -> Dict:
    """Check for a newer version and notify once per version. Returns what was
    found (for the API/tests). Never raises."""
    from .api import version_info as vi
    try:
        current = vi.get_current_version()
        branch = vi.get_git_branch()
        info = vi.check_for_updates(current, branch)
        latest = info.get("latest_version")
        if not info.get("available") or not latest:
            return {"available": False, "current": current, "latest": latest, "branch": branch}
        if not force and _last_notified() == latest:
            return {"available": True, "current": current, "latest": latest, "branch": branch, "notified": False}

        highlights: List[str] = []
        more = 0
        versions: List[str] = []
        try:
            status, text = vi._fetch_raw(branch, "frontend/src/releaseNotes.ts")
            if status == 200:
                highlights, more, versions = highlights_between(parse_release_notes(text), current, latest)
        except Exception as e:
            logger.debug("[UPDATE] Could not read release notes from GitHub: %s", e)

        from .api.notifications import send_app_update_notification
        sent = send_app_update_notification(current, latest, branch, highlights, more, len(versions), info.get("url") or "")
        if sent:
            _set_notified(latest)
            logger.info("[UPDATE] Update available: %s (running %s on %s); notification sent", latest, current, branch)
        else:
            logger.info("[UPDATE] Update available: %s (running %s on %s)", latest, current, branch)
        return {"available": True, "current": current, "latest": latest, "branch": branch, "notified": sent,
                "highlights": highlights, "more": more}
    except Exception as e:
        logger.debug("[UPDATE] Update check failed: %s", e)
        return {"available": False, "error": str(e)}
