# backend/overlay_cache.py
"""Pre-rendered overlay effect layers (matte, fade, top matte/fade, vignette,
wash) used by rendering.render_with_overlay_cache() for faster batch renders.

A cache file is named {preset_id}--{signature}.png under
config/overlays/{template_id}/, where the signature covers exactly the options
generate_overlay() reads plus the canvas size. So a season config with its own
matte, a Square Art (square canvas) render and the series poster each get their
own correct layer, and editing a preset can never leave a stale one in use.

Files are made at startup for every preset (series and season settings), when a
preset is saved or imported, and on a cache miss at render time.
"""
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .config import logger, settings

# Every option generate_overlay() reads.
EFFECT_KEYS = (
    "matte_height_ratio",
    "fade_height_ratio",
    "top_matte_height_ratio",
    "top_fade_height_ratio",
    "vignette_strength",
    "v12_wash_strength",
)
_NAME_RE = re.compile(r"^(?P<preset>.+)--(?P<sig>[0-9a-f]{12})$")


def overlay_dir(template_id: str) -> Path:
    return Path(settings.CONFIG_DIR) / "overlays" / template_id


def _canvas(options: Dict[str, Any]) -> Tuple[int, int]:
    from .templates.canvas import resolve_canvas_size
    return resolve_canvas_size(options or {})


def signature(options: Dict[str, Any]) -> str:
    """Short hash of what the effect layer depends on."""
    values = {}
    for key in EFFECT_KEYS:
        try:
            values[key] = round(float((options or {}).get(key) or 0.0), 4)
        except (TypeError, ValueError):
            values[key] = 0.0
    values["_canvas"] = list(_canvas(options))
    return hashlib.sha1(json.dumps(values, sort_keys=True).encode()).hexdigest()[:12]


def cache_path(template_id: str, preset_id: str, options: Dict[str, Any]) -> Path:
    return overlay_dir(template_id) / f"{preset_id}--{signature(options)}.png"


def parse_name(stem: str) -> Optional[Tuple[str, str]]:
    """(preset_id, signature) for a cache file name, None for anything else
    (e.g. the old {preset_id}.png files)."""
    m = _NAME_RE.match(stem)
    return (m.group("preset"), m.group("sig")) if m else None


def ensure(template_id: str, preset_id: str, options: Dict[str, Any]) -> Optional[Path]:
    """The cache file for these options, generating it when missing."""
    if not preset_id:
        return None
    path = cache_path(template_id, preset_id, options)
    if path.exists():
        return path
    try:
        from .rendering import generate_overlay
        w, h = _canvas(options)
        img = generate_overlay(options, w, h)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, "PNG")
        logger.info("[OVERLAY CACHE] Generated %s", path.name)
        return path
    except Exception as e:
        logger.warning("[OVERLAY CACHE] Couldn't generate %s/%s: %s", template_id, preset_id, e)
        return None


def preset_variants(preset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Option sets a preset renders with: the series/movie options and, when it
    has season settings, those resolved on top."""
    from . import database as db
    base = preset.get("options") or {}
    variants = [base]
    season = preset.get("season_options") or {}
    if season:
        variants.append(db.resolve_season_options(base, season))
    return variants


def refresh_preset(template_id: str, preset_id: str) -> int:
    """Generate the preset's caches from what's stored, and remove ones it no
    longer uses (older settings, the old unhashed file). Returns files made or kept."""
    from . import database as db
    preset = db.get_preset(template_id, preset_id)
    if not preset:
        remove_preset(template_id, preset_id)
        return 0
    keep: Set[str] = set()
    for opts in preset_variants(preset):
        path = ensure(template_id, preset_id, opts)
        if path:
            keep.add(path.name)
    _prune(template_id, preset_id, keep)
    return len(keep)


def remove_preset(template_id: str, preset_id: str) -> None:
    _prune(template_id, preset_id, set())


def _prune(template_id: str, preset_id: str, keep: Iterable[str]) -> None:
    keep = set(keep)
    d = overlay_dir(template_id)
    if not d.is_dir():
        return
    for f in d.iterdir():
        if not f.is_file() or f.name in keep:
            continue
        parsed = parse_name(f.stem)
        if f.stem == preset_id or (parsed and parsed[0] == preset_id):
            try:
                f.unlink()
            except OSError:
                pass


def warm_all() -> None:
    """Startup: make sure every preset has its caches, and drop leftovers from
    the old {preset_id}.png naming."""
    from . import database as db
    try:
        made = 0
        for template_id, tdata in (db.get_all_presets() or {}).items():
            for preset in (tdata or {}).get("presets", []):
                pid = preset.get("id")
                if not pid:
                    continue
                for opts in preset_variants(preset):
                    existed = cache_path(template_id, pid, opts).exists()
                    if ensure(template_id, pid, opts) and not existed:
                        made += 1
                legacy = overlay_dir(template_id) / f"{pid}.png"
                if legacy.exists():
                    try:
                        legacy.unlink()
                    except OSError:
                        pass
        if made:
            logger.info("[OVERLAY CACHE] Startup: generated %d overlay cache file(s)", made)
    except Exception as e:
        logger.warning("[OVERLAY CACHE] Startup warm-up failed: %s", e)


def is_orphan(template_id: str, stem: str, presets: Set[Tuple[str, str]]) -> bool:
    """For Cleanup: a file whose preset no longer exists, or an old-style name."""
    parsed = parse_name(stem)
    if not parsed:
        return True
    return (template_id, parsed[0]) not in presets
