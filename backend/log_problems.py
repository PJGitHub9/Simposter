"""Problems summary for the Logs page: every WARNING/ERROR line in one log
file, grouped by kind, with a plain explanation for the kinds we know.

Known kinds are matched by regex (first match wins, so specific ones come
first). Anything else is grouped by its message with numbers, ids and URLs
blanked out, so the same error on different items counts as one problem.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)?\s+(?:\[API\]\s+)?\[(WARNING|ERROR|CRITICAL)\]\s*(.*)$")

# (key, regex on the message, title, what it means / what to do)
_KNOWN = [
    ("image_tmdb", r"download image.*image\.tmdb\.org|image\.tmdb\.org.*(timed out|failed|error)",
     "Couldn't download an image from TMDb",
     "Usually a temporary TMDb or network problem. The next render, scan or Overlay Refresh tries again."),
    ("image_own", r"download image.*/api/(movie|tv-show|logo|backdrop)/",
     "Couldn't load Simposter's own cached image",
     "A poster was rendered on top of the server's current poster and that image wasn't available. Usually fixes itself after the next scan."),
    ("plex_size", r"exceeds Plex's upload size limit",
     "Poster too large for Plex as PNG, sent as JPEG",
     "Harmless: Plex rejects uploads over about 10 MB, so this poster was sent as a high-quality JPEG instead."),
    ("plex_down", r"\[PLEX\].*(Max retries|timed out|Connection|refused|unreachable|Name or service)",
     "Couldn't reach Plex",
     "Check that Plex is running and the URL in Settings → Media Servers is right."),
    ("server_upload", r"\[(MEDIA_SERVER_SEND|JELLYFIN|EMBY)[^\]]*\].*(upload failed|failed)",
     "Upload to Jellyfin/Emby failed",
     "Check the server is reachable. If the item was replaced or re-imported, scan the library and send again."),
    ("server_down", r"\[(JELLYFIN|EMBY)[^\]]*\].*(Max retries|timed out|Connection|refused)",
     "Couldn't reach Jellyfin/Emby",
     "Check the server is running and its URL and API key in Settings → Media Servers."),
    ("discord", r"\[DISCORD\]|discord\.com",
     "Discord notification not delivered",
     "Discord didn't answer or rejected the message. Check the webhook URL in Settings → Notifications."),
    ("apprise", r"\[APPRISE\]",
     "Apprise notification not delivered",
     "Check the Apprise URL in Settings → Notifications."),
    ("tmdb", r"\[TMDB\]",
     "TMDb request failed",
     "Check the TMDb API key in Settings → General. A 429 means too many requests; it slows down and retries."),
    ("mdblist", r"\[MDBLIST\]",
     "MDBList request failed",
     "Check the MDBList key in Settings → General. A 429 means the daily limit was reached."),
    ("lists", r"\[(WETRAKR|SIMKL|FLOPPY|LISTS?)\]",
     "List service request failed",
     "A WeTrakr, SIMKL or Floppy list couldn't be read. Check that service in Settings → General."),
    ("no_poster", r"No valid .*poster found|No poster found",
     "No poster found for an item",
     "TMDb/Fanart have no usable poster yet (common for new or unreleased titles). The retry queue tries again later."),
    ("overlay_refresh", r"\[OVERLAY_REFRESH\]",
     "Overlay Refresh couldn't update a poster",
     "Often a missing source image; the next Overlay Refresh tries again."),
    ("webhook", r"\[(RADARR|SONARR|TAUTULLI)?_?WEBHOOK",
     "Webhook problem",
     "A Radarr/Sonarr webhook couldn't be handled. The lines below say which item."),
    ("db_locked", r"database is locked",
     "Database was busy",
     "Two things wrote at once; it usually succeeds on the next try. Frequent ones on a network share can mean the share is slow."),
]
_KNOWN_RE = [(k, re.compile(rx, re.I), t, h) for k, rx, t, h in _KNOWN]

_URL = re.compile(r"https?://\S+")
_HEX = re.compile(r"\b[0-9a-f]{12,}\b", re.I)
_NUM = re.compile(r"\d+(?:\.\d+)?")
_MAX_SAMPLES = 5


def _generic_key(message: str) -> str:
    text = _URL.sub("<url>", message)
    text = _HEX.sub("<id>", text)
    text = _NUM.sub("#", text)
    return text[:140]


def summarize(path: Path) -> Dict[str, Any]:
    """Group the WARNING/ERROR lines of one log file."""
    groups: Dict[str, Dict[str, Any]] = {}
    total = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            m = _LINE.match(raw.rstrip("\n"))
            if not m:
                continue
            when, level, message = m.group(1), m.group(2), m.group(3)
            level = "error" if level in ("ERROR", "CRITICAL") else "warning"
            total += 1
            known = next(((k, t, h) for k, rx, t, h in _KNOWN_RE if rx.search(message)), None)
            if known:
                key, title, help_text = known
            else:
                key, title, help_text = "other:" + _generic_key(message), _generic_key(message), ""
            g = groups.get(key)
            if g is None:
                g = groups[key] = {"key": key, "title": title, "help": help_text, "level": level,
                                   "count": 0, "first": when, "last": when, "samples": []}
            g["count"] += 1
            g["last"] = when
            if level == "error":
                g["level"] = "error"
            g["samples"].append(f"{when} {message}")
            if len(g["samples"]) > _MAX_SAMPLES:
                g["samples"].pop(0)  # keep the most recent ones
    items = sorted(groups.values(), key=lambda g: (g["level"] != "error", -g["count"]))
    return {"total": total, "groups": items}


def resolve_date(date: Optional[str]) -> Optional[str]:
    """Only YYYYMMDD dates (the value is used in a file name)."""
    if date and not re.fullmatch(r"\d{8}", date):
        raise ValueError("date must be YYYYMMDD")
    return date
