"""Ordered poster candidates from TMDb, TVDB, Fanart.tv and MediUX.

One place builds the candidate list every poster-picking path uses, in the
user's ``apiOrder``. A source is only asked when it is in the order and has a
key (TMDb always). MediUX posters always have text, so a textless pick never
selects one (``pick_poster`` checks ``has_text``).
"""
from typing import Any, List, Optional

from . import database as db
from .config import logger, settings
from . import tmdb_client, tvdb_client, fanart_client, mediux_client
from .assets.selection import pick_poster

DEFAULT_ORDER = ["tmdb", "tvdb", "fanart", "mediux"]
_KNOWN = set(DEFAULT_ORDER)


def source_order() -> List[str]:
    try:
        raw = (db.get_ui_settings() or {}).get("apiOrder")
    except Exception:
        raw = None
    if not isinstance(raw, list) or not raw:
        raw = list(DEFAULT_ORDER)
    order: List[str] = []
    for name in raw:
        name = str(name).strip().lower()
        if name in _KNOWN and name not in order:
            order.append(name)
    if "mediux" in order and not mediux_client.get_mediux_key():
        order.remove("mediux")
    return order


def mediux_set_id_of(poster: Optional[dict]) -> Optional[str]:
    if not poster or poster.get("source") != "mediux":
        return None
    return poster.get("mediux_set_id") or None


_WARNED: set = set()


def _safe(label: str, fn, *args) -> Any:
    """Optional source: a failure is logged (warning once per source, then debug) and skipped."""
    try:
        return fn(*args)
    except Exception as e:
        if label in _WARNED:
            logger.debug("[POSTERS] %s lookup failed, skipping: %s", label, e)
        else:
            _WARNED.add(label)
            logger.warning("[POSTERS] %s lookup failed, skipping: %s", label, e)
        return None


def _enough(collected: List[dict], stop_when: Optional[str]) -> bool:
    return bool(stop_when) and pick_poster(collected, stop_when) is not None


def _posters(imgs: Optional[dict]) -> List[dict]:
    return list((imgs or {}).get("posters") or [])


def _language_first(entries: List[dict], details: dict, language_pref: str) -> List[dict]:
    good = {language_pref, "en", (details or {}).get("original_language"), None}
    lang = lambda e: e.get("language") or None
    return ([e for e in entries if lang(e) in good]
            + [e for e in entries if lang(e) not in good])


def _mediux_entries(sets: Optional[list], key: str) -> List[dict]:
    return [s[key] for s in (sets or []) if s.get(key)]


def _prefetched(prefetched: Optional[dict], src: str):
    """(True, imgs) when the caller already fetched ``src``'s images, else (False, None)."""
    if prefetched and src in prefetched:
        return True, prefetched.get(src) or {}
    return False, None


def movie_posters(tmdb_id: int, details: dict, tmdb_imgs: Optional[dict] = None,
                  *, language_pref: str = "en",
                  stop_when: Optional[str] = None,
                  prefetched: Optional[dict] = None) -> List[dict]:
    """``prefetched`` ({"tvdb": imgs, "fanart": imgs}) reuses images the caller
    already fetched instead of asking that source again."""
    details = details or {}
    result: List[dict] = []
    for src in source_order():
        if src == "tmdb":
            if tmdb_imgs is None:
                tmdb_imgs = tmdb_client.get_images_for_movie(
                    tmdb_id, details.get("original_language")) or {}
            result += _posters(tmdb_imgs)
        elif src == "tvdb":
            if not settings.TVDB_API_KEY:
                continue
            have, imgs = _prefetched(prefetched, "tvdb")
            if have:
                result += _posters(imgs)
                if _enough(result, stop_when):
                    break
                continue
            ext = _safe("TVDB id", tmdb_client.get_movie_external_ids, tmdb_id) or {}
            tvdb_id = ext.get("tvdb_id")
            if tvdb_id:
                result += _posters(_safe("TVDB", tvdb_client.get_movie_images, int(tvdb_id)))
        elif src == "fanart":
            if settings.FANART_API_KEY:
                have, imgs = _prefetched(prefetched, "fanart")
                result += _posters(imgs if have else
                                   _safe("Fanart", fanart_client.get_images_for_movie, tmdb_id))
        elif src == "mediux":
            sets = _safe("MediUX", mediux_client.get_movie_sets, tmdb_id)
            result += _language_first(_mediux_entries(sets, "poster"), details, language_pref)
        if _enough(result, stop_when):
            break
    return result


def series_posters(tmdb_id: int, tvdb_id: Optional[int], details: dict,
                   tmdb_imgs: Optional[dict] = None, *, language_pref: str = "en",
                  stop_when: Optional[str] = None,
                  prefetched: Optional[dict] = None) -> List[dict]:
    details = details or {}
    result: List[dict] = []
    for src in source_order():
        if src == "tmdb":
            if tmdb_imgs is None:
                tmdb_imgs = tmdb_client.get_images_for_tv_show(
                    tmdb_id, details.get("original_language")) or {}
            result += _posters(tmdb_imgs)
        elif src == "tvdb":
            if settings.TVDB_API_KEY and tvdb_id:
                have, imgs = _prefetched(prefetched, "tvdb")
                result += _posters(imgs if have else
                                   _safe("TVDB", tvdb_client.get_series_images, int(tvdb_id)))
        elif src == "fanart":
            if settings.FANART_API_KEY and tvdb_id:
                have, imgs = _prefetched(prefetched, "fanart")
                result += _posters(imgs if have else
                                   _safe("Fanart", fanart_client.get_images_for_tv_show, int(tvdb_id)))
        elif src == "mediux":
            sets = _safe("MediUX", mediux_client.get_show_sets, tmdb_id)
            result += _language_first(_mediux_entries(sets, "poster"), details, language_pref)
        if _enough(result, stop_when):
            break
    return result


def season_posters(tmdb_id: int, tvdb_id: Optional[int], season: int, details: dict,
                   series_list: List[dict], *, series_set_id: Optional[str] = None,
                   language_pref: str = "en", stop_when: Optional[str] = None,
                   prefetched: Optional[dict] = None) -> List[dict]:
    """[same-set MediUX season poster] + every source's season posters + series_list.
    ``prefetched`` ({"tmdb": season imgs, "tvdb": season imgs}) reuses images the
    caller already fetched."""
    details = details or {}
    same_set: List[dict] = []
    result: List[dict] = []
    for src in source_order():
        if src == "tmdb":
            have, imgs = _prefetched(prefetched, "tmdb")
            if not have:
                imgs = _safe("TMDb season", tmdb_client.get_tv_season_images,
                             tmdb_id, season, details.get("original_language"))
            result += _posters(imgs)
        elif src == "tvdb":
            if settings.TVDB_API_KEY and tvdb_id:
                have, imgs = _prefetched(prefetched, "tvdb")
                result += _posters(imgs if have else
                                   _safe("TVDB season", tvdb_client.get_season_images,
                                         int(tvdb_id), season))
        elif src == "mediux":
            sets = _safe("MediUX", mediux_client.get_show_sets, tmdb_id) or []
            others = []
            for s in sets:
                p = (s.get("season_posters") or {}).get(season)
                if not p:
                    continue
                if series_set_id and s.get("set_id") == series_set_id:
                    same_set.append(p)
                else:
                    others.append(p)
            result += _language_first(others, details, language_pref)
        if _enough(same_set + result, stop_when):
            break
    return same_set + result + list(series_list or [])


def mediux_backdrops(media_type: str, tmdb_id: int, details: Optional[dict] = None,
                     *, language_pref: str = "en") -> List[dict]:
    """MediUX set backdrops for the editors' backdrop lists ([] when MediUX isn't
    in the order or has no key). ``media_type`` is "movie" or "tv"."""
    if "mediux" not in source_order():
        return []
    fetch = mediux_client.get_movie_sets if media_type == "movie" else mediux_client.get_show_sets
    sets = _safe("MediUX", fetch, tmdb_id)
    return _language_first(_mediux_entries(sets, "backdrop"), details or {}, language_pref)
