"""
When may "Items that already have a poster: resend" re-upload a saved render
instead of rendering fresh?

The resend shortcut (webhooks.py, auto_generate.py) re-uploads the last image
saved for a Plex item, untouched. That's only right when the saved image is
what the preset would produce now. It isn't when:

- the preset draws overlays: a Radarr/Sonarr upgrade changes the file name,
  resolution, codecs and audio those overlays read, and ratings/lists move;
- the saved image was sent with a different template/preset, or with a
  fallback preset (e.g. no textless poster or logo existed yet);
- the preset was edited after the saved image was sent;
- there's no record of a successful send (we don't know what the image is).

In any of those cases the caller renders fresh with the preset instead.
"""
from __future__ import annotations

import json
from typing import Optional, Tuple

from . import database as db
from .config import logger

_SEND_ACTIONS = ("sent_to_plex", "resent_to_plex", "overlay_refresh")


def _preset_row(template_id: str, preset_id: str) -> Optional[dict]:
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT options_json, season_options_json, overlay_config_id, updated_at "
            "FROM presets WHERE template_id = ? AND id = ?",
            (template_id, preset_id),
        ).fetchone()
    return dict(row) if row else None


def _uses_overlays(row: dict) -> bool:
    if row.get("overlay_config_id"):
        return True
    for key in ("options_json", "season_options_json"):
        try:
            opts = json.loads(row.get(key) or "{}") or {}
        except Exception:
            continue
        if opts.get("overlay_config_ids") or opts.get("overlay_config_ids_below"):
            return True
    return False


def _last_real_send(rating_key: str) -> Optional[dict]:
    """The last send to Plex that actually rendered something. A
    resent_to_plex row only re-uploads an older image, so it says nothing
    about what that image is; skip past it to the render it came from."""
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT action, template_id, preset_id, created_at, "
            "COALESCE(poster_fallback_used, 0) AS pfb, COALESCE(logo_fallback_used, 0) AS lfb "
            "FROM poster_history WHERE rating_key = ? AND COALESCE(server_id, 'plex-1') = 'plex-1' "
            "AND COALESCE(status, 'success') = 'success' AND action IN (?, ?, ?) "
            "ORDER BY created_at DESC LIMIT 50",
            (str(rating_key), *_SEND_ACTIONS),
        ).fetchall()
    for r in rows:
        if r["action"] != "resent_to_plex":
            return dict(r)
    return None


def resend_check(rating_key: str, template_id: Optional[str], preset_id: Optional[str]) -> Tuple[bool, str]:
    """(ok_to_resend, reason). reason explains a refusal, for the log."""
    try:
        if not template_id or not preset_id:
            return False, "no preset given"
        preset = _preset_row(template_id, preset_id)
        if not preset:
            return False, f"preset '{preset_id}' not found"
        if _uses_overlays(preset):
            return False, f"preset '{preset_id}' uses overlays, which may have changed"
        last = _last_real_send(rating_key)
        if not last:
            return False, "no record of what the saved poster was rendered with"
        if (last.get("template_id"), last.get("preset_id")) != (template_id, preset_id):
            return False, f"saved poster was made with preset '{last.get('preset_id')}'"
        if last.get("pfb") or last.get("lfb"):
            return False, "saved poster used a fallback preset"
        updated = preset.get("updated_at")
        if updated and last.get("created_at") and str(updated) > str(last["created_at"]):
            return False, f"preset '{preset_id}' was edited after the saved poster was made"
        return True, ""
    except Exception as e:
        logger.debug("[RESEND] check failed for %s: %s", rating_key, e)
        return False, "could not check the saved poster"
