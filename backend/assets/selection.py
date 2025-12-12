import requests
from io import BytesIO
from PIL import Image
import numpy as np
import colorsys


# ---------------------------
# Logo Color Analysis
# ---------------------------

def analyze_logo_color(url: str) -> dict:
    """
    Analyzes logo color properties using HSV color space.
    Returns dict with 'brightness' (0-255) and 'saturation' (0-1).

    - White logos: high brightness, low saturation
    - Colored logos: high saturation
    - Dark logos: low brightness
    """
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")

        arr = np.array(img)
        rgb = arr[..., :3]
        alpha = arr[..., 3]

        # Filter to non-transparent pixels
        mask = alpha > 128
        if mask.sum() == 0:
            return {"brightness": 0, "saturation": 0, "valid": False}

        # Get RGB values of non-transparent pixels
        valid_pixels = rgb[mask]

        # Convert RGB (0-255) to HSV
        # Normalize RGB to 0-1 for colorsys
        valid_pixels_norm = valid_pixels / 255.0

        hsv_values = []
        for pixel in valid_pixels_norm:
            h, s, v = colorsys.rgb_to_hsv(pixel[0], pixel[1], pixel[2])
            hsv_values.append((h, s, v))

        hsv_array = np.array(hsv_values)

        # Calculate average saturation and brightness
        avg_saturation = float(hsv_array[:, 1].mean())  # 0-1
        avg_value = float(hsv_array[:, 2].mean())  # 0-1
        avg_brightness = avg_value * 255  # Convert to 0-255 for backward compatibility

        return {
            "brightness": avg_brightness,
            "saturation": avg_saturation,
            "valid": True
        }

    except Exception:
        return {"brightness": 0, "saturation": 0, "valid": False}


def compute_logo_brightness(url: str) -> float:
    """
    Legacy function for backward compatibility.
    Returns average brightness of all non-transparent pixels (0–255).
    """
    result = analyze_logo_color(url)
    return result["brightness"]


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
    Analyzes logo color properties to pick the best match.

    preference options:
    - "white": High brightness + low saturation (actual white/light logos)
    - "color": High saturation (vibrant colored logos)
    - "first": First available logo (no analysis)
    """
    if not logos:
        return None

    if preference == "first":
        return logos[0]

    # Analyze color properties for each logo
    analyzed = []
    for logo in logos:
        url = logo.get("url")
        if not url:
            continue

        color_data = analyze_logo_color(url)
        if not color_data["valid"]:
            continue

        analyzed.append((color_data, logo))

    if not analyzed:
        return logos[0]  # fallback to first if analysis fails

    if preference == "white":
        # White logo: maximize brightness, minimize saturation
        # Score = brightness * (1 - saturation)
        # This favors bright, desaturated (white/gray) logos
        def white_score(item):
            data = item[0]
            # Normalize brightness to 0-1 scale
            brightness_norm = data["brightness"] / 255.0
            # Invert saturation (low saturation = high score)
            desaturation = 1.0 - data["saturation"]
            # Combined score favoring bright + desaturated
            return brightness_norm * 0.7 + desaturation * 0.3

        best = max(analyzed, key=white_score)
        return best[1]

    if preference == "color":
        # Colored logo: maximize saturation
        # Among saturated logos, prefer brighter ones
        def color_score(item):
            data = item[0]
            brightness_norm = data["brightness"] / 255.0
            # Heavily weight saturation, slightly weight brightness
            return data["saturation"] * 0.8 + brightness_norm * 0.2

        best = max(analyzed, key=color_score)
        return best[1]

    return logos[0]  # fallback: first
