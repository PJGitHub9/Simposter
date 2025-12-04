# backend/templates/universal.py
# Universal template with full creative controls for cinematic posters

from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageOps, ImageEnhance, ImageFilter, ImageChops, ImageFont
import random
import numpy as np
import os
from pathlib import Path
from ..config import settings

# ============================================================
# Helpers
# ============================================================

def _resize_cover(
    img: Image.Image,
    target_w: int,
    target_h: int,
    zoom: float = 1.0,
) -> Image.Image:
    """
    Resize to fully cover the target canvas (like CSS background-size: cover),
    then apply an extra zoom factor (poster_zoom) and center-crop.
    """
    w, h = img.size
    if w == 0 or h == 0:
        return img.resize((target_w, target_h), Image.LANCZOS)

    base_scale = max(target_w / w, target_h / h)
    scale = base_scale * max(zoom, 0.01)

    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    x = max(0, (new_w - target_w) // 2)
    y = max(0, (new_h - target_h) // 2)
    return resized.crop((x, y, x + target_w, y + target_h))


def _add_vignette(img: Image.Image, strength: float) -> Image.Image:
    """Radial vignette; strength 0..1."""
    if strength <= 0:
        return img

    img = img.convert("RGB")
    w, h = img.size
    vig = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(vig)

    steps = 60
    max_r = max(w, h)

    for i in range(steps):
        r = max_r * (i / steps)
        a = int(255 * strength * (i / steps))
        bbox = (w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r)
        draw.ellipse(bbox, fill=a)

    vig = vig.filter(ImageFilter.GaussianBlur(90))
    black = Image.new("RGB", (w, h), 0)
    return Image.composite(black, img, vig)



def _add_grain(img: Image.Image, amount: float) -> Image.Image:
    """Film grain; amount 0..0.6"""
    if amount <= 0:
        return img
    
    img = img.convert("RGB")
    w, h = img.size
    
    # Pre-compute grain layer once
    grain_array = np.random.uniform(-128 * amount, 128 * amount, (h, w))
    grain_array = (128 + grain_array).clip(0, 255).astype(np.uint8)
    
    grain = Image.fromarray(grain_array, mode='L')
    grain = grain.filter(ImageFilter.GaussianBlur(1.5))
    grain_rgb = Image.merge("RGB", (grain, grain, grain))
    return Image.blend(img, grain_rgb, amount)

def _add_grain_fast(img: Image.Image, amount: float) -> Image.Image:
    """
    Film grain; amount 0..0.6
    """
    if amount <= 0:
        return img
    
    img = img.convert("RGB")
    w, h = img.size
    
    # Generate all random values at once
    grain_array = np.random.uniform(-128 * amount, 128 * amount, (h, w))
    grain_array = (128 + grain_array).clip(0, 255).astype(np.uint8)
    
    # Convert to PIL Image
    grain = Image.fromarray(grain_array, mode='L')
    grain = grain.filter(ImageFilter.GaussianBlur(1.5))
    grain_rgb = Image.merge("RGB", (grain, grain, grain))
    return Image.blend(img, grain_rgb, amount)




def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #RRGGBB (or RRGGBB) to (r,g,b)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (r, g, b)


def _solid_color_logo(logo: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """
    Return a logo where ONLY the non-transparent regions are filled with `color`,
    keeping the original alpha. No boxes / backgrounds.
    """
    logo = logo.convert("RGBA")
    r, g, b, a = logo.split()
    cr, cg, cb = color
    return Image.merge(
        "RGBA",
        (
            Image.new("L", logo.size, cr),
            Image.new("L", logo.size, cg),
            Image.new("L", logo.size, cb),
            a,
        ),
    )


def _load_font(font_family: str, font_size: int, font_weight: str = "700"):
    """
    Load a font by name. First checks /config/fonts (mounted volume),
    then repo config/fonts, then system fonts with sensible fallbacks.
    """
    font_extensions = ['.ttf', '.otf', '.TTF', '.OTF']

    def try_paths(base_dir: Path):
        for ext in font_extensions:
            font_path = base_dir / f"{font_family}{ext}"
            if font_path.exists():
                try:
                    return ImageFont.truetype(str(font_path), font_size)
                except Exception:
                    continue
        return None

    # 1) Mounted config volume fonts (/config/fonts by default)
    volume_fonts_dir = Path(settings.CONFIG_DIR) / "fonts"
    font_obj = try_paths(volume_fonts_dir)
    if font_obj:
        return font_obj

    # 2) Repo config/fonts (for local dev)
    repo_fonts_dir = Path(__file__).resolve().parent.parent / "config" / "fonts"
    font_obj = try_paths(repo_fonts_dir)
    if font_obj:
        return font_obj

    # 3) Common system font mappings for Windows/Linux/Mac
    system_font_map = {
        'Arial': ['arial.ttf', 'Arial.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf'],
        'Helvetica': ['Helvetica.ttc', 'helvetica.ttf', '/System/Library/Fonts/Helvetica.ttc'],
        'Times New Roman': ['times.ttf', 'Times New Roman.ttf', '/System/Library/Fonts/Supplemental/Times New Roman.ttf'],
        'Georgia': ['georgia.ttf', 'Georgia.ttf', '/System/Library/Fonts/Supplemental/Georgia.ttf'],
        'Verdana': ['verdana.ttf', 'Verdana.ttf', '/System/Library/Fonts/Supplemental/Verdana.ttf'],
        'Courier New': ['cour.ttf', 'Courier New.ttf', '/System/Library/Fonts/Supplemental/Courier New.ttf'],
        'Impact': ['impact.ttf', 'Impact.ttf', '/System/Library/Fonts/Supplemental/Impact.ttf'],
        # Debian/Pillow bundled fonts
        'DejaVu Sans': ['DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
        'DejaVu Sans Bold': ['DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'],
    }

    boldish = (font_weight or "").lower() in ("bold", "700", "800", "900")
    candidates = []
    candidates.extend(system_font_map.get(font_family, [font_family + '.ttf']))
    if boldish:
        candidates.extend([
            font_family + '-Bold.ttf',
            font_family + '-Bold.otf',
            'DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ])
    candidates.extend([
        'DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ])

    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, font_size)
        except Exception:
            continue

    print("[DEBUG] Falling back to Pillow default font; text may render very small. Install fonts in /config/fonts or add fonts-dejavu to the image.")
    return ImageFont.load_default()


def _render_text_overlay(
    canvas: Image.Image,
    text: str,
    options: Dict[str, Any]
) -> Image.Image:
    """
    Render custom text overlay on the canvas.
    Supports font customization, positioning, shadows, and outlines.
    """
    if not text or not text.strip():
        print(f"[DEBUG] Text overlay skipped - empty text: '{text}'")
        return canvas

    print(f"[DEBUG] Rendering text overlay: '{text}'")
    W, H = canvas.size
    print(f"[DEBUG] Canvas size: {W}x{H}")

    # Extract text options
    font_family = str(options.get("font_family", "Arial"))
    font_size = int(options.get("font_size", 120))
    font_weight = str(options.get("font_weight", "700"))
    text_color = _hex_to_rgb(options.get("text_color", "#ffffff"))
    text_align = str(options.get("text_align", "center"))
    text_transform = str(options.get("text_transform", "uppercase"))
    letter_spacing = int(options.get("letter_spacing", 2))
    line_height = float(options.get("line_height", 1.2))
    position_y = float(options.get("position_y", 0.75))

    # Shadow options
    shadow_enabled = bool(options.get("shadow_enabled", True))
    shadow_blur = int(options.get("shadow_blur", 10))
    shadow_offset_x = int(options.get("shadow_offset_x", 0))
    shadow_offset_y = int(options.get("shadow_offset_y", 4))
    shadow_color = _hex_to_rgb(options.get("shadow_color", "#000000"))
    shadow_opacity = float(options.get("shadow_opacity", 0.8))

    # Stroke options
    stroke_enabled = bool(options.get("stroke_enabled", False))
    stroke_width = int(options.get("stroke_width", 4))
    stroke_color = _hex_to_rgb(options.get("stroke_color", "#000000"))

    # Replace template variables
    movie_title = str(options.get("movie_title", ""))
    movie_year = str(options.get("movie_year", ""))

    text = text.replace("{title}", movie_title)
    text = text.replace("{year}", movie_year)
    print(f"[DEBUG] Text after template substitution: '{text}'")

    # Apply text transform
    if text_transform == "uppercase":
        text = text.upper()
    elif text_transform == "lowercase":
        text = text.lower()
    elif text_transform == "capitalize":
        text = text.title()

    # Load font
    font = _load_font(font_family, font_size, font_weight)
    print(f"[DEBUG] Font loaded: {font_family} size {font_size}")

    # Create a drawing context for text measurement (needs proper size for accurate bbox)
    temp_img = Image.new("RGBA", (W, H))
    temp_draw = ImageDraw.Draw(temp_img)

    # Helper function to apply letter spacing
    def apply_letter_spacing(text_line: str) -> str:
        if letter_spacing > 0:
            return ''.join(c + ' ' * letter_spacing for c in text_line).rstrip()
        return text_line

    # Helper function to measure text width
    def measure_text_width(text_line: str) -> int:
        spaced = apply_letter_spacing(text_line)
        bbox = temp_draw.textbbox((0, 0), spaced, font=font)
        return bbox[2] - bbox[0]

    # Helper function to wrap a line if it's too wide
    def wrap_line(line: str, max_width: int) -> list[str]:
        """Wrap a line into multiple lines if it exceeds max_width"""
        if not line:
            return ['']

        # Check if the whole line fits
        if measure_text_width(line) <= max_width:
            return [line]

        # Split into words and wrap
        words = line.split(' ')
        wrapped_lines = []
        current_line = ''

        for word in words:
            # Try adding the word
            test_line = current_line + (' ' if current_line else '') + word

            if measure_text_width(test_line) <= max_width:
                current_line = test_line
            else:
                # Word doesn't fit, check if we need to break the word itself
                if current_line:
                    wrapped_lines.append(current_line)
                    current_line = word
                else:
                    # Single word is too long, need to break it by characters
                    if measure_text_width(word) > max_width:
                        # Break word character by character
                        for char in word:
                            test_line = current_line + char
                            if measure_text_width(test_line) <= max_width:
                                current_line = test_line
                            else:
                                if current_line:
                                    wrapped_lines.append(current_line)
                                current_line = char
                    else:
                        current_line = word

        if current_line:
            wrapped_lines.append(current_line)

        return wrapped_lines if wrapped_lines else ['']

    # Calculate max width (canvas width minus margins)
    margin_left = 100
    margin_right = 100
    max_text_width = W - margin_left - margin_right

    # Split text into lines and wrap if needed
    lines = text.split('\n')
    wrapped_lines = []
    for line in lines:
        wrapped_lines.extend(wrap_line(line, max_text_width))

    # Measure all wrapped lines
    line_heights = []
    line_widths = []

    for line in wrapped_lines:
        spaced_line = apply_letter_spacing(line)
        bbox = temp_draw.textbbox((0, 0), spaced_line, font=font)
        line_width = bbox[2] - bbox[0]
        line_height_val = bbox[3] - bbox[1]

        line_widths.append(line_width)
        line_heights.append(line_height_val)

    # Calculate total text block height with line spacing
    total_height = sum(line_heights) + int(font_size * (line_height - 1) * (len(wrapped_lines) - 1))
    max_width = max(line_widths) if line_widths else 0

    print(f"[DEBUG] Text wrapped into {len(wrapped_lines)} lines (original: {len(lines)} lines)")
    print(f"[DEBUG] Max text width allowed: {max_text_width}px")

    # Calculate Y position
    y_pos = int(H * position_y - total_height / 2)
    print(f"[DEBUG] Text position: y={y_pos}, position_y={position_y}, total_height={total_height}")
    print(f"[DEBUG] Text color: {text_color}, align: {text_align}")

    # Create layer for text with extra space for shadow/stroke
    padding = max(shadow_blur + abs(shadow_offset_x) + abs(shadow_offset_y), stroke_width) + 50
    text_layer = Image.new("RGBA", (W + padding * 2, H + padding * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)

    # Draw each line
    current_y = y_pos + padding
    for i, line in enumerate(wrapped_lines):
        # Add letter spacing
        spaced_line = apply_letter_spacing(line)

        # Calculate X position based on alignment
        line_width = line_widths[i]
        if text_align == "center":
            x_pos = (W - line_width) // 2 + padding
        elif text_align == "right":
            x_pos = W - line_width - 100 + padding  # 100px margin from right
        else:  # left
            x_pos = 100 + padding  # 100px margin from left

        # Draw shadow if enabled
        if shadow_enabled and shadow_blur > 0:
            # Create shadow layer
            shadow_layer = Image.new("RGBA", text_layer.size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_layer)

            shadow_x = x_pos + shadow_offset_x
            shadow_y = current_y + shadow_offset_y

            # Draw shadow with stroke if stroke is enabled
            if stroke_enabled:
                shadow_draw.text(
                    (shadow_x, shadow_y),
                    spaced_line,
                    font=font,
                    fill=(*shadow_color, int(255 * shadow_opacity)),
                    stroke_width=stroke_width,
                    stroke_fill=(*shadow_color, int(255 * shadow_opacity))
                )
            else:
                shadow_draw.text(
                    (shadow_x, shadow_y),
                    spaced_line,
                    font=font,
                    fill=(*shadow_color, int(255 * shadow_opacity))
                )

            # Blur shadow
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur))
            text_layer = Image.alpha_composite(text_layer, shadow_layer)

        # Draw text with stroke/outline if enabled
        if stroke_enabled:
            draw.text(
                (x_pos, current_y),
                spaced_line,
                font=font,
                fill=(*text_color, 255),
                stroke_width=stroke_width,
                stroke_fill=(*stroke_color, 255)
            )
        else:
            draw.text(
                (x_pos, current_y),
                spaced_line,
                font=font,
                fill=(*text_color, 255)
            )

        # Move to next line
        current_y += line_heights[i] + int(font_size * (line_height - 1))

    # Crop text layer back to canvas size
    text_layer = text_layer.crop((padding, padding, W + padding, H + padding))

    # Composite text onto canvas
    canvas = canvas.convert("RGBA")
    canvas = Image.alpha_composite(canvas, text_layer)
    print(f"[DEBUG] Text overlay composited successfully")

    return canvas


# ============================================================
# Base poster (used by universal + uniformlogo)
# ============================================================

def build_base_poster(
    background: Image.Image,
    options: Dict[str, Any] | None,
) -> Image.Image:
    """
    Base poster builder with matte, fade, vignette, and grain effects.
    Used by:
      - universal template
      - uniformlogo template
    """

    if background is None:
        raise ValueError("Background image is required")

    if options is None:
        options = {}

    # fixed 2:3 canvas (TPDB friendly, vertical)
    canvas_w = 2000
    canvas_h = 3000

    # ------------- OPTIONS -------------
    poster_zoom = float(options.get("poster_zoom", 1.0))          # 1.0 = normal
    poster_shift_y = float(options.get("poster_shift_y", 0.0))    # -0.5..0.5

    matte_height_ratio = float(options.get("matte_height_ratio", 0.0))  # 0..0.5
    fade_height_ratio = float(options.get("fade_height_ratio", 0.0))    # 0..0.5

    vignette_strength = float(options.get("vignette_strength", 0.0))    # 0..1
    grain_amount = float(options.get("grain_amount", 0.0))              # 0..0.6

    # clamp helpers
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    poster_zoom = max(poster_zoom, 0.1)
    poster_shift_y = clamp(poster_shift_y, -0.5, 0.5)

    matte_height_ratio = clamp(matte_height_ratio, 0.0, 0.5)
    fade_height_ratio = clamp(fade_height_ratio, 0.0, 0.5)

    vignette_strength = clamp(vignette_strength, 0.0, 1.0)
    grain_amount = clamp(grain_amount, 0.0, 0.6)

    # ------------- BASE POSTER -------------
    base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))

    poster = _resize_cover(background, canvas_w, canvas_h, zoom=poster_zoom)
    shift_px = int(poster_shift_y * canvas_h)
    base.paste(poster, (0, shift_px))

    # ------------- MATTE + FADE -------------
    matte_h = int(canvas_h * matte_height_ratio)
    fade_h = int(canvas_h * fade_height_ratio)

    if matte_h > 0 or fade_h > 0:
        matte_mask = Image.new("L", (canvas_w, canvas_h), 0)
        mp = matte_mask.load()

        matte_start = canvas_h - matte_h               # where solid matte begins
        fade_start = max(0, matte_start - fade_h)      # top of fade

        for y in range(canvas_h):
            if y >= matte_start:
                alpha = 255  # solid matte
            elif y >= fade_start:
                t = (y - fade_start) / max(fade_h, 1)
                alpha = int(255 * t)  # from 0 → 255 downward
            else:
                alpha = 0  # pure poster
            for x in range(canvas_w):
                mp[x, y] = alpha

        black = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
        base = Image.composite(black, base, matte_mask)

    # ------------- VIGNETTE + GRAIN (poster only) -------------
    base_rgb = base.convert("RGB")
    if vignette_strength > 0:
        base_rgb = _add_vignette(base_rgb, vignette_strength)
    base_rgb = _add_grain(base_rgb, grain_amount)

    # --- WASHOUT EFFECT (neutral grey tone overlay) ---
    v12_wash = float(options.get("v12_wash_strength", 0.0))  # Recommended: 0.08–0.15
    if v12_wash > 0:
        # Neutral grey tone for cinematic washout effect
        grey_layer = Image.new("RGB", (canvas_w, canvas_h), (32, 32, 32))
        base_rgb = Image.blend(base_rgb, grey_layer, v12_wash)

    return base_rgb.convert("RGBA")


# ============================================================
# Universal template
# ============================================================

def render_universal(
    background: Image.Image,
    logo: Optional[Image.Image],
    options: Dict[str, Any] | None,
) -> Image.Image:
    """
    Primary "default" template renderer.
    Full creative controls for cinematic posters with matte, fade, vignette, and effects.
    """

    if options is None:
        options = {}

    base = build_base_poster(background, options)
    canvas = base  # RGBA 2000x3000
    W, H = canvas.size

    # ------------- LOGO OPTIONS -------------
    logo_scale = float(options.get("logo_scale", 0.5))         # fraction of canvas width
    logo_offset = float(options.get("logo_offset", 0.75))      # 0..1 top→bottom

    logo_mode = str(options.get("logo_mode", "stock") or "stock")
    logo_hex = str(options.get("logo_hex", "#FFFFFF") or "#FFFFFF")

    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    logo_scale = clamp(logo_scale, 0.1, 1.0)
    logo_offset = clamp(logo_offset, 0.0, 1.0)

    # ------------- LOGO -------------
    if logo is not None:
        logo = logo.convert("RGBA")

        if logo_mode == "match":
            # Color match using poster's average color
            poster_avg = background.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
            color = poster_avg[:3]
            logo = _solid_color_logo(logo, color)

        elif logo_mode == "hex":
            color = _hex_to_rgb(logo_hex)
            logo = _solid_color_logo(logo, color)

        # stock: keep original logo RGBA

        # Resize logo to logo_scale * canvas width
        max_w = int(W * logo_scale)
        if max_w > 0 and logo.width > 0:
            scale = max_w / logo.width
            new_size = (int(logo.width * scale), int(logo.height * scale))
            logo = logo.resize(new_size, Image.LANCZOS)

        # Absolute position: 0..1 top→bottom, based on logo height
        y_logo = int((H - logo.height) * logo_offset)
        x_logo = (W - logo.width) // 2

        canvas.alpha_composite(logo, (x_logo, y_logo))

    # ------------- TEXT OVERLAY -------------
    text_overlay_enabled = bool(options.get("text_overlay_enabled", False))
    print(f"[DEBUG] Text overlay enabled: {text_overlay_enabled}")
    if text_overlay_enabled:
        custom_text = str(options.get("custom_text", ""))
        print(f"[DEBUG] Custom text: '{custom_text}'")
        if custom_text:
            canvas = _render_text_overlay(canvas, custom_text, options)

    # ------------- ROUNDED CORNERS + BORDER -------------
    canvas = canvas.convert("RGBA")
    radius = int(min(W, H) * 0.03)

    # Rounded mask
    round_mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(round_mask).rounded_rectangle(
        [(0, 0), (W, H)],
        radius=radius,
        fill=255
    )
    canvas.putalpha(round_mask)

    border_enabled = bool(options.get("border_enabled", False))
    if border_enabled:
        border_px = int(options.get("border_px", 0))
        border_color = _hex_to_rgb(options.get("border_color", "#FFFFFF"))

        filled_bg = Image.new("RGBA", (W, H), (*border_color, 255))
        canvas = Image.alpha_composite(filled_bg, canvas)

        if border_px > 0:
            outer = round_mask

            inner = Image.new("L", (W, H), 0)
            ImageDraw.Draw(inner).rounded_rectangle(
                [(border_px, border_px), (W - border_px, H - border_px)],
                radius=max(1, radius - border_px),
                fill=255
            )

            border_mask = ImageChops.subtract(outer, inner)
            border_layer = Image.new("RGBA", (W, H), (*border_color, 255))
            border_layer.putalpha(border_mask)
            canvas = Image.alpha_composite(canvas, border_layer)

    return canvas.convert("RGB")
