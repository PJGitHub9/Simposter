"""Merging a fallback preset's options over the original preset's.

When a batch/webhook/scheduled render can't find the preferred poster or logo,
the preset's fallback rules can switch to another preset. The fallback preset's
options win, except for the overlay lists: the ORIGINAL preset's
``fallbackKeepOverlays`` option (default on) decides whose overlays the
fallback poster gets.

- on: the original preset's overlays stay on the fallback poster.
- off: only the fallback preset's own overlays (none if it has none).

A plain ``{**base, **fallback}`` merge kept the original's overlays only when the
fallback preset had never stored an overlay list, and swapped them for the
fallback's list when it had one, which nobody could see from the UI.
"""

from typing import Any, Dict

OVERLAY_KEYS = ("overlay_config_ids", "overlay_config_ids_below")


def keep_overlays(options: Dict[str, Any]) -> bool:
    """The original preset's 'use current overlays on fallback poster' setting."""
    v = (options or {}).get("fallbackKeepOverlays", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "off", "")
    return v is not False and v is not None and bool(v)


def merge_fallback_options(base: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    """``{**base, **fallback}`` with the overlay lists chosen by ``fallbackKeepOverlays``."""
    base = base or {}
    fallback = fallback or {}
    merged = {**base, **fallback}
    source = base if keep_overlays(base) else fallback
    for key in OVERLAY_KEYS:
        merged[key] = list(source.get(key) or [])
    # The setting belongs to the original preset; keep it with the render options.
    if "fallbackKeepOverlays" in base:
        merged["fallbackKeepOverlays"] = base["fallbackKeepOverlays"]
    return merged
