# backend/remote_files.py
"""Live files from a link instead of a path on the server: Overlay Manager's
live Kometa files and Poster Import's live files can both point at
`https://...` (a GitHub `blob` page link is turned into its raw file) or
Kometa's `git: <path>` shorthand (Kometa-Team/Community-Configs, as Kometa's
own modules/github.py builds it).

Each check sends the last ETag (If-None-Match), so an unchanged file costs one
small "not modified" reply; the last copy is kept in `remote_file_cache` and
returned again. Fetches go through safe_get(strict=True): public hosts only,
every redirect re-checked.
"""
import re
import threading
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

from . import database as db
from .config import logger

MAX_BYTES = 5 * 1024 * 1024
KOMETA_CONFIGS_RAW = "https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/"

_table_ready = False
_table_lock = threading.Lock()


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    with _table_lock:
        if _table_ready:
            return
        with db.get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS remote_file_cache (
                    url TEXT PRIMARY KEY,
                    etag TEXT,
                    body BLOB,
                    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""")
        _table_ready = True


def is_remote(source: str) -> bool:
    s = (source or "").strip()
    return bool(re.match(r"^(https?://|git:|repo:)", s, re.I))


def resolve_url(source: str) -> str:
    """The URL a live-file source is read from. Raises ValueError for a source
    Simposter can't use."""
    s = (source or "").strip()
    m = re.match(r"^(git|repo):\s*(.+)$", s, re.I)
    if m:
        if m.group(1).lower() == "repo":
            raise ValueError("repo: uses the custom_repo in your Kometa config; paste the file's full link instead")
        path = m.group(2).strip().lstrip("/")
        if not re.search(r"\.ya?ml$", path, re.I):
            path += ".yml"
        return KOMETA_CONFIGS_RAW + path
    if not re.match(r"^https?://", s, re.I):
        raise ValueError("Not a link")
    u = urlparse(s)
    if not u.netloc:
        raise ValueError("Not a valid link")
    # https://github.com/owner/repo/blob/branch/path.yml -> raw file
    gm = re.match(r"^/([^/]+)/([^/]+)/(?:blob|raw)/(.+)$", u.path)
    if u.netloc.lower() in ("github.com", "www.github.com") and gm:
        return f"https://raw.githubusercontent.com/{gm.group(1)}/{gm.group(2)}/{gm.group(3)}"
    return s


def validate(source: str) -> str:
    """Check a live-file link's form (it's fetched on the first check). Returns
    the source to store."""
    s = (source or "").strip()
    url = resolve_url(s)
    path = urlparse(url).path.lower()
    if not (path.endswith(".yml") or path.endswith(".yaml")):
        raise ValueError("The link should point at a .yml or .yaml file")
    from .middleware.validation import check_ssrf_safe
    err = check_ssrf_safe(url, strict=True)
    if err:
        raise ValueError(f"Simposter won't fetch this link: {err}")
    return s


def fetch(source: str) -> Tuple[bytes, str, bool]:
    """Read a live-file link. Returns (body, url, changed_on_server).
    changed_on_server is False when the server said "not modified" and the
    stored copy was used. Raises ValueError with a readable reason."""
    _ensure_table()
    url = resolve_url(source)
    with db.get_db() as conn:
        row = conn.execute("SELECT etag, body FROM remote_file_cache WHERE url = ?", (url,)).fetchone()
    from .config import EXTERNAL_IMAGE_FETCH_HEADERS
    from .middleware.validation import safe_get
    headers = dict(EXTERNAL_IMAGE_FETCH_HEADERS)
    headers["Accept"] = "text/plain, application/x-yaml, text/yaml, */*"
    if row and row["etag"] and row["body"] is not None:
        headers["If-None-Match"] = row["etag"]
    try:
        r = safe_get(url, strict=True, headers=headers, timeout=30, stream=True)
    except Exception as e:
        raise ValueError(f"Couldn't download the file ({e})")
    try:
        if r.status_code == 304 and row and row["body"] is not None:
            return bytes(row["body"]), url, False
        if r.status_code == 404:
            raise ValueError("The link answered 404: the file was moved or removed")
        if r.status_code != 200:
            raise ValueError(f"The link answered HTTP {r.status_code}")
        chunks, size = [], 0
        for chunk in r.iter_content(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("The file is larger than 5 MB")
            chunks.append(chunk)
        body = b"".join(chunks)
        etag = r.headers.get("ETag")
    finally:
        r.close()
    head = body[:400].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        raise ValueError("The link returned a web page, not a YAML file (use the file's raw link)")
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO remote_file_cache (url, etag, body, fetched_at) VALUES (?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, body=excluded.body, fetched_at=CURRENT_TIMESTAMP",
            (url, etag, body))
    return body, url, True


def image_finder(file_url: str):
    """find(wanted) for images an overlay file names by path: the path taken
    relative to the file's link, then its parent folders (Kometa repo files
    refer to images relative to the repo). Same contract as live_kometa's disk
    finder: (file name, bytes) or None."""
    from .api.kometa_import import download_remote_image

    def find(wanted: str):
        rel = str(wanted or "").replace("\\", "/").lstrip("/")
        if not rel or re.match(r"^[a-z]+://", rel, re.I):
            return None
        base = file_url
        tried = set()
        for _ in range(4):
            candidate = urljoin(base, rel)
            if candidate not in tried:
                tried.add(candidate)
                try:
                    got = download_remote_image(candidate)
                except Exception as e:
                    got = None
                    logger.debug("[REMOTE FILE] %s: %s", candidate, e)
                if got:
                    return rel.split("/")[-1], got[1]
            parent = urljoin(base, "..")
            if parent == base:
                break
            base = parent
        return None
    return find
