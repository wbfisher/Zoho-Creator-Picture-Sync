"""Failure alerting via webhook.

Set ALERT_WEBHOOK_URL to a Slack incoming webhook, Discord webhook, or any
endpoint that accepts a JSON POST. The payload includes both Slack ("text")
and Discord ("content") keys, so either works without configuration.

If no webhook is configured, alerts are logged at ERROR level so they at
least show up prominently in Railway logs.
"""
import logging

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


async def send_alert(subject: str, message: str) -> bool:
    """Send an alert. Never raises — alerting must not break the sync."""
    settings = get_settings()
    url = getattr(settings, "alert_webhook_url", "") or ""

    text = f"[Zoho Pictures Sync] {subject}\n{message}"

    if not url:
        logger.error(f"ALERT (no ALERT_WEBHOOK_URL configured): {text}")
        return False

    payload = {
        "text": text,       # Slack
        "content": text,    # Discord
        "subject": subject, # generic consumers
        "message": message,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                logger.error(
                    f"Alert webhook returned HTTP {response.status_code}: {response.text[:200]}"
                )
                return False
        logger.info(f"Alert sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send alert webhook: {e}")
        return False
