# backend/templates/uniformlogo.py

from PIL import Image
from ..config import settings
from .universal import build_base_poster, _hex_to_rgb, _solid_color_logo, _render_text_overlay


def render_uniform_logo(bg: Image.Image, logo: Image.Image, options: dict) -> Image.Image:
    """
    Template that fits any logo into a fixed bounding box.
    Allows override mode for manual scaling & Y offset.
    """

    # Build base (zoom, matte, fade, grain, etc.)
    canvas = build_base_poster(bg, options)
    W, H = canvas.size

    # Handle logo rendering if logo is provided
    if logo is not None:
        # Normalize SVG to raster if needed
        if logo.format == "SVG" or (hasattr(logo, "mode") and logo.mode == "P") or logo.mode == "LA":
            logo = logo.convert("RGBA")
        else:
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

        # Align logo within bounding box
        h_align = options.get("uniform_logo_h_align", "center")
        v_align = options.get("uniform_logo_v_align", "center")

        box_left = cx - max_w // 2
        box_right = cx + max_w // 2
        box_top = cy - max_h // 2
        box_bottom = cy + max_h // 2

        if h_align == "left":
            x = box_left
        elif h_align == "right":
            x = box_right - new_w
        else:  # center
            x = cx - new_w // 2

        if v_align == "top":
            y = box_top
        elif v_align == "bottom":
            y = box_bottom - new_h
        else:  # center
            y = cy - new_h // 2

        canvas.paste(logo_res, (x, y), logo_res)

    # ------------- TEXT OVERLAY (outside logo check) -------------
    text_overlay_enabled = bool(options.get("text_overlay_enabled", False))
    print(f"[DEBUG uniformlogo] Text overlay enabled: {text_overlay_enabled}")
    if text_overlay_enabled:
        custom_text = str(options.get("custom_text", ""))
        print(f"[DEBUG uniformlogo] Custom text: '{custom_text}'")
        if custom_text:
            canvas = _render_text_overlay(canvas, custom_text, options)

    # Border?
    if options.get("border_enabled", False):
        px = options.get("border_px", 0)
        if px > 0:
            border_color = options.get("border_color", "#FFFFFF")
            from PIL import ImageOps
            canvas = ImageOps.expand(canvas, border=px, fill=border_color)

    # Apply overlay configurations
    from .universal import apply_overlay_config
    metadata = options.get("metadata", {})
    preset_id = options.get("preset_id")
    overlay_config_ids = options.get("overlay_config_ids")
    if preset_id or overlay_config_ids:
        canvas = apply_overlay_config(canvas, preset_id, "uniformlogo", metadata, overlay_config_ids)

    return canvas
