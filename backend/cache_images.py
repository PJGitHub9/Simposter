"""Smaller files for the image caches under config/cache.

Display caches (posters, backdrops, square art, thumb art, logos) are only
shown in the app (grids, the editors' "Current" image, the overlay preview),
so they're stored downscaled: posters 1000px tall, the others 1280px on the
long side, JPEG quality 85; logos 800px wide and kept as PNG (transparency).
Backup downloads full-size images itself (art_cache's full_copy_to).

Resend caches (poster_renders, poster_renders_by_tmdb) are re-uploaded as-is
when a poster is resent, so they keep full resolution and are only stored as
JPEG quality 95 (4:4:4, Quirk #12) instead of multi-MB PNG.

shrink_existing() rewrites files written before this (once, in the background).
"""
from __future__ import annotations

import io
import os
import threading
from pathlib import Path
from typing import Optional, Tuple

from .config import logger, settings

# kind -> (max width, max height, keep PNG)
_LIMITS = {
    "poster": (None, 1000, False),
    "backdrop": (1280, 1280, False),
    "square_art": (1280, 1280, False),
    "thumb_art": (1280, 1280, False),
    "logo": (800, 800, True),
}
_DISPLAY_QUALITY = 85
_RENDER_QUALITY = 95


def _open(content: bytes):
    from PIL import Image
    img = Image.open(io.BytesIO(content))
    img.load()
    return img


def shrink_display(content: bytes, kind: str) -> Tuple[bytes, str]:
    """(bytes, extension) for a display-cache image. Returns the original
    (with its own extension) when it can't be read or wouldn't get smaller."""
    max_w, max_h, keep_png = _LIMITS.get(kind, (1280, 1280, False))
    orig_ext = _ext_of(content)
    try:
        from PIL import Image
        img = _open(content)
        scale = 1.0
        if max_w and img.width > max_w:
            scale = min(scale, max_w / img.width)
        if max_h and img.height > max_h:
            scale = min(scale, max_h / img.height)
        if scale < 1.0:
            img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        if keep_png:
            if img.mode not in ("RGBA", "LA", "P", "RGB", "L"):
                img = img.convert("RGBA")
            img.save(buf, "PNG", optimize=True)
            ext = "png"
        else:
            if img.mode in ("RGBA", "LA", "P"):
                rgba = img.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (0, 0, 0))
                bg.paste(rgba, mask=rgba.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(buf, "JPEG", quality=_DISPLAY_QUALITY, optimize=True)
            ext = "jpg"
        out = buf.getvalue()
        if scale >= 1.0 and len(out) >= len(content):
            return content, orig_ext
        return out, ext
    except Exception as e:
        logger.debug("[CACHE] Could not shrink %s image: %s", kind, e)
        return content, orig_ext


def shrink_render(content: bytes) -> bytes:
    """A PNG render becomes a full-size JPEG quality 95; anything else is kept."""
    if not content.startswith(b"\x89PNG"):
        return content
    try:
        from PIL import Image
        img = _open(content)
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (0, 0, 0))
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=_RENDER_QUALITY, subsampling=0, optimize=True)
        out = buf.getvalue()
        return out if len(out) < len(content) else content
    except Exception as e:
        logger.debug("[CACHE] Could not convert a render to JPEG: %s", e)
        return content


def _ext_of(content: bytes) -> str:
    if content.startswith(b"\x89PNG"):
        return "png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def write_display(cache_dir: Path, stem: str, content: bytes, kind: str) -> Optional[Path]:
    """Write a shrunk display image as {stem}.{ext}, removing the same item's
    file under any other extension (it would otherwise be found first)."""
    data, ext = shrink_display(content, kind)
    target = cache_dir / f"{stem}.{ext}"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        for other in ("jpg", "jpeg", "png", "webp"):
            if other != ext:
                stale = cache_dir / f"{stem}.{other}"
                if stale.exists():
                    try:
                        stale.unlink()
                    except OSError:
                        pass
        return target
    except Exception as e:
        logger.debug("[CACHE] Failed to write %s cache for %s: %s", kind, stem, e)
        return None


# ---------------------------------------------------------------------------
# One-time pass over files written before this
# ---------------------------------------------------------------------------

_MARKER = "cache_shrink_v1"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _cache_root() -> Path:
    return Path(settings.CONFIG_DIR) / "cache"


def _shrink_dir(folder: Path, kind: Optional[str]) -> Tuple[int, int, int]:
    """(files changed, bytes before, bytes after). kind None = a resend cache."""
    changed = before = after = 0
    if not folder.is_dir():
        return 0, 0, 0
    for path in list(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
            continue
        try:
            content = path.read_bytes()
            stat = path.stat()
            if kind is None:
                data, ext = shrink_render(content), path.suffix.lstrip(".")
            else:
                data, ext = shrink_display(content, kind)
            if len(data) >= len(content):
                continue
            target = path.with_suffix(f".{ext}") if kind is not None else path
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
            # Same modification time: cache-busting URLs and thumbnails stay valid.
            os.utime(target, (stat.st_atime, stat.st_mtime))
            if target != path and path.exists():
                path.unlink()
            changed += 1
            before += len(content)
            after += len(data)
        except Exception as e:
            logger.debug("[CACHE] Could not shrink %s: %s", path, e)
    return changed, before, after


def shrink_existing(force: bool = False) -> dict:
    """Shrink every cached image written before this change. Runs once per
    database (recorded in applied_migrations after it finishes); safe to
    interrupt, since already-small files are skipped on the next run."""
    from . import database as db
    if not force:
        try:
            with db.get_db() as conn:
                if conn.execute("SELECT 1 FROM applied_migrations WHERE name = ?", (_MARKER,)).fetchone():
                    return {"skipped": True}
        except Exception:
            pass
    root = _cache_root()
    folders = [
        ("posters", "poster"), ("backdrops", "backdrop"), ("square_art", "square_art"),
        ("thumb_art", "thumb_art"), ("logos", "logo"),
        ("poster_renders", None), ("poster_renders_by_tmdb", None),
    ]
    totals = {"files": 0, "before": 0, "after": 0}
    for name, kind in folders:
        changed, before, after = _shrink_dir(root / name, kind)
        if changed:
            logger.info("[CACHE] Shrank %d file(s) in cache/%s: %.0f MB -> %.0f MB",
                        changed, name, before / 1e6, after / 1e6)
        totals["files"] += changed
        totals["before"] += before
        totals["after"] += after
    try:
        with db.get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO applied_migrations (name) VALUES (?)", (_MARKER,))
            conn.commit()
    except Exception:
        pass
    if totals["files"]:
        logger.info("[CACHE] Image caches shrunk: %d file(s), %.1f GB freed",
                    totals["files"], (totals["before"] - totals["after"]) / 1e9)
    return totals


def start_shrink_existing() -> None:
    threading.Thread(target=shrink_existing, name="cache-shrink", daemon=True).start()
