# backend/templates/uniformlogo.py

from PIL import Image
from ..config import settings
from .universal import build_base_poster, _hex_to_rgb, _solid_color_logo


def render_uniform_logo(bg: Image.Image, logo: Image.Image, options: dict) -> Image.Image:
    """
    Template that fits any logo into a fixed bounding box.
    Allows override mode for manual scaling & Y offset.
    """

    # Build base (zoom, matte, fade, grain, etc.)
    canvas = build_base_poster(bg, options)
    W, H = canvas.size

    if logo is None:
        return canvas
    logo = logo.convert("RGBA")

    logo_mode = str(options.get("logo_mode", "stock") or "stock")
    logo_hex = str(options.get("logo_hex", "#FFFFFF") or "#FFFFFF")

    # Optional recolor (match/hex) like universal template
    if logo_mode == "match":
        poster_avg = bg.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
        color = poster_avg[:3]
        logo = _solid_color_logo(logo, color)
    elif logo_mode == "hex":
        color = _hex_to_rgb(logo_hex)
        logo = _solid_color_logo(logo, color)

    # ------------------------------
    # Bounding box (max W/H in px)
    # ------------------------------
    max_w = options.get("uniform_logo_max_w", 600)
    max_h = options.get("uniform_logo_max_h", 240)

    offset_x_pct = options.get("uniform_logo_offset_x", 0.5)
    offset_y_pct = options.get("uniform_logo_offset_y", 0.78)

    # Compute center of bounding box
    cx = int(W * offset_x_pct)
    cy = int(H * offset_y_pct)

    # ------------------------------
    # Auto-scaling (fit logo into bounding box)
    # ------------------------------
    lw, lh = logo.size

    scale = max_w / lw
    if lh * scale > max_h:
        scale = max_h / lh

    scale = min(scale, 1.0)  # never upscale logos

    # ------------------------------
    # Override mode?
    # ------------------------------
    if options.get("uniform_logo_override_enabled", False):
        scale = options.get("uniform_logo_override_scale", scale)
        offset_y_pct = options.get("uniform_logo_override_offset_y", offset_y_pct)
        cy = int(H * offset_y_pct)

    # Final logo size
    new_w = int(lw * scale)
    new_h = int(lh * scale)
    logo_res = logo.resize((new_w, new_h), Image.LANCZOS)

    # Center inside bounding box
    x = cx - new_w // 2
    y = cy - new_h // 2

    canvas.paste(logo_res, (x, y), logo_res)

    # Border?
    if options.get("border_enabled", False):
        px = options.get("border_px", 0)
        if px > 0:
            border_color = options.get("border_color", "#FFFFFF")
            from PIL import ImageOps
            canvas = ImageOps.expand(canvas, border=px, fill=border_color)

    return canvas
