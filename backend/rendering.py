# backend/rendering.py
from __future__ import annotations

from io import BytesIO
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Optional
from pathlib import Path

import requests
from PIL import Image

from .config import logger, settings
from .templates import get_renderer


def _download_image(url: str) -> Image.Image:
    """
    Fetch an image from a URL and return a PIL Image (RGBA).
    Supports both raster images and SVG files (if cairosvg is installed).
    Raises ValueError if the URL is empty or the fetch fails.
    """
    if not url:
        raise ValueError("Empty image URL")

    # Retry logic with exponential backoff for slow TMDB servers
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Increase timeout from 20s to 60s for slow connections
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            break
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(f"Timeout downloading image (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {url}")
                import time
                time.sleep(wait_time)
            else:
                logger.exception("Failed to download image after %d retries: %s", max_retries, url)
                raise ValueError(f"Failed to download image (timeout after {max_retries} retries): {url}")
        except Exception as e:
            logger.exception("Failed to download image: %s", url)
            raise ValueError(f"Failed to download image: {url}") from e

    content_type = resp.headers.get("content-type", "").lower()
    is_svg = (
        url.lower().split("?")[0].endswith(".svg")
        or "image/svg" in content_type
    )

    if is_svg:
        # Strategy 1: CairoSVG (fast, high quality but needs system Cairo)
        try:
            from cairosvg import svg2png  # type: ignore
            try:
                # Pass the URL so external refs resolve correctly
                png_data = svg2png(bytestring=resp.content, url=url)
                img = Image.open(BytesIO(png_data))
                img.load()
                logger.debug("Successfully converted SVG to PNG via CairoSVG: %s", url)
                return img.convert("RGBA")
            except Exception as e:
                logger.exception("CairoSVG failed to convert SVG from URL: %s", url)
        except Exception as e:  # pragma: no cover - optional dependency
            logger.warning("SVG Cairo backend unavailable (cairosvg): %s", e)

        # Strategy 2: pillow-resvg plugin (bundles resvg for Windows/mac/Linux)
        try:
            import pillow_resvg  # type: ignore  # noqa: F401 - registers SVG opener with Pillow
            try:
                img = Image.open(BytesIO(resp.content))
                img.load()
                logger.debug("Successfully converted SVG to PNG via pillow-resvg: %s", url)
                return img.convert("RGBA")
            except Exception as e:
                logger.exception("pillow-resvg failed to decode SVG: %s", url)
        except Exception as e:
            logger.warning("SVG pillow-resvg backend unavailable: %s", e)

        # Strategy 3: external resvg binary (no system installs required)
        # Look for explicit settings.RESVG_PATH, else common repo locations
        resvg_path: Optional[str] = None
        try:
            candidate = settings.RESVG_PATH.strip() if getattr(settings, "RESVG_PATH", "") else ""
            if candidate:
                p = Path(candidate)
                if p.exists():
                    resvg_path = str(p)
            if not resvg_path:
                # Try ./bin/resvg(.exe) and ./tools/resvg/resvg(.exe)
                for rel in ("bin/resvg.exe", "bin/resvg", "tools/resvg/resvg.exe", "tools/resvg/resvg"):
                    p = (Path(__file__).resolve().parent.parent / rel).resolve()
                    if p.exists():
                        resvg_path = str(p)
                        break
        except Exception:
            resvg_path = None

        if resvg_path:
            try:
                with tempfile.TemporaryDirectory() as td:
                    svg_fp = Path(td) / "in.svg"
                    png_fp = Path(td) / "out.png"
                    svg_fp.write_bytes(resp.content)
                    # Render at default size; allow resvg to use viewBox. Users can override with RESVG_PATH wrapper if needed.
                    subprocess.run([resvg_path, str(svg_fp), str(png_fp)], check=True, timeout=20)
                    img = Image.open(png_fp)
                    img.load()
                    logger.debug("Successfully converted SVG to PNG via resvg binary: %s", url)
                    return img.convert("RGBA")
            except Exception as e:
                logger.exception("resvg binary failed to convert SVG: %s (path=%s)", url, resvg_path)

        # Strategy 4: Inkscape CLI (widely available)
        inkscape_path: Optional[str] = None
        try:
            cand = settings.INKSCAPE_PATH.strip() if getattr(settings, "INKSCAPE_PATH", "") else ""
            if cand:
                p = Path(cand)
                if p.exists():
                    inkscape_path = str(p)
            if not inkscape_path:
                # Common install locations on Windows/macOS/Linux
                common = [
                    "C:/Program Files/Inkscape/bin/inkscape.exe",
                    "C:/Program Files/Inkscape/inkscape.exe",
                    "/usr/bin/inkscape",
                    "/usr/local/bin/inkscape",
                ]
                for rel in common:
                    p = Path(rel)
                    if p.exists():
                        inkscape_path = str(p)
                        break
            if not inkscape_path:
                # Fallback to PATH, but only if actually present
                found = shutil.which("inkscape")
                if found:
                    inkscape_path = found
        except Exception:
            inkscape_path = None

        if inkscape_path:
            try:
                with tempfile.TemporaryDirectory() as td:
                    svg_fp = Path(td) / "in.svg"
                    png_fp = Path(td) / "out.png"
                    svg_fp.write_bytes(resp.content)
                    # Inkscape 1.x syntax
                    cmd = [inkscape_path, "--export-type=png", f"--export-filename={png_fp}", str(svg_fp)]
                    subprocess.run(cmd, check=True, timeout=30)
                    img = Image.open(png_fp)
                    img.load()
                    logger.debug("Successfully converted SVG to PNG via Inkscape: %s", url)
                    return img.convert("RGBA")
            except FileNotFoundError:
                logger.debug("Inkscape not found at path=%s; skipping SVG conversion", inkscape_path)
            except Exception:
                logger.exception("Inkscape failed to convert SVG: %s (path=%s)", url, inkscape_path)

        # If all strategies failed, abort gracefully so rendering can continue without a logo
        raise ValueError(f"SVG not supported or failed to convert: {url}")

    try:
        img = Image.open(BytesIO(resp.content))
        img.load()
        return img.convert("RGBA")
    except Exception as e:
        logger.exception("Failed to decode image from URL: %s", url)
        raise ValueError(f"Failed to decode image: {url}") from e


def render_poster_image(
    template_id: str,
    background_url: str,
    logo_url: Optional[str],
    options: Optional[Dict[str, Any]] = None,
) -> Image.Image:
    """
    Single, canonical entry point for rendering.

    - Downloads the background and optional logo.
    - Looks up the template renderer via templates.get_renderer(...)
    - Passes (bg, logo, options) to that renderer.

    It does *not* know about TMDB, Radarr, presets, poster_filter, etc.
    That logic stays in the API layer (batch/webhooks/plexsend).
    """
    if options is None:
        options = {}

    # 1) Download images
    bg = _download_image(background_url)

    logo = None
    if logo_url:
        try:
            logo = _download_image(logo_url)
        except ValueError:
            # If logo fails, we just render without a logo
            logger.warning("Logo download failed, continuing without logo: %s", logo_url)
            logo = None

    logger.debug(
        "[RENDER] template=%s bg=%s logo=%s options_keys=%s",
        template_id,
        background_url,
        logo_url,
        sorted(options.keys()) if options else [],
    )

    # 2) Template renderer
    renderer = get_renderer(template_id)
    img = renderer(bg, logo, options)
    return img


def render_with_overlay_cache(
    template_id: str,
    preset_id: str,
    poster_url: str,
    logo_url: Optional[str],
    render_options: Dict[str, Any],
    use_cache: bool = True,
) -> Image.Image:
    """
    Render with optional overlay cache.

    If cache is enabled and overlay exists, uses fast path:
    - Download poster
    - Apply zoom/shift
    - Composite cached overlay
    - For uniformlogo: apply logo positioning, text overlay, border
    Otherwise falls back to full render_poster_image.
    """

    from .templates.universal import _resize_cover, _hex_to_rgb, _solid_color_logo, _render_text_overlay, _add_grain
    from PIL import ImageOps

    overlay_path = Path(settings.CONFIG_DIR) / "overlays" / template_id / f"{preset_id}.png"

    if use_cache and overlay_path.exists():
        try:
            logger.info(f"[CACHE] Overlay cache enabled and found: {overlay_path}")

            # Download poster and logo in parallel
            from concurrent.futures import ThreadPoolExecutor
            
            def download_image(url: str):
                """Helper to download image from URL."""
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                return BytesIO(resp.content)
            
            bg = None
            logo_bytes = None
            
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both downloads
                bg_future = executor.submit(download_image, poster_url)
                logo_future = executor.submit(download_image, logo_url) if logo_url else None
                
                # Get background (always needed)
                bg = Image.open(bg_future.result()).convert("RGBA")
                
                # Get logo if present
                if logo_future:
                    logo_bytes = logo_future.result()

            # Base canvas with poster zoom/shift
            canvas_w, canvas_h = 2000, 3000
            poster_zoom = float(render_options.get("poster_zoom", 1.0))
            poster_shift_y = float(render_options.get("poster_shift_y", 0.0))

            base = _resize_cover(bg, canvas_w, canvas_h, zoom=poster_zoom)
            shift_px = int(poster_shift_y * canvas_h)

            canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
            canvas.paste(base, (0, shift_px))

            # Composite cached overlay
            overlay = Image.open(overlay_path).convert("RGBA")
            canvas = Image.alpha_composite(canvas, overlay)

            # Apply grain after overlay (fresh per-render for proper blending)
            grain_amount = float(render_options.get("grain_amount", 0.0))
            if grain_amount > 0:
                canvas_rgb = canvas.convert("RGB")
                canvas_rgb = _add_grain(canvas_rgb, grain_amount)
                canvas = canvas_rgb.convert("RGBA")

            # Logo handling
            if logo_url and logo_bytes:
                logo = Image.open(logo_bytes).convert("RGBA")

                logo_mode = str(render_options.get("logo_mode", "stock") or "stock")
                logo_hex = str(render_options.get("logo_hex", "#FFFFFF") or "#FFFFFF")

                if logo_mode == "match":
                    poster_avg = bg.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
                    color = poster_avg[:3]
                    logo = _solid_color_logo(logo, color)
                elif logo_mode == "hex":
                    color = _hex_to_rgb(logo_hex)
                    logo = _solid_color_logo(logo, color)

                if template_id == "uniformlogo":
                    max_w = render_options.get("uniform_logo_max_w", 600)
                    max_h = render_options.get("uniform_logo_max_h", 240)
                    offset_x_pct = render_options.get("uniform_logo_offset_x", 0.5)
                    offset_y_pct = render_options.get("uniform_logo_offset_y", 0.78)

                    cx = int(canvas_w * offset_x_pct)
                    cy = int(canvas_h * offset_y_pct)

                    lw, lh = logo.size
                    scale = max_w / lw
                    if lh * scale > max_h:
                        scale = max_h / lh

                    if render_options.get("uniform_logo_override_enabled", False):
                        scale = render_options.get("uniform_logo_override_scale", scale)
                        offset_y_pct = render_options.get("uniform_logo_override_offset_y", offset_y_pct)
                        cy = int(canvas_h * offset_y_pct)

                    new_w = int(lw * scale)
                    new_h = int(lh * scale)
                    logo_res = logo.resize((new_w, new_h), Image.LANCZOS)

                    x = cx - new_w // 2
                    y = cy - new_h // 2
                    canvas.paste(logo_res, (x, y), logo_res)

                    logger.info("[CACHE] Applied uniformlogo positioning with cached overlay")
                else:
                    logger.info(f"[CACHE] Template {template_id} logo positioning not implemented in cache path; falling back")
                    return render_poster_image(template_id, poster_url, logo_url, render_options)

            # Text overlay
            text_overlay_enabled = bool(render_options.get("text_overlay_enabled", False))
            if text_overlay_enabled:
                custom_text = str(render_options.get("custom_text", ""))
                if custom_text:
                    canvas = _render_text_overlay(canvas, custom_text, render_options)

            # Border
            if render_options.get("border_enabled", False):
                px = render_options.get("border_px", 0)
                if px > 0:
                    border_color = render_options.get("border_color", "#FFFFFF")
                    canvas = ImageOps.expand(canvas, border=px, fill=border_color)

            logger.info("[CACHE] Successfully rendered with cached overlay")
            return canvas.convert("RGB")

        except Exception as e:
            logger.warning(f"[CACHE] Failed to use overlay cache, falling back to full render: {e}")

    else:
        logger.info(f"[CACHE] Overlay cache {'disabled' if not use_cache else 'missing'} for template={template_id} preset={preset_id}; using full render")

    return render_poster_image(template_id, poster_url, logo_url, render_options)


def generate_overlay(
    options: Dict[str, Any],
    canvas_w: int = 2000,
    canvas_h: int = 3000
) -> Image.Image:
    """
    Generate a cached overlay containing deterministic effects (matte, fade, vignette, wash).
    Grain is applied fresh per-render for proper blending and visibility.
    
    Returns RGBA image that can be composited over any poster.
    """
    from PIL import ImageDraw, ImageFilter
    
    # Extract options with defaults
    matte_height_ratio = float(options.get("matte_height_ratio", 0.0))
    fade_height_ratio = float(options.get("fade_height_ratio", 0.0))
    vignette_strength = float(options.get("vignette_strength", 0.0))
    v12_wash_strength = float(options.get("v12_wash_strength", 0.0))
    
    # Clamp values
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))
    
    matte_height_ratio = clamp(matte_height_ratio, 0.0, 0.5)
    fade_height_ratio = clamp(fade_height_ratio, 0.0, 0.5)
    vignette_strength = clamp(vignette_strength, 0.0, 1.0)
    v12_wash_strength = clamp(v12_wash_strength, 0.0, 1.0)
    
    # Start with transparent canvas
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    
    # --- MATTE + FADE ---
    # These create opacity gradients that darken the bottom portion
    matte_h = int(canvas_h * matte_height_ratio)
    fade_h = int(canvas_h * fade_height_ratio)
    
    if matte_h > 0 or fade_h > 0:
        # Create black layer with alpha gradient
        matte_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        pixels = matte_layer.load()
        
        matte_start = canvas_h - matte_h
        fade_start = max(0, matte_start - fade_h)
        
        for y in range(canvas_h):
            if y >= matte_start:
                alpha = 255  # solid black
            elif y >= fade_start:
                t = (y - fade_start) / max(fade_h, 1)
                alpha = int(255 * t)
            else:
                alpha = 0  # transparent
            
            for x in range(canvas_w):
                pixels[x, y] = (0, 0, 0, alpha)
        
        overlay = Image.alpha_composite(overlay, matte_layer)
    
    # --- VIGNETTE ---
    # Creates radial darkening from edges
    if vignette_strength > 0:
        vig_layer = Image.new("L", (canvas_w, canvas_h), 0)
        draw = ImageDraw.Draw(vig_layer)
        
        steps = 60
        max_r = max(canvas_w, canvas_h)
        
        for i in range(steps):
            r = max_r * (i / steps)
            a = int(255 * vignette_strength * (i / steps))
            bbox = (canvas_w / 2 - r, canvas_h / 2 - r, canvas_w / 2 + r, canvas_h / 2 + r)
            draw.ellipse(bbox, fill=a)
        
        vig_layer = vig_layer.filter(ImageFilter.GaussianBlur(90))
        
        # Convert to RGBA black with alpha from vignette
        vig_rgba = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        vig_pixels = vig_rgba.load()
        vig_alpha = vig_layer.load()
        
        for y in range(canvas_h):
            for x in range(canvas_w):
                vig_pixels[x, y] = (0, 0, 0, vig_alpha[x, y])
        
        overlay = Image.alpha_composite(overlay, vig_rgba)
    
    # --- WASH EFFECT ---
    # Neutral grey tone overlay for cinematic washout
    if v12_wash_strength > 0:
        wash_layer = Image.new("RGBA", (canvas_w, canvas_h), (32, 32, 32, int(255 * v12_wash_strength)))
        overlay = Image.alpha_composite(overlay, wash_layer)
    
    return overlay
