"""Disk cache for the Kometa Creator's textures and logo library.

The Kometa Creator uses images from Kometa-Team/Defaults-Image-Creation on
GitHub (Quirk #21). Two things used to live only in memory, so every restart
started from nothing:

- the directory listings (GitHub's Contents API, 60 unauthenticated requests
  an hour per IP), and
- the image bytes a render downloads (rendering.py's LRU cache).

Both are now also kept in config/cache/kometa_creator/. Listings are refreshed
after LISTING_TTL_SECONDS; images after IMAGE_MAX_AGE_SECONDS (the repo rarely
changes them). A failed refresh keeps using the copy on disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .config import settings, logger

RAW_PREFIX = "https://raw.githubusercontent.com/Kometa-Team/Defaults-Image-Creation/"
LISTING_TTL_SECONDS = 6 * 60 * 60
IMAGE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def cache_dir() -> Path:
    return Path(settings.CONFIG_DIR) / "cache" / "kometa_creator"


def is_kometa_asset_url(url: str) -> bool:
    return bool(url) and url.startswith(RAW_PREFIX)


def _image_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    suffix = Path(url.split("?")[0]).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
        suffix = ".img"
    return cache_dir() / "images" / f"{digest}{suffix}"


def read_image(url: str, allow_stale: bool = False) -> Optional[bytes]:
    """Cached bytes for a Kometa asset URL, or None. A copy older than
    IMAGE_MAX_AGE_SECONDS is only returned with allow_stale."""
    if not is_kometa_asset_url(url):
        return None
    path = _image_path(url)
    try:
        if not path.is_file():
            return None
        if not allow_stale and time.time() - path.stat().st_mtime > IMAGE_MAX_AGE_SECONDS:
            return None
        return path.read_bytes()
    except OSError:
        return None


def write_image(url: str, data: bytes) -> None:
    if not is_kometa_asset_url(url) or not data or len(data) > _MAX_IMAGE_BYTES:
        return
    path = _image_path(url)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as e:
        logger.debug("[KOMETA] Couldn't cache %s: %s", url, e)


def _listing_path(key: str) -> Path:
    safe = "".join(c for c in key if c.isalnum() or c in "_-") or "listing"
    return cache_dir() / f"listing_{safe}.json"


def load_listing(key: str) -> Optional[tuple[Any, float]]:
    """(items, fetched_at) saved for a listing, or None."""
    try:
        data = json.loads(_listing_path(key).read_text(encoding="utf-8"))
        return data["items"], float(data["fetched_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_listing(key: str, items: Any, fetched_at: float) -> None:
    path = _listing_path(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"items": items, "fetched_at": fetched_at}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.debug("[KOMETA] Couldn't save the %s listing: %s", key, e)


def cached_listing(key: str, memory: dict, fetch, fallback):
    """Listing for `key`: memory, then disk, refreshed from GitHub when older
    than LISTING_TTL_SECONDS. On a failed refresh the last copy (memory or
    disk) is kept; `fallback` is only used when there is none at all.
    `memory` maps key -> {"items", "fetched_at"}."""
    now = time.time()
    entry = memory.get(key)
    if entry is None:
        disk = load_listing(key)
        if disk is not None:
            entry = {"items": disk[0], "fetched_at": disk[1]}
            memory[key] = entry
    if entry is None or now - entry["fetched_at"] > LISTING_TTL_SECONDS:
        try:
            items = fetch()
            entry = {"items": items, "fetched_at": now}
            memory[key] = entry
            save_listing(key, items, now)
        except Exception as e:
            logger.debug("[KOMETA] Failed to refresh the %s listing from GitHub: %s", key, e)
            if entry is None:
                # Remember the failure for a while so every request doesn't
                # hit GitHub again; nothing is written to disk.
                entry = {"items": fallback, "fetched_at": now - LISTING_TTL_SECONDS + 10 * 60}
                memory[key] = entry
    return entry["items"]
