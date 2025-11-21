# backend/templates/universal.py
from typing import Dict, Any, Optional
from PIL import Image, ImageFilter, ImageDraw
import random


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
    """
    Film grain; amount 0..0.6
    """
    if amount <= 0:
        return img

    img = img.convert("RGB")
    w, h = img.size
    grain = Image.new("L", (w, h))
    gp = grain.load()

    rng = random.Random()
    for y in range(h):
        for x in range(w):
            v = 128 + int(rng.uniform(-128 * amount, 128 * amount))
            gp[x, y] = max(0, min(255, v))

    grain = grain.filter(ImageFilter.GaussianBlur(1.5))
    grain_rgb = Image.merge("RGB", (grain, grain, grain))

    # blend strength directly = amount
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


# ============================================================
# Universal Renderer
# ============================================================

def render(
    background: Image.Image,
    logo: Optional[Image.Image],
    options: Dict[str, Any] | None,
) -> Image.Image:
    """
    Single renderer obeying slider options.
    Templates (DarkMatte, Clean, etc.) ONLY change the 'options' dict;
    all sliders are always available.

    Options (all floats, usually 0..1 coming from the UI):
      - poster_zoom
      - poster_shift_y
      - matte_height_ratio
      - fade_height_ratio
      - vignette_strength
      - grain_amount
      - logo_scale
      - logo_offset        (0..1 → top..bottom of canvas)
      - logo_mode          ("stock" | "match" | "hex")
      - logo_hex           ("#RRGGBB")
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

    logo_scale = float(options.get("logo_scale", 0.5))         # fraction of canvas width
    logo_offset = float(options.get("logo_offset", 0.75))      # 0..1 top→bottom

    logo_mode = str(options.get("logo_mode", "stock") or "stock")
    logo_hex = str(options.get("logo_hex", "#FFFFFF") or "#FFFFFF")

    # clamp helpers
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    poster_zoom = max(poster_zoom, 0.1)
    poster_shift_y = clamp(poster_shift_y, -0.5, 0.5)

    matte_height_ratio = clamp(matte_height_ratio, 0.0, 0.5)
    fade_height_ratio = clamp(fade_height_ratio, 0.0, 0.5)

    vignette_strength = clamp(vignette_strength, 0.0, 1.0)
    grain_amount = clamp(grain_amount, 0.0, 0.6)

    logo_scale = clamp(logo_scale, 0.1, 1.0)
    logo_offset = clamp(logo_offset, 0.0, 1.0)

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
    base_rgb = _add_vignette(base_rgb, vignette_strength)
    base_rgb = _add_grain(base_rgb, grain_amount)

    base = base_rgb.convert("RGBA")

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
        max_w = int(canvas_w * logo_scale)
        if max_w > 0 and logo.width > 0:
            scale = max_w / logo.width
            new_size = (int(logo.width * scale), int(logo.height * scale))
            logo = logo.resize(new_size, Image.LANCZOS)

        # Absolute position: 0..1 top→bottom, based on logo height
        y_logo = int((canvas_h - logo.height) * logo_offset)
        x_logo = (canvas_w - logo.width) // 2

        base.alpha_composite(logo, (x_logo, y_logo))

    return base.convert("RGB")
