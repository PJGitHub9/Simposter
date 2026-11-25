"""Silo (Silo-Server/silo-server) client, using Silo's own API (/api/v2).

Facts checked against a real Silo server's /api/v2/openapi.json (2026-11-20,
CLAUDE.md Quirk #240):
- Auth is `Authorization: Bearer sa_...` (an admin API key). Catalog (viewer)
  endpoints also need `X-Profile-Id` (GET /profiles).
- Silo keeps ONE content id per title (e.g. movie-tmdb-10020) with a version
  per library, and one poster/backdrop/logo per title. Simposter keeps one
  cache row per Silo library, so this client reports:
    library ids as  silo-<id>                    (Silo's are short digits,
                                                  like Plex section ids)
    item keys as    <content_id>@silo-<library>   (one per library copy, no ":" so it works as a Windows file name)
  and strips both before calling Silo.
- Only poster/backdrop/logo can be uploaded (seasons: poster/backdrop).
- Collections are Silo's curated library collections (GET /admin/collections),
  keyed as collection-<id>@silo-<library>; they take a poster or backdrop
  (PUT /admin/collections/{id}/poster|backdrop). TMDb box sets are not listed:
  Silo only searches those (/catalog/box-sets needs q) and takes no artwork for them.
"""
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests

from ..config import logger
from .base import ImageType, Library, MediaItem, MediaItemMetadata, MediaServerClient

LIB_PREFIX = "silo-"
_KEY_SEP = "@"
_TIMEOUT = (10, 30)
# GET /admin/collections per (server url, library), for collection images.
_COLLECTION_LIST_TTL = 60
_collection_lists: Dict[Tuple[str, str], Tuple[float, Dict[str, dict]]] = {}
_collection_list_lock = threading.Lock()
_PAGE_LIMIT = 200  # Silo answers 422 above this
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
COLLECTION_PREFIX = "collection-"
SCOPED_KEY_MESSAGE = ("This API key has permissions ticked, so Silo won't let Simposter upload images. "
                      "Create a key with no permissions ticked (full access), on an admin account, "
                      "not tied to a profile.")

# Silo rate-limits API keys (default "standard" tier: 20 requests/second,
# 1200/minute; internal/ratelimit/config.go) and answers 429 with Retry-After.
# Requests are paced per server (shared by every SiloClient instance, since
# scan workers each build their own), and a 429 waits Retry-After and retries.
_MIN_INTERVAL = 1.0 / 15
_MAX_RETRIES = 3
_pace_lock = threading.Lock()
_next_slot: Dict[str, float] = {}
_EPISODE_CACHE_SECONDS = 600
# Server URLs whose key Silo refused include_file_paths for (shared by every
# client instance, so the 403 and its warning happen once per run).
_paths_refused: set = set()


def _pace(base: str) -> None:
    with _pace_lock:
        now = time.monotonic()
        slot = max(now, _next_slot.get(base, 0.0))
        _next_slot[base] = slot + _MIN_INTERVAL
    if slot > now:
        time.sleep(slot - now)


class SiloPinError(Exception):
    """The primary profile has a PIN and Simposter has none, or Silo refused it."""


# Profile tokens per (server URL, profile id): (token, expiry epoch or None),
# and PINs Silo rejected per (server URL, profile id, PIN hash).
_profile_tokens: Dict[Tuple[str, str], Tuple[str, Optional[int]]] = {}
_rejected_pins: set = set()
# One PIN check at a time: scan workers share a client, and several wrong PINs
# sent at once would count as several tries toward Silo's 5-try lockout.
_pin_lock = threading.Lock()


def _wrong_pin_message(name: str) -> str:
    return (f"Silo rejected the PIN for the profile {name}. Check it; Silo locks the profile "
            "for 5 minutes after 5 wrong tries.")


def _retry_after_seconds(resp) -> float:
    try:
        return float((getattr(resp, "headers", None) or {}).get("Retry-After") or 300)
    except (TypeError, ValueError):
        return 300.0


def _retry_after(resp) -> float:
    try:
        return min(max(float((getattr(resp, "headers", None) or {}).get("Retry-After") or 1), 0.5), 30.0)
    except (TypeError, ValueError):
        return 1.0


_UPLOAD_TYPE = {ImageType.POSTER: "poster", ImageType.BACKDROP: "backdrop", ImageType.LOGO: "logo"}
_DETAIL_URL_FIELD = {ImageType.POSTER: "poster_url", ImageType.BACKDROP: "backdrop_url", ImageType.LOGO: "logo_url"}


def _with_prefix(library_id: Optional[str]) -> Optional[str]:
    if not library_id:
        return None
    s = str(library_id)
    return s if s.startswith(LIB_PREFIX) else f"{LIB_PREFIX}{s}"


def native_library_id(library_id: str) -> str:
    s = str(library_id or "")
    return s[len(LIB_PREFIX):] if s.startswith(LIB_PREFIX) else s


def qualify(content_id: str, library_id: str) -> str:
    return f"{content_id}{_KEY_SEP}{_with_prefix(library_id)}"


def split_key(key: str) -> Tuple[str, Optional[str]]:
    s = str(key or "")
    if _KEY_SEP in s:
        content_id, lib = s.rsplit(_KEY_SEP, 1)
        return content_id, _with_prefix(lib)
    return s, None


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _url_id(value: str) -> str:
    """An id about to go into a Silo URL path. Silo's ids are letters, digits,
    "-" and "_"; anything else (a "/" or "..") could reach another admin
    route, so it is refused."""
    s = str(value or "")
    if not _SAFE_ID.match(s):
        raise ValueError(f"Not a Silo id: {s[:40]!r}")
    return s


def _iso_to_epoch(value: Any) -> Optional[int]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(re.sub(r"\.(\d{1,6})\d*", r".\1", s))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (TypeError, ValueError):
        return None


def _classify_resolution(value: Any) -> Optional[str]:
    """Silo's "2160p"/"1080p" to Plex's vocabulary (Quirk #180)."""
    if not value:
        return None
    m = re.match(r"(\d+)", str(value).lower())
    if not m:
        return "4k" if "4k" in str(value).lower() else None
    h = int(m.group(1))
    if h >= 4000:
        return "8k"
    if h >= 2000:
        return "4k"
    if h >= 1400:
        return "1440"
    if h >= 1000:
        return "1080"
    if h >= 700:
        return "720"
    return "sd"


def _url_version(url: Optional[str]) -> Optional[str]:
    """A Silo artwork path carries a content hash, so it changes with the image."""
    return url.split("?", 1)[0] if url else None


def _rating10(value: Any) -> Optional[float]:
    try:
        return round(float(value) / 10.0, 2) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


class SiloClient(MediaServerClient):
    def __init__(self, server_id: str, url: str, api_key: str, pin: Optional[str] = None):
        self.server_id = server_id
        self.url = (url or "").strip().rstrip("/")
        self.api_key = api_key or ""
        self.pin = (pin or "").strip() or None
        self.session = requests.Session()
        self._profile_id: Optional[str] = None
        self.profile_name: Optional[str] = None
        self._has_pin = False
        self.last_error: Optional[str] = None
        self._episodes: Dict[str, Tuple[float, List[dict]]] = {}
        self._listings: Dict[Tuple[str, str], Tuple[float, List[dict]]] = {}
        # Keys Silo just answered 404 for (the title was re-matched under a new
        # id); the scan cache still has them, so lookups must skip them.
        self._gone: set = set()
        # False once Silo refused include_file_paths (a key with permissions ticked).
        self._paths_allowed: Optional[bool] = False if self.url in _paths_refused else None

    def _request(self, method: str, url: str, **kw):
        """GET/POST with pacing; a 429 waits Retry-After and retries."""
        send = getattr(self.session, method.lower())
        resp = None
        for attempt in range(_MAX_RETRIES + 1):
            _pace(self.url)
            resp = send(url, **kw)
            if resp.status_code != 429 or attempt == _MAX_RETRIES:
                break
            wait = _retry_after(resp)
            logger.debug("[SILO_CLIENT:%s] Rate limited, retrying in %.1fs", self.server_id, wait)
            time.sleep(wait)
        return resp

    # ---- HTTP ---------------------------------------------------------
    def _headers(self, profile: bool = False) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"}
        if profile:
            pid = self._profile()
            if pid:
                h["X-Profile-Id"] = pid
                if self._has_pin:
                    h["X-Profile-Token"] = self._profile_token(pid)
        return h

    def _profile(self) -> Optional[str]:
        """The primary profile, which Simposter reads the catalog as."""
        if self._profile_id is None:
            r = self._request("GET", f"{self.url}/api/v2/profiles", headers=self._headers(), timeout=_TIMEOUT)
            r.raise_for_status()
            items = (r.json() or {}).get("items") or []
            primary = next((p for p in items if p.get("is_primary")), items[0] if items else None)
            self._profile_id = str(primary["id"]) if primary else ""
            self.profile_name = (primary or {}).get("name") or None
            self._has_pin = bool((primary or {}).get("has_pin"))
        return self._profile_id or None

    def _profile_token(self, pid: str) -> str:
        """X-Profile-Token for a PIN-locked profile (POST /profiles/{id}/verify-pin).
        Cached per server and profile until it expires, shared by every client
        instance. Silo locks the profile for 5 minutes after 5 wrong PINs, so a
        PIN Silo rejected is never sent again (until it changes)."""
        name = self.profile_name or "main"
        if not self.pin:
            raise SiloPinError(f"Silo's main profile ({name}) has a PIN. Enter it in the PIN field so "
                               "Simposter can read your libraries.")
        with _pin_lock:
            return self._profile_token_locked(pid, name)

    def _profile_token_locked(self, pid: str, name: str) -> str:
        key = (self.url, pid)
        cached = _profile_tokens.get(key)
        if cached and (cached[1] is None or cached[1] > time.time() + 60):
            return cached[0]
        rejected = (self.url, pid, hashlib.sha256(self.pin.encode()).hexdigest())
        if rejected in _rejected_pins:
            raise SiloPinError(_wrong_pin_message(name))
        _pace(self.url)
        r = self.session.post(f"{self.url}/api/v2/profiles/{pid}/verify-pin", json={"pin": self.pin},
                              headers=self._headers(), timeout=_TIMEOUT)
        if r.status_code == 429:
            minutes = max(1, round(_retry_after_seconds(r) / 60))
            raise SiloPinError(f"Silo has locked the profile {name} after too many wrong PINs. "
                               f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}.")
        r.raise_for_status()
        body = r.json() or {}
        token = body.get("profile_token")
        if not token:
            _rejected_pins.add(rejected)
            raise SiloPinError(_wrong_pin_message(name))
        _profile_tokens[key] = (token, _iso_to_epoch(body.get("expires_at")))
        return token

    def _get(self, path: str, params: Optional[dict] = None, profile: bool = False) -> Any:
        r = self._request("GET", f"{self.url}/api/v2{path}", params=params, headers=self._headers(profile),
                          timeout=_TIMEOUT)
        if profile and self._has_pin and r.status_code in (401, 403) and self._profile_id:
            # The token expired or the PIN changed: get a new one, once.
            _profile_tokens.pop((self.url, self._profile_id), None)
            r = self._request("GET", f"{self.url}/api/v2{path}", params=params, headers=self._headers(profile),
                              timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _paged(self, path: str, params: dict) -> Iterator[dict]:
        cursor = None
        while True:
            q = dict(params, limit=_PAGE_LIMIT)
            if cursor:
                q["cursor"] = cursor
            data = self._get(path, q) or {}
            for item in data.get("items") or []:
                yield item
            page = data.get("page") or {}
            cursor = page.get("next_cursor")
            if not page.get("has_more") or not cursor:
                return

    # ---- catalog helpers ---------------------------------------------
    def _catalog_items(self, library_id: Optional[str], kind: Optional[str], content_id: Optional[str] = None) -> Iterator[dict]:
        params: Dict[str, Any] = {}
        if library_id:
            params["library_id"] = native_library_id(library_id)
        if kind:
            params["type"] = kind
        if content_id:
            params["content_ids"] = content_id
        if self._paths_allowed is not False:
            try:
                # Fetched whole, so a 403 on the first page can fall back cleanly.
                return iter(list(self._paged("/admin/catalog/items", dict(params, include_file_paths="true"))))
            except requests.HTTPError as e:
                if getattr(getattr(e, "response", None), "status_code", None) != 403:
                    raise
                self._paths_allowed = False
                _paths_refused.add(self.url)
                logger.warning("[SILO_CLIENT:%s] This API key can't read file paths (Silo answered 403); "
                               "listing without them. Use a key with no permissions ticked.", self.server_id)
        return self._paged("/admin/catalog/items", params)

    def _catalog_item(self, key: str) -> Optional[dict]:
        content_id, _lib = split_key(key)
        for item in self._catalog_items(None, None, content_id):
            if item.get("content_id") == content_id:
                return item
        return None

    @staticmethod
    def _version(item: dict, library_id: Optional[str]) -> Optional[dict]:
        versions = item.get("versions") or []
        native = native_library_id(library_id) if library_id else None
        for v in versions:
            if native is None or str(v.get("library_id")) == native:
                return v
        return versions[0] if versions and native is None else None

    def _to_media_item(self, item: dict, library_id: str, art: Optional[Dict[str, Tuple]] = None,
                       file_path: Optional[str] = None) -> MediaItem:
        version = self._version(item, library_id) or {}
        # Only Silo's own (Rotten Tomatoes) score; a TMDb score is left to the
        # TMDb rating source so the overlay log credits it to TMDb.
        audience = _rating10(item.get("rating_rt_audience"))
        logo_v, backdrop_v = (art or {}).get(item.get("content_id"), (None, None))
        return MediaItem(
            id=qualify(item["content_id"], library_id),
            title=item.get("title") or "",
            year=item.get("year"),
            tmdb_id=item.get("tmdb_id") or None,
            tvdb_id=item.get("tvdb_id") or None,
            added_at=_iso_to_epoch(item.get("added_at")),
            library_id=_with_prefix(library_id),
            file_path=version.get("file_path") or file_path,
            image_version=_url_version(item.get("poster_url")),
            audience_rating=audience,
            critic_rating=_rating10(item.get("rating_rt_critic")),
            logo_version=logo_v,
            backdrop_version=backdrop_v,
            # No Etag from Silo: a hash of what the listing says about this
            # copy, so a scan skips the per-item metadata fetch when unchanged.
            etag=hashlib.md5(json.dumps([version, _url_version(item.get("poster_url")), logo_v, backdrop_v,
                                         item.get("tmdb_id"), item.get("tvdb_id")],
                                        sort_keys=True, default=str).encode()).hexdigest(),
        )

    # ---- MediaServerClient ------------------------------------------
    def test_connection(self) -> bool:
        self.last_error = None
        try:
            self._get("/system/info")
            me = self._get("/account/me") or {}
        except Exception as e:
            self.last_error = "Could not connect to Silo"
            logger.info("[SILO_CLIENT:%s] Connection test failed: %s", self.server_id, e)
            return False
        if me.get("role") != "admin":
            self.last_error = "This API key isn't an admin key, so Simposter can't upload posters"
            return False
        # A key with permissions ticked is only let into the routes they name,
        # and none covers admin collections or image uploads (Silo's
        # internal/auth/api_key_scopes.go): it gets 403 here.
        try:
            r = self._request("GET", f"{self.url}/api/v2/admin/collections/capabilities",
                              headers=self._headers(), timeout=_TIMEOUT)
            if r.status_code == 403:
                self.last_error = SCOPED_KEY_MESSAGE
                return False
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] Permission check failed: %s", self.server_id, e)
        # Simposter reads the catalog as the primary profile; a PIN on it needs
        # the PIN here too.
        try:
            pid = self._profile()
            if pid and self._has_pin:
                self._profile_token(pid)
        except SiloPinError as e:
            self.last_error = str(e)
            return False
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] Profile check failed: %s", self.server_id, e)
        return True

    def list_libraries(self) -> List[Library]:
        out = []
        for lib in (self._get("/libraries") or {}).get("items") or []:
            if lib.get("enabled") is False:
                continue
            kind = {"movies": "movie", "series": "tv"}.get(lib.get("type"))
            if kind:
                out.append(Library(id=_with_prefix(lib.get("id")), name=lib.get("name") or "", media_type=kind))
        return out

    def list_items(self, library_id: str, media_type: str) -> List[MediaItem]:
        kind = "movie" if media_type == "movie" else "series"
        items = [i for i in self._catalog_items(library_id, kind) if i.get("content_id")]
        art = self._artwork_versions(library_id)
        folders = self._series_folders(library_id) if kind == "series" else {}
        return [self._to_media_item(i, library_id, art, folders.get(i["content_id"])) for i in items]

    def _series_folders(self, library_id: str) -> Dict[str, str]:
        """{series content_id: show folder} for a library. Silo lists no files
        for a series, only for its episodes: the show folder is an episode's
        folder, one level up when that is a Season/Specials folder. Empty on
        any failure."""
        out: Dict[str, str] = {}
        try:
            for ep in self._library_episodes(library_id):
                sid = ep.get("series_id")
                if not sid or sid in out:
                    continue
                path = (self._version(ep, library_id) or {}).get("file_path")
                if not path:
                    continue
                folder = os.path.dirname(path.replace("\\", "/"))
                if re.match(r"^(season\s*\d+|specials?)$", os.path.basename(folder), re.I):
                    folder = os.path.dirname(folder)
                if folder:
                    out[sid] = folder
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] Show folders failed for %s: %s", self.server_id, library_id, e)
        return out

    def _artwork_versions(self, library_id: str) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        """{content_id: (logo version, backdrop version)} for a library. The
        admin listing has no logo/backdrop links; the viewer catalog query
        does, 100 titles per request. Empty on any failure (the scan then just
        doesn't notice logo/backdrop changes this time)."""
        out: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        body: Dict[str, Any] = {"library_id": native_library_id(library_id), "limit": 100,
                                "scope": "library", "skip_total": True}
        try:
            for _ in range(1000):
                r = self._request("POST", f"{self.url}/api/v2/catalog/query", json=body,
                                  headers=self._headers(profile=True), timeout=_TIMEOUT)
                r.raise_for_status()
                data = r.json() or {}
                for i in data.get("items") or []:
                    if i.get("content_id"):
                        out[i["content_id"]] = (_url_version(i.get("logo_url")), _url_version(i.get("backdrop_url")))
                page = data.get("page") or {}
                if not page.get("has_more") or not page.get("next_cursor"):
                    break
                body = dict(body, cursor=page["next_cursor"])
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] Artwork listing failed for %s: %s", self.server_id, library_id, e)
            return {}
        return out

    def get_item_metadata(self, item_id: str) -> MediaItemMetadata:
        item = self._catalog_item(item_id)
        if not item:
            return MediaItemMetadata()
        _cid, lib = split_key(item_id)
        v = self._version(item, lib) or {}
        channels = v.get("audio_channels")
        return MediaItemMetadata(
            tmdb_id=item.get("tmdb_id") or None,
            tvdb_id=item.get("tvdb_id") or None,
            video_resolution=_classify_resolution(v.get("resolution")),
            video_codec=(v.get("codec_video") or "").lower() or None,
            audio_codec=(v.get("codec_audio") or "").lower() or None,
            audio_channels=str(channels) if channels else None,
            audio_language=self._audio_language(item.get("content_id") or "", v.get("file_id")),
            edition=v.get("edition") or None,
        )

    def _audio_language(self, content_id: str, file_id: Any) -> Optional[str]:
        """The admin listing has no audio tracks; the item's detail does, per
        file. This library's file (by file_id), its default track else the
        first. None on any failure."""
        try:
            detail = self._get(f"/catalog/items/{_url_id(content_id)}", profile=True) or {}
            versions = detail.get("versions") or []
            version = next((x for x in versions if file_id and x.get("file_id") == file_id), None)
            if version is None and len(versions) == 1:
                version = versions[0]
            tracks = (version or {}).get("audio_tracks") or []
            track = next((t for t in tracks if t.get("default")), tracks[0] if tracks else None)
            if not track:
                return None
            from .jellyfin_client import JellyfinClient
            return JellyfinClient._normalize_language(track.get("language"))
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] Audio language for %s failed: %s", self.server_id, content_id, e)
            return None

    def item_exists(self, item_id: str) -> Optional[bool]:
        try:
            return self._catalog_item(item_id) is not None
        except Exception:
            return None

    def remove_label(self, item_id: str, label: str, content_type: Optional[str] = None) -> bool:
        return False  # Silo has no labels

    def add_label(self, item_id: str, label: str) -> bool:
        return False

    def find_item_by_external_id(self, tmdb_id: Optional[Any], tvdb_id: Optional[Any],
                                 media_type: str, library_id: Optional[str] = None) -> Optional[str]:
        tmdb = str(tmdb_id) if tmdb_id not in (None, "") else None
        tvdb = str(tvdb_id) if tvdb_id not in (None, "") else None
        if not (tmdb or tvdb):
            return None
        libs = [_with_prefix(library_id)] if library_id else [
            l.id for l in self.list_libraries() if l.media_type == media_type]
        kind = "movie" if media_type == "movie" else "series"
        for lib in libs:
            cached = self._find_in_scan_cache(lib, media_type, tmdb, tvdb)
            if cached:
                return cached
            items = self._library_listing(lib, kind)
            checks = ([("tvdb_id", tvdb), ("tmdb_id", tmdb)] if media_type == "tv" else [("tmdb_id", tmdb)])
            for field, value in checks:
                if not value:
                    continue
                for item in items:
                    if str(item.get(field) or "") == value and item.get("content_id"):
                        return qualify(item["content_id"], lib)
        return None

    def _find_in_scan_cache(self, library_id: str, media_type: str, tmdb: Optional[str], tvdb: Optional[str]) -> Optional[str]:
        """The scan already stored each Silo library's titles with their ids, so
        most lookups need no request at all."""
        try:
            from .. import database as db
            table = "movie_cache" if media_type == "movie" else "tv_cache"
            checks = [("tvdb_id", tvdb), ("tmdb_id", tmdb)] if media_type == "tv" else [("tmdb_id", tmdb)]
            with db.get_db() as conn:
                for col, value in checks:
                    if not value:
                        continue
                    row = conn.execute(
                        f"SELECT rating_key FROM {table} WHERE server_id = ? AND library_id = ? AND CAST({col} AS TEXT) = ? LIMIT 1",
                        (self.server_id, library_id, value)).fetchone()
                    if row and row[0] not in self._gone:
                        return row[0]
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] scan cache lookup failed: %s", self.server_id, e)
        return None

    def _library_listing(self, library_id: str, kind: str) -> List[dict]:
        """One library's titles (no file paths), listed once and reused for
        10 minutes, so a batch of lookups costs one listing, not one each."""
        key = (library_id, kind)
        cached = self._listings.get(key)
        if cached and time.monotonic() - cached[0] < _EPISODE_CACHE_SECONDS:
            return cached[1]
        items = list(self._paged("/admin/catalog/items", {"library_id": native_library_id(library_id), "type": kind}))
        self._listings[key] = (time.monotonic(), items)
        return items

    def get_folder_name(self, item_id: str, is_tv: bool = False) -> Optional[str]:
        content_id, lib = split_key(item_id)
        if is_tv and lib:
            folder = self._series_folders(lib).get(content_id)
            if folder:
                return os.path.basename(folder) or None
        item = self._catalog_item(item_id)
        if not item:
            return None
        _cid, lib = split_key(item_id)
        path = (self._version(item, lib) or {}).get("file_path")
        if not path:
            return None
        folder = os.path.dirname(path.replace("\\", "/"))
        name = os.path.basename(folder)
        if is_tv and re.match(r"^(season\s*\d+|specials?)$", name, re.I):
            name = os.path.basename(os.path.dirname(folder))
        return name or None

    # ---- images -------------------------------------------------------
    def upload_image(self, item_id: str, image_type: ImageType, image_bytes: bytes,
                     content_type: str = "image/jpeg", is_collection: bool = False) -> None:
        content_id, _lib = split_key(item_id)
        _url_id(content_id)
        if is_collection or content_id.startswith(COLLECTION_PREFIX):
            self._upload_collection_image(item_id, image_type, image_bytes, content_type)
            return
        slot = _UPLOAD_TYPE.get(image_type)
        if not slot:
            raise NotImplementedError(f"Silo has no {getattr(image_type, 'value', image_type)} image")
        if content_id.startswith("season-") and image_type == ImageType.LOGO:
            raise NotImplementedError("Silo seasons take a poster or backdrop only")
        if len(image_bytes or b"") > _MAX_UPLOAD_BYTES:
            raise ValueError("Silo accepts images up to 10 MB")
        ext = ".png" if "png" in (content_type or "") else ".webp" if "webp" in (content_type or "") else ".jpg"
        r = self._request(
            "POST", f"{self.url}/api/v2/admin/items/{content_id}/images/upload",
            headers=self._headers(),
            data={"type": slot},
            files={"image": (f"image{ext}", image_bytes, content_type or "application/octet-stream")},
            timeout=(10, 60),
        )
        if r.status_code == 404:
            self._gone.add(str(item_id))
        r.raise_for_status()
        logger.info("[SILO_CLIENT:%s] Uploaded %s for %s (%d bytes)", self.server_id, slot, item_id, len(image_bytes))
        self._after_upload(item_id, image_type, image_bytes, content_type)

    def _upload_collection_image(self, item_id: str, image_type: ImageType, image_bytes: bytes, content_type: str) -> None:
        content_id, _lib = split_key(item_id)
        if not content_id.startswith(COLLECTION_PREFIX):
            # A TMDb box set: Silo has no upload route for those (checked 2026-11-22).
            raise NotImplementedError("Silo can't take box-set artwork from other apps")
        slot = {ImageType.POSTER: "poster", ImageType.BACKDROP: "backdrop"}.get(image_type)
        if not slot:
            raise NotImplementedError("Silo collections take a poster or backdrop only")
        if len(image_bytes or b"") > _MAX_UPLOAD_BYTES:
            raise ValueError("Silo accepts images up to 10 MB")
        coll_id = _url_id(content_id[len(COLLECTION_PREFIX):])
        ext = ".png" if "png" in (content_type or "") else ".webp" if "webp" in (content_type or "") else ".jpg"
        r = self._request(
            "PUT", f"{self.url}/api/v2/admin/collections/{coll_id}/{slot}",
            headers=self._headers(),
            files={"image": (f"image{ext}", image_bytes, content_type or "application/octet-stream")},
            timeout=(10, 60),
        )
        r.raise_for_status()
        logger.info("[SILO_CLIENT:%s] Uploaded collection %s for %s (%d bytes)", self.server_id, slot, item_id, len(image_bytes))

    def _after_upload(self, item_id: str, image_type: ImageType, image_bytes: bytes, content_type: str) -> None:
        """Silo has one image per title, shared by every library the title is
        in. Mark the sibling copies as sent too, so their next scan doesn't
        flag Silo's new image as changed outside Simposter. Never raises."""
        asset = {ImageType.POSTER: "poster", ImageType.LOGO: "logo", ImageType.BACKDROP: "backdrop"}[image_type]
        try:
            from .. import database as db
            from ..poster_drift import record_sent
            from ..api.media_server_send import refresh_local_art_cache
            if asset != "poster":
                # Posters are recorded by their own send paths; logos/backdrops here,
                # as JellyfinClient/PlexClient do.
                record_sent(self.server_id, item_id, image_bytes, asset)
            siblings = db.get_silo_sibling_keys(self.server_id, item_id)
            for sib in siblings:
                record_sent(self.server_id, sib, image_bytes, asset)
                refresh_local_art_cache(sib, asset, image_bytes, content_type)
            self._warn_other_groups(item_id, siblings, asset)
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] Sibling update after upload failed for %s: %s", self.server_id, item_id, e)

    def _warn_other_groups(self, item_id: str, siblings: List[str], asset: str) -> None:
        """Silo's one image per title is shared across library groups; say so
        when this upload also replaced it for a copy in another group."""
        if not siblings:
            return
        from ..config import get_library_group_for

        def group_name(key: str) -> Optional[str]:
            lib = split_key(key)[1]
            for mt in ("movie", "tv"):
                g = get_library_group_for(self.server_id, lib, mt)
                if g:
                    return g.get("name") or g.get("id")
            return None

        own = group_name(item_id)
        others = sorted({n for n in (group_name(k) for k in siblings) if n and n != own})
        if others:
            logger.warning("[SILO_CLIENT:%s] Silo keeps one %s per title: sending it from %s also changed it in %s",
                           self.server_id, asset, own or "this library", ", ".join(others))

    def download_image(self, item_id: str, image_type: ImageType) -> Optional[bytes]:
        field = _DETAIL_URL_FIELD.get(image_type)
        if not field:
            return None
        content_id, _lib = split_key(item_id)
        try:
            _url_id(content_id)
            if content_id.startswith(COLLECTION_PREFIX):
                if image_type not in (ImageType.POSTER, ImageType.BACKDROP):
                    return None
                coll_id = content_id[len(COLLECTION_PREFIX):]
                detail = self._get(f"/admin/collections/{coll_id}") or {}
                if not detail.get(field):
                    # Silo's single-collection endpoint returns an empty
                    # poster_url/backdrop_url; only the list carries the
                    # signed link (300px poster, 1280px backdrop).
                    detail = self._collection_from_list(coll_id, _lib) or detail
            else:
                detail = self._get(f"/catalog/items/{content_id}", {"image_size": "original"}, profile=True) or {}
            url = detail.get(field)
            if not url:
                return None
            if url.startswith("/"):
                url = f"{self.url}{url}"
            r = self._request("GET", url, timeout=_TIMEOUT)  # signed URL; no auth needed
            r.raise_for_status()
            return r.content or None
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] download_image %s %s failed: %s", self.server_id, item_id, field, e)
            return None

    def _collection_from_list(self, coll_id: str, library_id: Optional[str]) -> Optional[dict]:
        """One collection's entry from GET /admin/collections (the only Silo
        response with its image links). The list is kept for a minute per
        server and library, so loading a page of collection posters asks once;
        its links are signed and stay valid well past that."""
        native = native_library_id(library_id) if library_id else None
        key = (self.url, native or "")
        with _collection_list_lock:
            hit = _collection_lists.get(key)
        if hit is None or time.monotonic() - hit[0] > _COLLECTION_LIST_TTL:
            data = self._get("/admin/collections", {"library_id": native} if native else None) or {}
            items = {str(c.get("id")): c for c in data.get("items") or [] if c.get("id")}
            with _collection_list_lock:
                _collection_lists[key] = (time.monotonic(), items)
        else:
            items = hit[1]
        return items.get(str(coll_id))

    # ---- seasons / episodes ------------------------------------------
    def _seasons(self, series_key: str) -> List[dict]:
        content_id, lib = split_key(series_key)
        data = self._get(f"/catalog/series/{_url_id(content_id)}/seasons", profile=True) or {}
        out = []
        for s in data.get("items") or []:
            if s.get("content_id") and s.get("season_number") is not None:
                out.append({"key": qualify(s["content_id"], lib) if lib else s["content_id"],
                            "title": s.get("title") or f"Season {s['season_number']}",
                            "index": int(s["season_number"]), "thumb": None})
        out.sort(key=lambda s: s["index"])
        return out

    def list_seasons(self, series_item_id: str) -> List[dict]:
        try:
            return self._seasons(series_item_id)
        except Exception as e:
            logger.error("[SILO_CLIENT:%s] list_seasons failed (series=%s): %s", self.server_id, series_item_id, e)
            return []

    def find_season_by_index(self, series_item_id: str, season_index: int) -> Optional[str]:
        for s in self.list_seasons(series_item_id):
            if s["index"] == season_index:
                return s["key"]
        return None

    def list_episode_media(self, series_item_id: str) -> List[tuple]:
        """[(season_key, info)] for each episode of a series, using the
        episode's version in this library (show/season quality, Quirk #190)."""
        content_id, lib = split_key(series_item_id)
        try:
            by_number = {s["index"]: s["key"] for s in self._seasons(series_item_id)}
            out = []
            for ep in self._library_episodes(lib):
                if ep.get("series_id") != content_id:
                    continue
                season_key = by_number.get(ep.get("season_number"))
                v = self._version(ep, lib)
                if not season_key or not v:
                    continue
                channels = v.get("audio_channels")
                info = {"video_resolution": _classify_resolution(v.get("resolution")),
                        "video_codec": (v.get("codec_video") or "").lower() or None,
                        "audio_codec": (v.get("codec_audio") or "").lower() or None,
                        "audio_channels": str(channels) if channels else None}
                out.append((season_key, {k: val for k, val in info.items() if val}))
            return out
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] list_episode_media failed (series=%s): %s", self.server_id, series_item_id, e)
            return []

    def _library_episodes(self, library_id: Optional[str]) -> List[dict]:
        """Every episode in a library, fetched once and reused for every show
        in a scan (it's one paged listing for the whole library)."""
        key = library_id or ""
        cached = self._episodes.get(key)
        if cached and time.monotonic() - cached[0] < _EPISODE_CACHE_SECONDS:
            return cached[1]
        episodes = list(self._catalog_items(library_id, "episode"))
        self._episodes[key] = (time.monotonic(), episodes)
        return episodes

    # ---- collections (Silo's curated library collections) ----------------
    def list_collections(self, library_id: Optional[str] = None) -> List[dict]:
        """Curated collections of one library (or every library). Errors are
        logged as warnings: an empty list here empties the Collections page."""
        native = native_library_id(library_id) if library_id else None
        try:
            data = self._get("/admin/collections", {"library_id": native} if native else None) or {}
        except Exception as e:
            logger.warning("[SILO_CLIENT:%s] Couldn't list collections for library %s: %s",
                           self.server_id, library_id or "(all)", e)
            return []
        out = []
        for c in data.get("items") or []:
            if not c.get("id"):
                continue
            libs = [str(x) for x in (c.get("library_ids") or [])] or [str(c.get("library_id") or "")]
            lib = native if native else (libs[0] if libs and libs[0] else None)
            if native and native not in libs and str(c.get("library_id") or "") != native:
                continue
            lib = _with_prefix(lib) if lib else None
            out.append({"key": qualify(f"{COLLECTION_PREFIX}{c['id']}", lib) if lib else f"{COLLECTION_PREFIX}{c['id']}",
                        "title": c.get("title") or "", "year": None, "addedAt": None, "poster": None,
                        "library_id": lib,
                        # No poster_url (e.g. a collage Silo draws itself): nothing to download.
                        "has_poster": bool(c.get("poster_url")),
                        "image_version": _url_version(c.get("poster_url"))})
        return out

    def list_collection_members(self, collection_item_id: str) -> List[dict]:
        content_id, lib = split_key(collection_item_id)
        if not content_id.startswith(COLLECTION_PREFIX) or not lib:
            return []
        try:
            coll_id = _url_id(content_id[len(COLLECTION_PREFIX):])
            native = _url_id(native_library_id(lib))
        except ValueError:
            return []
        out, cursor = [], None
        try:
            for _ in range(50):
                params: Dict[str, Any] = {"limit": _PAGE_LIMIT}
                if cursor:
                    params["cursor"] = cursor
                data = self._get(f"/library/{native}/collections/{coll_id}/items", params, profile=True) or {}
                for i in data.get("items") or []:
                    if i.get("content_id") and i.get("type") in (None, "movie", "series"):
                        out.append({"key": qualify(i["content_id"], lib), "title": i.get("title") or "",
                                    "year": i.get("year")})
                page = data.get("page") or {}
                cursor = page.get("next_cursor")
                if not page.get("has_more") or not cursor:
                    break
        except Exception as e:
            logger.debug("[SILO_CLIENT:%s] list_collection_members failed: %s", self.server_id, e)
        return out
