"""
Single source of truth for turning a save-location template + render context into a
final, sanitized, traversal-checked filesystem path.

Consolidates logic that used to be duplicated (and had drifted) across
api/save.py, api/batch.py (two separate call sites), and api/movies.py's
local-assets handlers:
- TV season/series naming was baked into the {title} token, which broke ordering
  when combined with literal text like " ({year})" after it.
- One batch.py call site had no /output|/config root remap or traversal check.
- local-assets browsed a stale legacy settings field even when the newer
  per-media-type fields were set.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import settings

DEFAULT_MOVIE_SAVE_LOCATION = "/config/output/{library}/{title}.jpg"
DEFAULT_TV_SAVE_LOCATION = "/config/output/{library}/{title} ({year}).jpg"

# Kept only as the legacy field's default value (for the one-time migration in
# ui_settings.py) and as a last-resort fallback; no longer exposed in the UI.
DEFAULT_SAVE_TEMPLATE = DEFAULT_MOVIE_SAVE_LOCATION


class PathTraversalError(ValueError):
    """Raised when a resolved save path would escape the allowed output/config roots."""


@dataclass
class SaveContext:
    media_type: str                     # "movie" | "tv-show"
    title: str
    year: Optional[int] = None
    rating_key: Optional[str] = None
    library_label: Optional[str] = None
    season: Optional[int] = None        # None => movie, or TV series-level poster
    filename_override: Optional[str] = None  # used only when the template has no file suffix
    folder_name: Optional[str] = None   # real on-disk folder name (from Plex), movies only

    @property
    def is_tv(self) -> bool:
        return self.media_type == "tv-show"


def resolve_library_label(library_id: Optional[str]) -> str:
    """Return a human-friendly library label (display name/title) given an id."""
    from . import database as db

    label: Optional[str] = None

    # Normalize incoming id so any accidental path-like strings are reduced to the last segment
    normalized_id = None
    if library_id:
        normalized_id = str(library_id).replace("\\", "/").rstrip("/")
        if "/" in normalized_id:
            normalized_id = normalized_id.split("/")[-1] or normalized_id
    lib_id = normalized_id or library_id

    try:
        ui_settings = db.get_ui_settings()
        plex_settings = ui_settings.get("plex", {}) if ui_settings else {}
        movie_mappings = plex_settings.get("libraryMappings", []) or []
        tv_mappings = plex_settings.get("tvShowLibraryMappings", []) or []
        all_mappings = movie_mappings + tv_mappings
    except Exception:
        all_mappings = []

    if not lib_id:
        if all_mappings:
            first = all_mappings[0]
            label = first.get("displayName") or first.get("title") or str(first.get("id") or "default")
        else:
            label = "default"
    else:
        for m in all_mappings:
            mid = str(m.get("id", ""))
            if mid == str(lib_id):
                label = m.get("displayName") or m.get("title") or mid
                break

    label = label or str(lib_id or "default")

    # If the label looks like a path (e.g., "config/output/Movies"), use only the trailing segment
    cleaned = label.replace("\\", "/").rstrip("/")
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1] or cleaned

    return cleaned


def get_save_template(media_type: str = "movie") -> str:
    """Read the save-location template for a media type from UI settings, with a
    DB -> settings.json -> legacy config.json -> hardcoded-default fallback chain."""
    field = "tvShowSaveLocation" if media_type == "tv-show" else "movieSaveLocation"
    default = DEFAULT_TV_SAVE_LOCATION if media_type == "tv-show" else DEFAULT_MOVIE_SAVE_LOCATION

    try:
        from . import database as db  # local import to avoid circular
        data = db.get_ui_settings()
        if data:
            tmpl = data.get(field) or data.get("saveLocation")
            if tmpl:
                return tmpl
    except Exception:
        pass

    settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
    legacy_file = Path(settings.CONFIG_DIR) / "ui_settings.json"
    for candidate_file in (settings_file, legacy_file):
        try:
            if candidate_file.exists():
                data = json.loads(candidate_file.read_text(encoding="utf-8"))
                return data.get(field) or data.get("saveLocation") or default
        except Exception:
            pass
    return default


def _get_tv_save_mode() -> str:
    try:
        from . import database as db
        ui_settings = db.get_ui_settings()
        if ui_settings:
            return ui_settings.get("tvShowSaveMode", "flat")
    except Exception:
        pass
    return "flat"


def _resolve_filename_token(ctx: SaveContext) -> str:
    """Kometa-spec bare filename stem (no extension): 'poster' for a movie or TV
    series-level poster, 'SeasonNN' (zero-padded, capital S) for a TV season poster."""
    if ctx.is_tv and ctx.season is not None:
        return f"Season{ctx.season:02d}"
    return "poster"


def apply_save_location_variables(template: str, ctx: SaveContext) -> str:
    """
    Substitute {library}/{title}/{folder}/{year}/{key}/{season}/{filename} in a
    save-location template.

    {folder} resolves to the real on-disk folder name Plex knows for this movie
    (independent of Plex's display-language title) -- falls back to {title} when
    unavailable (TV shows/seasons, or if Plex lookup failed). See
    config.get_movie_folder_name().

    Two modes, chosen purely by whether the template contains the literal "{filename}"
    (no stored/migrated flag needed — this is recomputed from the template string
    itself on every call):

    - Modern mode (template has {filename}): every token is an independent, literal
      substitution — {title} is never mutated. {filename} resolves to "poster" or
      "SeasonNN" per Kometa's asset-folder convention. This is what the built-in
      Flat/Asset-folders presets use.
    - Legacy mode (template has no {filename}): byte-identical to this function's
      original behavior — for TV, the season/series distinction is baked directly
      into the {title} substitution (" - series"/"/series", " - s01"/"/s01"),
      controlled by the tvShowSaveMode setting. Every template stored before this
      module existed has no {filename} token, so upgrading changes nothing for
      existing users unless they opt into a new preset.
    """
    result = template.replace("{library}", ctx.library_label or "")
    result = result.replace("{year}", str(ctx.year) if ctx.year else "")
    result = result.replace("{key}", ctx.rating_key or "")
    result = result.replace("{folder}", ctx.folder_name or ctx.title)

    if "{filename}" in result:
        result = result.replace("{filename}", _resolve_filename_token(ctx))
        result = result.replace("{title}", ctx.title)
        result = result.replace("{season}", f"s{ctx.season:02d}" if (ctx.is_tv and ctx.season is not None) else "")
    elif ctx.is_tv:
        tv_save_mode = _get_tv_save_mode()
        if ctx.season is not None:
            season_str = f"s{ctx.season:02d}"
            suffix = f"{ctx.title}/{season_str}" if tv_save_mode == "nested" else f"{ctx.title} - {season_str}"
            result = result.replace("{title}", suffix)
            result = result.replace("{season}", season_str)
        else:
            suffix = f"{ctx.title}/series" if tv_save_mode == "nested" else f"{ctx.title} - series"
            result = result.replace("{title}", suffix)
            result = result.replace("{season}", "")
    else:
        result = result.replace("{title}", ctx.title)
        result = result.replace("{season}", f"s{ctx.season:02d}" if ctx.season else "")

    # Clean up double slashes / whitespace / empty-variable punctuation artifacts
    result = result.replace("//", "/")
    result = " ".join(result.split())
    result = re.sub(r'\s*[-_]\s*\.', '.', result)      # " - ." or " _ ." -> "."
    result = re.sub(r'\s*\(\s*\)', '', result)          # " ()" or "()" -> ""
    result = re.sub(r'\s*\[\s*\]', '', result)          # " []" or "[]" -> ""
    result = re.sub(r'\s{2,}', ' ', result)
    return result


def _sanitize(save_path: str) -> str:
    """Remove only characters that are genuinely illegal in Windows/Linux filenames.
    Keeps everything else (including punctuation like , ' : & ! that commonly appear
    in real movie titles) -- the previous whitelist silently stripped these, causing
    generated folder names to drift from the real on-disk names Radarr/Kometa use
    (e.g. "Lock, Stock..." became "Lock Stock...", "L'Écume" lost its apostrophe)."""
    illegal = '<>:"|?*\0'
    safe = "".join(c for c in save_path if c not in illegal and ord(c) >= 32)
    return safe.strip()


def _remap_root(base_dir: Path) -> Path:
    """Map the literal /output and /config prefixes (and their relative equivalents)
    baked into the default templates onto the actually-configured OUTPUT_ROOT/CONFIG_DIR."""
    base_dir_str = str(base_dir).replace("\\", "/")

    if base_dir.is_absolute() and base_dir_str.startswith("/output"):
        tail = base_dir_str[len("/output"):].lstrip("/")
        return Path(settings.OUTPUT_ROOT) / tail if tail else Path(settings.OUTPUT_ROOT)

    if base_dir.is_absolute() and base_dir_str.startswith("/config"):
        tail = base_dir_str[len("/config"):].lstrip("/")
        return Path(settings.CONFIG_DIR) / tail if tail else Path(settings.CONFIG_DIR)

    if not base_dir.is_absolute():
        lower = base_dir_str.lower()
        if lower.startswith("config/"):
            tail = base_dir_str.split("/", 1)[1] if "/" in base_dir_str else ""
            return Path(settings.CONFIG_DIR) / tail
        if lower.startswith("output/"):
            tail = base_dir_str.split("/", 1)[1] if "/" in base_dir_str else ""
            return Path(settings.OUTPUT_ROOT) / tail
        return Path(settings.OUTPUT_ROOT) / base_dir_str.lstrip("/\\")

    return base_dir


def make_batch_subfolder_name() -> str:
    """One timestamp per batch run — call this once at the top of a batch endpoint and
    thread the result through every item so the whole run lands in the same folder."""
    return f"batch-{datetime.now():%Y-%m-%d-%H%M%S}"


def resolve_save_path(
    ctx: SaveContext,
    output_ext: str,
    batch_subfolder: Optional[str] = None,
) -> Path:
    """
    Single canonical entry point: template lookup -> variable substitution ->
    sanitization -> /output|/config root remap -> optional batch subfolder ->
    traversal-safety check -> final absolute Path.

    Does not create the directory or write the file — callers do that with the
    returned path. Raises PathTraversalError if the resolved path escapes the
    configured OUTPUT_ROOT/CONFIG_DIR roots.
    """
    template = get_save_template(ctx.media_type)
    substituted = apply_save_location_variables(template, ctx)
    safe_path = _sanitize(substituted)

    candidate = Path(safe_path)
    if candidate.suffix:
        base_dir = candidate.parent
        filename = f"{Path(candidate.name).stem}{output_ext}"
    else:
        base_dir = candidate
        stem = ctx.filename_override or "poster"
        filename = f"{Path(stem).stem}{output_ext}"

    base_dir = _remap_root(base_dir)

    if batch_subfolder:
        try:
            rel = base_dir.relative_to(settings.OUTPUT_ROOT)
            base_dir = Path(settings.OUTPUT_ROOT) / batch_subfolder / rel
        except ValueError:
            base_dir = Path(settings.OUTPUT_ROOT) / batch_subfolder / base_dir.name

    allowed_roots = [Path(settings.OUTPUT_ROOT).resolve(), Path(settings.CONFIG_DIR).resolve()]
    out_path = (base_dir / filename).resolve()
    if not any(out_path.is_relative_to(root) for root in allowed_roots):
        raise PathTraversalError(f"Resolved save path is outside the allowed output directories: {out_path}")

    return out_path


def resolve_save_root(media_type: str) -> Path:
    """Just the browsable root a media type's template resolves under (everything
    before the first '{'), for the local-assets list/serve/delete handlers, which
    don't have a single item's context to fully resolve a path."""
    template = get_save_template(media_type)
    base_path = template.split("{")[0].rstrip("/")
    return _remap_root(Path(base_path) if base_path else Path("/output")).resolve()


# ---------------------------------------------------------------------------
# "Save to asset folder on send" — makes the resend cache optionally live in the
# user's visible asset folder instead of (or as well as) the hidden internal cache.
# ---------------------------------------------------------------------------

def save_to_asset_folder_on_send_enabled() -> bool:
    try:
        from . import database as db
        ui_settings = db.get_ui_settings()
        return bool(ui_settings.get("saveToAssetFolderOnSend", False)) if ui_settings else False
    except Exception:
        return False


def save_or_cache_render(rating_key: str, img_bytes: bytes, ctx: Optional[SaveContext]) -> Path:
    """
    Persist a just-uploaded render so it can be resent later.

    When "save to asset folder on send" is enabled and enough context is available
    (ctx is not None), writes straight to the resolved asset-folder path — that file
    becomes the resend source, no separate hidden copy. Otherwise (setting off, or a
    caller that doesn't have full context to build ctx), falls back to the original
    hidden internal cache so resend keeps working exactly as before.
    """
    from .config import save_render_cache, _render_cache_path, logger

    if ctx is not None and save_to_asset_folder_on_send_enabled():
        try:
            out_path = resolve_save_path(ctx, ".jpg")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(img_bytes)
            return out_path
        except Exception as e:
            logger.warning(
                "[RENDER_CACHE] Failed to save to asset folder for %s, falling back to hidden cache: %s",
                rating_key, e,
            )

    save_render_cache(rating_key, img_bytes)
    return _render_cache_path(rating_key)


def load_cached_render(rating_key: str, ctx: Optional[SaveContext] = None) -> Optional[bytes]:
    """
    Load previously saved render bytes for resend, checking whichever location is
    currently authoritative: the resolved asset-folder path (if the setting is on and
    ctx is available), falling back to the hidden internal cache.
    """
    from .config import load_render_cache

    if ctx is not None and save_to_asset_folder_on_send_enabled():
        try:
            out_path = resolve_save_path(ctx, ".jpg")
            if out_path.exists():
                return out_path.read_bytes()
        except Exception:
            pass

    return load_render_cache(rating_key)
