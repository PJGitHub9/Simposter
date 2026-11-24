# backend/custom_posters.py
"""Poster import: Kometa-style YAML (`url_poster`, `seasons`) applied to a
library group, once or from a live file on disk. Two input shapes:

- Kometa metadata files: `metadata:` (or `collections:`) keyed by TMDb id (shows:
  TVDB id) or by title, optionally with `title:`/`year:`.
- TPDbCollectionMaker output: a bare mapping keyed by title, with `seasons:`.

Every image is downloaded once (one request per link the user put in the file)
and kept in config/cache/custom_posters/. A title's imported poster is stored
in `custom_posters`, and from then on it is that title's art:
- full renders (batch, webhooks, auto-generate, retries, Overlay Refresh, the
  Poster API) use it as the background instead of a TMDb poster
  (tmdb_render.custom_poster_override());
- Overlay only draws its overlays on it (overlay_only.resolve_base()).

What happens on import (per file, or per title in the review list):
- "template": render with a preset over the imported poster (mode Full);
- "overlay": Overlay only with the preset's overlays;
- "as_is": upload the image unchanged and set Leave alone.
Collections can only be uploaded as-is (poster modes don't cover them).
"""
import hashlib
import io
import json
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from . import database as db
from .config import logger, settings

MODES = ("template", "overlay", "as_is")
SOURCE = "poster_import"
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MIN_REQUEST_GAP = 0.5  # seconds between image downloads (one host, be polite)

_tables_lock = threading.Lock()
_tables_ready = False
_job_lock = threading.Lock()  # one import/sync at a time
_status_lock = threading.Lock()
_status: Dict[str, Any] = {"state": "idle"}
_fetch_lock = threading.Lock()
_last_fetch = 0.0


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

def ensure_tables() -> None:
    global _tables_ready
    if _tables_ready:
        return
    with _tables_lock:
        if _tables_ready:
            return
        with db.get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_posters (
                    media_type TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    season_index INTEGER NOT NULL DEFAULT -1,
                    tmdb_id INTEGER,
                    tvdb_id INTEGER,
                    title TEXT,
                    url TEXT NOT NULL,
                    source TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (media_type, item_key, season_index)
                )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_posters_tmdb ON custom_posters (media_type, tmdb_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_posters_tvdb ON custom_posters (media_type, tvdb_id)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS poster_import_files (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    name TEXT,
                    server_id TEXT NOT NULL,
                    library_id TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    template_id TEXT,
                    preset_id TEXT,
                    interval_hours REAL DEFAULT 6,
                    enabled INTEGER DEFAULT 1,
                    last_hash TEXT,
                    entry_sigs TEXT,
                    last_checked_at TEXT,
                    last_changed_at TEXT,
                    last_status TEXT,
                    last_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""")
            cols = {r[1] for r in conn.execute("PRAGMA table_info(poster_import_files)").fetchall()}
            if "require_approval" not in cols:
                conn.execute("ALTER TABLE poster_import_files ADD COLUMN require_approval INTEGER DEFAULT 0")
            if "pending_json" not in cols:
                conn.execute("ALTER TABLE poster_import_files ADD COLUMN pending_json TEXT")
        _tables_ready = True


# --------------------------------------------------------------------------
# Image files
# --------------------------------------------------------------------------

def _image_dir() -> Path:
    d = Path(settings.CONFIG_DIR) / "cache" / "custom_posters"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_stem(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:32]


def cached_path(url: str) -> Optional[Path]:
    """The downloaded copy of an imported image URL, if there is one."""
    if not url:
        return None
    try:
        stem = _url_stem(url)
        d = Path(settings.CONFIG_DIR) / "cache" / "custom_posters"
        for ext in (".jpg", ".png", ".webp"):
            p = d / f"{stem}{ext}"
            if p.is_file():
                return p
    except Exception:
        pass
    return None


def read_cached(url: str) -> Optional[bytes]:
    """Bytes of an imported image (no request). Used by the renderer, so a
    title's imported poster is never downloaded again."""
    p = cached_path(url)
    if p is None:
        return None
    try:
        return p.read_bytes()
    except OSError:
        return None


def _image_ext(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def download(url: str, force: bool = False) -> bytes:
    """Download an image the user listed (once; later calls read the disk copy).
    Raises ValueError with a readable reason."""
    if not force:
        cached = read_cached(url)
        if cached is not None:
            return cached
    from .config import EXTERNAL_IMAGE_FETCH_HEADERS
    from .middleware.validation import safe_get
    global _last_fetch
    with _fetch_lock:
        wait = MIN_REQUEST_GAP - (time.time() - _last_fetch)
        if wait > 0:
            time.sleep(wait)
        _last_fetch = time.time()
    try:
        r = safe_get(url, strict=True, headers=EXTERNAL_IMAGE_FETCH_HEADERS, timeout=30, stream=True)
    except Exception as e:
        raise ValueError(f"couldn't download it ({e})")
    try:
        if r.status_code != 200:
            raise ValueError(f"the link answered HTTP {r.status_code}")
        buf = io.BytesIO()
        for chunk in r.iter_content(65536):
            buf.write(chunk)
            if buf.tell() > MAX_IMAGE_BYTES:
                raise ValueError("the image is larger than 25 MB")
        data = buf.getvalue()
    finally:
        r.close()
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception:
        raise ValueError("the link isn't an image")
    stem = _url_stem(url)
    d = _image_dir()
    for old in d.glob(f"{stem}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    (d / f"{stem}{_image_ext(data)}").write_bytes(data)
    return data


# --------------------------------------------------------------------------
# Stored custom posters
# --------------------------------------------------------------------------

def _item_key(media_type: str, tmdb_id, tvdb_id) -> Optional[str]:
    if tmdb_id:
        return f"tmdb:{int(tmdb_id)}"
    if media_type == "tv" and tvdb_id:
        return f"tvdb:{int(tvdb_id)}"
    return None


def lookup(media_type: str, tmdb_id=None, tvdb_id=None, season_index: Optional[int] = None) -> Optional[str]:
    """The imported poster URL for a title (season_index None = the movie/show
    poster), or None. Only returns one whose image is on disk."""
    ensure_tables()
    media_type = "tv" if media_type in ("tv", "tv-show", "show") else "movie"
    s = -1 if season_index is None else int(season_index)
    where, params = [], []
    try:
        if tmdb_id:
            where.append("tmdb_id = ?")
            params.append(int(tmdb_id))
        if media_type == "tv" and tvdb_id:
            where.append("tvdb_id = ?")
            params.append(int(tvdb_id))
    except (TypeError, ValueError):
        return None
    if not where:
        return None
    with db.get_db() as conn:
        rows = conn.execute(
            f"SELECT url FROM custom_posters WHERE media_type = ? AND season_index = ? AND ({' OR '.join(where)}) "
            "ORDER BY updated_at DESC", [media_type, s] + params).fetchall()
    for r in rows:
        if cached_path(r["url"]) is not None:
            return r["url"]
    return None


def lookup_for_item(server_id: str, rating_key: str, season_index: Optional[int]) -> Optional[bytes]:
    """Imported poster bytes for one server copy (a season's key resolves
    through its show). Used by Overlay only to pick its base image."""
    try:
        key = str(rating_key)
        if season_index is not None:
            from .overlay_only import _show_key_for_season
            key = _show_key_for_season(key) or ""
        if not key:
            return None
        tmdb_id, tvdb_id = db.get_ids_for_rating_key(key)
    except Exception:
        return None
    url = None
    if season_index is None:
        url = lookup("movie", tmdb_id) or lookup("tv", tmdb_id, tvdb_id)
    else:
        url = lookup("tv", tmdb_id, tvdb_id, season_index)
    return read_cached(url) if url else None


def store(media_type: str, tmdb_id, tvdb_id, season_index: Optional[int], url: str, title: str, source: str) -> None:
    ensure_tables()
    key = _item_key(media_type, tmdb_id, tvdb_id)
    if not key:
        return
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO custom_posters (media_type, item_key, season_index, tmdb_id, tvdb_id, title, url, source, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(media_type, item_key, season_index) DO UPDATE SET url=excluded.url, title=excluded.title, "
            "tmdb_id=COALESCE(excluded.tmdb_id, custom_posters.tmdb_id), tvdb_id=COALESCE(excluded.tvdb_id, custom_posters.tvdb_id), "
            "source=excluded.source, updated_at=CURRENT_TIMESTAMP",
            (media_type, key, -1 if season_index is None else int(season_index),
             int(tmdb_id) if tmdb_id else None, int(tvdb_id) if tvdb_id else None, title, url, source))


def list_for_group(server_id: str, library_id: str, media_type: str) -> List[Dict[str, Any]]:
    """Stored imported posters for titles in this library group."""
    ensure_tables()
    rows = _library_rows(server_id, library_id, media_type)
    tmdb = {int(r["tmdb_id"]) for r in rows if r.get("tmdb_id")}
    tvdb = {int(r["tvdb_id"]) for r in rows if r.get("tvdb_id")}
    with db.get_db() as conn:
        stored = conn.execute("SELECT * FROM custom_posters WHERE media_type = ? ORDER BY title, season_index",
                              (media_type,)).fetchall()
    out = []
    for r in stored:
        if (r["tmdb_id"] and r["tmdb_id"] in tmdb) or (r["tvdb_id"] and r["tvdb_id"] in tvdb):
            out.append({"item_key": r["item_key"], "season_index": None if r["season_index"] < 0 else r["season_index"],
                        "tmdb_id": r["tmdb_id"], "tvdb_id": r["tvdb_id"], "title": r["title"], "url": r["url"],
                        "source": r["source"], "updated_at": r["updated_at"]})
    return out


def remove(media_type: str, item_key: str, season_index: Optional[int] = None) -> int:
    """Forget an imported poster (season_index None: the title and its seasons).
    The image file is kept while another row still uses its URL."""
    ensure_tables()
    with db.get_db() as conn:
        if season_index is None:
            urls = [r["url"] for r in conn.execute(
                "SELECT url FROM custom_posters WHERE media_type = ? AND item_key = ?", (media_type, item_key))]
            n = conn.execute("DELETE FROM custom_posters WHERE media_type = ? AND item_key = ?",
                             (media_type, item_key)).rowcount
        else:
            urls = [r["url"] for r in conn.execute(
                "SELECT url FROM custom_posters WHERE media_type = ? AND item_key = ? AND season_index = ?",
                (media_type, item_key, int(season_index)))]
            n = conn.execute("DELETE FROM custom_posters WHERE media_type = ? AND item_key = ? AND season_index = ?",
                             (media_type, item_key, int(season_index))).rowcount
        for url in set(urls):
            still = conn.execute("SELECT 1 FROM custom_posters WHERE url = ? LIMIT 1", (url,)).fetchone()
            if not still:
                p = cached_path(url)
                if p:
                    try:
                        p.unlink()
                    except OSError:
                        pass
    return n


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

_YEAR_IN_KEY = re.compile(r"^(.*?)[\s\-]*\((\d{4})\)\s*$")


def _int(v) -> Optional[int]:
    try:
        i = int(str(v).strip())
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def _url(v) -> Optional[str]:
    if isinstance(v, str) and re.match(r"^https?://", v.strip(), re.I):
        return v.strip()
    return None


def parse(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Entries from a Kometa metadata/collection file or TPDbCollectionMaker
    output. Each: {key, id, title, year, url, seasons: {n: url}, section,
    notes: [...]}. Returns (entries, file messages)."""
    from .kometa_import import ImportError_, _lenient_yaml
    try:
        data = _lenient_yaml(text)
    except ImportError_ as e:
        raise ValueError(str(e))
    except Exception as e:
        raise ValueError(f"Couldn't read the YAML: {e}")
    if not isinstance(data, dict):
        raise ValueError("Expected a list of titles with url_poster entries")

    sections: List[Tuple[str, dict]] = []
    if isinstance(data.get("metadata"), dict):
        sections.append(("metadata", data["metadata"]))
    if isinstance(data.get("collections"), dict):
        sections.append(("collections", data["collections"]))
    if not sections:
        sections.append(("metadata", data))

    messages: List[str] = []
    entries: List[Dict[str, Any]] = []
    for section, mapping in sections:
        for key, val in mapping.items():
            if not isinstance(val, dict):
                continue
            notes: List[str] = []
            url = _url(val.get("url_poster"))
            if val.get("file_poster") and not url:
                notes.append("file_poster isn't supported (use url_poster)")
            if val.get("url_background") or val.get("file_background"):
                notes.append("backgrounds are ignored")
            seasons: Dict[int, str] = {}
            raw_seasons = val.get("seasons")
            if isinstance(raw_seasons, dict):
                for sk, sv in raw_seasons.items():
                    idx = _int(sk) if str(sk).strip() != "0" else 0
                    su = _url(sv.get("url_poster")) if isinstance(sv, dict) else None
                    if idx is not None and su:
                        seasons[idx] = su
            if not url and not seasons:
                continue
            key_s = str(key).strip()
            item_id = _int(val.get("mapping_id")) or (_int(key_s) if isinstance(key, int) or key_s.isdigit() else None)
            title = str(val.get("title") or "").strip() or None
            year = _int(val.get("year"))
            if not item_id and not title:
                title = key_s
                m = _YEAR_IN_KEY.match(title)
                if m:
                    title, year = m.group(1).strip(), year or int(m.group(2))
                elif re.search(r"-\d{4}-(movie|show)$", title):
                    title = re.sub(r"-\d{4}-(movie|show)$", "", title)
            entries.append({"key": key_s, "id": item_id, "title": title, "year": year, "url": url,
                            "seasons": seasons, "section": section, "notes": notes})
    if not entries:
        messages.append("No titles with url_poster found")
    return entries, messages


def entry_signature(entry: Dict[str, Any]) -> str:
    raw = json.dumps([entry.get("url"), sorted((str(k), v) for k, v in (entry.get("seasons") or {}).items())])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def _norm(title: Any) -> str:
    s = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def group_members(server_id: str, library_id: str, media_type: str) -> Tuple[str, List[Tuple[str, str]]]:
    from . import poster_mode
    gid = poster_mode.group_id_for(server_id, library_id, media_type)
    try:
        _types, members, _rules = poster_mode._group_shape(gid)
    except Exception:
        members = []
    members = [(str(s), str(l)) for s, l in (members or [])]
    if (server_id, library_id) not in members:
        members.append((server_id, library_id))
    return gid, members


def _library_rows(server_id: str, library_id: str, media_type: str) -> List[Dict[str, Any]]:
    _gid, members = group_members(server_id, library_id, media_type)
    table = "tv_cache" if media_type == "tv" else "movie_cache"
    cols = "rating_key, server_id, library_id, title, year, tmdb_id" + (", tvdb_id" if media_type == "tv" else "")
    where = " OR ".join(["(server_id = ? AND library_id = ?)"] * len(members))
    params: List[Any] = []
    for s, l in members:
        params += [s, l]
    with db.get_db() as conn:
        rows = conn.execute(f"SELECT {cols} FROM {table} WHERE {where}", params).fetchall()
    return [dict(r) for r in rows]


def _collection_rows(server_id: str, library_id: str) -> List[Dict[str, Any]]:
    _gid, members = group_members(server_id, library_id, "movie")
    where = " OR ".join(["(server_id = ? AND library_id = ?)"] * len(members))
    params: List[Any] = []
    for s, l in members:
        params += [s, l]
    with db.get_db() as conn:
        rows = conn.execute(f"SELECT rating_key, server_id, library_id, title FROM collection_cache WHERE {where}",
                            params).fetchall()
    return [dict(r) for r in rows]


def match(entries: List[Dict[str, Any]], server_id: str, library_id: str, media_type: str) -> List[Dict[str, Any]]:
    """Attach the library copies each entry belongs to. status: matched,
    collection, not_found or ambiguous."""
    from .config import normalize_collection_title
    rows = _library_rows(server_id, library_id, media_type)
    by_tmdb: Dict[int, List[dict]] = {}
    by_tvdb: Dict[int, List[dict]] = {}
    by_title: Dict[str, List[dict]] = {}
    for r in rows:
        if r.get("tmdb_id"):
            by_tmdb.setdefault(int(r["tmdb_id"]), []).append(r)
        if r.get("tvdb_id"):
            by_tvdb.setdefault(int(r["tvdb_id"]), []).append(r)
        by_title.setdefault(_norm(r.get("title")), []).append(r)
    colls: Dict[str, List[dict]] = {}
    if media_type == "movie":
        for c in _collection_rows(server_id, library_id):
            colls.setdefault(_norm(normalize_collection_title(c.get("title") or "")), []).append(c)

    def _title_key(r: dict):
        if r.get("tmdb_id"):
            return ("tmdb", int(r["tmdb_id"]))
        if r.get("tvdb_id"):
            return ("tvdb", int(r["tvdb_id"]))
        return ("key", r["server_id"], r["rating_key"])

    out = []
    for e in entries:
        res = dict(e)
        hits: List[dict] = []
        if e.get("id"):
            i = int(e["id"])
            hits = (by_tvdb.get(i) or by_tmdb.get(i)) if media_type == "tv" else by_tmdb.get(i, [])
            hits = hits or []
        if not hits and e.get("title") and e.get("section") != "collections":
            hits = by_title.get(_norm(e["title"]), [])
            if e.get("year"):
                same_year = [h for h in hits if h.get("year") and int(h["year"]) == int(e["year"])]
                hits = same_year or ([] if any(h.get("year") for h in hits) else hits)
        titles = {_title_key(h) for h in hits}
        if len(titles) > 1:
            res.update(status="ambiguous", copies=[], message="More than one title matches; add a year or an id")
        elif hits:
            h0 = hits[0]
            # Every copy of the title in the group (a title can be on several servers).
            if h0.get("tmdb_id"):
                hits = by_tmdb.get(int(h0["tmdb_id"]), hits)
            elif h0.get("tvdb_id"):
                hits = by_tvdb.get(int(h0["tvdb_id"]), hits)
            res.update(status="matched", tmdb_id=h0.get("tmdb_id"), tvdb_id=h0.get("tvdb_id"),
                       matched_title=h0.get("title"), matched_year=h0.get("year"),
                       copies=[{"server_id": h["server_id"] or "plex-1", "rating_key": str(h["rating_key"]),
                                "library_id": h["library_id"]} for h in hits])
        else:
            cname = _norm(normalize_collection_title(e.get("title") or e.get("key") or ""))
            if media_type == "movie" and cname and colls.get(cname):
                cs = colls[cname]
                res.update(status="collection", matched_title=cs[0].get("title"),
                           copies=[{"server_id": c["server_id"] or "plex-1", "rating_key": str(c["rating_key"]),
                                    "library_id": c["library_id"]} for c in cs])
            else:
                res.update(status="not_found", copies=[], message="Not in this library group")
        out.append(res)
    return out


def preview(text: str, server_id: str, library_id: str, media_type: str) -> Dict[str, Any]:
    entries, messages = parse(text)
    matched = match(entries, server_id, library_id, media_type)
    counts: Dict[str, int] = {}
    for m in matched:
        counts[m["status"]] = counts.get(m["status"], 0) + 1
    return {"entries": matched, "messages": messages, "counts": counts}


# --------------------------------------------------------------------------
# Applying
# --------------------------------------------------------------------------

def _encode(data: bytes, server_id: str) -> Tuple[bytes, str]:
    from .api.save import encode_poster_for_plex
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        img = im.convert("RGB")
    return encode_poster_for_plex(img, for_plex=server_id == "plex-1")


def _upload_as_is(copy: Dict[str, Any], is_tv: bool, season_index: Optional[int], data: bytes,
                  title: str, year: Any, is_collection: bool = False) -> None:
    from . import media_server
    from .api.media_server_send import (_cache_poster_after_upload, _upload_poster_and_verify,
                                        upload_with_stale_retry)
    sid, rk = copy["server_id"], str(copy["rating_key"])
    client = media_server.get_client(sid)
    if client is None:
        raise ValueError(f"server {sid} isn't configured")
    payload, ctype = _encode(data, sid)
    if sid == "plex-1" or is_collection:
        _upload_poster_and_verify(client, sid, rk, payload, ctype, is_collection=is_collection)
        item_id = rk
    else:
        item_id, _cur = upload_with_stale_retry(
            sid, client, rk, None, lambda iid: _upload_poster_and_verify(client, sid, iid, payload, ctype))
    if not is_collection:
        _cache_poster_after_upload(str(item_id), payload, ctype, is_tv=is_tv)
    display = title
    if season_index is not None:
        display = f"{title} - {'Specials' if season_index == 0 else f'Season {season_index}'}"
    db.record_poster_history(
        rating_key=str(item_id), library_id=copy.get("library_id"), title=display, year=year,
        template_id=None, preset_id=None,
        action="sent_to_plex" if sid == "plex-1" else "sent_to_media_server",
        source=SOURCE, poster_data=payload, server_id=sid)


def _season_keys(copy: Dict[str, Any]) -> Dict[int, str]:
    from .api.batch import _list_show_seasons
    return {s["index"]: str(s["key"]) for s in _list_show_seasons(str(copy["rating_key"]), copy["server_id"])}


def _set_mode(gid: str, media_type: str, entry: Dict[str, Any], mode: str) -> None:
    from . import poster_mode
    item = [{"tmdb_id": entry.get("tmdb_id"), "tvdb_id": entry.get("tvdb_id")}]
    if mode == "as_is":
        poster_mode.set_manual(gid, media_type, item, "leave_alone")
    elif mode == "overlay":
        poster_mode.set_manual(gid, media_type, item, "overlay_only")
    else:
        current = poster_mode.effective(gid, media_type, entry.get("tmdb_id"), entry.get("tvdb_id"))[0]
        if current != "full":
            poster_mode.set_manual(gid, media_type, item, "full")


def apply_entry(entry: Dict[str, Any], gid: str, media_type: str, mode: str,
                template_id: Optional[str], preset_id: Optional[str]) -> Dict[str, Any]:
    """Download an entry's images, store them as the title's poster and apply
    them with `mode`. Returns {"status": "ok"|"error"|"skipped", "message"}."""
    is_tv = media_type == "tv"
    title = entry.get("matched_title") or entry.get("title") or entry.get("key")
    year = entry.get("matched_year") or entry.get("year")
    copies = entry.get("copies") or []
    if not copies:
        return {"status": "skipped", "message": entry.get("message") or "Not in this library group"}

    images: Dict[Optional[int], bytes] = {}
    problems: List[str] = []
    if entry.get("url"):
        try:
            images[None] = download(entry["url"])
        except ValueError as e:
            problems.append(f"poster: {e}")
    for idx, url in sorted((entry.get("seasons") or {}).items()):
        try:
            images[int(idx)] = download(url)
        except ValueError as e:
            problems.append(f"season {idx}: {e}")
    if not images:
        return {"status": "error", "message": "; ".join(problems) or "No images"}

    sent: List[str] = []
    errors: List[str] = list(problems)

    if entry.get("status") == "collection":
        if None not in images:
            return {"status": "error", "message": "; ".join(errors) or "No collection poster"}
        for c in copies:
            try:
                _upload_as_is(c, False, None, images[None], title, None, is_collection=True)
                sent.append(c["server_id"])
            except Exception as e:
                errors.append(f"{c['server_id']}: {e}")
        return _result(sent, errors, "uploaded as-is (collections can't use a preset)")

    for idx in images:
        url = entry["url"] if idx is None else entry["seasons"][idx]
        store(media_type, entry.get("tmdb_id"), entry.get("tvdb_id"), idx, url, title, SOURCE)

    _set_mode(gid, media_type, entry, mode)

    if mode == "as_is":
        for c in copies:
            try:
                if None in images:
                    _upload_as_is(c, is_tv, None, images[None], title, year)
                season_imgs = {k: v for k, v in images.items() if k is not None}
                if season_imgs:
                    keys = _season_keys(c)
                    for idx, data in season_imgs.items():
                        if idx in keys:
                            _upload_as_is({**c, "rating_key": keys[idx]}, True, idx, data, title, year)
                        else:
                            errors.append(f"{c['server_id']}: no season {idx}")
                sent.append(c["server_id"])
            except Exception as e:
                errors.append(f"{c['server_id']}: {e}")
        return _result(sent, errors, "uploaded as-is, set to Leave alone")

    if mode == "overlay":
        from . import overlay_only
        c0 = copies[0]
        res = overlay_only.apply_for_title(
            c0["server_id"], c0["rating_key"], c0.get("library_id"), is_tv, template_id or "uniformlogo", preset_id,
            SOURCE, include_series=None in images, include_seasons=any(k is not None for k in images),
            affected_seasons=[k for k in images if k is not None] or None,
            tmdb_id=entry.get("tmdb_id"), tvdb_id=entry.get("tvdb_id"), title_hint=title, year_hint=year)
        for r in res.get("results", []):
            if r.get("status") == "ok":
                sent.append(r.get("server_id"))
            elif r.get("status") == "error":
                errors.append(f"{r.get('server_id')}: {r.get('reason')}")
            elif r.get("reason"):
                errors.append(f"{r.get('server_id')}: {r.get('reason')}")
        return _result(sent, errors, "overlays applied (Overlay only)")

    # template: a normal render; the imported poster is used as its background.
    from .api import batch
    plex_copy = next((c for c in copies if c["server_id"] == "plex-1"), None)
    c0 = plex_copy or copies[0]
    others = [c["server_id"] for c in copies if c["server_id"] != c0["server_id"]]
    targets = ([c0["server_id"]] if c0["server_id"] != "plex-1" else []) + others
    kwargs = dict(send_to_plex=c0["server_id"] == "plex-1", library_id=c0.get("library_id") or "",
                  source=SOURCE, targets=list(dict.fromkeys(targets)), source_server_id=c0["server_id"])
    try:
        if is_tv:
            result = batch.process_single_tv_show_poster(
                c0["rating_key"], template_id or "uniformlogo", preset_id,
                include_seasons=any(k is not None for k in images), **kwargs)
        else:
            result = batch.process_single_movie_poster(c0["rating_key"], template_id or "uniformlogo", preset_id, **kwargs)
    except Exception as e:
        return {"status": "error", "message": f"render failed: {e}"}
    if not result:
        return {"status": "error", "message": "; ".join(errors + ["render failed (see the log)"])}
    status = result.get("status") if isinstance(result, dict) else "ok"
    if status in ("error", "failed"):
        return {"status": "error", "message": "; ".join(errors + [str(result.get("error") or "render failed")])}
    return _result([c["server_id"] for c in copies], errors, f"rendered with preset {preset_id}")


def _result(sent: List[str], errors: List[str], what: str) -> Dict[str, Any]:
    from .media_server.registry import get_server_label
    if sent:
        names = ", ".join(get_server_label(s) for s in dict.fromkeys(s for s in sent if s))
        msg = f"{what} on {names}"
        if errors:
            msg += f" ({'; '.join(errors)})"
        return {"status": "ok" if not errors else "partial", "message": msg}
    return {"status": "error", "message": "; ".join(errors) or "Nothing was sent"}


# --------------------------------------------------------------------------
# Jobs (one at a time, polled by the page)
# --------------------------------------------------------------------------

def get_status() -> Dict[str, Any]:
    with _status_lock:
        return json.loads(json.dumps(_status))


def _set_status(**kw: Any) -> None:
    with _status_lock:
        _status.update(kw)


def is_running() -> bool:
    return get_status().get("state") == "running"


def run_import(entries: List[Dict[str, Any]], server_id: str, library_id: str, media_type: str,
               mode: str, template_id: Optional[str], preset_id: Optional[str],
               overrides: Optional[Dict[str, str]] = None, label: str = "Import") -> Dict[str, Any]:
    """Apply matched entries (blocking). overrides: {entry key: mode | "skip"}."""
    gid, _members = group_members(server_id, library_id, media_type)
    todo = [e for e in entries if e.get("status") in ("matched", "collection")
            and (overrides or {}).get(e["key"]) != "skip"]
    _set_status(state="running", label=label, total=len(todo), processed=0, current="",
                results=[], started_at=datetime.now().isoformat(timespec="seconds"), error=None)
    results = []
    counts = {"ok": 0, "partial": 0, "error": 0, "skipped": 0}
    for e in todo:
        title = e.get("matched_title") or e.get("title") or e.get("key")
        _set_status(current=title)
        m = (overrides or {}).get(e["key"]) or mode
        if m not in MODES:
            m = mode
        try:
            r = apply_entry(e, gid, media_type, m, template_id, preset_id)
        except Exception as ex:
            logger.exception("[POSTER_IMPORT] %s failed", title)
            r = {"status": "error", "message": str(ex)}
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        results.append({"key": e["key"], "title": title, "mode": m, **r})
        (logger.warning if r["status"] == "error" else logger.info)(
            "[POSTER_IMPORT] %s: %s", title, r.get("message"))
        with _status_lock:
            _status["processed"] = _status.get("processed", 0) + 1
            _status["results"] = results[-500:]
    summary = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    _set_status(state="done", current="", summary=summary or "nothing to do",
                finished_at=datetime.now().isoformat(timespec="seconds"))
    logger.info("[POSTER_IMPORT] %s finished: %s", label, summary or "nothing to do")
    return {"counts": counts, "results": results}


def mark_starting(label: str, total: int = 0) -> None:
    """Report "running" before the worker thread starts, so the page's first
    status poll doesn't see the previous state and stop polling."""
    _set_status(state="running", label=label, total=total, processed=0, current="Starting…",
                results=[], summary=None, error=None)


def start_import(**kwargs: Any) -> bool:
    if not _job_lock.acquire(blocking=False):
        return False
    entries = kwargs.get("entries") or []
    mark_starting(kwargs.get("label") or "Import",
                  sum(1 for e in entries if e.get("status") in ("matched", "collection")))

    def worker():
        try:
            run_import(**kwargs)
        except Exception as e:
            logger.exception("[POSTER_IMPORT] Import failed")
            _set_status(state="error", error=str(e))
        finally:
            _job_lock.release()
    threading.Thread(target=worker, daemon=True, name="poster-import").start()
    return True


# --------------------------------------------------------------------------
# Live files
# --------------------------------------------------------------------------

_FILE_COLS = ("id", "path", "name", "server_id", "library_id", "media_type", "mode", "template_id", "preset_id",
              "interval_hours", "enabled", "last_hash", "entry_sigs", "last_checked_at", "last_changed_at",
              "last_status", "last_message", "created_at", "require_approval", "pending_json")


def _file_row(r) -> Dict[str, Any]:
    d = {k: r[k] for k in _FILE_COLS}
    d["enabled"] = bool(d["enabled"])
    d["require_approval"] = bool(d["require_approval"])
    try:
        d["entry_sigs"] = json.loads(d["entry_sigs"] or "{}")
    except ValueError:
        d["entry_sigs"] = {}
    try:
        d["pending"] = json.loads(d.pop("pending_json") or "[]")
    except ValueError:
        d["pending"] = []
    return d


def get_files(server_id: Optional[str] = None, library_id: Optional[str] = None,
              media_type: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_tables()
    with db.get_db() as conn:
        rows = conn.execute(f"SELECT {', '.join(_FILE_COLS)} FROM poster_import_files ORDER BY created_at").fetchall()
    out = [_file_row(r) for r in rows]
    if server_id is not None:
        out = [f for f in out if f["server_id"] == server_id and f["library_id"] == str(library_id)
               and f["media_type"] == media_type]
    return out


def get_file(file_id: str) -> Optional[Dict[str, Any]]:
    ensure_tables()
    with db.get_db() as conn:
        r = conn.execute(f"SELECT {', '.join(_FILE_COLS)} FROM poster_import_files WHERE id = ?", (file_id,)).fetchone()
    return _file_row(r) if r else None


def save_file(data: Dict[str, Any]) -> Dict[str, Any]:
    ensure_tables()
    fid = data.get("id") or uuid.uuid4().hex[:12]
    old = get_file(fid)
    reset = old is not None and (old["path"] != data["path"] or old["mode"] != data["mode"]
                                 or old["preset_id"] != data.get("preset_id"))
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO poster_import_files (id, path, name, server_id, library_id, media_type, mode, template_id, "
            "preset_id, interval_hours, enabled, require_approval) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET path=excluded.path, name=excluded.name, mode=excluded.mode, "
            "template_id=excluded.template_id, preset_id=excluded.preset_id, interval_hours=excluded.interval_hours, "
            "enabled=excluded.enabled, require_approval=excluded.require_approval",
            (fid, data["path"], data.get("name") or "", data["server_id"], str(data["library_id"]),
             data["media_type"], data["mode"], data.get("template_id") or "uniformlogo", data.get("preset_id"),
             float(data.get("interval_hours") or 6), 1 if data.get("enabled", True) else 0,
             1 if data.get("require_approval") else 0))
        if reset:
            # A different file, mode or preset: apply every entry again on the next check.
            conn.execute("UPDATE poster_import_files SET last_hash = NULL, entry_sigs = NULL, pending_json = NULL "
                         "WHERE id = ?", (fid,))
    return get_file(fid)


def update_file_status(file_id: str, **fields: Any) -> None:
    if "entry_sigs" in fields and not isinstance(fields["entry_sigs"], str):
        fields["entry_sigs"] = json.dumps(fields["entry_sigs"])
    if "pending" in fields:
        p = fields.pop("pending")
        fields["pending_json"] = json.dumps(p) if p else None
    sets = [k for k in fields if k in _FILE_COLS and k != "id"]
    if not sets:
        return
    with db.get_db() as conn:
        conn.execute(f"UPDATE poster_import_files SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?",
                     [fields[k] for k in sets] + [file_id])


def delete_file(file_id: str) -> bool:
    ensure_tables()
    with db.get_db() as conn:
        return conn.execute("DELETE FROM poster_import_files WHERE id = ?", (file_id,)).rowcount > 0


def sync_file(file_id: str, force: bool = False, approve: bool = False) -> Dict[str, Any]:
    """Re-read a live file and apply entries that are new or changed since the
    last check (all of them with force). An entry removed from the file is left
    as it is. With "ask before applying" on, changed titles are only listed
    (status pending) until approve=True. Blocks; returns {"status", "message"}."""
    live = get_file(file_id)
    if not live:
        return {"status": "error", "message": "Not found"}
    from .live_kometa import read_source, source_name
    label = f"Live file {live.get('name') or source_name(live['path'])}"
    if not is_running():
        mark_starting(label)

    def done(status: str, message: str, **extra: Any) -> Dict[str, Any]:
        update_file_status(file_id, last_checked_at=datetime.now().isoformat(timespec="seconds"),
                           last_status=status, last_message=message, **extra)
        if get_status().get("label") == label and status != "busy":
            _set_status(state="error" if status == "error" else "done", current="",
                        summary=message, error=message if status == "error" else None,
                        finished_at=datetime.now().isoformat(timespec="seconds"))
        (logger.warning if status == "error" else logger.info)("[POSTER_IMPORT] %s: %s", live["path"], message)
        return {"status": status, "message": message}

    try:
        raw, _url = read_source(live["path"])
    except (ValueError, OSError) as e:
        return done("error", str(e))
    digest = hashlib.sha256(raw).hexdigest()
    if not force and not approve and digest == live.get("last_hash") and not live.get("pending"):
        return done("unchanged", "No changes since the last check")
    try:
        entries, _msgs = parse(raw.decode("utf-8-sig", errors="replace"))
    except ValueError as e:
        return done("error", f"Couldn't read the file: {e}")
    matched = match(entries, live["server_id"], live["library_id"], live["media_type"])
    old_sigs = {} if force else (live.get("entry_sigs") or {})
    sigs = {e["key"]: entry_signature(e) for e in matched}
    todo = [e for e in matched if old_sigs.get(e["key"]) != sigs[e["key"]]]
    applicable = [e for e in todo if e["status"] in ("matched", "collection")]
    if live.get("require_approval") and not approve and applicable:
        pending = [{"key": e["key"], "title": e.get("matched_title") or e.get("title") or e["key"],
                    "season_count": len(e.get("seasons") or {})} for e in applicable]
        return done("pending", f"{len(pending)} title(s) new or changed; review them and press Apply",
                    pending=pending, last_hash=digest)
    if not _job_lock.acquire(blocking=False):
        return done("busy", "Another import is running; trying again on the next check")
    try:
        res = run_import(todo, live["server_id"], live["library_id"], live["media_type"], live["mode"],
                         live.get("template_id"), live.get("preset_id"), label=label)
    finally:
        _job_lock.release()
    c = res["counts"]
    applied = c.get("ok", 0) + c.get("partial", 0)
    # Entries that failed keep their old signature, so the next check tries them again.
    keep = dict(old_sigs)
    failed_keys = {r["key"] for r in res["results"] if r["status"] == "error"}
    for e in matched:
        if e["key"] not in failed_keys and e["status"] in ("matched", "collection"):
            keep[e["key"]] = sigs[e["key"]]
    not_found = sum(1 for e in matched if e["status"] in ("not_found", "ambiguous"))
    parts = [f"{applied} applied" if todo else "no changed titles"]
    if c.get("error"):
        parts.append(f"{c['error']} failed")
    if not_found:
        parts.append(f"{not_found} not in this library")
    return done("updated" if applied else ("error" if c.get("error") else "unchanged"), ", ".join(parts), pending=[],
                last_hash=digest if not c.get("error") else live.get("last_hash"), entry_sigs=keep,
                last_changed_at=datetime.now().isoformat(timespec="seconds") if applied else live.get("last_changed_at"))
