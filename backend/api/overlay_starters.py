"""Starter overlays: ready-made overlays a user can add from the Overlay Manager.

The list comes from the simposter-assets repo (starter_overlays/index.json and
the files it names), so a new or updated starter only needs a push there. The
last good copy is kept in config/cache/starter_overlays/; the files bundled in
backend/starter_overlays/ are the fallback when neither is available. A remote
starter replaces a bundled one with the same id.

Images and fonts aren't shipped: their layers link to the creator's files
(pinned to a commit), downloaded into the user's image library / config/fonts
when the overlay is added, the same way a Kometa import downloads linked
images (Quirk #164).

A starter may set "min_version" (e.g. "v1.8.40") when it uses something older
Simposter versions can't draw; older installs list it but can't add it.
"""
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from .. import database as db
from ..config import logger, settings
from .kometa_import import _AssetSaver, _font_dir, download_remote_image, _remote_cache

router = APIRouter()

_STARTER_DIR = Path(__file__).resolve().parent.parent / "starter_overlays"
_REMOTE_BASE = "https://raw.githubusercontent.com/PJGitHub9/simposter-assets/main/starter_overlays/"
_REMOTE_MAX_AGE = 600          # re-check simposter-assets at most every 10 minutes
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_FONT_BYTES = 10 * 1024 * 1024
_SAFE_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.json$")

_lock = threading.Lock()
_remote: Optional[List[Dict[str, Any]]] = None
_remote_checked = 0.0


def _cache_dir() -> Path:
    d = Path(settings.CONFIG_DIR) / "cache" / "starter_overlays"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _overlays_in(text: str, source: str) -> List[Dict[str, Any]]:
    data = json.loads(text)
    out = []
    for o in data.get("overlays", []):
        if isinstance(o, dict) and o.get("id"):
            out.append({**o, "_source": source})
    return out


def _fetch(name: str) -> str:
    import requests
    from ..config import EXTERNAL_IMAGE_FETCH_HEADERS
    r = requests.get(_REMOTE_BASE + name, headers=EXTERNAL_IMAGE_FETCH_HEADERS, timeout=10)
    r.raise_for_status()
    if len(r.content) > _MAX_FILE_BYTES:
        raise ValueError(f"{name} is larger than 2 MB")
    return r.text


def _read_disk_copy() -> Optional[List[Dict[str, Any]]]:
    d = _cache_dir()
    index = d / "index.json"
    if not index.exists():
        return None
    out: List[Dict[str, Any]] = []
    try:
        for name in json.loads(index.read_text(encoding="utf-8")).get("files", []):
            f = d / str(name)
            if _SAFE_FILE.match(str(name)) and f.exists():
                out += _overlays_in(f.read_text(encoding="utf-8"), "simposter-assets")
        return out
    except Exception:
        return None


def _remote_starters(refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Starters from simposter-assets: fetched at most every 10 minutes, else
    the last good copy on disk. None when there has never been one."""
    global _remote, _remote_checked
    with _lock:
        now = time.time()
        if _remote is None:
            _remote = _read_disk_copy()
        if refresh or now - _remote_checked > _REMOTE_MAX_AGE:
            _remote_checked = now
            try:
                index_text = _fetch("index.json")
                names = [str(n) for n in json.loads(index_text).get("files", []) if _SAFE_FILE.match(str(n)) and str(n) != "index.json"]
                files = {n: _fetch(n) for n in names}
                overlays: List[Dict[str, Any]] = []
                for n, text in files.items():
                    overlays += _overlays_in(text, "simposter-assets")
                d = _cache_dir()
                for old in d.glob("*.json"):
                    if old.name != "index.json" and old.name not in files:
                        old.unlink(missing_ok=True)
                for n, text in files.items():
                    (d / n).write_text(text, encoding="utf-8")
                (d / "index.json").write_text(index_text, encoding="utf-8")
                _remote = overlays
            except Exception as e:
                logger.debug("[STARTERS] Couldn't fetch starter overlays from simposter-assets: %s", e)
        return _remote


def _bundled_starters() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in sorted(_STARTER_DIR.glob("*.json")):
        try:
            out += _overlays_in(path.read_text(encoding="utf-8"), "built-in")
        except Exception as e:
            logger.warning("[STARTERS] Couldn't read %s: %s", path.name, e)
    return out


def _load_starters(refresh: bool = False) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {s["id"]: s for s in _bundled_starters()}
    for s in _remote_starters(refresh) or []:
        by_id[s["id"]] = s
    return list(by_id.values())


def _version_block(starter: Dict[str, Any]) -> Optional[str]:
    """The version a starter needs when this install is older, else None."""
    needed = str(starter.get("min_version") or "").strip()
    if not needed:
        return None
    from .version_info import parse_version
    current = db.get_app_version()
    if current == "unknown":
        return None
    return needed if parse_version(needed) > parse_version(current) else None


def _find(starter_id: str) -> Dict[str, Any]:
    starter = next((s for s in _load_starters() if s["id"] == starter_id), None)
    if not starter:
        raise HTTPException(404, "No such starter overlay")
    return starter


@router.get("/overlay-starters")
def api_list_starters(refresh: bool = False):
    items = []
    for s in _load_starters(refresh):
        items.append({
            "id": s["id"],
            "name": s.get("name") or s["id"],
            "description": s.get("description") or "",
            "credit": s.get("credit") or {},
            "layers": len(s.get("elements") or []),
            "installed": db.get_overlay_config(s["id"]) is not None,
            "needs_version": _version_block(s),
            "source": s.get("_source"),
        })
    items.sort(key=lambda i: i["name"].lower())
    return {"starters": items}


def _download_font(font: Dict[str, Any]) -> Optional[str]:
    """Fetch a font the overlay uses into config/fonts unless it's already there."""
    name = Path(str(font.get("file") or "")).name
    url = str(font.get("url") or "")
    if not name or not url or Path(name).suffix.lower() not in (".ttf", ".otf"):
        return None
    target = _font_dir() / name
    if target.exists():
        return name
    try:
        from ..middleware.validation import safe_get
        from ..config import EXTERNAL_IMAGE_FETCH_HEADERS
        r = safe_get(url, strict=True, headers=EXTERNAL_IMAGE_FETCH_HEADERS, timeout=30, stream=True)
        r.raise_for_status()
        content = r.raw.read(_MAX_FONT_BYTES + 1, decode_content=True)
        if len(content) > _MAX_FONT_BYTES:
            raise ValueError("larger than 10 MB")
        from PIL import ImageFont
        import io
        ImageFont.truetype(io.BytesIO(content), 20)  # a real font, or this raises
        target.write_bytes(content)
        return name
    except Exception as e:
        logger.warning("[STARTERS] Couldn't download font %s: %s", name, e)
        return None


@router.post("/overlay-starters/{starter_id}/install")
def api_install_starter(starter_id: str, replace: bool = False):
    """Add a starter overlay: download its images and fonts, then save it under
    the starter's id. Already added: 409 unless replace=true, which overwrites
    it with the shipped version (layers, notes and whole-overlay rules; local
    edits are lost). Overwritten in place, not deleted and re-added: deleting
    an overlay unticks it from every preset that uses it."""
    starter = _find(starter_id)
    needed = _version_block(starter)
    if needed:
        raise HTTPException(409, f"This starter overlay needs Simposter {needed} or newer")
    existing = db.get_overlay_config(starter_id)
    if existing and not replace:
        raise HTTPException(409, "This starter overlay is already added")

    _remote_cache.clear()
    saver = _AssetSaver(dry_run=False)
    elements: List[Dict[str, Any]] = []
    missing: List[str] = []
    for el in starter.get("elements") or []:
        el = dict(el)
        url = el.get("url")
        if url and not el.get("asset_id"):
            got = download_remote_image(url)
            asset_id = saver.save(got[0], got[1]) if got else None
            if asset_id:
                el["asset_id"] = asset_id
            else:
                missing.append(url.rsplit("/", 1)[-1])
        elements.append(el)
    fonts = [f for f in (_download_font(f) for f in starter.get("fonts") or []) if f]

    db.save_overlay_config(
        starter_id, starter.get("name") or starter_id, elements, starter.get("streaming_region") or "US",
        conditions=starter.get("conditions") or [],
        notes=starter.get("notes") or "",
    )
    logger.info("[STARTERS] Added '%s': %d image(s) downloaded, %d reused, %d missing, fonts %s",
                starter.get("name"), saver.saved, saver.reused, len(missing), fonts or "none")
    return {"status": "ok", "config_id": starter_id, "images": saver.saved + saver.reused,
            "missing": missing, "fonts": fonts}
