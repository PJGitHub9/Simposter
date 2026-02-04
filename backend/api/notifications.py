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
        "auto_generate": "discordNotifyAutoGenerate"
    }

    setting_key = source_map.get(source)
    if setting_key and not settings.get(setting_key, True):
        return False

    # Check library filter
    notify_libraries = settings.get("discordNotifyLibraries", [])
    if notify_libraries and library_id and library_id not in notify_libraries:
        return False

    return True


def _get_library_name(library_id: Optional[str]) -> str:
    """Get display name for a library."""
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

        return library_id
    except Exception:
        return library_id


def _get_source_emoji(source: str) -> str:
    """Get emoji for notification source."""
    return {
        "batch": "\U0001F4E6",  # Package
        "manual": "\U0001F3A8",  # Artist palette
        "webhook": "\U0001F517",  # Link
        "auto_generate": "\U0001F504"  # Arrows
    }.get(source, "\U0001F3AC")  # Clapper board default


def _get_source_label(source: str) -> str:
    """Get readable label for notification source."""
    return {
        "batch": "Batch Edit",
        "manual": "Manual Send",
        "webhook": "Webhook",
        "auto_generate": "Auto-Generate"
    }.get(source, source)


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
    failed_count: int = 0
) -> bool:
    """
    Send a Discord webhook notification for poster generation.

    Args:
        poster_data: Optional bytes of the poster image to attach directly to Discord

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

        action_text = "Sent to Plex" if action == "sent_to_plex" else "Saved locally"

        embed = {
            "title": f"{emoji} {source_label} Complete",
            "description": description,
            "color": color,
            "fields": [
                {
                    "name": "Library",
                    "value": library_name,
                    "inline": True
                },
                {
                    "name": "Template",
                    "value": template_id or "N/A",
                    "inline": True
                },
                {
                    "name": "Action",
                    "value": action_text,
                    "inline": True
                }
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


def send_batch_notification(
    library_id: Optional[str],
    template_id: str,
    preset_id: str,
    success_count: int,
    failed_count: int,
    source: str = "batch"
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
        action="sent_to_plex",
        count=total,
        success_count=success_count,
        failed_count=failed_count
    )


def start_batch_progress_notification(
    library_id: Optional[str],
    template_id: str,
    total_count: int,
    source: str = "batch"
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
                    "name": "Template",
                    "value": template_id or "N/A",
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
                    "name": "Template",
                    "value": template_id or "N/A",
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
            {
                "name": "Library",
                "value": library_name,
                "inline": True
            },
            {
                "name": "Template",
                "value": template_id or "N/A",
                "inline": True
            },
            {
                "name": "Total",
                "value": str(total_count),
                "inline": True
            }
        ]

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
