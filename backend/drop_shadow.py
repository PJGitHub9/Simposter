# backend/drop_shadow.py
"""Photoshop-style drop shadow compositing for logos (no Spread control —
see note below)."""

import math
from PIL import Image, ImageFilter


def add_drop_shadow(
    source: Image.Image,
    opacity_pct: float = 60,
    angle_deg: float = -45,
    distance_px: float = 8,
    size_px: float = 15,
    shadow_color: tuple = (0, 0, 0),
) -> tuple[Image.Image, int]:
    """
    Composite a drop shadow behind `source` (RGBA).

    Returns (result_image, padding) — padding is how much bigger the result
    is than `source` on each side; subtract it from the intended paste (x, y)
    so the sharp source layer stays exactly where it was meant to go, while
    the shadow overflows around it.

    Note: Photoshop's "Spread" control is intentionally not implemented. The
    only fast way to approximate it in PIL is ImageFilter.MaxFilter with a
    large kernel, which causes multi-second/timeout-length renders on
    poster-sized (2000x3000+) images — no faster alternative found.
    """
    if source.mode != "RGBA":
        source = source.convert("RGBA")

    opacity = max(0.0, min(1.0, opacity_pct / 100.0))
    blur_radius = max(0.0, size_px)

    # Angle convention: angle represents the LIGHT SOURCE direction
    # (Photoshop convention), so the shadow falls on the OPPOSITE side.
    angle_rad = math.radians(angle_deg)
    offset_x = round(-distance_px * math.cos(angle_rad))
    offset_y = round(distance_px * math.sin(angle_rad))

    # Pad before blurring — blurring without padding clips the blur at the
    # source image's original edges.
    padding = int(blur_radius * 3) + max(abs(offset_x), abs(offset_y)) + 10
    padded_w = source.width + padding * 2
    padded_h = source.height + padding * 2

    alpha_mask = Image.new("L", (padded_w, padded_h), 0)
    alpha_mask.paste(source.split()[3], (padding, padding))
    blurred_alpha = (
        alpha_mask.filter(ImageFilter.GaussianBlur(blur_radius))
        if blur_radius > 0 else alpha_mask
    )
    scaled_alpha = blurred_alpha.point(lambda p: int(p * opacity))

    solid_color_layer = Image.new("RGBA", (padded_w, padded_h), shadow_color + (0,))
    solid_color_layer.putalpha(scaled_alpha)

    shadow_layer = Image.alpha_composite(
        Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0)), solid_color_layer
    )
    shifted_shadow = Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0))
    shifted_shadow.paste(shadow_layer, (offset_x, offset_y))

    source_positioned = Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0))
    source_positioned.paste(source, (padding, padding), source)

    result = Image.alpha_composite(shifted_shadow, source_positioned)
    return result, padding
