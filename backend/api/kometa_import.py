# backend/api/kometa_import.py
"""Import Kometa overlay files as overlay configs (Overlay Manager → Import Kometa).

One request carries the overlay YAML files plus any images/fonts they use
(loose files, a folder, or a zip). dry_run=true returns the report only;
dry_run=false also saves the configs, images (as overlay assets) and fonts.
See backend/kometa_import.py for the expansion and mapping.
"""
import hashlib
import json
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import database as db
from .. import kometa_import as ki
from ..config import logger, settings
from ..schemas import OverlayElement
from .overlay_config import _get_overlay_assets_dir, _sanitize_filename, api_list_fonts

router = APIRouter()


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _font_dir() -> Path:
    d = Path(settings.CONFIG_DIR) / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d


class _AssetSaver:
    """Saves matched images as overlay assets once per file, reusing an existing
    asset with the same file name and identical bytes (re-imports)."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.by_hash: Dict[str, str] = {}
        self.saved = 0
        self.reused = 0
        self.existing = {a["file_path"]: a["id"] for a in db.get_all_overlay_assets()} if not dry_run else {}

    def save(self, upload_path: str, content: bytes) -> Optional[str]:
        digest = hashlib.sha256(content).hexdigest()
        if digest in self.by_hash:
            return self.by_hash[digest]
        if self.dry_run:
            self.by_hash[digest] = f"dry-{digest[:8]}"
            return self.by_hash[digest]
        from PIL import Image
        import io
        try:
            with Image.open(io.BytesIO(content)) as img:
                width, height = img.size
        except Exception:
            return None
        name = PurePosixPath(upload_path).stem
        ext = PurePosixPath(upload_path).suffix.lower() or ".png"
        assets_dir = _get_overlay_assets_dir()
        base = _sanitize_filename(name)
        n = 1
        while True:
            filename = f"{base}{ext}" if n == 1 else f"{base}-{n}{ext}"
            path = assets_dir / filename
            rel = f"assets/{filename}"
            if not path.exists():
                path.write_bytes(content)
                asset_id = str(uuid.uuid4())
                db.save_overlay_asset(asset_id, name, rel, ext[1:], width, height)
                self.saved += 1
                break
            if path.read_bytes() == content:
                asset_id = self.existing.get(rel)
                if not asset_id:
                    asset_id = str(uuid.uuid4())
                    db.save_overlay_asset(asset_id, name, rel, ext[1:], width, height)
                    self.saved += 1
                else:
                    self.reused += 1
                break
            n += 1
        self.by_hash[digest] = asset_id
        return asset_id


_MAX_REMOTE_IMAGE_BYTES = 15 * 1024 * 1024
_remote_cache: Dict[str, Optional[Tuple[str, bytes]]] = {}


def download_remote_image(url: str) -> Optional[Tuple[str, bytes]]:
    """(file name, bytes) of an image an overlay links to, or None. Public URLs
    only (same SSRF guard as the badge proxy); one download per URL per import."""
    if url in _remote_cache:
        return _remote_cache[url]
    result = None
    try:
        import requests
        from urllib.parse import urlparse, unquote
        from ..middleware.validation import assert_external_fetch_safe
        from ..config import EXTERNAL_IMAGE_FETCH_HEADERS
        assert_external_fetch_safe(url)
        r = requests.get(url, headers=EXTERNAL_IMAGE_FETCH_HEADERS, timeout=20, stream=True)
        r.raise_for_status()
        content = r.raw.read(_MAX_REMOTE_IMAGE_BYTES + 1, decode_content=True)
        if len(content) > _MAX_REMOTE_IMAGE_BYTES:
            raise ValueError("larger than 15 MB")
        from PIL import Image
        import io
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
        name = PurePosixPath(unquote(urlparse(url).path)).name or "image.png"
        if not PurePosixPath(name).suffix:
            name += ".png"
        result = (name, content)
    except Exception as e:
        logger.warning("[KOMETA IMPORT] Couldn't download %s: %s", url, e)
    _remote_cache[url] = result
    return result


def finalize_elements(
    elements: List[Dict[str, Any]],
    report: List[Dict[str, Any]],
    find_image,
    find_font,
    saver: "_AssetSaver",
    dry_run: bool,
    available_fonts: set,
    saved_font_names: Dict[str, str],
    missing_images: Dict[str, List[str]],
):
    """Attach images and fonts to mapped elements and validate them. find_image /
    find_font(wanted_path) return (name, bytes) or None. Shared by the upload
    import and live Kometa files. Returns (elements, fonts written)."""
    fonts_saved = 0
    entries = {e["name"]: e for e in report}
    final_elements: List[Dict[str, Any]] = []
    for element in elements:
        entry = entries.get(element["name"], {"messages": []})
        # Image
        wanted = entry.get("image")
        if wanted:
            found = find_image(wanted)
            entry["image_match"] = found[0] if found else None
            if found:
                match, content = found
                asset_id = saver.save(match, content)
                if asset_id and not dry_run:
                    element["asset_id"] = asset_id
                scale_px = entry.pop("scale_px", None)
                if scale_px and (scale_px.get("width") or scale_px.get("height")):
                    try:
                        from PIL import Image
                        import io
                        with Image.open(io.BytesIO(content)) as img:
                            w, h = img.size
                        element["scale"] = (scale_px["width"] / w) if scale_px.get("width") else (scale_px["height"] / h)
                    except Exception:
                        pass
            else:
                missing_images.setdefault(wanted, []).append(element["name"])
                entry["messages"].append(f"image {PurePosixPath(wanted).name} wasn't found")
                if entry.get("status") == "ok":
                    entry["status"] = "warning"
        # Image the overlay links to (url, git, Kometa default): download it into the
        # image library so it's listed in the editor and doesn't depend on the link.
        remote = element.get("url")
        if remote and not element.get("asset_id"):
            name = PurePosixPath(str(remote).split("?")[0]).name or "image"
            if dry_run:
                entry["messages"].append(f"image {name} will be downloaded from its link")
            else:
                got = download_remote_image(str(remote))
                asset_id = saver.save(got[0], got[1]) if got else None
                if asset_id:
                    element["asset_id"] = asset_id
                    entry["messages"].append(f"downloaded image {got[0]}")
                else:
                    entry["messages"].append(f"couldn't download {name}; the layer keeps the link and fetches it when rendering")
                    if entry.get("status") == "ok":
                        entry["status"] = "warning"
        # Font
        font = entry.get("font")
        if font:
            family = element.get("font_family") or ""
            found = find_font(font)
            if found:
                fname = PurePosixPath(found[0]).name
                if not dry_run and fname not in saved_font_names:
                    target = _font_dir() / fname
                    content = found[1]
                    if not target.exists() or target.read_bytes() != content:
                        target.write_bytes(content)
                        fonts_saved += 1
                    saved_font_names[fname] = PurePosixPath(fname).stem
                element["font_family"] = PurePosixPath(fname).stem
            elif family.lower() not in available_fonts:
                entry["messages"].append(f"font {PurePosixPath(str(font)).name} not found; upload it or the default font is used")
                if entry.get("status") == "ok":
                    entry["status"] = "warning"
        try:
            final_elements.append(OverlayElement(**element).model_dump(exclude_none=True))
        except Exception as e:
            entry["status"] = "skipped"
            entry["messages"].append(f"invalid element: {e}")
    return final_elements, fonts_saved


@router.post("/overlay-configs/kometa-import")
async def api_kometa_import(
    files: List[UploadFile] = File(...),
    library_type: str = Form("movie"),
    dry_run: bool = Form(True),
    names: str = Form("{}"),
    selected: str = Form(""),
    overwrite: bool = Form(True),
):
    library_type = "show" if str(library_type).lower() in ("show", "tv", "tv-show") else "movie"
    try:
        name_map: Dict[str, str] = json.loads(names or "{}") or {}
        selected_list: Optional[List[str]] = json.loads(selected) if selected else None
    except json.JSONDecodeError:
        raise HTTPException(400, "Bad names/selected value")

    uploads = []
    for f in files:
        uploads.append((f.filename or "file", await f.read()))
    try:
        bundle = ki.collect_uploads(uploads)
    except ki.ImportError_ as e:
        raise HTTPException(400, str(e))
    if not bundle["yaml"]:
        raise HTTPException(400, "No .yml files found in the upload")

    yaml_texts = {path: _decode(content) for path, content in bundle["yaml"].items()}
    _remote_cache.clear()
    available_fonts = {f.lower() for f in api_list_fonts().get("fonts", [])}
    saver = _AssetSaver(dry_run)
    existing_configs = {c["name"]: c["id"] for c in db.get_all_overlay_configs()} if overwrite else {}

    fonts_saved = 0
    saved_font_names: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []
    missing_images: Dict[str, List[str]] = {}

    for path, text in sorted(yaml_texts.items()):
        stem = PurePosixPath(path).stem
        item: Dict[str, Any] = {"path": path, "kind": "overlays", "messages": []}
        try:
            data = ki._load_yaml(text)
        except ki.ImportError_ as e:
            item.update(kind="error", error=str(e))
            results.append(item)
            continue
        if not data.get("overlays"):
            item.update(kind="templates" if data.get("templates") else "other")
            results.append(item)
            continue
        if selected_list is not None and path not in selected_list:
            item.update(kind="excluded")
            results.append(item)
            continue

        try:
            elements, report, file_messages = ki.expand_file(text, library_type, yaml_texts)
        except ki.ImportError_ as e:
            item.update(kind="error", error=str(e))
            results.append(item)
            continue
        item["messages"].extend(file_messages)

        def _find_upload(kind: str):
            def find(wanted: str):
                match = ki.match_upload(wanted, bundle[kind])
                return (match, bundle[kind][match]) if match else None
            return find

        final_elements, added_fonts = finalize_elements(
            elements, report, _find_upload("image"), _find_upload("font"), saver, dry_run,
            available_fonts, saved_font_names, missing_images,
        )
        fonts_saved += added_fonts

        config_name = (name_map.get(path) or stem).strip() or stem
        config_id = existing_configs.get(config_name) or f"overlay-kometa-{uuid.uuid4().hex[:10]}"
        item.update(
            config_name=config_name,
            config_id=config_id,
            replaces_existing=config_name in existing_configs,
            element_count=len(final_elements),
            overlays=report,
            counts={s: sum(1 for r in report if r["status"] == s) for s in ("ok", "warning", "hidden", "skipped")},
        )
        if not dry_run and final_elements:
            db.save_overlay_config(config_id, config_name, final_elements)
            logger.info("[KOMETA IMPORT] Saved %s (%d elements) as %s", path, len(final_elements), config_id)
        results.append(item)

    return {
        "dry_run": dry_run,
        "library_type": library_type,
        "files": results,
        "uploaded": {k: len(v) for k, v in bundle.items()},
        "missing_images": [{"path": p, "used_by": sorted(set(v))} for p, v in sorted(missing_images.items())],
        "assets_saved": saver.saved,
        "assets_reused": saver.reused,
        "fonts_saved": fonts_saved,
    }
