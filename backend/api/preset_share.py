"""Sharing presets as a file (Template Manager -> Share).

A share is the same JSON the preset export produces (backend/api/presets.py),
with overlays optional. Without overlays, or with overlays that use no image
or font files, it's a .json file. When files are needed it's a .zip:

    presets.json   the export; each overlay image has "zip_path" instead of
                   base64 "data", and "_font_files" lists the fonts
    assets/...     overlay images
    fonts/...      fonts from config/fonts the presets/overlays use and that
                   Simposter can't download by itself

/presets/import-file takes either file and hands the JSON to the normal
preset import, so overlays are reused/renamed the same way (overlay_bundle).
"""
import base64
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..config import logger, settings
from .. import database as db
from .presets import _compact_export, _full_export, _selected_presets, api_presets_import

router = APIRouter()

_FONT_EXTS = (".ttf", ".otf", ".ttc")
_OVERLAY_KEYS = ("overlay_config_ids", "overlay_config_ids_below", "overlay_config_id")
_MAX_UPLOAD = 200 * 1024 * 1024
_MAX_ENTRY = 50 * 1024 * 1024


def _keys(req: dict) -> List[dict]:
    keys = req.get("keys")
    if not keys and req.get("template_id") and req.get("preset_id"):
        keys = [{"template_id": req["template_id"], "preset_id": req["preset_id"]}]
    if not keys:
        raise HTTPException(400, "Pick at least one preset")
    return keys


def _strip_overlays(export: dict) -> dict:
    export.pop("_overlays", None)
    for key, tdata in export.items():
        if str(key).startswith("_") or not isinstance(tdata, dict):
            continue
        for preset in tdata.get("presets") or []:
            for opts_key in ("options", "season_options"):
                opts = preset.get(opts_key)
                if isinstance(opts, dict):
                    for k in _OVERLAY_KEYS:
                        opts.pop(k, None)
    return export


def _font_names(export: dict) -> Set[str]:
    names: Set[str] = set()
    for key, tdata in export.items():
        if str(key).startswith("_") or not isinstance(tdata, dict):
            continue
        for preset in tdata.get("presets") or []:
            for opts_key in ("options", "season_options"):
                font = (preset.get(opts_key) or {}).get("font_family")
                if isinstance(font, str) and font.strip():
                    names.add(font.strip())
    for cfg in (export.get("_overlays") or {}).get("configs") or []:
        for el in cfg.get("elements") or []:
            for k in ("font_family", "font_path"):
                v = el.get(k) if isinstance(el, dict) else None
                if isinstance(v, str) and v.strip():
                    names.add(Path(v.strip().replace("\\", "/")).stem)
    return names


def _font_files(names: Set[str]) -> List[Path]:
    """Font files in config/fonts for these names, skipping fonts the other
    install can download itself (Simposter's font set, Kometa's fonts)."""
    from ..templates.universal import _asset_font_entry, _KOMETA_REMOTE_FONTS, _KOMETA_REPO_FONTS, _normalize_font_token
    folder = Path(settings.CONFIG_DIR) / "fonts"
    if not folder.is_dir():
        return []
    by_stem = {f.stem.lower(): f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in _FONT_EXTS}
    out = []
    for name in sorted(names):
        path = by_stem.get(name.lower())
        if not path:
            continue
        token = _normalize_font_token(name)
        try:
            downloadable = bool(_asset_font_entry(name)) or token in _KOMETA_REMOTE_FONTS or token in _KOMETA_REPO_FONTS
        except Exception:
            downloadable = False
        if not downloadable:
            out.append(path)
    return out


def _build(req: dict) -> Dict[str, Any]:
    data = _selected_presets(_keys(req))
    if not data:
        raise HTTPException(404, "Preset not found")
    export = _compact_export(data) if req.get("compact", True) else _full_export(data)
    if not req.get("include_overlays", True):
        export = _strip_overlays(export)
    fonts = _font_files(_font_names(export))
    assets = [a for a in (export.get("_overlays") or {}).get("assets") or [] if a.get("data")]
    return {"export": export, "fonts": fonts, "assets": assets, "data": data}


def _share_name(data: dict) -> str:
    names = [p.get("name") or p.get("id") for t in data.values() for p in t.get("presets", [])]
    base = names[0] if len(names) == 1 else f"{len(names)}-presets"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(base)).strip("-") or "presets"


@router.post("/presets/share-info")
def api_preset_share_info(req: dict = Body(...)):
    """What a share of these presets would contain, for the Share dialog."""
    with_overlays = _build({**req, "include_overlays": True})
    overlays = [{"id": c["id"], "name": c.get("name") or c["id"]}
                for c in (with_overlays["export"].get("_overlays") or {}).get("configs") or []]
    fonts_without = _font_files(_font_names(_strip_overlays(json.loads(json.dumps(with_overlays["export"])))))
    return {
        "overlays": overlays,
        "images": len(with_overlays["assets"]),
        "fonts": [f.stem for f in with_overlays["fonts"]],
        "fonts_without_overlays": [f.stem for f in fonts_without],
    }


@router.post("/presets/share")
def api_preset_share(req: dict = Body(...)):
    """Download presets as .json, or .zip when overlay images/fonts go with them.
    Body: {template_id, preset_id} or {keys: [...]}, include_overlays (default
    true), compact (default true)."""
    built = _build(req)
    export, fonts, assets = built["export"], built["fonts"], built["assets"]
    name = _share_name(built["data"])
    if not fonts and not assets:
        body = json.dumps(export, indent=2)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="simposter-{name}.json"'})

    buf = io.BytesIO()
    used: Set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset in assets:
            file_name = re.sub(r"[^A-Za-z0-9._-]+", "_", asset.get("file_name") or f"{asset['id']}.png")
            zip_path = f"assets/{file_name}"
            if zip_path in used:
                zip_path = f"assets/{asset['id']}-{file_name}"
            used.add(zip_path)
            zf.writestr(zip_path, base64.b64decode(asset.pop("data")))
            asset["zip_path"] = zip_path
        export["_font_files"] = []
        for font in fonts:
            zf.write(font, f"fonts/{font.name}")
            export["_font_files"].append({"name": font.stem, "file": f"fonts/{font.name}"})
        zf.writestr("presets.json", json.dumps(export, indent=2))
    logger.info("[PRESETS] Shared %s as zip: %d image(s), %d font(s)", name, len(assets), len(fonts))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="simposter-{name}.zip"'})


def _read_zip(raw: bytes) -> Dict[str, Any]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Not a valid zip file")
    entries = {i.filename: i for i in zf.infolist()}

    def read(name: str) -> Optional[bytes]:
        info = entries.get(name)
        if not info or info.is_dir() or info.file_size > _MAX_ENTRY:
            return None
        return zf.read(info)

    raw_json = read("presets.json")
    if raw_json is None:
        raise HTTPException(400, "This zip has no presets.json")
    try:
        payload = json.loads(raw_json.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "presets.json isn't valid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(400, "presets.json isn't a preset export")

    for asset in (payload.get("_overlays") or {}).get("assets") or []:
        if isinstance(asset, dict) and asset.get("zip_path") and not asset.get("data"):
            data = read(str(asset.pop("zip_path")))
            asset["data"] = base64.b64encode(data).decode("ascii") if data else None

    fonts_saved = 0
    folder = Path(settings.CONFIG_DIR) / "fonts"
    for font in payload.pop("_font_files", None) or []:
        file_name = Path(str((font or {}).get("file") or "")).name
        if not file_name or Path(file_name).suffix.lower() not in _FONT_EXTS:
            continue
        data = read(f"fonts/{file_name}")
        if not data:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / file_name
        if target.exists():
            continue  # a font of that name is already here: keep it
        target.write_bytes(data)
        fonts_saved += 1
    payload["_fonts_saved"] = fonts_saved
    return payload


@router.post("/presets/import-file")
async def api_preset_import_file(file: UploadFile = File(...)):
    """Import a shared preset file: a .zip from Share, or a .json export."""
    raw = await file.read(_MAX_UPLOAD + 1)
    if len(raw) > _MAX_UPLOAD:
        raise HTTPException(413, "File is too large")
    if raw[:4] == b"PK\x03\x04":
        payload = _read_zip(raw)
    else:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            raise HTTPException(400, "Not a preset .json or .zip file")
        if not isinstance(payload, dict):
            raise HTTPException(400, "Not a preset export")
    fonts_saved = payload.pop("_fonts_saved", 0)
    result = await api_presets_import(payload)
    return {**result, "fonts_saved": fonts_saved}
