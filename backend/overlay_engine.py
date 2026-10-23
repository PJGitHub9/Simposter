"""Overlay engine v2: element selection and Kometa-style placement.

Step 1 of the Kometa overlay plan (ai_repo/simposter/kometa-overlay-config-plan.md).
Everything here is opt-in per element; an element without any of these keys
renders exactly as before.

Selection (select_elements):
  - conditions: [{"field", "op", "value"}], all must pass. Fields are read from
    the overlay metadata ("data context"); "filepath" checks every media file
    path a scan stored, "label" checks the item's labels.
  - group + weight: of the elements that passed, only the highest weight in each
    group renders (Kometa's group/weight).
  - suppress: names of elements to drop when this element renders (Kometa's
    suppress_overlays).

Placement (render_kometa_element), used when element["placement"] == "kometa":
  - horizontal_align / vertical_align + horizontal_offset / vertical_offset in
    Kometa's 1000x1500 coordinate space (ints, or "10%" strings), scaled to the
    real canvas at render time.
  - optional back box: back_color, back_width, back_height, back_radius,
    back_padding, back_align, back_line_color, back_line_width.
  - content: an uploaded asset (asset_id), an external image (url) or text with
    {variable} placeholders filled from the data context.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

KOMETA_W = 1000
KOMETA_H = 1500

_VAR_RE = re.compile(r"\{([A-Za-z0-9_.]+)\}")


# --------------------------------------------------------------------------
# Data context
# --------------------------------------------------------------------------

_RESOLUTION_ALIASES = {
    "4k": "4k", "2160": "4k", "2160p": "4k", "uhd": "4k",
    "1080": "1080p", "1080p": "1080p", "1080i": "1080p", "fhd": "1080p",
    "720": "720p", "720p": "720p", "hd": "720p",
    "576": "sd", "576p": "sd", "480": "sd", "480p": "sd", "sd": "sd",
}


def normalize_resolution(value: Any) -> Optional[str]:
    """Plex says "4k"/"1080"/"720"/"sd"; Jellyfin may say "2160p". Map both to
    one vocabulary: 4k, 1080p, 720p, sd."""
    if value is None:
        return None
    key = str(value).strip().lower()
    return _RESOLUTION_ALIASES.get(key, key or None)


_LIST_FIELDS = ("list", "lists", "mdblist_list")


def _rating_field_names() -> set:
    from .mdblist_client import RATING_FIELDS
    return set(RATING_FIELDS) | {"user_rating"}


def needed_data(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Which lazily-loaded data the elements use: stored file paths, MDBList
    ratings (conditions or text variables), and MDBList lists (conditions)."""
    rating_fields = _rating_field_names()
    needs = {"paths": False, "ratings": False, "lists": [], "ids": False, "added": False, "status": False}
    for element in elements:
        for cond in element.get("conditions") or []:
            if not isinstance(cond, dict):
                continue
            field = str(cond.get("field") or "").strip().lower()
            if field in ("filepath", "file_path", "filename"):
                needs["paths"] = True
            elif field in rating_fields:
                needs["ratings"] = True
            elif field in ("tmdb_id", "tvdb_id"):
                needs["ids"] = True
            elif field in ("days_since_added", "added"):
                needs["added"] = True
            elif field == "show_status":
                needs["status"] = True
            elif field in _LIST_FIELDS:
                for value in (cond.get("value") if isinstance(cond.get("value"), list) else [cond.get("value")]):
                    if value and str(value) not in needs["lists"]:
                        needs["lists"].append(str(value))
        text = element.get("text")
        if text:
            names = {m.group(1) for m in _VAR_RE.finditer(str(text))}
            if names & rating_fields:
                needs["ratings"] = True
            if "days_since_added" in names:
                needs["added"] = True
            if "show_status" in names:
                needs["status"] = True
    return needs


# TMDb show status -> the words Kometa's tvdb_status filter uses (plus canceled,
# which TMDb distinguishes from ended).
_SHOW_STATUS = {
    "returning series": "continuing", "ended": "ended", "canceled": "canceled", "cancelled": "canceled",
    "in production": "upcoming", "planned": "upcoming", "pilot": "upcoming",
}


def _is_tv(ctx: Dict[str, Any]) -> bool:
    return str(ctx.get("media_type") or "").lower() in ("tv", "show", "tv-show")


def _item_ids(ctx: Dict[str, Any]) -> Tuple[Optional[Any], Optional[Any], str]:
    media_type = "show" if str(ctx.get("media_type") or "").lower() in ("tv", "show", "tv-show") else "movie"
    tmdb_id, tvdb_id = ctx.get("tmdb_id"), ctx.get("tvdb_id")
    if not tmdb_id and ctx.get("rating_key"):
        try:
            from . import database as db
            tmdb_id, tvdb_id = db.get_ids_for_rating_key(str(ctx["rating_key"]))
        except Exception:
            pass
    return tmdb_id, tvdb_id, media_type


def build_context(meta: Dict[str, Any], needs_paths: bool = False,
                  elements: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Data context for conditions and text variables. Starts from the overlay
    metadata and adds derived fields. File paths, MDBList ratings and MDBList
    list membership are loaded only when the given elements use them (cached,
    so a render normally makes no API call)."""
    needs = needed_data(elements) if elements else {"paths": False, "ratings": False, "lists": []}
    needs.setdefault("added", False)
    needs.setdefault("status", False)
    needs_paths = needs_paths or needs["paths"]
    ctx = dict(meta or {})
    # Why data a rule needs is missing (shown in the render log by data_summary()).
    notes: Dict[str, str] = {}
    ctx["_notes"] = notes
    ctx["resolution"] = normalize_resolution(ctx.get("video_resolution"))
    if ctx.get("year") is None and ctx.get("movie_year") not in (None, ""):
        ctx["year"] = ctx.get("movie_year")
    if ctx.get("title") is None and ctx.get("movie_title"):
        ctx["title"] = ctx.get("movie_title")
    labels = ctx.get("labels") or []
    ctx["labels"] = [str(label) for label in labels]
    if needs_paths and "file_paths" not in ctx:
        paths: List[str] = []
        rating_key = ctx.get("rating_key")
        if rating_key:
            try:
                from . import database as db
                paths = db.get_file_paths(str(rating_key))
            except Exception:
                paths = []
        ctx["file_paths"] = paths
        if not paths:
            notes["filepath"] = "no file path stored yet, scan the library"
    if needs.get("ids") and (ctx.get("tmdb_id") in (None, "") or ctx.get("tvdb_id") in (None, "")) and ctx.get("rating_key"):
        try:
            from . import database as db
            cached_tmdb, cached_tvdb = db.get_ids_for_rating_key(str(ctx["rating_key"]))
            if ctx.get("tmdb_id") in (None, "") and cached_tmdb:
                ctx["tmdb_id"] = cached_tmdb
            if ctx.get("tvdb_id") in (None, "") and cached_tvdb:
                ctx["tvdb_id"] = cached_tvdb
        except Exception:
            pass
    if needs["added"] and ctx.get("days_since_added") in (None, ""):
        added_at = ctx.get("added_at") or ctx.get("addedAt")
        if not added_at and ctx.get("rating_key"):
            try:
                from . import database as db
                added_at = db.get_added_at_for_rating_key(str(ctx["rating_key"]))
            except Exception:
                added_at = None
        try:
            if added_at:
                import time
                ctx["days_since_added"] = max(0, int((time.time() - float(added_at)) // 86400))
        except (TypeError, ValueError):
            pass
        if ctx.get("days_since_added") in (None, ""):
            notes["days_since_added"] = "no date added stored yet, scan the library"
    if needs["status"] and ctx.get("show_status") in (None, ""):
        if not _is_tv(ctx):
            notes["show_status"] = "only TV shows have a status"
        else:
            tmdb_id, _tvdb, _mt = _item_ids(ctx)
            if not tmdb_id:
                notes["show_status"] = "this show has no TMDb ID"
            else:
                try:
                    from .tmdb_client import get_tv_show_details
                    raw = str(get_tv_show_details(int(tmdb_id)).get("status") or "").strip().lower()
                    if raw:
                        ctx["show_status"] = _SHOW_STATUS.get(raw, raw)
                    else:
                        notes["show_status"] = "TMDb has no status for this show"
                except Exception as e:
                    notes["show_status"] = f"TMDb lookup failed: {e}"
    if needs["ratings"] or needs["lists"]:
        tmdb_id, tvdb_id, media_type = _item_ids(ctx)
        try:
            from . import mdblist_client as mdb
            if not mdb.has_key():
                if needs["ratings"]:
                    notes["ratings"] = "no MDBList API key in Settings > General"
                if needs["lists"]:
                    notes["lists"] = "no MDBList API key in Settings > General"
            else:
                if needs["ratings"]:
                    if not tmdb_id and not tvdb_id:
                        notes["ratings"] = "this item has no TMDb/TVDB ID"
                    data = mdb.get_ratings(media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id) if (tmdb_id or tvdb_id) else None
                    fields = mdb.rating_fields(data or {})
                    for key, value in fields.items():
                        if ctx.get(key) in (None, ""):  # values from the media server win
                            ctx[key] = value
                    if (tmdb_id or tvdb_id) and not fields:
                        notes["ratings"] = "MDBList has no ratings for this item"
                if needs["lists"]:
                    ctx["lists"] = mdb.lists_containing(needs["lists"], media_type, tmdb_id) if tmdb_id else []
                    if not tmdb_id:
                        notes["lists"] = "this item has no TMDb ID"
        except Exception as e:  # never fail a render over ratings
            from .config import logger
            logger.debug("[OVERLAY] MDBList lookup failed: %s", e)
            notes.setdefault("ratings", f"MDBList lookup failed: {e}")
    return ctx


# --------------------------------------------------------------------------
# Conditions
# --------------------------------------------------------------------------

_NUMERIC_OPS = {"gt", "gte", "lt", "lte"}


def _as_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field_values(field: str, ctx: Dict[str, Any]) -> List[Any]:
    """Every value a field has for this item (most fields have one; filepath
    and label can have several)."""
    field = (field or "").strip().lower()
    if field in ("filepath", "file_path", "filename"):
        return list(ctx.get("file_paths") or [])
    if field in ("label", "labels"):
        return list(ctx.get("labels") or [])
    if field in _LIST_FIELDS:
        return list(ctx.get("lists") or [])
    value = ctx.get(field)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def check_condition(cond: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    """One condition. Unknown ops fail closed (the element doesn't render), so a
    typo never shows a badge on every poster."""
    op = str(cond.get("op") or "eq").strip().lower()
    target = cond.get("value")
    values = _field_values(str(cond.get("field") or ""), ctx)
    field = str(cond.get("field") or "").strip().lower()
    if field == "resolution":
        target = normalize_resolution(target) if not isinstance(target, list) else [normalize_resolution(t) for t in target]
    if field in _LIST_FIELDS:
        from .mdblist_client import normalize_list_url
        target = [normalize_list_url(t) or t for t in target] if isinstance(target, list) else (normalize_list_url(target) or target)

    if op == "exists":
        return bool(values)
    if op == "not_exists":
        return not values

    if op in ("regex", "not_regex"):
        # A list of patterns matches when any of them does (Kometa filter lists).
        try:
            patterns = [re.compile(str(t or "")) for t in (target if isinstance(target, list) else [target])]
        except re.error:
            return False
        hit = any(p.search(str(v)) for p in patterns for v in values)
        return hit if op == "regex" else not hit

    if op in _NUMERIC_OPS:
        threshold = _as_number(target)
        nums = [n for n in (_as_number(v) for v in values) if n is not None]
        if threshold is None or not nums:
            return False
        n = nums[0]
        return {"gt": n > threshold, "gte": n >= threshold, "lt": n < threshold, "lte": n <= threshold}[op]

    lowered = [str(v).strip().lower() for v in values]
    if op in ("in", "not_in"):
        if isinstance(target, (list, tuple)):
            options = list(target)
        else:
            options = str(target or "").split(",")  # "a, b" is a list too
        wanted = {str(t).strip().lower() for t in options if t is not None}
        hit = any(v in wanted for v in lowered)
        return hit if op == "in" else not hit
    if op in ("eq", "is", "contains"):
        want = str(target).strip().lower() if target is not None else ""
        return want in lowered if op != "contains" else any(want in v for v in lowered)
    if op in ("ne", "not", "not_contains"):
        want = str(target).strip().lower() if target is not None else ""
        return want not in lowered if op != "not_contains" else not any(want in v for v in lowered)
    return False


def conditions_pass(element: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    for cond in element.get("conditions") or []:
        if isinstance(cond, dict) and not check_condition(cond, ctx):
            return False
    return True


def _labels_pass(element: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    """The existing show_if_label/hide_if_label rule (case-insensitive)."""
    labels_lower = [label.lower() for label in ctx.get("labels") or []]
    show = element.get("show_if_label")
    hide = element.get("hide_if_label")
    if show and str(show).lower() not in labels_lower:
        return False
    if hide and str(hide).lower() in labels_lower:
        return False
    return True


def needs_file_paths(elements: List[Dict[str, Any]]) -> bool:
    for element in elements:
        for cond in element.get("conditions") or []:
            if isinstance(cond, dict) and str(cond.get("field") or "").lower() in ("filepath", "file_path", "filename"):
                return True
    return False


def select_elements(elements: List[Dict[str, Any]], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Which elements render for this item, in their original order.

    1. label rules and conditions
    2. group/weight: highest weight per group wins (ties keep the first)
    3. suppress: a rendering element removes the named elements
    """
    passing = [e for e in elements if _labels_pass(e, ctx) and conditions_pass(e, ctx)]

    winners: Dict[str, Tuple[float, int]] = {}
    for idx, element in enumerate(passing):
        group = element.get("group")
        if not group:
            continue
        weight = _as_number(element.get("weight")) or 0.0
        best = winners.get(group)
        if best is None or weight > best[0]:
            winners[group] = (weight, idx)
    kept = [
        e for idx, e in enumerate(passing)
        if not e.get("group") or winners.get(e["group"], (None, idx))[1] == idx
    ]

    suppressed = set()
    for element in kept:
        for name in element.get("suppress") or []:
            suppressed.add(str(name))
    if suppressed:
        kept = [e for e in kept if str(e.get("name") or "") not in suppressed]
    return kept


# --------------------------------------------------------------------------
# Text variables
# --------------------------------------------------------------------------

def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def fill_text(template: str, ctx: Dict[str, Any]) -> Optional[str]:
    """Replace {variable} placeholders. Returns None when a referenced variable
    is missing or blank, so the element is skipped rather than drawing an empty
    pill (Kometa's ignore_blank_results)."""
    missing = False

    def repl(match: "re.Match[str]") -> str:
        nonlocal missing
        key = match.group(1)
        if key in ("title", "movie_title"):
            value = ctx.get("movie_title") or ctx.get("title")
        elif key in ("year", "movie_year"):
            value = ctx.get("movie_year") or ctx.get("year")
        else:
            value = ctx.get(key)
        if value is None or str(value).strip() == "":
            missing = True
            return ""
        return _format_value(value)

    out = _VAR_RE.sub(repl, template or "")
    return None if missing else out


# --------------------------------------------------------------------------
# Kometa placement
# --------------------------------------------------------------------------

def _offset_px(value: Any, span: int, kometa_span: int) -> int:
    """Kometa offset (int pixels in 1000x1500 space, or "10%") -> canvas pixels."""
    if value is None:
        return 0
    text = str(value).strip()
    if text.endswith("%"):
        pct = _as_number(text[:-1]) or 0.0
        return int(round(span * pct / 100.0))
    num = _as_number(text) or 0.0
    return int(round(num * span / kometa_span))


def place_box(element: Dict[str, Any], W: int, H: int, bw: int, bh: int) -> Tuple[int, int]:
    """Top-left corner of a bw x bh box placed with Kometa's align + offset."""
    h_align = str(element.get("horizontal_align") or "left").lower()
    v_align = str(element.get("vertical_align") or "top").lower()
    hx = _offset_px(element.get("horizontal_offset"), W, KOMETA_W)
    vy = _offset_px(element.get("vertical_offset"), H, KOMETA_H)
    if h_align == "right":
        x = W - bw - hx
    elif h_align == "center":
        x = (W - bw) // 2 + hx
    else:
        x = hx
    if v_align == "bottom":
        y = H - bh - vy
    elif v_align == "center":
        y = (H - bh) // 2 + vy
    else:
        y = vy
    return x, y


def _scale(W: int, H: int) -> float:
    """Size multiplier from Kometa's 1000x1500 canvas (2.0 for 2000x3000)."""
    return min(W / KOMETA_W, H / KOMETA_H)


def _parse_color(value: Any, default: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """#RGB, #RRGGBB or #RRGGBBAA."""
    if not value:
        return default
    text = str(value).strip().lstrip("#")
    try:
        if len(text) == 3:
            r, g, b = (int(c * 2, 16) for c in text)
            return (r, g, b, 255)
        if len(text) == 6:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255)
        if len(text) == 8:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16))
    except ValueError:
        pass
    return default


def _load_element_font(element: Dict[str, Any], size: int):
    """A font file stored with the overlay assets (font_path, relative to the
    config dir), else the app's normal font lookup by family."""
    font_path = element.get("font_path")
    if font_path:
        try:
            from .config import settings
            path = Path(font_path)
            if not path.is_absolute():
                path = Path(settings.CONFIG_DIR) / path
            if path.exists():
                return _apply_font_style(ImageFont.truetype(str(path), size), element.get("font_style"))
        except Exception:
            pass
    from .templates.universal import _load_font
    weight = str(element.get("font_weight") or "700")
    return _apply_font_style(_load_font(element.get("font_family") or "arial", size, weight), element.get("font_style"))


def _apply_font_style(font, style: Any):
    """Pick a named style of a variable font (Kometa's font_style). A font with
    no such style, or no styles at all, is used as it is."""
    if not style or font is None:
        return font
    try:
        wanted = str(style).strip().lower()
        for name in font.get_variation_names():
            label = name.decode("utf-8", "ignore") if isinstance(name, bytes) else str(name)
            if label.strip().lower() == wanted:
                font.set_variation_by_name(name)
                break
    except Exception:
        pass  # not a variable font (or no FreeType variation support)
    return font


def _load_element_image(element: Dict[str, Any]) -> Optional[Image.Image]:
    from .config import settings
    asset_id = element.get("asset_id")
    if asset_id:
        try:
            from . import database as db
            asset = db.get_overlay_asset(asset_id)
            if asset:
                path = Path(settings.CONFIG_DIR) / asset["file_path"]
                if path.exists():
                    return Image.open(path).convert("RGBA")
        except Exception:
            return None
    url = element.get("url")
    if url:
        from .templates.universal import _fetch_url_badge_image
        img = _fetch_url_badge_image(str(url))
        return img.convert("RGBA") if img is not None else None
    return None


def _render_content(element: Dict[str, Any], ctx: Dict[str, Any], s: float) -> Optional[Image.Image]:
    """The element's content as a transparent RGBA image, sized for the canvas."""
    text_template = element.get("text")
    if text_template:
        text = fill_text(str(text_template), ctx)
        if not text:
            return None
        size = max(1, int(round((_as_number(element.get("font_size")) or 40) * s)))
        font = _load_element_font(element, size)
        stroke = int(round((_as_number(element.get("stroke_width")) or 0) * s))
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        left, top, right, bottom = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
        img = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)), (0, 0, 0, 0))
        ImageDraw.Draw(img).text(
            (-left, -top), text, font=font,
            fill=_parse_color(element.get("font_color"), (255, 255, 255, 255)),
            stroke_width=stroke,
            stroke_fill=_parse_color(element.get("stroke_color"), (0, 0, 0, 255)),
        )
        addon = _load_addon_image(element, s)
        return _with_addon(img, addon, element, s) if addon is not None else img

    img = _load_element_image(element)
    if img is None:
        return None
    mult = (_as_number(element.get("scale")) or 1.0) * s
    if abs(mult - 1.0) > 1e-6:
        img = img.resize((max(1, int(img.width * mult)), max(1, int(img.height * mult))), Image.LANCZOS)
    return img


def _load_addon_image(element: Dict[str, Any], s: float) -> Optional[Image.Image]:
    """The image drawn next to a text layer (Kometa's text addon), sized for the canvas."""
    if not (element.get("asset_id") or element.get("url")):
        return None
    img = _load_element_image(element)
    if img is None:
        return None
    mult = (_as_number(element.get("addon_scale")) or 1.0) * s
    if abs(mult - 1.0) > 1e-6:
        img = img.resize((max(1, int(img.width * mult)), max(1, int(img.height * mult))), Image.LANCZOS)
    return img


def _with_addon(text_img: Image.Image, addon: Image.Image, element: Dict[str, Any], s: float) -> Image.Image:
    """Text and its addon image in one box, laid out like Kometa's get_backdrop:
    left/right put them side by side (top-aligned), top/bottom stack them
    (the narrower one centered)."""
    off = int(round((_as_number(element.get("addon_offset")) or 0) * s))
    pos = str(element.get("addon_position") or "left").lower()
    tw, th = text_img.size
    iw, ih = addon.size
    if pos in ("left", "right"):
        bw, bh = tw + iw + off, max(th, ih)
        if pos == "left":
            tx, ty, ax, ay = iw + off, 0, 0, 0
        else:
            tx, ty, ax, ay = 0, 0, tw + off, 0
    else:
        bw, bh = max(tw, iw), th + ih + off
        tx, ax = (bw - tw) // 2, (bw - iw) // 2
        if pos == "top":
            ty, ay = ih + off, 0
        else:
            ty, ay = 0, th + off
    out = Image.new("RGBA", (max(1, bw), max(1, bh)), (0, 0, 0, 0))
    out.alpha_composite(addon, (ax, ay))
    out.alpha_composite(text_img, (tx, ty))
    return out


def blur_radius(elements: List[Dict[str, Any]], W: int, H: int) -> float:
    """The blur to apply for these selected layers: the largest one (Kometa uses
    the strongest blur(N) only), scaled from Kometa's 1000x1500 canvas."""
    amounts = [_as_number(e.get("blur_amount")) or 0 for e in elements if e.get("type") == "blur"]
    amount = max([a for a in amounts if a > 0], default=0)
    return amount * _scale(W, H) if amount else 0.0


def apply_blur(canvas: Image.Image, radius: float) -> Image.Image:
    if radius <= 0:
        return canvas
    from PIL import ImageFilter
    return canvas.filter(ImageFilter.GaussianBlur(radius))


def queue_placements(selected: List[Dict[str, Any]]) -> Dict[int, Optional[Dict[str, Any]]]:
    """Kometa queues: the selected layers of each queue, highest weight first,
    take the queue's positions in order. Returns {id(element): position} for
    queued layers; None means the queue ran out of positions (not drawn)."""
    queues: Dict[str, List[Tuple[float, int, Dict[str, Any]]]] = {}
    for idx, element in enumerate(selected):
        name = element.get("queue")
        if name and isinstance(element.get("queue_positions"), list):
            queues.setdefault(str(name), []).append((_as_number(element.get("weight")) or 0.0, idx, element))
    out: Dict[int, Optional[Dict[str, Any]]] = {}
    for members in queues.values():
        members.sort(key=lambda m: (-m[0], m[1]))
        for slot, (_, _, element) in enumerate(members):
            positions = element.get("queue_positions") or []
            pos = positions[slot] if slot < len(positions) and isinstance(positions[slot], dict) else None
            out[id(element)] = pos
    return out


def render_kometa_element(canvas: Image.Image, element: Dict[str, Any], ctx: Dict[str, Any]) -> Image.Image:
    """Draw one Kometa-placed element (back box + content) onto the canvas."""
    if canvas.mode != "RGBA":
        canvas = canvas.convert("RGBA")
    W, H = canvas.size
    s = _scale(W, H)

    if element.get("box_only"):
        # Kometa's "backdrop" overlay: just the box. A missing size fills the canvas.
        content = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        element = dict(element)
        element.setdefault("back_width", KOMETA_W)
        element.setdefault("back_height", KOMETA_H)
    else:
        content = _render_content(element, ctx, s)
    if content is None:
        return canvas

    pad = int(round((_as_number(element.get("back_padding")) or 0) * s))
    back_w = _as_number(element.get("back_width"))
    back_h = _as_number(element.get("back_height"))
    bw = int(round(back_w * s)) if back_w else content.width + pad * 2
    bh = int(round(back_h * s)) if back_h else content.height + pad * 2

    x, y = place_box(element, W, H, bw, bh)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))

    back_color = element.get("back_color")
    line_w = int(round((_as_number(element.get("back_line_width")) or 0) * s))
    if back_color or (line_w and element.get("back_line_color")):
        radius = int(round((_as_number(element.get("back_radius")) or 0) * s))
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle(
            [x, y, x + bw - 1, y + bh - 1],
            radius=radius,
            fill=_parse_color(back_color, (0, 0, 0, 0)) if back_color else None,
            outline=_parse_color(element.get("back_line_color"), (255, 255, 255, 255)) if line_w else None,
            width=line_w or 1,
        )

    # Content inside the box (Kometa's back_align); centered by default.
    align = str(element.get("back_align") or "center").lower()
    cx = x + (bw - content.width) // 2
    cy = y + (bh - content.height) // 2
    if "left" in align:
        cx = x + pad
    elif "right" in align:
        cx = x + bw - pad - content.width
    if "top" in align:
        cy = y + pad
    elif "bottom" in align:
        cy = y + bh - pad - content.height
    content_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    content_layer.paste(content, (cx, cy))  # clips at the canvas edge
    layer = Image.alpha_composite(layer, content_layer)
    return Image.alpha_composite(canvas, layer)


# --------------------------------------------------------------------------
# Plain-language explanations for the render log
# --------------------------------------------------------------------------

FIELD_LABELS = {
    "resolution": "Resolution", "video_resolution": "Resolution", "video_codec": "Video codec",
    "audio_codec": "Audio codec", "audio_channels": "Audio channels", "audio_language": "Audio language",
    "filepath": "File path", "file_path": "File path", "filename": "File path", "edition": "Edition",
    "label": "Label", "labels": "Label", "list": "MDBList list", "lists": "MDBList list", "mdblist_list": "MDBList list",
    "media_type": "Movie or show", "year": "Year", "title": "Title", "studio": "Studio",
    "streaming_platform": "Streaming platform", "tmdb_id": "TMDb ID", "tvdb_id": "TVDB ID",
    "audience_rating": "Audience rating", "critic_rating": "Critic rating", "mdb_rating": "MDBList score",
    "mdb_average_rating": "MDBList average", "mdb_imdb_rating": "IMDb rating", "mdb_tomatoes_rating": "Rotten Tomatoes",
    "mdb_tomatoesaudience_rating": "RT audience", "mdb_metacritic_rating": "Metacritic",
    "mdb_metacriticuser_rating": "Metacritic user score", "mdb_tmdb_rating": "TMDb rating",
    "mdb_trakt_rating": "Trakt rating", "mdb_letterboxd_rating": "Letterboxd rating",
    "mdb_myanimelist_rating": "MyAnimeList score",
    "days_since_added": "Days since added", "show_status": "Show status",
}
_OP_WORDS = {
    "eq": "is", "is": "is", "ne": "is not", "not": "is not", "in": "is one of", "not_in": "is none of",
    "contains": "contains", "not_contains": "doesn't contain", "regex": "matches", "not_regex": "doesn't match",
    "gt": "is above", "gte": "is at least", "lt": "is below", "lte": "is at most",
    "exists": "is set", "not_exists": "is empty",
}


def element_label(element: Dict[str, Any]) -> str:
    name = str(element.get("name") or "").strip()
    if name:
        return name
    etype = str(element.get("type") or "layer").replace("_", " ")
    text = str(element.get("text") or "").strip()
    return f'{etype} "{text[:30]}"' if text else etype


def _short(values: Any, limit: int = 3) -> str:
    vals = values if isinstance(values, (list, tuple)) else [values]
    vals = [str(v) for v in vals if v not in (None, "")]
    if len(vals) > limit:
        return ", ".join(vals[:limit]) + f" +{len(vals) - limit} more"
    return ", ".join(vals) or "(nothing)"


def describe_failure(cond: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Why one condition doesn't match, e.g. 'TMDb ID is 1291595; needs: is one of 656908, 858035 +11 more'."""
    field = str(cond.get("field") or "").strip().lower()
    if not field:
        return "a condition has no field"
    if field.startswith("_"):
        return "uses a Kometa rule Simposter can't check"
    label = FIELD_LABELS.get(field, field)
    op = str(cond.get("op") or "eq").strip().lower()
    want = "" if op in ("exists", "not_exists") else " " + _short(cond.get("value"))
    needs = f"needs: {_OP_WORDS.get(op, op)}{want}"
    values = _field_values(field, ctx)
    if not values:
        notes = ctx.get("_notes") or {}
        key = "ratings" if field in _rating_field_names() else "lists" if field in _LIST_FIELDS else field
        why = notes.get(key) or notes.get("filepath" if key in ("file_path", "filename") else key)
        return f"{label} is unknown{f' ({why})' if why else ''}; {needs}"
    actual = _short([PurePosixPath(str(v)).name if field in ("filepath", "file_path", "filename") else v for v in values])
    return f"{label} is {actual}; {needs}"


def explain_selection(elements: List[Dict[str, Any]], ctx: Dict[str, Any]) -> List[Tuple[Dict[str, Any], Optional[str]]]:
    """[(element, None if drawn else why not)], using the same rules as select_elements()."""
    reasons: Dict[int, Optional[str]] = {}
    passing: List[Dict[str, Any]] = []
    for element in elements:
        labels_lower = [label.lower() for label in ctx.get("labels") or []]
        show, hide = element.get("show_if_label"), element.get("hide_if_label")
        if show and str(show).lower() not in labels_lower:
            reasons[id(element)] = f'needs the label "{show}"'
            continue
        if hide and str(hide).lower() in labels_lower:
            reasons[id(element)] = f'has the label "{hide}"'
            continue
        failed = next((c for c in element.get("conditions") or [] if isinstance(c, dict) and not check_condition(c, ctx)), None)
        if failed is not None:
            reasons[id(element)] = describe_failure(failed, ctx)
            continue
        passing.append(element)

    winners: Dict[str, Tuple[float, int]] = {}
    for idx, element in enumerate(passing):
        group = element.get("group")
        if group:
            weight = _as_number(element.get("weight")) or 0.0
            best = winners.get(group)
            if best is None or weight > best[0]:
                winners[group] = (weight, idx)
    kept: List[Dict[str, Any]] = []
    for idx, element in enumerate(passing):
        group = element.get("group")
        if group and winners.get(group, (None, idx))[1] != idx:
            reasons[id(element)] = f'another layer won in set "{group}" ({element_label(passing[winners[group][1]])})'
        else:
            kept.append(element)

    hiders: Dict[str, str] = {}
    for element in kept:
        for name in element.get("suppress") or []:
            hiders.setdefault(str(name), element_label(element))
    for element in kept:
        name = str(element.get("name") or "")
        if name and name in hiders:
            reasons[id(element)] = f"hidden by {hiders[name]}"
        else:
            reasons[id(element)] = None
    return [(e, reasons.get(id(e), "not drawn")) for e in elements]


def data_summary(ctx: Dict[str, Any], elements: List[Dict[str, Any]]) -> str:
    """The item data the rules were checked against, in a line."""
    parts: List[str] = []
    res = ctx.get("resolution")
    if res:
        parts.append(str(res).upper() if res in ("4k", "sd") else str(res))
    for key in ("video_codec", "audio_codec"):
        if ctx.get(key):
            parts.append(str(ctx[key]).upper())
    if ctx.get("audio_channels"):
        parts.append(f"{ctx['audio_channels']}ch")
    if ctx.get("audio_language"):
        parts.append(f"lang {ctx['audio_language']}")
    if ctx.get("edition"):
        parts.append(f'edition "{ctx["edition"]}"')
    for key, label in (("tmdb_id", "TMDb"), ("tvdb_id", "TVDB")):
        if ctx.get(key):
            parts.append(f"{label} {ctx[key]}")
    if ctx.get("labels"):
        parts.append("labels " + _short(ctx["labels"], 4))
    if ctx.get("file_paths"):
        parts.append("file " + PurePosixPath(str(ctx["file_paths"][0])).name)
    notes = dict(ctx.get("_notes") or {})
    needs = needed_data(elements)
    if needs["ratings"]:
        used = sorted({str(c.get("field")).lower() for e in elements for c in (e.get("conditions") or [])
                       if isinstance(c, dict) and str(c.get("field") or "").lower() in _rating_field_names()}
                      | {m.group(1) for e in elements for m in _VAR_RE.finditer(str(e.get("text") or ""))
                         if m.group(1) in _rating_field_names()})
        shown = [f"{FIELD_LABELS.get(k, k)} {_format_value(ctx[k])}" for k in used if ctx.get(k) not in (None, "")]
        parts.append("ratings: " + (", ".join(shown) if shown else notes.get("ratings") or "none found"))
    if needs["lists"]:
        parts.append("on MDBList lists: " + (_short(ctx.get("lists") or [], 3) if ctx.get("lists") else notes.get("lists") or "none"))
    if needs.get("added"):
        parts.append(f"added {ctx['days_since_added']} days ago" if ctx.get("days_since_added") not in (None, "")
                     else "date added: " + (notes.get("days_since_added") or "unknown"))
    if needs.get("status"):
        parts.append("status " + str(ctx.get("show_status") or notes.get("show_status") or "unknown"))
    if needs["paths"] and notes.get("filepath"):
        parts.append("file: " + notes["filepath"])
    return ", ".join(parts) or "no media info"
