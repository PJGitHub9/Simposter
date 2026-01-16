import requests
from io import BytesIO
from PIL import Image
import numpy as np
import colorsys
from concurrent.futures import ThreadPoolExecutor, as_completed


# ---------------------------
# Logo Mode/Preference Mapping
# ---------------------------

def map_logo_mode_to_preference(logo_mode_or_preference: str) -> str:
    """
    Map logo_mode values to valid pick_logo preference values.

    In templates, logo_mode can be:
    - "original": Use the original/preferred logo (maps to "white" for clean logos)
    - "white": Prefer white/light logos
    - "color": Prefer colored logos
    - "first": Use first available logo
    - "none": Don't use a logo

    pick_logo only understands: "white", "color", "first"
    """
    mapping = {
        "original": "white",  # "original" means original/clean/professional logo
        "white": "white",
        "color": "color",
        "first": "first",
        "none": "first"  # Shouldn't be called with "none", but default to first if it is
    }
    return mapping.get(logo_mode_or_preference, "first")


# ---------------------------
# Logo Color Analysis
# ---------------------------

def _tmdb_thumb(url: str) -> str:
    """Use a smaller TMDb size for faster analysis when possible."""
    try:
        if "image.tmdb.org/t/p/" in url and "/original/" in url:
            return url.replace("/original/", "/w300/")
        return url
    except Exception:
        return url


def analyze_logo_color(url: str) -> dict:
    """
    Fast logo color analysis using HSV color space on a thumbnail image.
    Returns dict with 'brightness' (0-255) and 'saturation' (0-1).
    """
    try:
        thumb = _tmdb_thumb(url)
        r = requests.get(thumb, timeout=8)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        # Downscale further to cap work (keeps transparency)
        max_w = 256
        if img.width > max_w:
            ratio = max_w / float(img.width)
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

        arr = np.array(img)
        rgb = arr[..., :3]
        alpha = arr[..., 3]

        # Filter to non-transparent pixels; be permissive to keep samples
        mask = alpha > 64
        if mask.sum() == 0:
            return {"brightness": 0, "saturation": 0, "valid": False}

        valid_pixels = rgb[mask]
        # Subsample to speed up on very large masks
        if valid_pixels.shape[0] > 20000:
            valid_pixels = valid_pixels[:: int(valid_pixels.shape[0] / 20000) or 1]

        valid_pixels_norm = valid_pixels / 255.0
        hsv_values = [colorsys.rgb_to_hsv(p[0], p[1], p[2]) for p in valid_pixels_norm]
        hsv_array = np.array(hsv_values)

        avg_saturation = float(hsv_array[:, 1].mean())
        avg_value = float(hsv_array[:, 2].mean())
        avg_brightness = avg_value * 255

        return {"brightness": avg_brightness, "saturation": avg_saturation, "valid": True}
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
    """Exact poster-selection matching the frontend, strict on requested type."""
    if not posters:
        return None

    if filter_mode == "textless":
        # Require a textless poster; if none, return None so caller can trigger fallback
        return next((p for p in posters if not p.get("has_text")), None)

    if filter_mode == "text":
        # Require a poster with text; if none, return None so caller can trigger fallback
        return next((p for p in posters if p.get("has_text")), None)

    return posters[0]  # "all"


# ---------------------------
# Logo Selection
# ---------------------------

def _sort_logos_for_analysis(logos: list, language_pref: str = "en") -> list:
    """
    Sort logos by quality heuristic prioritizing:
    1. Language (textless/null first, then preferred language, then English, then others)
    2. Width (larger first)
    3. Source (TMDB first)
    """
    from ..config import logger

    def key(l: dict):
        w = l.get("width") or 0
        src = l.get("source") or ""
        lang = l.get("language") or None  # None/null = textless logo

        # Language ranking: preferred > English > textless > other
        # Note: We prioritize English/preferred over textless because TMDB sometimes
        # incorrectly marks non-English logos as textless (language=null)
        if lang == language_pref:
            lang_rank = 0  # Preferred language (highest priority)
        elif lang == "en":
            lang_rank = 1  # English (always second priority)
        elif lang is None:
            lang_rank = 2  # Textless logos (may have incorrect metadata)
        else:
            lang_rank = 3  # Other languages (lowest priority)

        src_rank = 0 if src == "tmdb" else 1
        return (lang_rank, -int(w), src_rank)

    sorted_logos = sorted(logos, key=key)
    return sorted_logos


def pick_logo(logos: list, preference: str, white_fallback: str = "use_next", language_pref: str = "en"):
    """
    Faster logo selection with limited concurrent analysis on thumbnails.

    preference options:
    - "white": High brightness + low saturation (actual white/light logos)
    - "color": High saturation (vibrant colored logos)
    - "first": First available logo (no analysis)

    white_fallback options:
    - "use_next": Use next available logo if white not found
    - "skip": Return None (skip logo entirely)

    language_pref: Preferred language code (e.g., "en"). Textless logos (language=None) are always prioritized highest.
    """
    if not logos:
        return None

    # Filter out SVG logos since we don't have cairo/resvg dependencies
    logos = [l for l in logos if not (l.get("url") or "").lower().endswith(".svg")]
    if not logos:
        return None

    if preference == "first":
        return logos[0]

    # Limit analysis to top-N candidates to reduce network/CPU work
    TOP_N = 6
    candidates = _sort_logos_for_analysis(logos, language_pref)[:TOP_N]

    analyzed = []

    def work(l: dict):
        url = l.get("url")
        if not url:
            return None
        data = analyze_logo_color(url)
        if not data.get("valid"):
            return None
        return (data, l)

    # Analyze concurrently for speed
    with ThreadPoolExecutor(max_workers=min(TOP_N, 6)) as ex:
        futures = [ex.submit(work, l) for l in candidates]
        for f in as_completed(futures):
            res = f.result()
            if res:
                analyzed.append(res)

    if not analyzed:
        if preference == "white":
            return None if white_fallback == "skip" else logos[0]
        return None if preference == "white" else logos[0]

    if preference == "white":
        WHITE_SAT_MAX = 0.25
        WHITE_BRIGHT_MIN = 60.0
        white_candidates = [
            item for item in analyzed
            if item[0]["saturation"] <= WHITE_SAT_MAX and item[0]["brightness"] >= WHITE_BRIGHT_MIN
        ]
        if not white_candidates:
            # No white logo found; apply global white fallback
            if white_fallback == "skip":
                return None
            else:  # use_next
                return logos[0]

        def white_score(item):
            data = item[0]
            logo = item[1]
            brightness_norm = data["brightness"] / 255.0
            desaturation = 1.0 - data["saturation"]
            color_score = brightness_norm * 0.7 + desaturation * 0.3

            # Add language preference bonus
            lang = logo.get("language")
            if lang == language_pref:
                lang_bonus = 0.5  # Strong preference for preferred language
            elif lang == "en":
                lang_bonus = 0.3  # Moderate preference for English
            elif lang is None:
                lang_bonus = 0.0  # No bonus for textless (may be mislabeled)
            else:
                lang_bonus = -0.5  # Penalty for other languages

            return color_score + lang_bonus

        best = max(white_candidates, key=white_score)
        return best[1]

    if preference == "color":
        def color_score(item):
            data = item[0]
            brightness_norm = data["brightness"] / 255.0
            return data["saturation"] * 0.8 + brightness_norm * 0.2
        best = max(analyzed, key=color_score)
        return best[1]

    return logos[0]

