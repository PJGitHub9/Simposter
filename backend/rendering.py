# backend/rendering.py
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Optional

import requests
from PIL import Image

from .config import logger
from .templates import get_renderer


def _download_image(url: str) -> Image.Image:
    """
    Fetch an image from a URL and return a PIL Image (RGBA).
    Raises ValueError if the URL is empty or the fetch fails.
    """
    if not url:
        raise ValueError("Empty image URL")

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        logger.exception("Failed to download image: %s", url)
        raise ValueError(f"Failed to download image: {url}") from e

    try:
        img = Image.open(BytesIO(resp.content))
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
