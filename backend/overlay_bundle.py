"""
Pack overlay configs and the badge/image asset files they use into plain JSON
(files base64-embedded), and unpack them again.

Used by:
- preset export/import (backend/api/presets.py): a preset that uses overlay
  configs carries those configs and their assets with it, so it renders the
  same on another install.
- the full database backup (backend/api/database.py).
"""
import base64
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from . import database as db
from .config import settings, logger

# Preset option keys that hold overlay config ids.
OVERLAY_ID_LIST_KEYS = ("overlay_config_ids", "overlay_config_ids_below")
LEGACY_OVERLAY_ID_KEY = "overlay_config_id"


def _assets_dir() -> Path:
    d = Path(settings.CONFIG_DIR) / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def overlay_ids_in_options(options: Optional[Dict[str, Any]]) -> Set[str]:
    """Overlay config ids a preset's options refer to."""
    ids: Set[str] = set()
    if not isinstance(options, dict):
        return ids
    for key in OVERLAY_ID_LIST_KEYS:
        val = options.get(key)
        if isinstance(val, list):
            ids.update(str(v) for v in val if v)
    legacy = options.get(LEGACY_OVERLAY_ID_KEY) or options.get("overlayConfigId")
    if legacy:
        ids.add(str(legacy))
    return ids


def asset_ids_in_elements(elements: Iterable[Dict[str, Any]]) -> Set[str]:
    """Asset ids used by overlay elements (custom images and image-mode badges)."""
    ids: Set[str] = set()
    for el in elements or []:
        if not isinstance(el, dict):
            continue
        if el.get("asset_id"):
            ids.add(str(el["asset_id"]))
        badge_assets = el.get("badge_assets")
        if isinstance(badge_assets, dict):
            ids.update(str(v) for v in badge_assets.values() if v)
    return ids


def _asset_file(asset: Dict[str, Any]) -> Optional[Path]:
    rel = asset.get("file_path") or ""
    base = Path(settings.CONFIG_DIR).resolve()
    try:
        p = (base / rel).resolve()
        p.relative_to(base)
    except Exception:
        return None
    return p if p.is_file() else None


def pack_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    """Asset row plus its file as base64 (data is None when the file is missing)."""
    path = _asset_file(asset)
    data = base64.b64encode(path.read_bytes()).decode("ascii") if path else None
    return {
        "id": asset["id"],
        "name": asset.get("name"),
        "file_name": Path(asset.get("file_path") or "").name,
        "file_type": asset.get("file_type"),
        "width": asset.get("width"),
        "height": asset.get("height"),
        "data": data,
    }


def build_bundle(config_ids: Optional[Iterable[str]] = None, all_assets: bool = False) -> Dict[str, Any]:
    """
    Overlay configs (all when config_ids is None) and the assets they use.
    all_assets=True also includes assets no config uses (full backup).
    """
    if config_ids is None:
        configs = db.get_all_overlay_configs()
    else:
        configs = [c for c in (db.get_overlay_config(cid) for cid in sorted(set(config_ids))) if c]

    if all_assets:
        assets = db.get_all_overlay_assets()
    else:
        wanted: Set[str] = set()
        for c in configs:
            wanted |= asset_ids_in_elements(c.get("elements") or [])
        assets = [a for a in (db.get_overlay_asset(aid) for aid in sorted(wanted)) if a]

    return {
        "configs": [
            {
                "id": c["id"],
                "name": c.get("name"),
                "elements": c.get("elements") or [],
                "streaming_region": c.get("streaming_region") or "US",
            }
            for c in configs
        ],
        "assets": [pack_asset(a) for a in assets],
    }


def _safe_file_name(name: str, file_type: Optional[str]) -> str:
    stem = Path(name or "").stem or "asset"
    ext = Path(name or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = "." + (file_type or "png").lower().lstrip(".")
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
    stem = re.sub(r"[^\w\-]+", "-", stem).strip("-") or "asset"
    return f"{stem}{ext}"


def _write_asset_file(file_name: str, data: bytes, overwrite: bool) -> str:
    """Write an asset file into config/assets; returns the relative file_path."""
    d = _assets_dir()
    target = d / file_name
    if target.exists() and not overwrite and target.read_bytes() != data:
        stem, ext = target.stem, target.suffix
        n = 2
        while (d / f"{stem}-{n}{ext}").exists():
            if (d / f"{stem}-{n}{ext}").read_bytes() == data:
                return f"assets/{stem}-{n}{ext}"
            n += 1
        target = d / f"{stem}-{n}{ext}"
    if not target.exists() or overwrite or target.read_bytes() != data:
        target.write_bytes(data)
    return f"assets/{target.name}"


def restore_bundle(bundle: Optional[Dict[str, Any]], replace: bool = False) -> Dict[str, str]:
    """
    Recreate overlay configs and assets from a bundle.

    replace=False (preset import): keeps everything already there. An asset
    whose id already exists is reused. A config whose id exists with the same
    elements is reused; with different elements it's saved under a new id.
    Returns {old_config_id: new_config_id} for configs that got a new id.

    replace=True (database restore): deletes every existing overlay config and
    asset row first, then restores the bundle with its original ids.
    """
    remap: Dict[str, str] = {}
    if not isinstance(bundle, dict):
        return remap
    configs = bundle.get("configs") or []
    assets = bundle.get("assets") or []

    if replace:
        with db.get_db() as conn:
            conn.execute("DELETE FROM overlay_configs")
            conn.execute("DELETE FROM overlay_assets")

    for a in assets:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        aid = str(a["id"])
        if not replace:
            existing = db.get_overlay_asset(aid)
            if existing and _asset_file(existing):
                continue
        raw = a.get("data")
        if not raw:
            logger.warning("[OVERLAY_BUNDLE] Asset %s has no file data; skipped", aid)
            continue
        try:
            data = base64.b64decode(raw)
        except Exception:
            logger.warning("[OVERLAY_BUNDLE] Asset %s has invalid file data; skipped", aid)
            continue
        rel = _write_asset_file(_safe_file_name(a.get("file_name") or a.get("name") or aid, a.get("file_type")), data, overwrite=replace)
        db.save_overlay_asset(
            aid,
            a.get("name") or Path(rel).stem,
            rel,
            (a.get("file_type") or Path(rel).suffix.lstrip(".")),
            a.get("width"),
            a.get("height"),
        )

    for c in configs:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        cid = str(c["id"])
        elements = c.get("elements") or []
        new_id = cid
        if not replace:
            existing = db.get_overlay_config(cid)
            if existing:
                if json.dumps(existing.get("elements") or [], sort_keys=True) == json.dumps(elements, sort_keys=True):
                    continue
                new_id = f"overlay-{uuid.uuid4().hex[:12]}"
                remap[cid] = new_id
        db.save_overlay_config(new_id, c.get("name") or new_id, elements, c.get("streaming_region") or "US")

    logger.info(
        "[OVERLAY_BUNDLE] Restored %d overlay config(s), %d asset(s)%s",
        len(configs), len(assets), f", {len(remap)} renamed" if remap else "",
    )
    return remap


def remap_options(options: Dict[str, Any], remap: Dict[str, str]) -> Dict[str, Any]:
    """Point a preset's overlay config ids at their new ids."""
    if not remap or not isinstance(options, dict):
        return options
    out = dict(options)
    for key in OVERLAY_ID_LIST_KEYS:
        val = out.get(key)
        if isinstance(val, list):
            out[key] = [remap.get(str(v), v) for v in val]
    for key in (LEGACY_OVERLAY_ID_KEY, "overlayConfigId"):
        if out.get(key) in remap:
            out[key] = remap[out[key]]
    return out


def bundle_for_presets(preset_entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Bundle for the overlay configs a list of preset entries uses, or None."""
    ids: Set[str] = set()
    for p in preset_entries:
        ids |= overlay_ids_in_options(p.get("options"))
        ids |= overlay_ids_in_options(p.get("season_options"))
    if not ids:
        return None
    bundle = build_bundle(ids)
    return bundle if bundle["configs"] else None
