"""Pure TMDb-driven asset selection for poster renders.

Moved verbatim (behaviour-preserving) out of ``backend/api/batch.py`` so the same
preset derivation and poster/logo selection -- including the poster/logo fallback
template switching -- can be reused outside the batch pipeline (e.g. a "poster by
TMDb id" API) without importing the batch router.

Must NOT import from ``backend/api/batch.py`` (batch imports this module).
"""
from dataclasses import dataclass, field, replace as _dc_replace
from io import BytesIO
from typing import Literal, Optional

from .config import load_presets, logger, settings
from . import database as db
from .assets.selection import pick_poster, pick_logo, map_logo_mode_to_preference
from .logo_sources import get_logos_merged
from .tmdb_client import (
    TMDBError,
    _cached_tmdb_get,
    get_images_for_movie,
    get_images_for_tv_show,
    get_movie_details,
    get_tv_external_ids,
    get_tv_season_images,
    get_tv_show_details,
)
from . import tvdb_client
from .fanart_client import get_images_for_tv_show as get_fanart_tv_images
from .rendering import render_with_overlay_cache


class NoPosterAvailableError(Exception):
    """Raised when no poster exists anywhere (TMDb/Fanart), even after fallback --
    e.g. an unreleased movie/show TMDb has a page for but hasn't gotten poster art
    yet. Distinct from a genuine failure: the item may still succeed on a later
    retry once source art appears, so this is logged plainly and left pending
    rather than recorded as a "failed" History entry."""


@dataclass
class PresetContext:
    template_id: str
    preset_id: Optional[str]
    options: dict
    poster_filter: str
    logo_mode: str
    logo_preference: str
    season_options: dict
    season_poster_filter: str
    white_logo_fallback: str
    language_pref: str
    presets_data: dict = field(default_factory=dict)


@dataclass
class AssetChoice:
    poster: Optional[dict]
    poster_url: Optional[str]
    logo_url: Optional[str]
    template_id: str
    preset_id: Optional[str]
    options: dict
    logo_mode: str
    poster_fallback_action: Optional[str]
    poster_fallback_template: Optional[str]
    poster_fallback_preset: Optional[str]
    logo_fallback_used: bool
    logo_fallback_template: Optional[str]
    logo_fallback_preset: Optional[str]
    skip_status: Optional[str]  # "skipped_no_poster" | "skipped_no_logo" | None


def load_preset_context(
    template_id: str,
    preset_id: Optional[str],
    req_options: Optional[dict] = None,
    log_label: str = "[BATCH]",
) -> PresetContext:
    """Base render options for a template/preset, exactly as _execute_batch derives
    them: preset options underneath req_options, season options from the preset's
    own season_options (else a copy of the base), global white-logo fallback and
    language preference from the DB. ``log_label`` prefixes the log lines (batch
    keeps the default; the poster API passes "[POSTER API]")."""
    # Load preset options if provided
    presets_data = load_presets() or {}
    base_options = dict(req_options or {})
    base_poster_filter = base_options.get("poster_filter", "all")
    base_logo_mode = base_options.get("logo_mode", "first")
    base_logo_preference = base_options.get("logo_preference") or base_logo_mode or "first"
    base_logo_preference = map_logo_mode_to_preference(base_logo_preference)
    season_poster_filter = base_poster_filter  # Default to same as series
    season_options = dict(base_options)  # Default to same as series
    white_logo_fallback = db.get_setting("fallback.white_logo_fallback") or "use_next"
    language_pref = db.get_setting("pref.language") or "en"  # Language preference for logo selection
    if preset_id:
        if template_id in presets_data:
            preset_list = presets_data[template_id]["presets"]
            preset = next((p for p in preset_list if p["id"] == preset_id), None)
            if preset:
                preset_opts = preset.get("options", {})
                base_options = {**preset_opts, **base_options}
                base_poster_filter = base_options.get("poster_filter", base_poster_filter)
                base_logo_mode = base_options.get("logo_mode", base_logo_mode)
                base_logo_preference = base_options.get("logo_preference") or base_logo_mode or base_logo_preference
                base_logo_preference = map_logo_mode_to_preference(base_logo_preference)
                logger.debug("%s Applied preset '%s' options for template '%s'", log_label, preset_id, template_id)

                # Extract season_options if available (for TV show batch)
                season_opts = preset.get("season_options", {})
                if season_opts:
                    season_options = {**season_opts}
                    season_poster_filter = season_options.get("poster_filter", base_poster_filter)
                    logger.debug("%s Extracted season_options with poster_filter='%s'", log_label, season_poster_filter)
                else:
                    season_options = dict(base_options)
                    season_poster_filter = base_poster_filter
            else:
                logger.warning("%s Preset '%s' not found for template '%s'", log_label, preset_id, template_id)
        else:
            logger.warning("%s Template '%s' not found in presets", log_label, template_id)

    return PresetContext(
        template_id=template_id,
        preset_id=preset_id,
        options=base_options,
        poster_filter=base_poster_filter,
        logo_mode=base_logo_mode,
        logo_preference=base_logo_preference,
        season_options=season_options,
        season_poster_filter=season_poster_filter,
        white_logo_fallback=white_logo_fallback,
        language_pref=language_pref,
        presets_data=presets_data,
    )


def select_movie_assets(
    tmdb_id: int,
    details: dict,
    imgs: dict,
    ctx: PresetContext,
    log_label: str,
    *,
    rating_key: Optional[str] = None,
    title_hint: Optional[str] = None,
) -> AssetChoice:
    """Pick the poster + logo for a movie, applying the preset's poster/logo
    fallback rules (template switch / continue / skip). ``"skip"`` outcomes come
    back as an AssetChoice with ``skip_status`` set; no poster even after fallback
    raises NoPosterAvailableError.

    ``rating_key``/``title_hint`` only feed log lines (the batch caller passes its
    Plex rating_key and display title so its log output is unchanged)."""
    movie_details = details
    if rating_key is None:
        rating_key = str(tmdb_id)
    if title_hint is None:
        title_hint = movie_details.get("title") or rating_key
    template_id = ctx.template_id
    preset_id = ctx.preset_id
    presets_data = ctx.presets_data
    white_logo_fallback = ctx.white_logo_fallback
    language_pref = ctx.language_pref
    render_options_base = dict(ctx.options)
    poster_filter = ctx.poster_filter
    logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or ctx.logo_preference
    logo_preference = map_logo_mode_to_preference(logo_preference)
    logo_mode = ctx.logo_mode

    posters = imgs.get("posters", [])

    # Get logos using merged sources based on preference
    logo_source_pref = render_options_base.get("logoSource") or render_options_base.get("logo_source")
    logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
    logger.debug(
        "%s rating_key=%s [%s] posters=%d logos=%d filter=%s logo_pref=%s",
        log_label,
        rating_key,
        title_hint,
        len(posters),
        len(logos),
        poster_filter,
        logo_preference,
    )

    def _choice(poster, poster_url, logo_url, skip_status=None):
        return AssetChoice(
            poster=poster,
            poster_url=poster_url,
            logo_url=logo_url,
            template_id=template_id,
            preset_id=preset_id,
            options=render_options_base,
            logo_mode=logo_mode,
            poster_fallback_action=poster_fallback_action_used,
            poster_fallback_template=poster_fallback_template_used,
            poster_fallback_preset=poster_fallback_preset_used,
            logo_fallback_used=logo_fallback_used,
            logo_fallback_template=logo_fallback_template_used,
            logo_fallback_preset=logo_fallback_preset_used,
            skip_status=skip_status,
        )

    # ---------------------------
    # Auto-select assets
    # ---------------------------
    poster = pick_poster(posters, poster_filter)
    logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference, white_logo_fallback, language_pref)

    poster_fallback_action_used = None
    poster_fallback_template_used = None
    poster_fallback_preset_used = None
    logo_fallback_used = False
    logo_fallback_template_used = None
    logo_fallback_preset_used = None

    # Fallback handling for poster preference (runs before any logo fallback)
    if not poster:
        fallback_action = render_options_base.get("fallbackPosterAction") or "continue"
        poster_fallback_action_used = fallback_action
        fallback_template = render_options_base.get("fallbackPosterTemplate")
        fallback_preset = render_options_base.get("fallbackPosterPreset")
        if fallback_action == "template" and fallback_template:
            poster_fallback_template_used = fallback_template
            poster_fallback_preset_used = fallback_preset
            template_id = fallback_template
            if fallback_preset:
                tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
                fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None)
                if fpreset:
                    fp_opts = fpreset.get("options", {})
                    # Let fallback preset options override original options (matching preview behavior)
                    render_options_base = {**render_options_base, **fp_opts}
                    poster_filter = render_options_base.get("poster_filter", poster_filter)
                    logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or logo_preference
                    logo_preference = map_logo_mode_to_preference(logo_preference)
                    logo_mode = render_options_base.get("logo_mode", logo_mode)
                    preset_id = fallback_preset
                    logger.info("%s Applied fallback poster template '%s' preset '%s'", log_label, fallback_template, fallback_preset)
                else:
                    logger.warning("%s Fallback preset '%s' not found for template '%s'", log_label, fallback_preset, fallback_template)
            # Re-pick poster with updated filter from fallback preset
            poster = pick_poster(posters, poster_filter)
            # Re-evaluate logos with any updated preferences from the fallback preset
            logo_source_pref = render_options_base.get("logoSource") or render_options_base.get("logo_source")
            logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
            logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference, white_logo_fallback, language_pref)
        elif fallback_action == "skip":
            return _choice(None, None, None, skip_status="skipped_no_poster")
        else:  # continue
            poster = posters[0] if posters else None

    if not poster:
        raise NoPosterAvailableError("No valid poster found (even after fallback).")

    poster_url = poster.get("url")
    # Initialize logo_url for fallback logic
    logo_url = None

    # Only run logo fallback when poster handling chose to continue
    allow_logo_fallback = poster_fallback_action_used in (None, "continue")

    # Logo fallback handling
    if allow_logo_fallback and not logo and logo_mode != "none":
        fallback_logo_action = render_options_base.get("fallbackLogoAction") or "continue"
        fallback_logo_template = render_options_base.get("fallbackLogoTemplate")
        fallback_logo_preset = render_options_base.get("fallbackLogoPreset")
        logger.info("%s No logo found for %s [%s] — fallback action: %s", log_label, rating_key, title_hint, fallback_logo_action)
        if fallback_logo_action == "template" and fallback_logo_template:
            logo_fallback_used = True
            logo_fallback_template_used = fallback_logo_template
            logo_fallback_preset_used = fallback_logo_preset
            template_id = fallback_logo_template
            if fallback_logo_preset:
                tpl_presets = presets_data.get(fallback_logo_template, {}).get("presets", [])
                fpreset = next((p for p in tpl_presets if p.get("id") == fallback_logo_preset), None)
                if fpreset:
                    fp_opts = fpreset.get("options", {})
                    # Let fallback preset options override original options (matching preview behavior)
                    render_options_base = {**render_options_base, **fp_opts}
                    poster_filter = render_options_base.get("poster_filter", poster_filter)
                    logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or logo_preference
                    logo_preference = map_logo_mode_to_preference(logo_preference)
                    logo_mode = render_options_base.get("logo_mode", logo_mode)
                    preset_id = fallback_logo_preset
                    logger.info("%s Applied fallback logo template '%s' preset '%s'", log_label, fallback_logo_template, fallback_logo_preset)
                    # Re-fetch logos if logo source changed, or check for static logo override
                    logo_source_pref = render_options_base.get("logoSource") or render_options_base.get("logo_source")
                    logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
                    # Re-pick poster with the fallback template's poster_filter
                    poster = pick_poster(posters, poster_filter)
                    if poster:
                        poster_url = poster.get("url")
                        logger.info("%s Re-picked poster with fallback filter '%s': %s", log_label, poster_filter, poster_url)
                    # Check if fallback preset provides a static logo URL
                    logo_override = render_options_base.get("logo_url") or render_options_base.get("logoUrl")
                    if logo_override:
                        logo_url = logo_override
                        logo = None
                        logger.info("%s Using static logo URL from fallback preset: %s", log_label, logo_url)
                else:
                    logger.warning("%s Fallback logo preset '%s' not found for template '%s'", log_label, fallback_logo_preset, fallback_logo_template)
            # Re-pick logo with updated preference and mode from fallback preset
            if logo_mode != "none" and logo_url is None:
                logo = pick_logo(logos, logo_preference, white_logo_fallback, language_pref)
                if logo:
                    logger.info("%s Picked logo after fallback: preference=%s", log_label, logo_preference)
        elif fallback_logo_action == "skip":
            return _choice(poster, poster_url, None, skip_status="skipped_no_logo")
        # else continue without logo

    # Set final logo_url if not already set by fallback override
    if logo_url is None:
        logo_url = logo.get("url") if logo else None
    logger.info(f"{log_label} [{title_hint}] Picked logo pref={logo_preference}")
    logger.info(f"{log_label} [{title_hint}] Picked poster={poster_url}")
    logger.info(f"{log_label} [{title_hint}] Picked logo={logo_url}")

    return _choice(poster, poster_url, logo_url)


def select_tv_series_assets(
    tmdb_id: int,
    show_details: dict,
    show_imgs: dict,
    ctx: PresetContext,
    req_fallbacks: dict,
    log_label: str,
    *,
    fallback_log_context: str = "",
) -> AssetChoice:
    """Pick the series poster + logo for a TV show, applying the preset's poster
    fallback rule (template switch / continue / skip). Mirrors the batch TV series
    selection exactly -- which deliberately differs from movies: after a fallback
    the poster is re-picked with ``"all"``, there is no logo fallback, the fallback
    preset is read fresh via ``load_presets()``, and ``req_fallbacks`` (the batch
    request's ``fallbackPosterAction/Template/Preset``) fill in whatever the render
    options don't set.

    ``show_imgs`` must already hold the merged series posters/logos (TMDb +
    TVDB/Fanart) under ``"posters"``/``"logos"``. ``"skip"`` comes back as an
    AssetChoice with ``skip_status="skipped_no_poster"``; no poster otherwise
    raises NoPosterAvailableError. ``ctx.options`` is returned as-is (not copied)
    when no fallback applies. ``poster_fallback_action`` is the branch actually
    taken ("template"/"continue"/"skip") or None. ``fallback_log_context`` is only
    spliced into the "Applying template fallback" log line (the two batch callers'
    wording differs: "" vs " for series")."""
    if req_fallbacks is None:
        req_fallbacks = {}
    template_id = ctx.template_id
    preset_id = ctx.preset_id
    render_options = ctx.options
    posters = show_imgs.get("posters", [])
    logos = show_imgs.get("logos", [])

    poster_fallback_action_used = None
    poster_fallback_template_used = None
    poster_fallback_preset_used = None

    def _choice(poster, poster_url, logo_url, skip_status=None):
        return AssetChoice(
            poster=poster,
            poster_url=poster_url,
            logo_url=logo_url,
            template_id=template_id,
            preset_id=preset_id,
            options=render_options,
            logo_mode=ctx.logo_mode,
            poster_fallback_action=poster_fallback_action_used,
            poster_fallback_template=poster_fallback_template_used,
            poster_fallback_preset=poster_fallback_preset_used,
            logo_fallback_used=False,
            logo_fallback_template=None,
            logo_fallback_preset=None,
            skip_status=skip_status,
        )

    # Select poster with template fallback logic (matching preview.py behavior)
    poster = pick_poster(posters, ctx.poster_filter)

    if not poster:
        # Apply template fallback if no poster found with filter
        fallback_action = render_options.get("fallbackPosterAction") or req_fallbacks.get("fallbackPosterAction") or "continue"
        fallback_template = render_options.get("fallbackPosterTemplate") or req_fallbacks.get("fallbackPosterTemplate")
        fallback_preset = render_options.get("fallbackPosterPreset") or req_fallbacks.get("fallbackPosterPreset")

        if fallback_action == "skip":
            # Skip action - do not render this series
            poster_fallback_action_used = "skip"
            logger.info("%s Skipping series poster (fallbackPosterAction=skip, no poster found with filter)", log_label)
            return _choice(None, None, None, skip_status="skipped_no_poster")
        elif fallback_action == "template" and fallback_template:
            poster_fallback_action_used = "template"
            poster_fallback_template_used = fallback_template
            poster_fallback_preset_used = fallback_preset
            logger.info("%s Applying template fallback%s: %s/%s", log_label, fallback_log_context, fallback_template, fallback_preset)
            # Load fallback preset and merge options
            presets_data = load_presets()
            tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
            fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None) if fallback_preset else None
            if fpreset:
                fp_opts = fpreset.get("options", {})
                render_options = {**render_options, **fp_opts}
                template_id = fallback_template
                preset_id = fallback_preset
                # Now try to get ANY available poster
                poster = pick_poster(posters, "all")
                logger.info("%s Using fallback poster from TMDB after template switch", log_label)
            else:
                logger.warning("%s Fallback preset '%s' not found for template '%s'", log_label, fallback_preset, fallback_template)
        else:
            # continue action - try to get any available poster
            poster_fallback_action_used = "continue"
            poster = pick_poster(posters, "all")

    if not poster:
        raise NoPosterAvailableError("No poster found for series")

    logo = None if str(ctx.logo_mode).lower() == "none" else pick_logo(logos, ctx.logo_preference, ctx.white_logo_fallback, ctx.language_pref)

    poster_url = poster.get("url")
    logo_url = logo.get("url") if logo else None
    return _choice(poster, poster_url, logo_url)


def select_tv_season_assets(
    tmdb_id: int,
    season_index: int,
    show_details: dict,
    series_posters: list,
    series_logos: list,
    ctx: PresetContext,
    req_fallbacks: dict,
    log_label: str,
    *,
    tvdb_id: Optional[int] = None,
    season_title: Optional[str] = None,
) -> AssetChoice:
    """Pick the poster + logo for one TV season, exactly as the batch season loop
    does: fetch the TMDb season posters (+ the TVDB season posters when
    ``tvdb_id`` is given), select from season + series posters with the season
    poster filter, apply the poster fallback (re-pick with ``"all"``; fallback
    preset's season options resolved against its own base), then pick the logo
    from ``series_logos`` with the (possibly season-specific) logo mode.

    Effective season options are ``db.resolve_season_options(ctx.options,
    ctx.season_options)``. ``ctx.season_poster_filter``, ``ctx.logo_mode`` and
    ``ctx.logo_preference`` are the season loop's base values. No poster (and the
    ``"skip"`` action) come back as ``skip_status="skipped_no_poster"`` -- the
    season loop never raises for a missing season poster. ``options`` in the
    result is a fresh dict the caller may add ``season_text`` etc. to.

    ``tvdb_id`` is keyword-only because the brief's signature has no TVDB id but
    the TVDB season extension needs one; ``season_title`` only feeds log lines."""
    if req_fallbacks is None:
        req_fallbacks = {}
    if season_title is None:
        season_title = f"Season {season_index}"
    season_poster_filter = ctx.season_poster_filter
    final_season_options = db.resolve_season_options(ctx.options, ctx.season_options)

    # Get season-specific images
    try:
        season_imgs = get_tv_season_images(tmdb_id, season_index, show_details.get("original_language"))
        season_posters = season_imgs.get("posters", [])
    except Exception as e:
        logger.warning("%s Failed to get TMDB season images for season %d: %s", log_label, season_index, e)
        season_posters = []

    if tvdb_id:
        try:
            if settings.TVDB_API_KEY:
                tvdb_season_imgs = tvdb_client.get_season_images(int(tvdb_id), season_index)
                season_posters.extend(tvdb_season_imgs.get("posters", []))
        except Exception:
            pass

    # Combine season + series posters for selection
    all_posters = season_posters + series_posters

    logger.debug("%s Season %d: posters=%d (season=%d series=%d) logos=%d filter=%s",
                log_label, season_index, len(all_posters), len(season_posters), len(series_posters),
                len(series_logos), season_poster_filter)

    # Select poster with template fallback logic (matching preview.py behavior)
    poster = pick_poster(all_posters, season_poster_filter)

    season_template_id = ctx.template_id
    season_preset_id = ctx.preset_id
    season_render_options = dict(final_season_options)

    # Track fallback usage for season
    poster_fallback_action_used = None
    season_poster_fallback_template = None
    season_poster_fallback_preset = None

    if not poster:
        # Apply template fallback if no poster found with filter
        fallback_action = final_season_options.get("fallbackPosterAction") or req_fallbacks.get("fallbackPosterAction") or "continue"
        fallback_template = final_season_options.get("fallbackPosterTemplate") or req_fallbacks.get("fallbackPosterTemplate")
        fallback_preset = final_season_options.get("fallbackPosterPreset") or req_fallbacks.get("fallbackPosterPreset")

        if fallback_action == "skip":
            # Skip action - do not render this season
            poster_fallback_action_used = "skip"
            logger.info("%s Skipping %s (fallbackPosterAction=skip, no poster found with filter)", log_label, season_title)
        elif fallback_action == "template" and fallback_template:
            poster_fallback_action_used = "template"
            season_poster_fallback_template = fallback_template
            season_poster_fallback_preset = fallback_preset
            logger.info("%s Applying template fallback for season %s: %s/%s", log_label, season_title, fallback_template, fallback_preset)
            # Load fallback preset and merge options
            presets_data = load_presets()
            tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
            fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None) if fallback_preset else None
            if fpreset:
                # Use the fallback preset's season options, resolved against its own base
                # options (season_options may be stored as a sparse diff, not a full copy).
                fp_opts = db.resolve_season_options(fpreset.get("options", {}), fpreset.get("season_options", {}))
                season_render_options = {**final_season_options, **fp_opts}
                season_template_id = fallback_template
                season_preset_id = fallback_preset
                # Now try to get ANY available poster
                poster = pick_poster(all_posters, "all")
                logger.info("%s Using fallback poster from TMDB after template switch", log_label)
            else:
                logger.warning("%s Fallback preset '%s' not found for template '%s'", log_label, fallback_preset, fallback_template)
        else:
            # continue action - try to get any available poster
            poster_fallback_action_used = "continue"
            poster = pick_poster(all_posters, "all")

    # Extract logo mode from season options (may differ from series logo mode)
    season_logo_mode = season_render_options.get("logo_mode", ctx.logo_mode)

    def _choice(poster, poster_url, logo_url, skip_status=None):
        return AssetChoice(
            poster=poster,
            poster_url=poster_url,
            logo_url=logo_url,
            template_id=season_template_id,
            preset_id=season_preset_id,
            options=season_render_options,
            logo_mode=season_logo_mode,
            poster_fallback_action=poster_fallback_action_used,
            poster_fallback_template=season_poster_fallback_template,
            poster_fallback_preset=season_poster_fallback_preset,
            logo_fallback_used=False,
            logo_fallback_template=None,
            logo_fallback_preset=None,
            skip_status=skip_status,
        )

    if not poster:
        return _choice(None, None, None, skip_status="skipped_no_poster")

    season_logo_preference = season_render_options.get("logo_preference") or season_logo_mode or ctx.logo_preference
    season_logo_preference = map_logo_mode_to_preference(season_logo_preference)

    # Select logo using season-specific logo mode
    logo = None if str(season_logo_mode).lower() == "none" else pick_logo(series_logos, season_logo_preference, ctx.white_logo_fallback, ctx.language_pref)

    poster_url = poster.get("url")
    logo_url = logo.get("url") if logo else None
    return _choice(poster, poster_url, logo_url)


# --------------------------------------------------------------------------
# Series image merge (shared by both batch TV callers and render_for_tmdb)
# --------------------------------------------------------------------------
def fetch_tv_series_images(
    tmdb_id: int,
    tvdb_id: Optional[int],
    show_details: dict,
    *,
    log_label: Optional[str] = None,
) -> dict:
    """Series-level images for a TV show: TMDb's ``get_images_for_tv_show`` result
    with TVDB posters+logos and Fanart.tv logos appended in place (only when
    ``tvdb_id`` is known and the matching API key is set). Returns that same dict,
    so ``"posters"``/``"logos"`` hold the merged lists (``"backdrops"`` is TMDb's).

    Moved from the two batch TV callers (``_render_tv_series_poster`` and
    ``_render_all_tv_seasons``), which built exactly this. A TVDB/Fanart failure is
    never fatal: with ``log_label`` it is logged as
    ``"<log_label> TVDB/Fanart series fetch failed: ..."`` (the series-poster
    caller's behaviour), with ``None`` it is swallowed silently (the seasons
    caller's behaviour)."""
    show_imgs = get_images_for_tv_show(tmdb_id, show_details.get("original_language"))
    posters = show_imgs.setdefault("posters", [])
    logos = show_imgs.setdefault("logos", [])

    # Merge with TVDB/Fanart if available
    if tvdb_id:
        try:
            if settings.TVDB_API_KEY:
                tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                posters.extend(tvdb_imgs.get("posters", []))
                logos.extend(tvdb_imgs.get("logos", []))
        except Exception as e:
            if log_label is not None:
                logger.warning("%s TVDB series fetch failed: %s", log_label, e)

        try:
            if settings.FANART_API_KEY:
                fanart_imgs = get_fanart_tv_images(int(tvdb_id))
                logos.extend(fanart_imgs.get("logos", []))
        except Exception as e:
            if log_label is not None:
                logger.warning("%s Fanart series fetch failed: %s", log_label, e)

    return show_imgs


# --------------------------------------------------------------------------
# Render a finished poster from just a TMDb id + preset (no media server)
# --------------------------------------------------------------------------
_API_LOG = "[POSTER API]"


@dataclass
class RenderResult:
    image_bytes: bytes
    title: str
    year: Optional[str]
    tmdb_poster_path: Optional[str]


def _is_tmdb_not_found(err: Exception) -> bool:
    """True when a TMDBError wraps an HTTP 404 (TMDb has no such id)."""
    resp = getattr(err.__cause__, "response", None)
    return getattr(resp, "status_code", None) == 404


def _tmdb_raw(media_type: str, tmdb_id: int) -> Optional[dict]:
    """TMDb's raw /movie/{id} or /tv/{id} payload -- the same (5-minute cached)
    request ``get_movie_details``/``get_tv_show_details`` make, so no extra call.
    None when TMDb has no such id; any other TMDb error propagates."""
    path = f"/tv/{tmdb_id}" if media_type == "tv" else f"/movie/{tmdb_id}"
    try:
        return _cached_tmdb_get(path, {})
    except TMDBError as e:
        if _is_tmdb_not_found(e):
            return None
        raise


def fetch_tmdb_poster_path(media_type: str, tmdb_id: int) -> Optional[str]:
    """TMDb's own ``poster_path`` (e.g. ``"/abc.jpg"``) for a movie/show, or None
    when the id doesn't exist or has no poster. Used for the plain-TMDb-poster
    redirect when a render takes too long."""
    data = _tmdb_raw(media_type, tmdb_id)
    if not data:
        return None
    return data.get("poster_path") or None


def _season_title(season: int) -> str:
    """Plex's default season label -- what batch passes as ``season_text``."""
    return "Specials" if season == 0 else f"Season {season}"


def _inject_library_metadata(render_options: dict, media_type: str, tmdb_id: int) -> None:
    """Resolution/codec/audio/edition badges for a title that is also in a
    library, via the same injector batch uses. May do one live Plex metadata
    fetch for a Plex item (a Jellyfin/Emby item reads the scan cache). Not in a
    library -> rating_key None -> the injector is a no-op."""
    from .config import inject_plex_media_metadata
    try:
        rating_key = db.find_rating_key_by_tmdb_id(media_type, tmdb_id)
    except Exception as e:  # badges are a nice-to-have; never fail a render over them
        logger.debug("%s rating_key lookup failed for %s tmdb_id=%s: %s", _API_LOG, media_type, tmdb_id, e)
        rating_key = None
    is_tv = media_type == "tv"
    inject_plex_media_metadata(
        render_options, rating_key,
        tmdb_id=tmdb_id, is_tv=is_tv,
        log_prefix=f"{_API_LOG} ",
    )
    # The injector returns early when rating_key is falsy, so a title that isn't in
    # any library would otherwise render without metadata["tmdb_id"]/["media_type"]
    # -- the keys the studio/streaming-platform badges (universal.py) and the
    # TMDb-id-driven rating badges (overlay_engine._item_ids) read. Batch always
    # has a rating_key and so always gets them; set the same values the injector
    # sets on that path. Set only if missing so the library path is untouched.
    meta = render_options.get("metadata") or {}
    meta.setdefault("tmdb_id", tmdb_id)
    meta.setdefault("media_type", "tv" if is_tv else "movie")
    render_options["metadata"] = meta


def _render_jpeg(
    template_id: str,
    preset_id: Optional[str],
    poster_url: str,
    logo_url: Optional[str],
    render_options: dict,
) -> bytes:
    ui_settings = db.get_ui_settings()
    use_overlay_cache = ui_settings.get("performance", {}).get("useOverlayCache", True)
    img = render_with_overlay_cache(
        template_id,
        preset_id,
        poster_url,
        logo_url,
        render_options,
        use_cache=use_overlay_cache,
    )
    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


def _render_movie(tmdb_id: int, ctx: PresetContext, poster_path: Optional[str]) -> Optional[RenderResult]:
    details = get_movie_details(tmdb_id)
    imgs = get_images_for_movie(tmdb_id, details.get("original_language"))
    try:
        choice = select_movie_assets(tmdb_id, details, imgs, ctx, _API_LOG)
    except NoPosterAvailableError:
        logger.info("%s No poster art for movie tmdb_id=%s yet", _API_LOG, tmdb_id)
        return None
    if choice.skip_status:
        logger.info("%s movie tmdb_id=%s %s", _API_LOG, tmdb_id, choice.skip_status)
        return None

    # Exactly _process_single_movie's render options.
    render_options = dict(choice.options)
    render_options["movie_title"] = details.get("title", "")
    render_options["movie_year"] = details.get("year", "")
    _inject_library_metadata(render_options, "movie", tmdb_id)
    if choice.preset_id:
        render_options["preset_id"] = choice.preset_id

    image_bytes = _render_jpeg(
        choice.template_id,
        choice.preset_id,
        choice.poster_url,
        choice.logo_url if choice.logo_mode != "none" else None,
        render_options,
    )
    return RenderResult(
        image_bytes=image_bytes,
        title=details.get("title", ""),
        year=details.get("year") or None,
        tmdb_poster_path=poster_path,
    )


def _render_tv(tmdb_id: int, season: Optional[int], ctx: PresetContext, raw: dict) -> Optional[RenderResult]:
    if season is not None:
        known = {s.get("season_number") for s in (raw.get("seasons") or [])}
        if season not in known:
            logger.info("%s tv tmdb_id=%s has no season %s", _API_LOG, tmdb_id, season)
            return None

    show_details = get_tv_show_details(tmdb_id)
    title = show_details.get("name") or ""
    year = show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None

    tvdb_id = None
    try:
        tvdb_id = get_tv_external_ids(tmdb_id).get("tvdb_id")
    except Exception:
        pass

    # Same per-show derivation _process_single_tv_show applies on top of
    # _execute_batch's (load_preset_context's) base values.
    logo_preference = ctx.options.get("logo_preference") or ctx.options.get("logo_mode") or ctx.logo_preference
    tv_ctx = _dc_replace(
        ctx,
        options=dict(ctx.options),
        logo_preference=map_logo_mode_to_preference(logo_preference),
        season_options=db.resolve_season_options(ctx.options, ctx.season_options),
        season_poster_filter=ctx.season_poster_filter or ctx.poster_filter,
    )

    show_imgs = fetch_tv_series_images(tmdb_id, tvdb_id, show_details, log_label=_API_LOG)

    season_title = None
    if season is None:
        try:
            choice = select_tv_series_assets(tmdb_id, show_details, show_imgs, tv_ctx, {}, _API_LOG)
        except NoPosterAvailableError:
            logger.info("%s No poster art for tv tmdb_id=%s yet", _API_LOG, tmdb_id)
            return None
    else:
        season_title = _season_title(season)
        choice = select_tv_season_assets(
            tmdb_id, season, show_details,
            show_imgs.get("posters", []), show_imgs.get("logos", []),
            tv_ctx, {}, _API_LOG,
            tvdb_id=tvdb_id, season_title=season_title,
        )
    if choice.skip_status or not choice.poster:
        logger.info("%s tv tmdb_id=%s season=%s %s", _API_LOG, tmdb_id, season, choice.skip_status or "no poster")
        return None

    render_options = dict(choice.options)
    if season is not None:
        # _render_all_tv_seasons sets these on the season's options.
        render_options["season_text"] = season_title
        render_options["season_number"] = str(season)
    # _render_and_save_poster's order: inject, preset_id, then {title}/{year}.
    _inject_library_metadata(render_options, "tv", tmdb_id)
    if choice.preset_id:
        render_options["preset_id"] = choice.preset_id
    render_options["movie_title"] = title or ""
    render_options["movie_year"] = str(year) if year else ""

    image_bytes = _render_jpeg(
        choice.template_id, choice.preset_id, choice.poster_url, choice.logo_url, render_options,
    )
    return RenderResult(
        image_bytes=image_bytes,
        title=title,
        year=year or None,
        tmdb_poster_path=raw.get("poster_path") or None,
    )


def render_for_tmdb(
    media_type: Literal["movie", "tv"],
    tmdb_id: int,
    season: Optional[int],
    template_id: str,
    preset_id: str,
) -> Optional[RenderResult]:
    """Render a finished poster (JPEG, quality 95, 4:4:4 chroma) for a TMDb movie,
    TV series (``season=None``) or TV season with the given template/preset, using
    the batch pipeline's preset derivation, asset selection/fallbacks and render
    options -- no media server needed (library badges are added when the title
    also happens to be in a scanned library).

    Returns None when TMDb has no such id (or the show no such season), when no
    poster art exists yet, or when the preset's fallback says to skip. Other
    errors (TMDb unreachable/no key, render failure) propagate to the caller."""
    raw = _tmdb_raw(media_type, tmdb_id)
    if raw is None:
        logger.info("%s TMDb has no %s with id %s", _API_LOG, media_type, tmdb_id)
        return None

    ctx = load_preset_context(template_id, preset_id, None, log_label=_API_LOG)
    if media_type == "movie":
        return _render_movie(tmdb_id, ctx, raw.get("poster_path") or None)
    return _render_tv(tmdb_id, season, ctx, raw)
