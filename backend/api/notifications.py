"""
Discord webhook notifications for poster generation events.
"""
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from .. import database as db
from ..config import logger

router = APIRouter()


class TestWebhookRequest(BaseModel):
    webhook_url: str


class TestAppriseRequest(BaseModel):
    urls: List[str]


class DiscordNotification(BaseModel):
    """Data for a Discord notification"""
    title: str
    year: Optional[int] = None
    template_id: str
    preset_id: str
    library_id: Optional[str] = None
    source: str  # 'batch', 'manual', 'webhook', 'auto_generate'
    action: str  # 'sent_to_plex', 'saved'
    poster_url: Optional[str] = None  # URL to poster image if available
    count: int = 1  # Number of posters (for batch)
    success_count: int = 0
    failed_count: int = 0


def _get_notification_settings() -> Dict[str, Any]:
    """Get notification settings from the database."""
    try:
        ui_settings = db.get_ui_settings()
        if not ui_settings:
            return {}
        return ui_settings.get("notifications", {})
    except Exception as e:
        logger.error(f"[DISCORD] Failed to get notification settings: {e}")
        return {}


def _library_passes_filter(notify_libraries: List[str], library_id: Optional[str]) -> bool:
    """Library filter, group-aware. The filter list holds library ids picked in
    Settings -> Notifications; a library passes when it's in the list OR any
    library in its library group is. Without this, a send to a group's
    Jellyfin/Emby library was dropped whenever only its Plex library (or the
    other way round) had been picked, even though they're the same library."""
    if not notify_libraries or not library_id:
        return True
    wanted = {str(x) for x in notify_libraries}
    if str(library_id) in wanted:
        return True
    try:
        ui_settings = db.get_ui_settings() or {}
        for group in ui_settings.get("libraryGroups", []) or []:
            ids = {str(m.get("libraryId")) for m in group.get("members", []) or []}
            if str(library_id) in ids and ids & wanted:
                return True
    except Exception:
        pass
    return False


def _should_notify_apprise(source: str, library_id: Optional[str] = None) -> bool:
    """Check if an Apprise notification should be sent."""
    settings = _get_notification_settings()

    if not settings.get("appriseEnabled", False):
        return False

    if not settings.get("appriseUrls"):
        return False

    source_map = {
        "batch": "appriseNotifyBatch",
        "manual": "appriseNotifyManual",
        "webhook": "appriseNotifyWebhook",
        "auto_generate": "appriseNotifyAutoGenerate",
        "media_mirror": "appriseNotifyMediaMirror",
    }

    setting_key = source_map.get(source)
    if setting_key and not settings.get(setting_key, True):
        return False

    # Check library filter
    if not _library_passes_filter(settings.get("appriseNotifyLibraries", []), library_id):
        return False

    return True


def _should_notify(source: str, library_id: Optional[str] = None) -> bool:
    """
    Check if a notification should be sent based on settings.

    Args:
        source: The source of the notification ('batch', 'manual', 'webhook', 'auto_generate')
        library_id: The library ID (optional)

    Returns:
        True if notification should be sent, False otherwise
    """
    settings = _get_notification_settings()

    if not settings.get("discordEnabled", False):
        return False

    if not settings.get("discordWebhookUrl"):
        return False

    # Check source type
    source_map = {
        "batch": "discordNotifyBatch",
        "manual": "discordNotifyManual",
        "webhook": "discordNotifyWebhook",
        "auto_generate": "discordNotifyAutoGenerate",
        "media_mirror": "discordNotifyMediaMirror",
    }

    setting_key = source_map.get(source)
    if setting_key and not settings.get(setting_key, True):
        return False

    # Check library filter
    if not _library_passes_filter(settings.get("discordNotifyLibraries", []), library_id):
        return False

    return True


def _get_library_name(library_id: Optional[str]) -> str:
    """Get display name for a library. Checks Plex's own libraryMappings/
    tvShowLibraryMappings first (unchanged, original behavior), then falls
    back to scanning libraryGroups for ANY member whose libraryId matches --
    needed because a Jellyfin/Emby-only library (Phase 8a) has no Plex
    mapping entry at all, so without this a Jellyfin/Emby manual-send or
    sync notification showed a raw library id/GUID instead of a real name.
    Doesn't need server_id/media_type to disambiguate -- a Plex library_id
    (short digits) and a Jellyfin/Emby one (a GUID) don't realistically
    collide, the same reasoning this app's db.get_cached_movies() docstring
    already established for not needing server-scoped lookups elsewhere."""
    if not library_id:
        return "Unknown Library"

    try:
        ui_settings = db.get_ui_settings()
        if not ui_settings:
            return library_id

        plex_settings = ui_settings.get("plex", {})

        # Check movie libraries
        for mapping in plex_settings.get("libraryMappings", []):
            if mapping.get("id") == library_id:
                return mapping.get("displayName") or mapping.get("title") or library_id

        # Check TV libraries
        for mapping in plex_settings.get("tvShowLibraryMappings", []):
            if mapping.get("id") == library_id:
                return mapping.get("displayName") or mapping.get("title") or library_id

        # Fall back to a Jellyfin/Emby-only Library Group member (no Plex side
        # to have a mapping entry for at all). Group name first, then the
        # member's own library name -- the same priority the UI (History,
        # Local Assets, search) and backup folders use, so a library is called
        # the same thing everywhere.
        for group in ui_settings.get("libraryGroups", []) or []:
            for member in group.get("members", []) or []:
                if str(member.get("libraryId")) == str(library_id):
                    return group.get("name") or member.get("libraryName") or library_id

        return library_id
    except Exception:
        return library_id


def _get_source_emoji(source: str) -> str:
    """Get emoji for notification source."""
    return {
        "batch": "\U0001F4E6",  # Package
        "manual": "\U0001F3A8",  # Artist palette
        "webhook": "\U0001F517",  # Link
        "auto_generate": "\U0001F504",  # Arrows
        "media_mirror": "\U0001FA9E",  # Mirror
    }.get(source, "\U0001F3AC")  # Clapper board default


def _get_source_label(source: str) -> str:
    """Get readable label for notification source."""
    return {
        "batch": "Batch Edit",
        "manual": "Manual Send",
        "webhook": "Webhook",
        "auto_generate": "Auto-Generate",
        "media_mirror": "Media Mirror",
    }.get(source, source)


def _get_action_text(action: str, server_id: Optional[str] = None) -> str:
    """Human-readable label for a notification's "Action" field/line,
    server-aware. Consolidates what used to be 3 independently-duplicated
    ternaries (native Discord, Discord-via-Apprise, plain-text Apprise) that
    only ever distinguished "sent_to_plex" from everything else -- silently
    collapsing "sent_to_media_server" (the real Jellyfin/Emby sync action,
    see record_poster_history() call sites in media_server_send.py/webhooks.py)
    and "resent_to_plex" into the same misleading "Saved locally" text. One
    source of truth now, matching get_server_label()'s own "can't drift"
    reasoning (registry.py) -- extend HERE if a new action string is ever
    added, not by re-copying a ternary a 4th time."""
    if action == "sent_to_plex":
        return "Sent to Plex"
    if action == "resent_to_plex":
        return "Resent to Plex"
    if action == "sent_to_media_server":
        if server_id:
            from ..media_server import get_server_label
            return f"Sent to {get_server_label(server_id)}"
        return "Sent to media server"
    return "Saved locally"


def _get_asset_type_label(asset_type: str) -> Optional[str]:
    """Readable label for a non-poster asset type, matching this app's own
    established emoji convention (see CLAUDE.md's Emoji Usage Convention) so a
    notification reads consistently with the rest of the UI. Returns None for
    "poster" (the default) so existing poster notifications are unchanged --
    no "Asset" field is added to the embed/body unless something OTHER than a
    poster was sent, which is the whole point of this field existing."""
    labels = {
        "poster": "\U0001F3AC Poster",
        "logo": "\U0001F5BC️ Logo",
        "backdrop": "\U0001F39E️ Backdrop",
        "square_art": "\U0001F533 Square Art",
    }
    # A combined send ("poster+logo") lists every asset, poster included.
    parts = [p for p in (asset_type or "poster").split("+") if p]
    if parts == ["poster"]:
        return None
    if len(parts) == 1:
        return labels.get(parts[0])
    return " + ".join(labels.get(p, p) for p in parts)


def _get_synced_servers_label(synced_server_ids: Optional[List[str]]) -> Optional[str]:
    """Readable "Also synced to: X, Y" value for a notification that ALSO
    pushed to one or more linked Jellyfin/Emby servers alongside its primary
    action (a manual Plex send with a linked library, a webhook/batch run
    whose cross-server sync -- webhooks.py's _sync_poster_to_other_servers()
    or media_server_send.py's sync_render_to_linked_servers() -- reached a
    linked server too). Returns None (no field/line added at all) when the
    list is empty, matching _get_asset_type_label()'s own "only add the field
    when something non-default happened" convention. Deliberately excludes
    'plex-1' -- a Plex delivery already has its own "Action: Sent to Plex"/
    "Resent to Plex" text; this field exists only to surface the servers a
    primary action's own action/server_id can't already express (which is
    always exactly one), not to restate Plex a second time."""
    if not synced_server_ids:
        return None
    from ..media_server import get_server_label
    seen = []
    for sid in synced_server_ids:
        if sid and sid != "plex-1" and sid not in seen:
            seen.append(sid)
    if not seen:
        return None
    return ", ".join(get_server_label(sid) for sid in seen)


def _get_preset_label(template_id: Optional[str], preset_id: Optional[str]) -> str:
    """The preset's display name (falls back to its id, then the template)."""
    if preset_id:
        if template_id:
            try:
                preset = db.get_preset(template_id, preset_id)
                if preset and preset.get("name"):
                    return str(preset["name"])
            except Exception:
                pass
        return str(preset_id)
    return template_id or "N/A"


def _get_servers_label(action: str, server_id: Optional[str], synced_server_ids: Optional[List[str]]) -> Optional[str]:
    """Every server this notification's poster reached: the primary send's
    server (Plex for sent/resent_to_plex, `server_id` for a media-server
    send) followed by any linked servers it was also synced to."""
    ids: List[str] = []
    if action in ("sent_to_plex", "resent_to_plex"):
        ids.append("plex-1")
    elif action == "sent_to_media_server" and server_id:
        ids.append(server_id)
    for sid in synced_server_ids or []:
        if sid and sid not in ids:
            ids.append(sid)
    if not ids:
        return None
    from ..media_server import get_server_label
    return ", ".join(get_server_label(sid) for sid in ids)


def _get_short_action(action: str) -> str:
    if action == "resent_to_plex":
        return "Resent"
    if action in ("sent_to_plex", "sent_to_media_server"):
        return "Sent"
    return "Saved locally"


def _summary_fields(
    library_id: Optional[str],
    template_id: Optional[str],
    preset_id: Optional[str],
    action: str,
    server_id: Optional[str],
    synced_server_ids: Optional[List[str]],
    asset_type: str = "poster",
) -> List[tuple]:
    """(name, value) pairs shared by every notification layout:
    Library / Preset / Action(s) / Servers (+ Asset for non-poster sends)."""
    fields = [("Library", _get_library_name(library_id))]
    # Logo/backdrop sends aren't rendered from a preset -- leave the field out
    # rather than showing "N/A".
    if preset_id or template_id:
        fields.append(("Preset", _get_preset_label(template_id, preset_id)))
    fields.append(("Action", _get_short_action(action)))
    servers = _get_servers_label(action, server_id, synced_server_ids)
    if servers:
        fields.append(("Servers", servers))
    asset_label = _get_asset_type_label(asset_type)
    if asset_label:
        fields.append(("Asset", asset_label))
    return fields


def send_discord_notification(
    title: str,
    year: Optional[int] = None,
    template_id: str = "",
    preset_id: str = "",
    library_id: Optional[str] = None,
    source: str = "manual",
    action: str = "sent_to_plex",
    poster_url: Optional[str] = None,
    poster_data: Optional[bytes] = None,
    count: int = 1,
    success_count: int = 0,
    failed_count: int = 0,
    asset_type: str = "poster",
    server_id: Optional[str] = None,
    synced_server_ids: Optional[List[str]] = None,
) -> bool:
    """
    Send a Discord webhook notification for poster generation.

    Args:
        poster_data: Optional bytes of the poster image to attach directly to Discord
        synced_server_ids: Linked Jellyfin/Emby server_ids ALSO reached this run
            (webhook/batch cross-server sync), on top of whatever `action` already
            says -- see _get_synced_servers_label()'s own docstring.

    Returns:
        True if notification was sent successfully, False otherwise
    """
    if not _should_notify(source, library_id):
        logger.debug(f"[DISCORD] Notification skipped (disabled or filtered): source={source}, library={library_id}")
        return False

    settings = _get_notification_settings()
    webhook_url = settings.get("discordWebhookUrl", "")

    if not webhook_url:
        return False

    try:
        # Build the embed
        emoji = _get_source_emoji(source)
        source_label = _get_source_label(source)
        library_name = _get_library_name(library_id)

        # Color based on action/status
        if failed_count > 0 and success_count == 0:
            color = 0xFF4757  # Red for all failures
        elif failed_count > 0:
            color = 0xFFA502  # Orange for partial failures
        else:
            color = 0x3DD6B7  # Green for success (Simposter accent color)

        # Build description based on context
        if count > 1:
            # Batch notification
            description = f"**{success_count}** posters generated successfully"
            if failed_count > 0:
                description += f"\n**{failed_count}** failed"
        else:
            # Single poster notification
            year_str = f" ({year})" if year else ""
            description = f"**{title}**{year_str}"

        embed = {
            "title": f"{emoji} {source_label} Complete",
            "description": description,
            "color": color,
            "fields": [
                {"name": name, "value": value, "inline": True}
                for name, value in _summary_fields(library_id, template_id, preset_id, action, server_id, synced_server_ids, asset_type)
            ],
            "footer": {
                "text": "Simposter"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # Add poster thumbnail - either from attached file or URL
        if poster_data:
            # Use attachment reference for embedded image
            embed["thumbnail"] = {"url": "attachment://poster.jpg"}
        elif poster_url:
            embed["thumbnail"] = {"url": poster_url}

        # Send with or without file attachment
        if poster_data:
            # Use multipart/form-data to include the image
            import json
            files = {
                "file": ("poster.jpg", poster_data, "image/jpeg")
            }
            payload_json = json.dumps({"embeds": [embed]})
            response = requests.post(
                webhook_url,
                data={"payload_json": payload_json},
                files=files,
                timeout=15
            )
        else:
            # Simple JSON request without file
            payload = {
                "embeds": [embed]
            }
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )

        if response.status_code in (200, 204):
            logger.info(f"[DISCORD] Notification sent: {title} ({source})")
            return True
        else:
            logger.warning(f"[DISCORD] Failed to send notification: HTTP {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"[DISCORD] Error sending notification: {e}")
        return False


def _resolve_discord_webhook_url(apprise_url: str) -> Optional[str]:
    """
    Convert an Apprise URL to a raw Discord webhook URL if it is a Discord URL.
    Handles both:
      - Raw webhook: https://discord.com/api/webhooks/...
      - Apprise scheme: discord://webhook_id/webhook_token
    Returns the HTTPS webhook URL, or None if not a Discord URL.
    """
    import re
    url = apprise_url.strip()
    if url.startswith("https://discord.com/api/webhooks/"):
        return url
    if url.startswith("https://discordapp.com/api/webhooks/"):
        return url
    # Apprise discord:// or discords:// (TTS variant) scheme
    m = re.match(r"^discords?://([^/]+)/(.+)$", url, re.IGNORECASE)
    if m:
        webhook_id, webhook_token = m.group(1), m.group(2)
        # Strip any trailing Apprise options (e.g. ?tts=yes)
        webhook_token = webhook_token.split("?")[0].rstrip("/")
        return f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}"
    return None


def _build_notification_embed(
    title: str,
    year: Optional[int],
    template_id: str,
    library_id: Optional[str],
    source: str,
    action: str,
    count: int,
    success_count: int,
    failed_count: int,
    poster_data: Optional[bytes] = None,
    asset_type: str = "poster",
    server_id: Optional[str] = None,
    synced_server_ids: Optional[List[str]] = None,
    preset_id: Optional[str] = None,
) -> dict:
    """Build a Discord embed dict — shared between native Discord and Apprise Discord paths."""
    emoji = _get_source_emoji(source)
    source_label = _get_source_label(source)

    if failed_count > 0 and success_count == 0:
        color = 0xFF4757
    elif failed_count > 0:
        color = 0xFFA502
    else:
        color = 0x3DD6B7

    if count > 1:
        description = f"**{success_count}** posters generated successfully"
        if failed_count > 0:
            description += f"\n**{failed_count}** failed"
    else:
        year_str = f" ({year})" if year else ""
        description = f"**{title}**{year_str}"

    embed = {
        "title": f"{emoji} {source_label} Complete",
        "description": description,
        "color": color,
        "fields": [
            {"name": name, "value": value, "inline": True}
            for name, value in _summary_fields(library_id, template_id, preset_id, action, server_id, synced_server_ids, asset_type)
        ],
        "footer": {"text": "Simposter"},
        "timestamp": datetime.utcnow().isoformat(),
    }

    if poster_data:
        embed["thumbnail"] = {"url": "attachment://poster.jpg"}

    return embed


def send_apprise_notification(
    title: str,
    year: Optional[int] = None,
    template_id: str = "",
    preset_id: str = "",
    library_id: Optional[str] = None,
    source: str = "manual",
    action: str = "sent_to_plex",
    count: int = 1,
    success_count: int = 0,
    failed_count: int = 0,
    poster_data: Optional[bytes] = None,
    asset_type: str = "poster",
    server_id: Optional[str] = None,
    synced_server_ids: Optional[List[str]] = None,
) -> bool:
    """
    Send an Apprise notification for poster generation events.
    Discord webhook URLs (raw or apprise scheme) receive rich embeds identical to
    the native Discord integration. All other URLs go through Apprise as plain text.
    """
    if not _should_notify_apprise(source, library_id):
        logger.debug(f"[APPRISE] Notification skipped (disabled or filtered): source={source}")
        return False

    settings = _get_notification_settings()
    urls = settings.get("appriseUrls", [])
    if not urls:
        return False

    emoji = _get_source_emoji(source)
    source_label = _get_source_label(source)
    library_name = _get_library_name(library_id)
    action_text = _get_action_text(action, server_id)

    discord_urls: List[str] = []
    other_urls: List[str] = []
    for url in urls:
        if not url.strip():
            continue
        discord_webhook = _resolve_discord_webhook_url(url)
        if discord_webhook:
            discord_urls.append(discord_webhook)
        else:
            other_urls.append(url.strip())

    overall_ok = True

    # --- Discord URLs: send rich embed directly ---
    if discord_urls:
        import json as _json
        embed = _build_notification_embed(
            title=title, year=year, template_id=template_id,
            library_id=library_id, source=source, action=action,
            count=count, success_count=success_count, failed_count=failed_count,
            poster_data=poster_data, asset_type=asset_type, server_id=server_id,
            synced_server_ids=synced_server_ids, preset_id=preset_id,
        )
        for webhook_url in discord_urls:
            try:
                if poster_data:
                    files = {"file": ("poster.jpg", poster_data, "image/jpeg")}
                    resp = requests.post(
                        webhook_url,
                        data={"payload_json": _json.dumps({"embeds": [embed]})},
                        files=files,
                        timeout=15,
                    )
                else:
                    resp = requests.post(
                        webhook_url,
                        json={"embeds": [embed]},
                        timeout=10,
                    )
                if resp.status_code in (200, 204):
                    logger.info(f"[APPRISE] Discord embed sent: {title} ({source})")
                else:
                    logger.warning(f"[APPRISE] Discord embed failed: HTTP {resp.status_code}")
                    overall_ok = False
            except Exception as e:
                logger.error(f"[APPRISE] Discord embed error: {e}")
                overall_ok = False

    # --- Other URLs: plain text via Apprise ---
    if other_urls:
        try:
            import apprise
            ap = apprise.Apprise()
            for url in other_urls:
                ap.add(url)

            if len(ap) > 0:
                notify_title = f"{emoji} Simposter — {source_label} Complete"
                if count > 1:
                    body = f"{success_count} posters generated successfully"
                    if failed_count > 0:
                        body += f"\n{failed_count} failed"
                else:
                    year_str = f" ({year})" if year else ""
                    body = f"{title}{year_str}"
                for name, value in _summary_fields(library_id, template_id, preset_id, action, server_id, synced_server_ids, asset_type):
                    body += f"\n{name}: {value}"

                result = ap.notify(title=notify_title, body=body)
                if result:
                    logger.info(f"[APPRISE] Notification sent: {title} ({source})")
                else:
                    logger.warning(f"[APPRISE] One or more Apprise services failed")
                    overall_ok = False
        except ImportError:
            logger.error("[APPRISE] apprise library not installed — add 'apprise' to requirements.txt")
            overall_ok = False
        except Exception as e:
            logger.error(f"[APPRISE] Error sending notification: {e}")
            overall_ok = False

    return overall_ok


_MIRROR_ASSET_LABELS = [
    ("poster", "Posters"),
    ("logo", "Logos"),
    ("backdrop", "Backdrops"),
    ("square_art", "Square Art"),
]


def _mirror_count_lines(counts: Dict[str, Dict[str, int]], prefix: str = "") -> List[tuple]:
    """("Posters", "3/40 copied (37 unchanged)") pairs, one per asset type that
    the run actually checked."""
    lines = []
    for key, label in _MIRROR_ASSET_LABELS:
        c = counts.get(key)
        if not c or not c.get("total"):
            continue
        value = f"{c.get('copied', 0)}/{c['total']} copied"
        extras = []
        if c.get("unchanged"):
            extras.append(f"{c['unchanged']} unchanged")
        if c.get("failed"):
            extras.append(f"{c['failed']} failed")
        if extras:
            value += f" ({', '.join(extras)})"
        lines.append((f"{prefix}{label}" if not prefix else f"{prefix}{label.lower()}", value))
    return lines


def send_media_mirror_notification(
    group_name: str,
    library_id: Optional[str],
    source_server_id: Optional[str],
    target_server_ids: List[str],
    asset_counts: Dict[str, Dict[str, int]],
    collection_counts: Dict[str, Dict[str, int]],
    totals: Dict[str, int],
    scheduled: bool = False,
    error: Optional[str] = None,
) -> None:
    """Run summary for a Media Mirror run (Quirk #151): which servers, and per
    asset type how many items were copied out of how many the source had.
    Sent to Discord and/or Apprise, controlled by their own "Media Mirror"
    toggles in Settings -> Notifications plus the usual library filter.

    A scheduled run that copied nothing and had no failures is not announced
    -- a nightly "nothing changed" message would just be noise. A manual run
    always is, and a failed run always is."""
    nothing_happened = not error and not totals.get("updated") and not totals.get("failed")
    if scheduled and nothing_happened:
        logger.debug("[MIRROR] Scheduled run changed nothing -- no notification")
        return

    send_discord = _should_notify("media_mirror", library_id)
    send_apprise = _should_notify_apprise("media_mirror", library_id)
    if not send_discord and not send_apprise:
        return

    from ..media_server import get_server_label
    group_label = group_name or _get_library_name(library_id)
    servers = None
    if source_server_id:
        targets = ", ".join(get_server_label(t) for t in target_server_ids) or "—"
        servers = f"{get_server_label(source_server_id)} → {targets}"

    fields: List[tuple] = [("Library", group_label)]
    if servers:
        fields.append(("Servers", servers))
    if error:
        description = f"Run failed: {error}"
        color = 0xFF4757
    else:
        fields.extend(_mirror_count_lines(asset_counts))
        fields.extend(_mirror_count_lines(collection_counts, prefix="Collection "))
        if totals.get("unmapped"):
            fields.append(("Unmapped", f"{totals['unmapped']} item(s) not found on a target"))
        if totals.get("failed"):
            description = f"Run finished with {totals['failed']} failed item(s)"
            color = 0xFFA502
        elif totals.get("updated"):
            description = f"Run successful — {totals['updated']} of {totals.get('checked', 0)} item(s) updated"
            color = 0x3DD6B7
        else:
            description = f"Run successful — nothing changed ({totals.get('checked', 0)} item(s) checked)"
            color = 0x3DD6B7

    title = f"\U0001FA9E {'Scheduled ' if scheduled else ''}Media Mirror Complete"
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": [{"name": n, "value": v, "inline": True} for n, v in fields],
        "footer": {"text": "Simposter"},
        "timestamp": datetime.utcnow().isoformat(),
    }

    settings = _get_notification_settings()
    if send_discord:
        try:
            resp = requests.post(settings.get("discordWebhookUrl", ""), json={"embeds": [embed]}, timeout=10)
            if resp.status_code not in (200, 204):
                logger.warning("[DISCORD] Media Mirror notification failed: HTTP %s", resp.status_code)
        except Exception as e:
            logger.error("[DISCORD] Media Mirror notification error: %s", e)

    if send_apprise:
        other_urls: List[str] = []
        for url in settings.get("appriseUrls", []) or []:
            if not url.strip():
                continue
            discord_webhook = _resolve_discord_webhook_url(url)
            if discord_webhook:
                try:
                    resp = requests.post(discord_webhook, json={"embeds": [embed]}, timeout=10)
                    if resp.status_code not in (200, 204):
                        logger.warning("[APPRISE] Media Mirror Discord embed failed: HTTP %s", resp.status_code)
                except Exception as e:
                    logger.error("[APPRISE] Media Mirror Discord embed error: %s", e)
            else:
                other_urls.append(url.strip())
        if other_urls:
            try:
                import apprise
                ap = apprise.Apprise()
                for url in other_urls:
                    ap.add(url)
                body = description + "".join(f"\n{n}: {v}" for n, v in fields)
                if len(ap) > 0 and not ap.notify(title=f"{title} — Simposter", body=body):
                    logger.warning("[APPRISE] One or more Apprise services failed (Media Mirror)")
            except Exception as e:
                logger.error("[APPRISE] Media Mirror notification error: %s", e)


def send_batch_notification(
    library_id: Optional[str],
    template_id: str,
    preset_id: str,
    success_count: int,
    failed_count: int,
    source: str = "batch",
    action: str = "sent_to_plex",
    synced_server_ids: Optional[List[str]] = None,
) -> bool:
    """
    Send a notification for batch processing completion.

    Args:
        library_id: The library ID
        template_id: Template used
        preset_id: Preset used
        success_count: Number of successful posters
        failed_count: Number of failed posters
        source: Source type ('batch', 'auto_generate', etc.)
        action: Was previously ALWAYS hardcoded "sent_to_plex" here, regardless
            of whether the batch run actually targeted Plex at all -- a real,
            misleading bug for a Jellyfin/Emby-only batch (req.send_to_plex
            False, targets=[...] only), which would still have said "Sent to
            Plex" despite never touching Plex. Callers now pass the batch's
            real `req.send_to_plex`-derived action instead.
        synced_server_ids: Union of every non-Plex server_id actually synced
            to across the whole batch run, for the "Also synced to" field --
            independent of `action`, since a run can send to Plex directly
            AND sync to a linked Jellyfin/Emby server in the same pass.

    Returns:
        True if notification was sent successfully
    """
    total = success_count + failed_count
    return send_discord_notification(
        title=f"{total} posters processed",
        template_id=template_id,
        preset_id=preset_id,
        library_id=library_id,
        source=source,
        action=action,
        count=total,
        success_count=success_count,
        failed_count=failed_count,
        synced_server_ids=synced_server_ids,
    )


def start_batch_progress_notification(
    library_id: Optional[str],
    template_id: str,
    total_count: int,
    source: str = "batch",
    preset_id: Optional[str] = None,
) -> Optional[str]:
    """
    Send initial batch progress notification and return the message ID for updates.

    Returns:
        Message ID if successful, None otherwise
    """
    if not _should_notify(source, library_id):
        return None

    settings = _get_notification_settings()
    webhook_url = settings.get("discordWebhookUrl", "")
    if not webhook_url:
        return None

    try:
        library_name = _get_library_name(library_id)
        emoji = _get_source_emoji(source)
        source_label = _get_source_label(source)

        embed = {
            "title": f"{emoji} {source_label} Started",
            "description": f"Processing **0/{total_count}** posters...",
            "color": 0x3DD6B7,  # Simposter accent color
            "fields": [
                {
                    "name": "Library",
                    "value": library_name,
                    "inline": True
                },
                {
                    "name": "Preset",
                    "value": _get_preset_label(template_id, preset_id),
                    "inline": True
                },
                {
                    "name": "Status",
                    "value": "Starting...",
                    "inline": True
                }
            ],
            "footer": {
                "text": "Simposter"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # Add ?wait=true to get the message object back (including ID)
        response = requests.post(
            f"{webhook_url}?wait=true",
            json={"embeds": [embed]},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            message_id = data.get("id")
            logger.info(f"[DISCORD] Batch progress started, message_id={message_id}")
            return message_id
        else:
            logger.warning(f"[DISCORD] Failed to start batch progress: HTTP {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"[DISCORD] Error starting batch progress: {e}")
        return None


def update_batch_progress_notification(
    message_id: str,
    library_id: Optional[str],
    template_id: str,
    current_index: int,
    total_count: int,
    current_title: str,
    success_count: int,
    failed_count: int,
    source: str = "batch",
    poster_data: Optional[bytes] = None,
    poster_fallback_count: int = 0,
    logo_fallback_count: int = 0,
    preset_id: Optional[str] = None,
) -> bool:
    """
    Update an existing batch progress notification.

    Args:
        message_id: The Discord message ID to update
        poster_data: Optional poster image bytes to show as thumbnail

    Returns:
        True if update was successful
    """
    settings = _get_notification_settings()
    webhook_url = settings.get("discordWebhookUrl", "")
    if not webhook_url or not message_id:
        return False

    try:
        library_name = _get_library_name(library_id)
        emoji = _get_source_emoji(source)
        source_label = _get_source_label(source)

        # Progress bar
        progress_pct = int((current_index / total_count) * 100) if total_count > 0 else 0
        filled = int(progress_pct / 10)
        progress_bar = "█" * filled + "░" * (10 - filled)

        embed = {
            "title": f"{emoji} {source_label} In Progress",
            "description": f"**{current_index}/{total_count}** - {current_title}\n\n`{progress_bar}` {progress_pct}%",
            "color": 0x3DD6B7,
            "fields": [
                {
                    "name": "Library",
                    "value": library_name,
                    "inline": True
                },
                {
                    "name": "Preset",
                    "value": _get_preset_label(template_id, preset_id),
                    "inline": True
                },
                {
                    "name": "Success",
                    "value": str(success_count),
                    "inline": True
                }
            ],
            "footer": {
                "text": "Simposter"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        if failed_count > 0:
            embed["fields"].append({
                "name": "Failed",
                "value": str(failed_count),
                "inline": True
            })

        # Show fallback counts if any were used
        if poster_fallback_count > 0 or logo_fallback_count > 0:
            fallback_parts = []
            if poster_fallback_count > 0:
                fallback_parts.append(f"Poster: {poster_fallback_count}")
            if logo_fallback_count > 0:
                fallback_parts.append(f"Logo: {logo_fallback_count}")
            embed["fields"].append({
                "name": "\U0001F504 Fallbacks",
                "value": " | ".join(fallback_parts),
                "inline": True
            })

        # Add poster thumbnail if provided
        if poster_data:
            embed["thumbnail"] = {"url": "attachment://poster.jpg"}

        edit_url = f"{webhook_url}/messages/{message_id}"

        if poster_data:
            import json
            files = {
                "file": ("poster.jpg", poster_data, "image/jpeg")
            }
            payload_json = json.dumps({"embeds": [embed]})
            response = requests.patch(
                edit_url,
                data={"payload_json": payload_json},
                files=files,
                timeout=15
            )
        else:
            response = requests.patch(
                edit_url,
                json={"embeds": [embed]},
                timeout=10
            )

        if response.status_code == 200:
            return True
        else:
            logger.warning(f"[DISCORD] Failed to update batch progress: HTTP {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"[DISCORD] Error updating batch progress: {e}")
        return False


def complete_batch_progress_notification(
    message_id: str,
    library_id: Optional[str],
    template_id: str,
    total_count: int,
    success_count: int,
    failed_count: int,
    source: str = "batch",
    poster_data: Optional[bytes] = None,
    poster_fallback_count: int = 0,
    logo_fallback_count: int = 0,
    synced_server_ids: Optional[List[str]] = None,
    preset_id: Optional[str] = None,
    action: str = "sent_to_plex",
) -> bool:
    """
    Update batch progress notification with final completion status.
    """
    settings = _get_notification_settings()
    webhook_url = settings.get("discordWebhookUrl", "")
    if not webhook_url or not message_id:
        return False

    try:
        library_name = _get_library_name(library_id)
        emoji = _get_source_emoji(source)
        source_label = _get_source_label(source)

        # Color based on results
        if failed_count > 0 and success_count == 0:
            color = 0xFF4757  # Red for all failures
        elif failed_count > 0:
            color = 0xFFA502  # Orange for partial failures
        else:
            color = 0x3DD6B7  # Green for success

        description = f"**{success_count}** posters generated successfully"
        if failed_count > 0:
            description += f"\n**{failed_count}** failed"

        fields = [
            {"name": name, "value": value, "inline": True}
            for name, value in _summary_fields(library_id, template_id, preset_id, action, None, synced_server_ids)
        ]
        fields.append({"name": "Total", "value": str(total_count), "inline": True})

        # Show fallback counts if any were used
        if poster_fallback_count > 0 or logo_fallback_count > 0:
            fallback_parts = []
            if poster_fallback_count > 0:
                fallback_parts.append(f"Poster: {poster_fallback_count}")
            if logo_fallback_count > 0:
                fallback_parts.append(f"Logo: {logo_fallback_count}")
            fields.append({
                "name": "\U0001F504 Fallbacks",
                "value": " | ".join(fallback_parts),
                "inline": True
            })

        embed = {
            "title": f"{emoji} {source_label} Complete",
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {
                "text": "Simposter"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        if poster_data:
            embed["thumbnail"] = {"url": "attachment://poster.jpg"}

        edit_url = f"{webhook_url}/messages/{message_id}"

        if poster_data:
            import json
            files = {
                "file": ("poster.jpg", poster_data, "image/jpeg")
            }
            payload_json = json.dumps({"embeds": [embed]})
            response = requests.patch(
                edit_url,
                data={"payload_json": payload_json},
                files=files,
                timeout=15
            )
        else:
            response = requests.patch(
                edit_url,
                json={"embeds": [embed]},
                timeout=10
            )

        if response.status_code == 200:
            logger.info(f"[DISCORD] Batch progress completed")
            return True
        else:
            logger.warning(f"[DISCORD] Failed to complete batch progress: HTTP {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"[DISCORD] Error completing batch progress: {e}")
        return False


@router.post("/notifications/test-apprise")
def test_apprise_notification(request: TestAppriseRequest):
    """Test Apprise URLs by sending a test notification to all of them."""
    if not request.urls:
        return {"success": False, "error": "No URLs provided"}

    valid_urls = [u.strip() for u in request.urls if u.strip()]
    if not valid_urls:
        return {"success": False, "error": "No valid URLs provided"}

    try:
        import apprise
        ap = apprise.Apprise()
        for url in valid_urls:
            ap.add(url)

        if len(ap) == 0:
            return {"success": False, "error": "No valid Apprise URLs could be loaded"}

        result = ap.notify(
            title="\U0001F3AC Simposter Test",
            body="Your Apprise notification is configured correctly!"
        )

        if result:
            return {"success": True}
        else:
            return {"success": False, "error": "Apprise failed to deliver to one or more services — check your URLs"}

    except ImportError:
        return {"success": False, "error": "Apprise library not installed. Run: pip install apprise"}
    except Exception as e:
        logger.error(f"[APPRISE] Test error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/notifications/test-discord")
def test_discord_webhook(request: TestWebhookRequest):
    """Test a Discord webhook by sending a test message."""
    if not request.webhook_url:
        return {"success": False, "error": "Webhook URL is required"}

    try:
        embed = {
            "title": "\U0001F3AC Simposter Test",
            "description": "Your Discord webhook is configured correctly!",
            "color": 0x3DD6B7,  # Simposter accent color
            "fields": [
                {
                    "name": "Status",
                    "value": "Connection successful",
                    "inline": True
                }
            ],
            "footer": {
                "text": "Simposter Notifications"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        payload = {
            "embeds": [embed]
        }

        response = requests.post(
            request.webhook_url,
            json=payload,
            timeout=10
        )

        if response.status_code in (200, 204):
            return {"success": True}
        else:
            return {"success": False, "error": f"Discord returned HTTP {response.status_code}"}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Connection timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"[DISCORD] Test webhook error: {e}")
        return {"success": False, "error": "An unexpected error occurred"}
