# backend/templates/universal.py
# Universal template with full creative controls for cinematic posters

from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageOps, ImageEnhance, ImageFilter, ImageChops, ImageFont
import random
import numpy as np
import os
import io
import time
import hashlib
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
    Load a font by name. Searches in this order:
    1. /config/fonts (mounted volume for custom fonts)
    2. repo config/fonts (bundled fonts)
    3. System font directories

    Supports exact matches, partial matches, and weight-specific variants.
    Users can upload custom .ttf or .otf files to /config/fonts/
    """
    font_extensions = ['.ttf', '.otf', '.TTF', '.OTF', '.ttc', '.TTC']
    boldish = (font_weight or "").lower() in ("bold", "700", "800", "900")

    def scan_directory(base_dir: Path):
        """Scan directory for matching fonts with fuzzy matching."""
        if not base_dir.exists():
            return None

        # Try exact match first
        for ext in font_extensions:
            font_path = base_dir / f"{font_family}{ext}"
            if font_path.exists():
                try:
                    print(f"[FONT] Loaded '{font_family}' from {font_path}")
                    return ImageFont.truetype(str(font_path), font_size)
                except Exception as e:
                    print(f"[FONT] Failed to load {font_path}: {e}")

            # Try with weight suffix if bold requested
            if boldish:
                for suffix in ['-Bold', '-bold', 'Bold', 'bold', '-B', 'B', '-Heavy', 'Heavy']:
                    font_path = base_dir / f"{font_family}{suffix}{ext}"
                    if font_path.exists():
                        try:
                            print(f"[FONT] Loaded '{font_family}' (bold) from {font_path}")
                            return ImageFont.truetype(str(font_path), font_size)
                        except Exception as e:
                            print(f"[FONT] Failed to load {font_path}: {e}")

        # Try recursive search with fuzzy matching
        try:
            font_lower = font_family.lower().replace(' ', '').replace('-', '')
            matched_fonts = []

            # First pass: collect all matching fonts with metadata
            for font_file in base_dir.rglob('*'):
                if font_file.suffix.lower() not in ['.ttf', '.otf', '.ttc']:
                    continue

                file_lower = font_file.stem.lower().replace(' ', '').replace('-', '')

                # Match if font_family is in filename
                if font_lower in file_lower or file_lower in font_lower:
                    has_bold = any(w in file_lower for w in ['bold', 'heavy', 'black', 'bd'])
                    has_italic = 'italic' in file_lower or 'oblique' in file_lower
                    has_light = 'light' in file_lower or 'thin' in file_lower

                    # Skip italics unless specifically requested
                    if has_italic and 'italic' not in font_family.lower():
                        continue

                    matched_fonts.append({
                        'path': font_file,
                        'has_bold': has_bold,
                        'has_light': has_light,
                        'has_italic': has_italic,
                        'is_exact_weight': (boldish and has_bold) or (not boldish and not has_bold and not has_light)
                    })

            # Sort by preference: exact weight match first
            matched_fonts.sort(key=lambda x: (
                not x['is_exact_weight'],  # Exact weight match first
                x['has_italic'],  # Non-italic preferred
                x['has_light']  # Non-light preferred
            ))

            # Try loading fonts in priority order
            for font_info in matched_fonts:
                try:
                    font_obj = ImageFont.truetype(str(font_info['path']), font_size)
                    match_type = "exact weight" if font_info['is_exact_weight'] else "fallback weight"
                    print(f"[FONT] Loaded '{font_family}' via fuzzy match ({match_type}) from {font_info['path']}")
                    return font_obj
                except Exception as e:
                    print(f"[FONT] Failed to load {font_info['path']}: {e}")

        except Exception as e:
            print(f"[FONT] Error scanning directory {base_dir}: {e}")

        return None

    # 1) Check /config/fonts (user custom fonts directory)
    volume_fonts_dir = Path(settings.CONFIG_DIR) / "fonts"
    # Create directory if it doesn't exist
    try:
        volume_fonts_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    font_obj = scan_directory(volume_fonts_dir)
    if font_obj:
        return font_obj

    # 2) Check repo config/fonts (bundled fonts)
    repo_fonts_dir = Path(__file__).resolve().parent.parent.parent / "config" / "fonts"
    font_obj = scan_directory(repo_fonts_dir)
    if font_obj:
        return font_obj

    # 3) System font directories (Windows/Linux/macOS)
    system_font_dirs = [
        Path('/usr/share/fonts'),  # Linux
        Path('/System/Library/Fonts'),  # macOS system
        Path('/Library/Fonts'),  # macOS shared
        Path('C:/Windows/Fonts'),  # Windows
        Path(os.path.expanduser('~/Library/Fonts')),  # macOS user
        Path(os.path.expanduser('~/.fonts')),  # Linux user
    ]

    for sys_dir in system_font_dirs:
        if sys_dir.exists():
            font_obj = scan_directory(sys_dir)
            if font_obj:
                return font_obj

    # 4) Common font name aliases as fallback
    # Map font families to their actual file names on different systems
    system_font_map = {
        'Arial': {
            'regular': ['arial.ttf', 'Arial.ttf'],
            'bold': ['arialbd.ttf', 'Arial Bold.ttf', 'Arial-Bold.ttf']
        },
        'Helvetica': {
            'regular': ['Helvetica.ttf', 'HelveticaNeue.ttc', 'Helvetica Neue.ttf', 'arial.ttf'],  # Fallback to Arial
            'bold': ['Helvetica-Bold.ttf', 'HelveticaNeue-Bold.ttc', 'Helvetica Neue Bold.ttf', 'arialbd.ttf']
        },
        'Times New Roman': {
            'regular': ['times.ttf', 'Times New Roman.ttf'],
            'bold': ['timesbd.ttf', 'Times New Roman Bold.ttf']
        },
        'Georgia': {
            'regular': ['georgia.ttf', 'Georgia.ttf'],
            'bold': ['georgiab.ttf', 'Georgia Bold.ttf']
        },
        'Verdana': {
            'regular': ['verdana.ttf', 'Verdana.ttf'],
            'bold': ['verdanab.ttf', 'Verdana Bold.ttf']
        },
        'Courier New': {
            'regular': ['cour.ttf', 'Courier New.ttf'],
            'bold': ['courbd.ttf', 'Courier New Bold.ttf']
        },
        'Impact': {
            'regular': ['impact.ttf', 'Impact.ttf'],
            'bold': ['impact.ttf', 'Impact.ttf']  # Impact doesn't have bold
        },
        'Trebuchet MS': {
            'regular': ['trebuc.ttf', 'Trebuchet MS.ttf'],
            'bold': ['trebucbd.ttf', 'Trebuchet MS Bold.ttf']
        },
        'Comic Sans MS': {
            'regular': ['comic.ttf', 'Comic Sans MS.ttf'],
            'bold': ['comicbd.ttf', 'Comic Sans MS Bold.ttf']
        },
        'DejaVu Sans': {
            'regular': ['DejaVuSans.ttf'],
            'bold': ['DejaVuSans-Bold.ttf']
        },
        'Liberation Sans': {
            'regular': ['LiberationSans-Regular.ttf'],
            'bold': ['LiberationSans-Bold.ttf']
        },
        'Roboto': {
            'regular': ['Roboto-Regular.ttf'],
            'bold': ['Roboto-Bold.ttf']
        },
    }

    # Build candidate list based on weight
    candidates = []
    if font_family in system_font_map:
        weight_key = 'bold' if boldish else 'regular'
        # Try requested weight first
        candidates.extend(system_font_map[font_family].get(weight_key, []))
        # Then try opposite weight as fallback
        fallback_key = 'regular' if boldish else 'bold'
        candidates.extend(system_font_map[font_family].get(fallback_key, []))

    # Add generic fallbacks (weight-aware)
    if boldish:
        candidates.extend([
            'DejaVuSans-Bold.ttf',
            'LiberationSans-Bold.ttf',
            'FreeSansBold.ttf',
            'arialbd.ttf',  # Windows Arial Bold
            'Arial-Bold.ttf',
        ])
    else:
        candidates.extend([
            'DejaVuSans.ttf',
            'LiberationSans-Regular.ttf',
            'FreeSans.ttf',
            'arial.ttf',  # Windows Arial
            'Arial.ttf',
        ])

    for font_name in candidates:
        try:
            font_obj = ImageFont.truetype(font_name, font_size)
            print(f"[FONT] Loaded system font: {font_name} (weight={'bold' if boldish else 'regular'})")
            return font_obj
        except Exception:
            continue

    print(f"[FONT] WARNING: Could not load '{font_family}' (weight={'bold' if boldish else 'regular'}). Using Pillow default.")
    print(f"[FONT] To fix: Upload .ttf/.otf files to {volume_fonts_dir}")
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
    shadow_enabled = bool(options.get("shadow_enabled", False))  # Default: disabled
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
    season_text = str(options.get("season_text", ""))

    text = text.replace("{title}", movie_title)
    text = text.replace("{year}", movie_year)
    text = text.replace("{season}", season_text)
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


# ============================================================
# Overlay Rendering
# ============================================================

def apply_overlay_config(
    canvas: Image.Image,
    preset_id: Optional[str],
    template_id: str,
    metadata: Optional[Dict[str, Any]] = None,
    overlay_config_ids: Optional[list] = None
) -> Image.Image:
    """
    Apply overlay configurations to the canvas.

    Overlay configs come from two sources (both are applied, deduped):
    1. The preset's linked overlay_config_id (legacy single-link)
    2. Explicit overlay_config_ids passed in render options (multi-select)

    Args:
        canvas: The base poster image
        preset_id: The preset ID (to look up overlay_config_id)
        template_id: The template ID
        metadata: Optional metadata dict with fields like video_resolution, audio_codec, labels, etc.
        overlay_config_ids: Optional list of overlay config IDs to apply directly

    Returns:
        Canvas with overlays applied
    """
    from .. import database as db
    from ..config import logger

    # Collect all config IDs to apply (deduped, ordered)
    config_ids: list[str] = []
    seen: set[str] = set()

    # 1. From preset's linked overlay_config_id
    if preset_id:
        try:
            preset = db.get_preset(template_id, preset_id)
            if preset:
                linked_id = preset.get("overlay_config_id")
                if linked_id and linked_id not in seen:
                    config_ids.append(linked_id)
                    seen.add(linked_id)
        except Exception as e:
            logger.error(f"[OVERLAY] Failed to load preset {preset_id}: {e}")

    # 2. From explicit overlay_config_ids
    if overlay_config_ids:
        for cid in overlay_config_ids:
            if cid and cid not in seen:
                config_ids.append(cid)
                seen.add(cid)

    if not config_ids:
        logger.info("[OVERLAY] No overlay config IDs to apply (preset_id=%s, explicit_ids=%s)", preset_id, overlay_config_ids)
        return canvas

    # Log available metadata for overlay rendering
    meta = metadata or {}

    # Pre-pass: resolve streaming platform and studio if any config needs them
    tmdb_id = meta.get("tmdb_id")
    if tmdb_id:
        needs_streaming = "streaming_platform" not in meta
        needs_studio = "studio" not in meta

        for cid in config_ids:
            if not needs_streaming and not needs_studio:
                break
            try:
                cfg = db.get_overlay_config(cid)
                if not cfg:
                    continue
                element_types = {e.get("type") for e in cfg.get("elements", [])}

                if needs_streaming and "streaming_platform_badge" in element_types:
                    try:
                        from ..tmdb_client import get_watch_providers, normalize_provider_name
                        region = cfg.get("streaming_region") or "US"
                        media_type = meta.get("media_type", "movie")
                        providers = get_watch_providers(int(tmdb_id), media_type, region)
                        if providers:
                            provider = providers[0]
                            slug = normalize_provider_name(provider.get("provider_name", ""))
                            meta["streaming_platform"] = slug
                            # Store TMDb logo URL so "url" mode works without manual URL config
                            logo_path = provider.get("logo_path", "")
                            if logo_path:
                                meta["streaming_platform_logo_url"] = f"https://image.tmdb.org/t/p/w200{logo_path}"
                            logger.debug("[OVERLAY] Resolved streaming platform: %s (region=%s)", slug, region)
                    except Exception as sp_err:
                        logger.debug("[OVERLAY] Streaming platform pre-pass error: %s", sp_err)
                    needs_streaming = False

                if needs_studio and "studio_badge" in element_types:
                    try:
                        from ..tmdb_client import get_studio_name
                        media_type = meta.get("media_type", "movie")
                        slug = get_studio_name(int(tmdb_id), media_type)
                        if slug:
                            meta["studio"] = slug
                            logger.debug("[OVERLAY] Resolved studio: %s", slug)
                    except Exception as st_err:
                        logger.debug("[OVERLAY] Studio pre-pass error: %s", st_err)
                    needs_studio = False

            except Exception as cfg_err:
                logger.debug("[OVERLAY] Pre-pass config error for %s: %s", cid, cfg_err)

    logger.info("[OVERLAY] Metadata available for overlays: %s", {k: v for k, v in meta.items() if k != "labels"})

    # Convert to RGBA for overlay compositing
    if canvas.mode != "RGBA":
        canvas = canvas.convert("RGBA")

    W, H = canvas.size

    for config_id in config_ids:
        try:
            overlay_config = db.get_overlay_config(config_id)
            if not overlay_config:
                logger.warning(f"[OVERLAY] Overlay config {config_id} not found")
                continue

            elements = overlay_config.get("elements", [])
            if not elements:
                logger.info(f"[OVERLAY] Overlay config '{overlay_config['name']}' has no elements, skipping")
                continue

            element_types = [e.get("type", "unknown") for e in elements]
            logger.info(f"[OVERLAY] Applying overlay config '{overlay_config['name']}' with {len(elements)} elements: {element_types}")

            for element in elements:
                try:
                    canvas = _apply_overlay_element(canvas, element, W, H, meta)
                except Exception as elem_err:
                    logger.error(f"[OVERLAY] Failed to apply element {element.get('type')}: {elem_err}")

        except Exception as e:
            logger.error(f"[OVERLAY] Failed to apply overlay config {config_id}: {e}")

    return canvas


def _get_text_anchor(element: Dict[str, Any]) -> str:
    """Map element text_align to PIL text anchor. Default is center ('mm')."""
    align = (element.get("text_align") or "center").lower()
    return {"left": "lm", "right": "rm"}.get(align, "mm")


def _apply_overlay_element(canvas: Image.Image, element: Dict[str, Any], W: int, H: int, metadata: Dict[str, Any]) -> Image.Image:
    """Apply a single overlay element to the canvas."""
    from ..config import logger

    element_type = element.get("type")
    logger.info("[OVERLAY] Processing element type='%s' at position=(%.2f, %.2f)",
                element_type, element.get("position_x", 0.5), element.get("position_y", 0.5))

    # Check conditional rendering based on labels
    if not _should_render_element(element, metadata):
        logger.info("[OVERLAY]   -> Skipped (conditional label filter)")
        return canvas

    # Calculate position
    pos_x = element.get("position_x", 0.5)
    pos_y = element.get("position_y", 0.5)
    x = int(W * pos_x)
    y = int(H * pos_y)

    # Metadata badge types (new + legacy aliases)
    _BADGE_DEFAULTS = {
        "video_badge":              ("video_resolution", 40),
        "audio_badge":              ("audio_codec", 30),
        "edition_badge":            ("edition", 30),
        "streaming_platform_badge": ("streaming_platform", 30),
        "studio_badge":             ("studio", 30),
        "resolution_badge":         ("video_resolution", 40),  # legacy alias
        "codec_badge":              ("audio_codec", 30),       # legacy alias
    }

    if element_type in _BADGE_DEFAULTS:
        default_field, default_font_size = _BADGE_DEFAULTS[element_type]
        return _apply_metadata_badge(canvas, element, x, y, metadata, default_field, default_font_size)
    elif element_type == "custom_image":
        return _apply_custom_image(canvas, element, x, y)
    elif element_type == "text_label":
        return _apply_text_label(canvas, element, x, y)
    elif element_type == "label_badge":
        return _apply_label_badge(canvas, element, x, y, metadata)

    logger.warning("[OVERLAY]   -> Unknown element type '%s', skipping", element_type)
    return canvas


def _should_render_element(element: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
    """Check if element should be rendered based on conditional rules (case-insensitive)."""
    show_if_label = element.get("show_if_label")
    hide_if_label = element.get("hide_if_label")
    labels = metadata.get("labels", [])
    labels_lower = [l.lower() for l in labels]

    if show_if_label and show_if_label.lower() not in labels_lower:
        return False

    if hide_if_label and hide_if_label.lower() in labels_lower:
        return False

    return True


def _calc_paste_position(x: int, y: int, ow: int, oh: int, anchor: str) -> tuple[int, int]:
    """Calculate top-left paste position for an image given an anchor point."""
    h_anchors = {
        "left":   0,
        "center": ow // 2,
        "right":  ow,
    }
    v_anchors = {
        "top":    0,
        "center": oh // 2,
        "bottom": oh,
    }
    parts = anchor.lower().split("-") if anchor else ["center"]
    if len(parts) == 1:
        h_off = h_anchors.get("center", ow // 2)
        v_off = v_anchors.get("center", oh // 2)
    else:
        v_off = v_anchors.get(parts[0], oh // 2)
        h_off = h_anchors.get(parts[1], ow // 2)
    return x - h_off, y - v_off


def _apply_canvas_size_constraints(img: Image.Image, element: Dict[str, Any], W: int, H: int) -> Image.Image:
    """Apply percentage-based width/height and max-pixel constraints (custom_image only)."""
    ow, oh = img.size

    pct_width = element.get("width")
    pct_height = element.get("height")
    if pct_width and pct_width > 0:
        ratio = int(W * pct_width) / ow
        ow = int(W * pct_width)
        oh = int(oh * ratio)
        img = img.resize((ow, oh), Image.LANCZOS)
    if pct_height and pct_height > 0:
        ratio = int(H * pct_height) / oh
        oh = int(H * pct_height)
        ow = int(ow * ratio)
        img = img.resize((ow, oh), Image.LANCZOS)

    max_width = element.get("max_width")
    max_height = element.get("max_height")
    if max_width or max_height:
        ow, oh = img.size
        cap = 1.0
        if max_width and ow > max_width:
            cap = min(cap, max_width / ow)
        if max_height and oh > max_height:
            cap = min(cap, max_height / oh)
        if cap < 1.0:
            img = img.resize((int(ow * cap), int(oh * cap)), Image.LANCZOS)

    return img


def _render_badge_asset(canvas: Image.Image, element: Dict[str, Any], x: int, y: int, asset_id: str, value: str = "") -> Optional[Image.Image]:
    """Try to render a badge using an asset image. Returns updated canvas on success, None on failure.
    Uses alpha_composite so semi-transparent badge edges composite correctly without darkening."""
    from .. import database as db

    asset = db.get_overlay_asset(asset_id)
    if not asset:
        return None

    asset_path = Path(settings.CONFIG_DIR) / asset["file_path"]
    if not asset_path.exists():
        return None

    overlay_img = Image.open(asset_path).convert("RGBA")

    # Per-value scale/anchor override element-level fallback
    val_key = value.lower() if value else ""
    badge_scales = element.get("badge_scales") or {}
    badge_anchors = element.get("badge_anchors") or {}
    scale_multiplier = badge_scales.get(val_key) if val_key in badge_scales else element.get("scale")
    anchor = badge_anchors.get(val_key) if val_key in badge_anchors else element.get("anchor", "center")

    if scale_multiplier and scale_multiplier > 0:
        ow, oh = overlay_img.size
        overlay_img = overlay_img.resize((int(ow * scale_multiplier), int(oh * scale_multiplier)), Image.LANCZOS)

    ow, oh = overlay_img.size
    paste_x, paste_y = _calc_paste_position(x, y, ow, oh, anchor or "center")
    badge_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    badge_layer.paste(overlay_img, (paste_x, paste_y))
    return Image.alpha_composite(canvas, badge_layer)


def _normalize_badge_url(url: str) -> str:
    """Normalize known URL patterns to direct-download equivalents.
    GitHub blob viewer URLs → raw.githubusercontent.com CDN URLs."""
    import re
    # github.com/.../blob/branch/path → raw.githubusercontent.com/.../branch/path
    m = re.match(r'https?://github\.com/([^/]+/[^/]+)/blob/([^?#]+)', url)
    if m:
        return f'https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}'
    # Strip stray ?raw / ?raw=true suffixes that users copy from GitHub
    url = re.sub(r'\?raw(=true)?$', '', url, flags=re.IGNORECASE)
    return url


def _fetch_url_badge_image(url: str) -> Optional[Image.Image]:
    """Download a badge image from a URL with 7-day disk cache. Returns None on any error."""
    import requests as _requests
    from ..config import logger

    if not url or not url.startswith(("http://", "https://")):
        return None

    # Normalize before caching so blob URLs and raw URLs share the same cache entry
    url = _normalize_badge_url(url)

    cache_dir = Path(settings.CONFIG_DIR) / "url_badge_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_path = cache_dir / f"{url_hash}.png"

    # Return cached copy if fresh (7-day TTL)
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < 604800:
            try:
                return Image.open(cache_path).convert("RGBA")
            except Exception:
                cache_path.unlink(missing_ok=True)

    # Download and cache
    try:
        resp = _requests.get(url, timeout=10, headers={"User-Agent": "Simposter/1.0"})
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img.save(str(cache_path), "PNG")
        logger.debug("[OVERLAY] Cached URL badge: %s → %s", url[:80], cache_path.name)
        return img
    except Exception as e:
        logger.warning("[OVERLAY] Failed to fetch URL badge '%s': %s", url[:80], e)
        return None


# Friendly display labels for auto-detected slugs (streaming_platform and studio fields).
# Used as fallback when badge_texts is empty — so "apple-tv-plus" renders as "Apple TV+"
# rather than "APPLE-TV-PLUS" even for configs that pre-date the default text pre-population.
_SLUG_DISPLAY_LABELS: dict[str, str] = {
    # Streaming platforms
    "netflix": "Netflix", "prime-video": "Prime Video", "disney-plus": "Disney+",
    "max": "Max", "hulu": "Hulu", "apple-tv-plus": "Apple TV+",
    "paramount-plus": "Paramount+", "peacock": "Peacock", "tubi": "Tubi",
    "crunchyroll": "Crunchyroll", "shudder": "Shudder", "mubi": "MUBI",
    # Studios / networks
    "a24": "A24", "amazon-mgm": "Amazon MGM", "apple-original": "Apple Original",
    "disney": "Disney", "marvel-studios": "Marvel Studios", "pixar": "Pixar",
    "warner-bros": "Warner Bros.", "universal": "Universal", "paramount": "Paramount",
    "sony-pictures": "Sony Pictures", "20th-century": "20th Century", "lionsgate": "Lionsgate",
    "blumhouse": "Blumhouse", "focus-features": "Focus Features", "dreamworks": "DreamWorks",
    "amblin": "Amblin", "legendary": "Legendary", "bad-robot": "Bad Robot",
    "hbo": "HBO", "fx": "FX", "amc": "AMC", "showtime": "Showtime", "starz": "Starz",
    "cbs": "CBS", "nbc": "NBC", "abc": "ABC", "fox": "FOX",
}


def _apply_metadata_badge(
    canvas: Image.Image, element: Dict[str, Any], x: int, y: int,
    metadata: Dict[str, Any], default_field: str = "video_resolution", default_font_size: int = 40,
) -> Image.Image:
    """Unified metadata badge renderer for video, audio, edition, and legacy types.
    Supports per-value badge modes: none (skip), text (render text), image (render asset)."""
    from ..config import logger

    metadata_field = element.get("metadata_field") or default_field
    value = metadata.get(metadata_field, "")
    if not value:
        logger.info("[OVERLAY]   -> Metadata badge: no value for field '%s' (metadata keys: %s)", metadata_field, list(metadata.keys()))
        return canvas

    logger.info("[OVERLAY]   -> Metadata badge: %s = '%s'", metadata_field, value)

    # Check per-value mode; fall back to '__other__' catch-all, then "text"
    badge_modes = element.get("badge_modes") or {}
    _key = value.lower()
    mode = badge_modes.get(_key)
    if mode is None:
        mode = badge_modes.get("__other__", "text")

    if mode == "none":
        logger.info("[OVERLAY]   -> Mode is 'none' for value '%s', skipping", value)
        return canvas

    if mode == "image":
        badge_assets = element.get("badge_assets") or {}
        asset_id = badge_assets.get(value.lower())
        if asset_id:
            try:
                result = _render_badge_asset(canvas, element, x, y, asset_id, value=value)
                if result is not None:
                    logger.info("[OVERLAY]   -> Rendered metadata badge as image (asset=%s)", asset_id)
                    return result
            except Exception as e:
                logger.warning(f"[OVERLAY] Failed to render metadata badge asset: {e}")
        logger.info("[OVERLAY]   -> Image mode but asset not found, falling through to text")

    if mode == "url":
        badge_urls = element.get("badge_urls") or {}
        url = (badge_urls.get(value.lower()) or "").strip()
        # Auto-fall back to TMDb-derived logo URL stored in metadata during pre-pass
        if not url:
            auto_key = f"{metadata_field}_logo_url"
            url = (metadata.get(auto_key) or "").strip()
        if url:
            img = _fetch_url_badge_image(url)
            if img is not None:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                val_key = value.lower()
                badge_scales = element.get("badge_scales") or {}
                badge_anchors = element.get("badge_anchors") or {}
                scale_multiplier = (badge_scales[val_key] if val_key in badge_scales
                                    else badge_scales.get("__other__") if "__other__" in badge_scales
                                    else element.get("scale"))
                anchor = (badge_anchors[val_key] if val_key in badge_anchors
                          else badge_anchors.get("__other__") if "__other__" in badge_anchors
                          else element.get("anchor", "center"))
                if scale_multiplier and scale_multiplier > 0:
                    ow, oh = img.size
                    img = img.resize((int(ow * scale_multiplier), int(oh * scale_multiplier)), Image.LANCZOS)
                ow, oh = img.size
                paste_x, paste_y = _calc_paste_position(x, y, ow, oh, anchor or "center")
                # alpha_composite (not paste) is required: paste() linearly blends the alpha
                # channel even with an RGBA mask, causing semi-transparent edge pixels to set
                # canvas alpha < 255, which then renders as black on convert("RGB").
                # alpha_composite uses the "over" operation which always keeps dst alpha = 255
                # when the destination is fully opaque.
                badge_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                badge_layer.paste(img, (paste_x, paste_y))
                canvas = Image.alpha_composite(canvas, badge_layer)
                logger.info("[OVERLAY]   -> Rendered metadata badge from URL: %s", url[:80])
                return canvas
        logger.info("[OVERLAY]   -> URL mode: no URL or fetch failed for '%s', falling through to text", value)

    if mode == "asset":
        from ..simposter_assets import get_asset_url
        asset_url = get_asset_url(value.lower())
        if asset_url:
            img = _fetch_url_badge_image(asset_url)
            if img is not None:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                val_key = value.lower()
                badge_scales = element.get("badge_scales") or {}
                badge_anchors = element.get("badge_anchors") or {}
                scale_multiplier = (badge_scales[val_key] if val_key in badge_scales
                                    else badge_scales.get("__other__") if "__other__" in badge_scales
                                    else element.get("scale"))
                anchor = (badge_anchors[val_key] if val_key in badge_anchors
                          else badge_anchors.get("__other__") if "__other__" in badge_anchors
                          else element.get("anchor", "center"))
                if scale_multiplier and scale_multiplier > 0:
                    ow, oh = img.size
                    img = img.resize((int(ow * scale_multiplier), int(oh * scale_multiplier)), Image.LANCZOS)
                ow, oh = img.size
                paste_x, paste_y = _calc_paste_position(x, y, ow, oh, anchor or "center")
                badge_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                badge_layer.paste(img, (paste_x, paste_y))
                canvas = Image.alpha_composite(canvas, badge_layer)
                logger.info("[OVERLAY]   -> Rendered metadata badge from simposter asset: %s", asset_url[:80])
                return canvas
        logger.info("[OVERLAY]   -> Asset mode: no simposter asset for '%s', falling through to text", value)

    # Text rendering using element font settings
    font_family = element.get("font_family", "arial")
    font_size = element.get("font_size", default_font_size)
    font_color_hex = element.get("font_color", "#FFFFFF")
    font = _load_font(font_family, font_size)

    if font_color_hex and font_color_hex.startswith("#") and len(font_color_hex) >= 7:
        rgb = tuple(int(font_color_hex[i:i+2], 16) for i in (1, 3, 5))
    else:
        rgb = (255, 255, 255)

    # Use custom display text if set, fall back to friendly slug label, then uppercase raw value
    badge_texts = element.get("badge_texts") or {}
    display_text = badge_texts.get(value.lower()) or _SLUG_DISPLAY_LABELS.get(value.lower()) or value.upper()

    logger.info("[OVERLAY]   -> Rendering metadata badge text '%s' (font=%s size=%s color=%s) at (%d, %d)",
                display_text, font_family, font_size, font_color_hex, x, y)

    draw = ImageDraw.Draw(canvas)
    anchor = _get_text_anchor(element)
    draw.text((x, y), display_text, fill=(*rgb, 255), font=font, anchor=anchor)
    return canvas


def _apply_custom_image(canvas: Image.Image, element: Dict[str, Any], x: int, y: int) -> Image.Image:
    """Apply custom image overlay from asset library."""
    from .. import database as db

    asset_id = element.get("asset_id")
    if not asset_id:
        return canvas

    asset = db.get_overlay_asset(asset_id)
    if not asset:
        return canvas

    asset_path = Path(settings.CONFIG_DIR) / asset["file_path"]
    if not asset_path.exists():
        return canvas

    overlay_img = Image.open(asset_path).convert("RGBA")

    W, H = canvas.size

    # Apply scale multiplier first (if provided)
    scale_multiplier = element.get("scale")
    if scale_multiplier and scale_multiplier > 0:
        ow, oh = overlay_img.size
        overlay_img = overlay_img.resize((int(ow * scale_multiplier), int(oh * scale_multiplier)), Image.LANCZOS)

    # Apply percentage-based width/height and max-pixel constraints
    overlay_img = _apply_canvas_size_constraints(overlay_img, element, W, H)

    ow, oh = overlay_img.size
    anchor = element.get("anchor", "center")
    paste_x, paste_y = _calc_paste_position(x, y, ow, oh, anchor)

    badge_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    badge_layer.paste(overlay_img, (paste_x, paste_y))
    return Image.alpha_composite(canvas, badge_layer)


def _apply_text_label(canvas: Image.Image, element: Dict[str, Any], x: int, y: int) -> Image.Image:
    """Apply text label overlay."""
    text = element.get("text", "")
    if not text:
        return canvas

    font_family = element.get("font_family", "arial")
    font_size = element.get("font_size", 40)
    font_color = element.get("font_color", "#FFFFFF")

    if font_color.startswith("#") and len(font_color) >= 7:
        rgb = tuple(int(font_color[i:i+2], 16) for i in (1, 3, 5))
    else:
        rgb = (255, 255, 255)

    font = _load_font(font_family, font_size)
    draw = ImageDraw.Draw(canvas)
    anchor = _get_text_anchor(element)
    draw.text((x, y), text, fill=(*rgb, 255), font=font, anchor=anchor)
    return canvas


def _apply_label_badge(canvas: Image.Image, element: Dict[str, Any], x: int, y: int, metadata: Dict[str, Any]) -> Image.Image:
    """Apply badge based on Plex label presence."""
    label_name = element.get("label_name", "")
    if not label_name:
        return canvas

    labels = metadata.get("labels", [])
    if label_name not in labels:
        return canvas

    # Render the label as a badge
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except:
        font = ImageFont.load_default()

    anchor = _get_text_anchor(element)
    draw.text((x, y), label_name, fill=(255, 255, 255, 255), font=font, anchor=anchor)
    return canvas
