"""simposter_assets.py

Maps badge-value slugs to logo URLs using logos.json from the simposter-assets repo:
  https://github.com/PJGitHub9/simposter-assets

logos.json format (array of objects, one per logo):
  [
    { "name": "capital arts entertainment.png",
      "url": "https://raw.githubusercontent.com/.../logos/capital arts entertainment.png",
      "date_added": "2026-03-12" },
    ...
  ]

Slug resolution priority:
  1. logos.json from the repo    (authoritative; refreshed every hour)
  2. Hardcoded _OVERRIDES below  (fallback when network unavailable)
  3. Heuristic title-case guess  (last resort; may 404)

Matching: the slug "capital-arts-entertainment" matches an entry whose
"name" field (after stripping .png) normalises to the same slug.
"""

import re
import threading
import urllib.parse
import time
from typing import Optional

ASSET_BASE   = "https://raw.githubusercontent.com/PJGitHub9/simposter-assets/main/logos/"
_LOGOS_URL   = "https://raw.githubusercontent.com/PJGitHub9/simposter-assets/main/logos.json"
_INDEX_TTL   = 3600  # seconds between re-fetches (1 hour)

# Hardcoded overrides kept as a network-free fallback.
_OVERRIDES: dict[str, str] = {
    # Streaming platforms
    "netflix":         "Netflix.png",
    "prime-video":     "Amazon Prime Video.png",
    "disney-plus":     "Disney Plus.png",
    "max":             "@ max.png",
    "hulu":            "Hulu.png",
    "apple-tv-plus":   "Apple TV.png",
    "paramount-plus":  "Paramount+.png",
    "peacock":         "Peacock.png",
    "tubi":            "Tubi TV.png",
    "crunchyroll":     "Crunchyroll.png",
    "shudder":         "Shudder.png",
    "mubi":            "MUBI.png",

    # Studios / production companies
    "a24":             "A24.png",
    "amazon-mgm":      "Amazon MGM Studios.png",
    "apple-original":  "Apple Original Films.png",
    "disney":          "Disney.png",
    "marvel-studios":  "Marvel Studios.png",
    "pixar":           "Pixar.png",
    "warner-bros":     "Warner Bros.png",
    "universal":       "Universal Pictures.png",
    "paramount":       "Paramount Pictures.png",
    "sony-pictures":   "Sony Pictures.png",
    "20th-century":    "20th Century Studios.png",
    "lionsgate":       "Lionsgate Films.png",
    "blumhouse":       "Blumhouse Television.png",
    "focus-features":  "Focus Features.png",
    "dreamworks":      "Dreamworks.png",
    "amblin":          "Amblin Entertainment.png",
    "legendary":       "Legendary Entertainment.png",
    "bad-robot":       "Bad Robot.png",

    # TV networks
    "hbo":             "HBO.png",
    "fx":              "FX Productions.png",
    "amc":             "AMC.png",
    "showtime":        "Showtime.png",
    "starz":           "Starz.png",
    "cbs":             "CBS Entertainment Production.png",
    "nbc":             "NBC.png",
    "abc":             "ABC.png",
    "fox":             "FOX.png",
}

# In-memory cache: normalised-slug → direct URL (from logos.json)
_logos_cache: dict[str, str] = {}
# Parallel cache: TMDb company_id (int) → direct URL — populated when logos.json has a "tmdb_id" column
_logos_id_cache: dict[int, str] = {}
_logos_fetched_at: float = 0    # timestamp of last SUCCESSFUL fetch
_logos_attempted_at: float = 0  # timestamp of last attempt (success or failure)
_LOGOS_RETRY_COOLDOWN = 60      # seconds to wait before retrying a failed fetch
_fetch_lock = threading.Lock()  # prevents concurrent fetches / race with prewarm


def _name_to_slug(name: str) -> str:
    """Normalise an asset name (or filename) to a lookup slug.

    "Capital Arts Entertainment.png" → "capital-arts-entertainment"
    "@ max.png"                      → "max"
    "Paramount+.png"                 → "paramount"
    "1-2-3 Production.png"           → "1-2-3-production"
    """
    # Strip file extension first
    s = re.sub(r"\.[a-zA-Z]{2,4}$", "", name).lower().strip()
    s = re.sub(r"[^a-z0-9\s\-]", "", s)  # keep letters, digits, spaces, hyphens
    s = re.sub(r"\s+", "-", s)            # spaces → hyphens
    s = re.sub(r"-+", "-", s).strip("-")  # collapse multiple hyphens
    return s


def _find_key(obj: dict, *candidates: str) -> Optional[str]:
    """Return the first key in *candidates* that exists in *obj* (case-insensitive)."""
    lowered = {k.lower(): k for k in obj}
    for c in candidates:
        if c.lower() in lowered:
            return lowered[c.lower()]
    return None


def _fetch_logos() -> dict[str, str]:
    """Fetch logos.json and build a {slug: url} map (1-hour in-memory cache).

    Callers that arrive while a fetch is in-progress will *block* on the lock
    and get the populated cache once the fetch completes — they never see the
    empty intermediate state (the prewarm race condition).

    Returns the current cache (possibly empty) immediately if:
      - Cache is fresh (< 1 hour old), OR
      - A fetch failed recently (> 60s cooldown before retrying).
    Never raises — always returns a dict.
    """
    global _logos_cache, _logos_id_cache, _logos_fetched_at, _logos_attempted_at
    now = time.time()

    # Fast path: return without acquiring the lock if cache is fresh
    if _logos_cache and (now - _logos_fetched_at) < _INDEX_TTL:
        return _logos_cache

    with _fetch_lock:
        # Double-checked locking: re-read globals now that we hold the lock
        now = time.time()
        if _logos_cache and (now - _logos_fetched_at) < _INDEX_TTL:
            return _logos_cache  # another thread already populated the cache

        # Don't retry too soon after a failed attempt
        if (now - _logos_attempted_at) < _LOGOS_RETRY_COOLDOWN and _logos_attempted_at > 0:
            return _logos_cache

        _logos_attempted_at = now  # record that we're about to try

        try:
            import requests
            # Use a short connect timeout (5 s) + read timeout (8 s)
            resp = requests.get(_LOGOS_URL, timeout=(5, 8), headers={"User-Agent": "Simposter/1.0"})
            resp.raise_for_status()
            entries = resp.json()

            if not isinstance(entries, list):
                return _logos_cache  # unexpected format, keep old cache

            new_cache: dict[str, str] = {}
            new_id_cache: dict[int, str] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                # Locate the name and url fields flexibly
                name_key = _find_key(entry, "name", "asset name", "asset_name", "title")
                url_key  = _find_key(entry, "url", "link", "src", "image_url")
                if not name_key or not url_key:
                    continue

                name = str(entry[name_key]).strip()
                url  = str(entry[url_key]).strip()
                if not name or not url:
                    continue

                # Percent-encode spaces and other unsafe chars in the URL path
                # (logos.json stores raw URLs with literal spaces)
                parsed = urllib.parse.urlparse(url)
                url = urllib.parse.urlunparse(
                    parsed._replace(path=urllib.parse.quote(parsed.path, safe="/"))
                )

                slug = _name_to_slug(name)
                if slug:
                    new_cache[slug] = url

                # Also index by TMDb company ID if the entry has one
                id_key = _find_key(entry, "tmdb_production_company_id", "tmdb_id", "company_id", "tmdb_company_id")
                if id_key:
                    try:
                        new_id_cache[int(entry[id_key])] = url
                    except (ValueError, TypeError):
                        pass

            _logos_cache = new_cache
            _logos_id_cache = new_id_cache
            _logos_fetched_at = now

        except Exception:
            pass  # Keep whatever was cached (empty dict on first failure)

        return _logos_cache


def _default_url(slug: str) -> str:
    """Last-resort heuristic: title-case filename in the repo's /logos/ directory."""
    name = slug.replace("-", " ").title()
    return ASSET_BASE + urllib.parse.quote(f"{name}.png")


def get_asset_url(slug: str, company_id: Optional[int] = None) -> Optional[str]:
    """Return the logo URL for *slug* (or *company_id*), or None if both are empty.

    Resolution order:
      0. TMDb company ID (most reliable — stable across name variations)
      1. logos.json slug lookup (authoritative, covers all uploaded files)
      2. _OVERRIDES dict          (hardcoded fallback, no network required)
      3. Heuristic title-case URL (may 404 if the file doesn't exist)
    """
    if not slug and company_id is None:
        return None

    # 0. TMDb company ID — check _logos_id_cache populated from logos.json tmdb_id column
    if company_id is not None:
        _fetch_logos()  # ensure cache is populated (no-op if fresh)
        import logging as _logging
        _log = _logging.getLogger(__name__)
        _log.info("[ASSETS] ID lookup: company_id=%s, id_cache_size=%d, slug_cache_size=%d, hit=%s",
                  company_id, len(_logos_id_cache), len(_logos_cache), company_id in _logos_id_cache)
        if company_id in _logos_id_cache:
            return _logos_id_cache[company_id]

    if not slug:
        return None
    slug = slug.lower()

    # 1. logos.json (slug derived by normalising the "asset name" field)
    logos = _fetch_logos()
    if slug in logos:
        return logos[slug]

    # 2. Hardcoded overrides (exact slug match)
    if slug in _OVERRIDES:
        return ASSET_BASE + urllib.parse.quote(_OVERRIDES[slug])

    # 3. Heuristic
    return _default_url(slug)


def get_full_map() -> dict[str, str]:
    """Return {slug: url} for every known slug (logos.json + overrides merged).
    Used by the /api/simposter-assets-map endpoint.
    """
    # Overrides as base, logos.json entries take precedence
    merged: dict[str, str] = {
        slug: ASSET_BASE + urllib.parse.quote(fn)
        for slug, fn in _OVERRIDES.items()
    }
    for slug, url in _fetch_logos().items():
        merged[slug] = url
    return merged
