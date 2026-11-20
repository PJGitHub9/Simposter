"""Compact preset exports: leave out options that equal the renderer's own
default, and put them back on import.

Each value in RENDER_DEFAULTS is what the backend uses when a preset doesn't
have the key at all: every `.get("key", <default>)` for that key in the
backend has this one literal default, and the key is never read without a
default or checked with `in`. Keys read in more than one way (font size,
position, logo box size, logo mode, ...) are never left out.

A compact export carries `_compact: COMPACT_VERSION`. Import puts the left-out
values back (expand_payload), so the stored preset is complete and the editors
show the same values as before. An older Simposter ignores the marker; it then
stores the preset without those keys, which still renders the same, since the
renderer falls back to these same values.

The pre-v1.8.88 compact export (no marker) used a hand-written list taken from
editor defaults, not renderer defaults; presets exported that way can't be
repaired on import, because they can't be told apart from a full export.

If you change a `.get()` default for one of these keys in the renderer, change
it here too (and bump COMPACT_VERSION if old exports would expand differently).
"""
from __future__ import annotations

from typing import Any

COMPACT_VERSION = 2

RENDER_DEFAULTS: dict[str, Any] = {
    # Poster
    "poster_zoom": 1.0,
    "poster_shift_y": 0.0,
    "matte_height_ratio": 0.0,
    "fade_height_ratio": 0.0,
    "top_matte_height_ratio": 0.0,
    "top_fade_height_ratio": 0.0,
    "vignette_strength": 0.0,
    "grain_amount": 0.0,
    # Border
    "border_enabled": False,
    "border_px": 0,
    "border_color": "#FFFFFF",
    # Logo
    "logo_hex": "#FFFFFF",
    "uniform_logo_h_align": "center",
    "uniform_logo_v_align": "center",
    "uniform_logo_shadow_enabled": False,
    "uniform_logo_shadow_opacity": 60,
    "uniform_logo_shadow_angle": -45,
    "uniform_logo_shadow_distance": 8,
    "uniform_logo_shadow_size": 15,
    "uniform_logo_shadow_color": "#000000",
    # Text
    "text_color": "#ffffff",
    "text_transform": "uppercase",
    "letter_spacing": 2,
    "line_height": 1.2,
    "shadow_enabled": False,
    "shadow_blur": 10,
    "shadow_color": "#000000",
    "shadow_offset_x": 0,
    "shadow_offset_y": 4,
    "shadow_opacity": 0.8,
    "stroke_enabled": False,
    # Kometa template
    "kometa_base_color": "#202020",
    "kometa_center_fade_strength": 0.0,
    "kometa_logo_offset_y": 0,
    "kometa_logo_width": 2000,
    "kometa_white_wash": False,
}

_MISSING = object()


def _same(a: Any, b: Any) -> bool:
    # bool is an int in Python (True == 1); only treat it as equal to a bool.
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def compact_options(opts: dict) -> dict:
    """Options without the keys that equal RENDER_DEFAULTS. Floats are kept
    exactly: rounding even to 10 decimals moved text by a pixel in a real
    preset (position_y 0.7833333333333333 sits on a pixel boundary)."""
    out = {}
    for k, v in (opts or {}).items():
        default = RENDER_DEFAULTS.get(k, _MISSING)
        if default is not _MISSING and _same(v, default):
            continue
        out[k] = v
    return out


def expand_options(opts: dict) -> dict:
    """Put back every RENDER_DEFAULTS key the options don't have."""
    out = dict(opts or {})
    for k, v in RENDER_DEFAULTS.items():
        out.setdefault(k, v)
    return out


def expand_payload(payload: dict, version: Any) -> dict:
    """Expand every preset's options in an import payload marked `_compact`.
    Season options are a diff against the options, so they are left as they are."""
    try:
        if int(version) < 2:
            return payload
    except (TypeError, ValueError):
        return payload
    for tpl_data in payload.values():
        if not isinstance(tpl_data, dict):
            continue
        for preset in tpl_data.get("presets", []) or []:
            if isinstance(preset, dict):
                preset["options"] = expand_options(preset.get("options") or {})
    return payload
