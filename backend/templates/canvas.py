"""Canvas-size resolution for Square Art.

Square Art deliberately reuses a user's EXISTING uniformlogo/kometa template and
preset, rendered against a different canvas, rather than being its own template_id
-- see CLAUDE.md's Square Art feature note for why (touches far fewer dispatch
sites, and doesn't fragment presets into a separate namespace). The canvas is
selected per-request via options["canvas_mode"], never persisted onto a preset.

Canvas width is deliberately IDENTICAL across every mode -- only height changes.
This is the single biggest simplifying choice here: every width-anchored option
(uniform_logo_max_w, kometa_logo_width, text wrap width, badge x-position ratios,
...) stays correct unmodified on a square canvas with no per-field rework. Only
options anchored to canvas HEIGHT in absolute pixels need rescaling -- see
HEIGHT_ANCHORED_OPTION_KEYS below.
"""
from typing import Dict, Any, Tuple

CANVAS_SIZES = {
    "default": (2000, 3000),
    "square": (2000, 2000),
}


def resolve_canvas_size(options: Dict[str, Any] | None) -> Tuple[int, int]:
    mode = (options or {}).get("canvas_mode") or "default"
    return CANVAS_SIZES.get(mode, CANVAS_SIZES["default"])


# Absolute-pixel option fields anchored to canvas HEIGHT (not a ratio, and not
# anchored to the unchanging canvas width) -- these are the only fields that need
# rescaling for a non-default canvas height. Re-derived directly from each field's
# actual semantics, not assumed: uniform_logo_max_w/kometa_logo_width are width-
# anchored (canvas_w never changes, so they need no scaling); font sizes are
# width-driven wrap / auto-shrink-to-fit under text_bbox_enabled, so they inherit
# the uniform_logo_max_h fix for free rather than needing their own entry.
HEIGHT_ANCHORED_OPTION_KEYS = ("uniform_logo_max_h", "kometa_logo_offset_y")


def scale_options_for_canvas(options: Dict[str, Any] | None) -> Dict[str, Any]:
    """Rescales height-anchored absolute-px option values so an existing preset's
    tuned proportions carry over to a shorter (or taller) canvas, instead of the
    raw numbers being reinterpreted against a different height unchanged. No-op
    (returns options unchanged) for the default canvas height."""
    if not options:
        return options or {}
    canvas_w, canvas_h = resolve_canvas_size(options)
    default_h = CANVAS_SIZES["default"][1]
    if canvas_h == default_h:
        return options
    ratio = canvas_h / default_h
    scaled = dict(options)
    for key in HEIGHT_ANCHORED_OPTION_KEYS:
        val = scaled.get(key)
        if val is not None:
            try:
                scaled[key] = float(val) * ratio
            except (TypeError, ValueError):
                pass
    return scaled
