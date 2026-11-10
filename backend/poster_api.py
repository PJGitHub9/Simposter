"""Poster API core: lookup order, stale-while-revalidate and the render queue.

Lookup order for ``serve()`` (spec section 3.2):

* no ``preset``: pinned row -> library poster (``poster_renders_by_tmdb/``, read-only)
  -> API-rendered default row (stale hash: serve it and queue a re-render)
  -> render now with the default preset.
* ``preset=X``: unknown/non-uniformlogo preset -> not_found; rendered row for X
  (stale: serve + re-render) -> render now with X.

Rendering goes through one module-level ThreadPoolExecutor sized from
``performance.concurrentRenders`` with in-flight de-duplication (one Future per
request key), so N clients asking for the same cold title cause one render. A cold
request waits ``posterApi.waitSeconds`` and otherwise gets a redirect to the stock
TMDb poster while the render keeps going and saves when done.

``serve()`` only returns paths/bytes/urls; recording hits (``touch_served``) is the
HTTP route's job so admin previews don't count.
"""
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple

from . import database as db
from . import poster_api_store as store
from .config import load_presets, logger
from .poster_api_store import CacheKey
from .tmdb_render import fetch_tmdb_poster_path, render_for_tmdb

TEMPLATE_ID = "uniformlogo"  # Kometa presets are never valid for the API
FALLBACK_PRESET_ID = "simposter-main"  # starter preset used when no default is set
NEGATIVE_TTL = 600  # seconds a genuine "no art" result is remembered
NO_KEY_WARN_INTERVAL = 600
TMDB_POSTER_URL = "https://image.tmdb.org/t/p/w780{}"
_LOG = "[POSTER API]"


@dataclass
class Served:
    kind: Literal["file", "bytes", "redirect", "not_found"]
    path: Optional[Path] = None
    data: Optional[bytes] = None
    url: Optional[str] = None
    source: Optional[str] = None  # "pinned" | "library" | "rendered"
    generated: bool = False  # rendered during this request (vs. an earlier render)


_NOT_FOUND = Served(kind="not_found")

# All three guarded by _lock. The lock is never held while waiting on a future or
# doing file/DB/network I/O.
_lock = threading.Lock()
_inflight: Dict[Tuple, Future] = {}
_negative: Dict[Tuple, float] = {}
_executor: Optional[ThreadPoolExecutor] = None
_executor_size: Optional[int] = None
_last_no_key_warning = 0.0


def _tuple(key: CacheKey) -> Tuple:
    return (key.media_type, int(key.tmdb_id), key.season, key.preset_key or "", key.group or "")


# ------------------------------------------------------------------ settings
def _concurrent_renders() -> int:
    try:
        perf = (db.get_ui_settings() or {}).get("performance") or {}
        return max(1, int(perf.get("concurrentRenders", 2)))
    except (TypeError, ValueError):
        return 2


def _get_executor() -> ThreadPoolExecutor:
    """Executor sized max(1, performance.concurrentRenders), read fresh. When the
    value changes a new executor is built; the old one is shut down without
    cancelling, so its queued/running renders still finish and resolve their
    futures."""
    global _executor, _executor_size
    size = _concurrent_renders()  # DB read outside the lock
    old = None
    with _lock:
        if _executor is None or _executor_size != size:
            old = _executor
            _executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix="poster-api")
            _executor_size = size
        ex = _executor
    if old is not None:
        old.shutdown(wait=False)
    return ex


def _has_tmdb_key() -> bool:
    """Same source tmdb_client ends up using: the key saved in Settings, else the
    TMDB_API_KEY env var (what _apply_runtime_settings copies into settings).
    Read fresh from the DB (Quirk #36)."""
    tmdb = (db.get_ui_settings() or {}).get("tmdb") or {}
    return bool(str(tmdb.get("apiKey") or "").strip() or os.getenv("TMDB_API_KEY", "").strip())


def _warn_no_key() -> None:
    global _last_no_key_warning
    now = time.time()
    with _lock:
        if now - _last_no_key_warning < NO_KEY_WARN_INTERVAL:
            return
        _last_no_key_warning = now
    logger.warning("%s Poster API: no TMDb key set -- requests that need a render return 404", _LOG)


def _uniformlogo_preset_ids() -> list:
    return [p.get("id") for p in (load_presets().get(TEMPLATE_ID) or {}).get("presets", []) if p.get("id")]


def _default_preset_id(media_type: str) -> Optional[str]:
    """Settings default for the media type if it still exists, else the
    starter preset "simposter-main" if present, else the first uniformlogo
    preset; None when there are no uniformlogo presets at all."""
    ids = _uniformlogo_preset_ids()
    if not ids:
        return None
    s = store.get_settings()
    want = s.defaultTvPreset if media_type == "tv" else s.defaultMoviePreset
    if want and want in ids:
        return want
    return FALLBACK_PRESET_ID if FALLBACK_PRESET_ID in ids else ids[0]


# ------------------------------------------------------------------ render queue
def _render_job(key: CacheKey, template_id: str, preset_id: str, skip_if_fresh: bool) -> Optional[Path]:
    """Runs on the executor. Returns the rendered file's path, or None (no art,
    or an error). Never raises; only a genuine None from render_for_tmdb is
    negatively cached."""
    t = _tuple(key)
    title = None
    try:
        phash = store.preset_hash(template_id, preset_id)
        if skip_if_fresh:
            # A cold request that lost a race with a just-finished render.
            e = store.get_entry(key, "rendered")
            if e and e.get("preset_hash") == phash:
                return Path(e["path"])
        result = render_for_tmdb(key.media_type, key.tmdb_id, key.season, template_id, preset_id,
                                 members=store.group_members(key.media_type, key.group))
        if result is None:
            with _lock:
                _negative[t] = time.time()
            logger.info("%s No poster art for %s %s%s -- not retrying for %ds", _LOG, key.media_type,
                        key.tmdb_id, "" if key.season is None else f" season {key.season}", NEGATIVE_TTL)
            return None
        title = result.title
        store.put_entry(key, "rendered", result.image_bytes, result.title, phash)
        with _lock:
            _negative.pop(t, None)
        e = store.get_entry(key, "rendered")
        return Path(e["path"]) if e else None
    except Exception as exc:
        logger.error("%s Render failed for '%s' (%s tmdb %s%s, preset %s): %s", _LOG, title or "?",
                     key.media_type, key.tmdb_id, "" if key.season is None else f" season {key.season}",
                     preset_id, exc, exc_info=True)
        return None


def _queue(key: CacheKey, template_id: str, preset_id: str, skip_if_fresh: bool) -> Future:
    t = _tuple(key)
    ex = _get_executor()
    with _lock:
        fut = _inflight.get(t)
        if fut is not None:
            return fut
        holder: list = []

        def job():
            try:
                return _render_job(key, template_id, preset_id, skip_if_fresh)
            finally:
                with _lock:  # waits until the submitter stored the future
                    if holder and _inflight.get(t) is holder[0]:
                        del _inflight[t]

        try:
            fut = ex.submit(job)
        except RuntimeError:  # executor shut down by a concurrent rebuild
            one_off = ThreadPoolExecutor(max_workers=1, thread_name_prefix="poster-api")
            fut = one_off.submit(job)
            one_off.shutdown(wait=False)
        holder.append(fut)
        _inflight[t] = fut
        return fut


def queue_render(key: CacheKey, template_id: str, preset_id: str) -> Future:
    """Queue a (re-)render of ``key`` with the given template/preset; joins an
    identical in-flight render instead of starting another. The Future resolves to
    the saved file's Path, or None."""
    return _queue(key, template_id, preset_id, skip_if_fresh=False)


def regenerate(key: CacheKey) -> None:
    """Queue a fresh render for the key (its preset, or the default) without waiting."""
    preset_id = key.preset_key or _default_preset_id(key.media_type)
    if not preset_id or preset_id not in _uniformlogo_preset_ids():
        logger.warning("%s Regenerate skipped for %s %s: no usable preset", _LOG, key.media_type, key.tmdb_id)
        return
    queue_render(key, TEMPLATE_ID, preset_id)


def pin(key_without_preset: CacheKey, image_bytes: bytes, title: Optional[str]) -> None:
    """Store a user-supplied poster as the pinned image (always the default slot)."""
    key = CacheKey(key_without_preset.media_type, key_without_preset.tmdb_id, key_without_preset.season, "")
    store.put_entry(key, "pinned", image_bytes, title, "")


# ------------------------------------------------------------------ lookup
def _negatively_cached(key: CacheKey) -> bool:
    t = _tuple(key)
    with _lock:
        ts = _negative.get(t)
        if ts is None:
            return False
        if time.time() - ts < NEGATIVE_TTL:
            return True
        del _negative[t]
        return False


def _redirect_or_not_found(key: CacheKey) -> Served:
    try:
        poster_path = fetch_tmdb_poster_path(key.media_type, key.tmdb_id)
    except Exception as exc:
        logger.info("%s TMDb poster lookup failed for %s %s: %s", _LOG, key.media_type, key.tmdb_id, exc)
        return _NOT_FOUND
    if not poster_path:
        return _NOT_FOUND
    return Served(kind="redirect", url=TMDB_POSTER_URL.format(poster_path))


def resolve_request_group(media_type: str, group: Optional[str]) -> Optional[str]:
    """Group id for a request: the ``group`` parameter (id or name), else the
    settings default for the media type. "" = any library. None = the parameter
    names no library group of this media type."""
    if group and group.strip():
        g = store.resolve_group(media_type, group)
        return str(g["id"]) if g else None
    s = store.get_settings()
    default = s.tvGroup if media_type == "tv" else s.movieGroup
    g = store.resolve_group(media_type, default) if default else None
    return str(g["id"]) if g else ""  # a removed default group falls back to any library


def serve(media_type: str, tmdb_id: int, season: Optional[int], preset: Optional[str],
          group: Optional[str] = None) -> Served:
    if media_type not in ("movie", "tv"):
        return _NOT_FOUND
    group_id = resolve_request_group(media_type, group)
    if group_id is None:
        return _NOT_FOUND
    key = CacheKey(media_type, int(tmdb_id), season, preset or "", group_id)
    if preset:
        if preset not in _uniformlogo_preset_ids():
            return _NOT_FOUND
        preset_id = preset
    else:
        # A pinned poster applies to every group.
        pinned = store.get_entry(CacheKey(media_type, key.tmdb_id, season, ""), "pinned")
        if pinned:
            return Served(kind="file", path=Path(pinned["path"]), source="pinned")
        lib = store.library_poster_path(media_type, key.tmdb_id, season,
                                        store.group_members(media_type, group_id))
        if lib is not None:
            return Served(kind="file", path=lib, source="library")
        preset_id = _default_preset_id(media_type)
        if not preset_id:
            # no usable preset: an existing default render is still servable as-is
            # (its hash can't be checked against anything)
            rendered = store.get_entry(key, "rendered")
            if rendered:
                return Served(kind="file", path=Path(rendered["path"]), source="rendered")
            return _NOT_FOUND

    has_key = _has_tmdb_key()
    rendered = store.get_entry(key, "rendered")
    if rendered:
        if rendered.get("preset_hash") != store.preset_hash(TEMPLATE_ID, preset_id):
            # stale-while-revalidate; a re-render that just found no art is not
            # retried until its negative entry expires (else every hit re-renders)
            if has_key and not _negatively_cached(key):
                queue_render(key, TEMPLATE_ID, preset_id)
            elif not has_key:
                _warn_no_key()
        return Served(kind="file", path=Path(rendered["path"]), source="rendered")

    if not has_key:
        _warn_no_key()
        return _NOT_FOUND
    if _negatively_cached(key):
        return _NOT_FOUND

    fut = _queue(key, TEMPLATE_ID, preset_id, skip_if_fresh=True)
    wait = store.get_settings().waitSeconds
    try:
        path = fut.result(timeout=wait)
    except FutureTimeout:
        return _redirect_or_not_found(key)
    if path is not None and Path(path).is_file():
        return Served(kind="file", path=Path(path), source="rendered", generated=True)
    return _NOT_FOUND
