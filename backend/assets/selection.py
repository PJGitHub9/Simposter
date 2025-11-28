import requests
from io import BytesIO
from PIL import Image
import numpy as np


# ---------------------------
# Brightness Calculation
# ---------------------------

def compute_logo_brightness(url: str) -> float:
    """
    Returns average brightness of all non-transparent pixels (0–255).
    Used to detect "white" vs "colored" logos.
    """
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")

        arr = np.array(img)
        rgb = arr[..., :3]
        alpha = arr[..., 3]

        mask = alpha > 128   # ignore transparent pixels
        if mask.sum() == 0:
            return 0  # treat fully transparent as dark

        gray = rgb.mean(axis=2)
        return float(gray[mask].mean())

    except Exception:
        return 0  # fallback for broken downloads


# ---------------------------
# Poster Selection
# ---------------------------

def pick_poster(posters: list, filter_mode: str):
    """Exact poster-selection matching the frontend."""
    if not posters:
        return None

    if filter_mode == "textless":
        return next((p for p in posters if not p.get("has_text")), posters[0])

    if filter_mode == "text":
        return next((p for p in posters if p.get("has_text")), posters[0])

    return posters[0]  # "all"


# ---------------------------
# Logo Selection
# ---------------------------

def pick_logo(logos: list, preference: str):
    """
    Matches frontend: detect brightness of each logo (white ≈ bright).
    preference: "white" | "color" | "first"
    """
    if not logos:
        return None

    # get brightness for each logo URL
    scored = []
    for logo in logos:
        url = logo.get("url")
        if not url:
            continue

        brightness = compute_logo_brightness(url)
        scored.append((brightness, logo))

    if not scored:
        return None

    # sort by brightness (brightest → darkest)
    scored.sort(key=lambda x: x[0], reverse=True)

    if preference == "white":
        return scored[0][1]   # brightest

    if preference == "color":
        return scored[-1][1]  # darkest

    return logos[0]  # fallback: first
