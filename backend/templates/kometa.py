# backend/templates/kometa.py
"""
Kometa-style collection poster template.

Modeled directly on bullmoose00's create_poster.ps1 (Plex-Stuff repo) — read in
full (not just summarized) after an initial pass got the logo/gradient mechanics
wrong. The real script's composite pipeline (ImageMagick):

  magick -size 2000x3000 xc:$base_color base.jpg
  magick -gravity center base.jpg $gradient_bitmap -flatten gradient.jpg
  magick $logo -resize $logo_resize logo.png                      # WIDTH-only resize, aspect preserved, no height cap
  magick gradient.jpg logo.png -gravity center -geometry +0$logo_offset -composite out.jpg
    # ^ logo is ALWAYS horizontally centered — only a vertical pixel offset from
    #   center exists (+down / -up, range -1500..1500). There is no horizontal
    #   offset or "bounding box" concept at all in the original tool.

This template matches that model: `kometa_logo_width` (px, aspect-preserved resize
target) + `kometa_logo_offset_y` (raw px offset from vertical center, +down/-up) —
not the box-fit-with-x/y-offset system uniformlogo uses for its logo, which doesn't
match how this tool (or the workflow it's replacing) actually positions a logo.

The background itself is synthesized upstream in rendering.py's
render_poster_image() from the kometa_base_color option — see that module for why.
The gradient bitmaps (0=none/1=center-out/2=bottom-up/3=top-down/4=bottom-top) are
reproduced procedurally via build_base_poster()'s existing matte/fade/vignette
machinery instead of vendoring bullmoose00's actual image assets (per your call) —
the frontend's Gradient Style dropdown just maps the 0-4 choice onto those existing
option keys, so this file itself doesn't need to know about the enum at all.

Deliberately NOT a wrapper around render_uniform_logo: this keeps a Kometa preset's
stored options small and self-describing (own kometa_* keys, no drop shadow, no
override-scale mode, no overlay-config badge buckets — collections have no
resolution/codec/edition metadata to badge) instead of inheriting uniformlogo's
full ~45-field option surface. Only the truly generic low-level helpers are shared.
"""

import numpy as np
from PIL import Image, ImageOps, ImageFilter

from .universal import build_base_poster, _hex_to_rgb, _solid_color_logo, _render_text_overlay


def _add_center_fade(canvas: Image.Image, strength: float) -> Image.Image:
    """
    Radial center-out fade to black, calibrated to actually reach black at the
    canvas corners — unlike universal.py's shared _add_vignette(), which sizes
    its falloff using max(w, h) = 3000 while the real corner distance on this
    2000x3000 canvas is only ~1803px. That mismatch means _add_vignette() never
    gets dark enough even at strength=1.0 (caps around ~60% there), which is
    fine for its actual job — a subtle photo-poster vignette other templates
    already rely on — but far too weak for the dramatic bright-center/black-
    corners look real Kometa "center-out" separator posters have.

    Kept local to this template rather than changing that shared helper (used
    by uniformlogo too) or its tuning for existing users.
    """
    if strength <= 0:
        return canvas

    W, H = canvas.size
    cx, cy = W / 2, H / 2
    max_r = (cx ** 2 + cy ** 2) ** 0.5  # true corner distance, not max(w, h)

    ys, xs = np.mgrid[0:H, 0:W]
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    alpha = np.clip((dist / max_r) * 255 * strength, 0, 255).astype(np.uint8)
    mask = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(40))

    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, canvas.convert("RGB"), mask).convert("RGBA")


def render_kometa(bg: Image.Image, logo: Image.Image, options: dict) -> Image.Image:
    """
    Template for Kometa-style collection posters: flat-color background + fade/
    center-glow (from build_base_poster's generic matte/fade/grain options plus
    this template's own center-fade), centered logo, optional text, optional
    border.
    """

    # Solid-color canvas (synthesized by the caller) still goes through
    # build_base_poster() so the existing matte/fade/top-matte/top-fade/grain/
    # wash sliders work here too — they're what produce the gradient-fade look
    # bullmoose00's script gets from pre-rendered bitmaps, generated fresh every
    # render instead. (Its own vignette_strength option is deliberately left at
    # 0 here — Kometa's "Center-Out" style uses kometa_center_fade_strength /
    # _add_center_fade() above instead, for the reasons in that function's docstring.)
    canvas = build_base_poster(bg, options)
    W, H = canvas.size

    center_fade_strength = float(options.get("kometa_center_fade_strength", 0.0))
    if center_fade_strength > 0:
        canvas = _add_center_fade(canvas, center_fade_strength)

    if logo is not None:
        logo = logo.convert("RGBA")

        if options.get("kometa_white_wash", False):
            logo = _solid_color_logo(logo, (255, 255, 255))

        # Width-only resize (aspect-preserved, no height cap) — matches
        # `-resize $logo_resize`, not a fit-inside-a-box model.
        target_w = max(1, int(options.get("kometa_logo_width", 2000)))
        lw, lh = logo.size
        scale = target_w / lw if lw else 1.0
        new_w = target_w
        new_h = max(1, int(lh * scale))
        logo_res = logo.resize((new_w, new_h), Image.LANCZOS)

        # Always horizontally centered; only a vertical px offset from center —
        # matches `-gravity center -geometry +0$logo_offset` exactly.
        offset_y = int(options.get("kometa_logo_offset_y", 0))
        cx = W // 2
        cy = H // 2 + offset_y
        x = cx - new_w // 2
        y = cy - new_h // 2
        canvas.paste(logo_res, (x, y), logo_res)

    if options.get("text_overlay_enabled", False):
        custom_text = str(options.get("custom_text", ""))
        if custom_text:
            canvas = _render_text_overlay(canvas, custom_text, options)

    if options.get("border_enabled", False):
        px = options.get("border_px", 0)
        if px > 0:
            border_color = options.get("border_color", "#FFFFFF")
            canvas = ImageOps.expand(canvas, border=px, fill=border_color)

    return canvas
