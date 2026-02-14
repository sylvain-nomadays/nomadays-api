"""
Appointment reminder service.

Runs as a daily scheduled job (APScheduler) at 07:00 UTC (09:00 Paris).
Calls the Next.js cron endpoint /api/cron/appointment-reminders which handles
the actual reminder logic (find J-1 appointments, send emails, mark as sent).

This approach keeps all appointment + email logic in the Next.js server actions
(single source of truth) while leveraging APScheduler for reliable scheduling.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def process_appointment_reminders() -> None:
    """
    Call the Next.js cron endpoint to send J-1 appointment reminders.
    """
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    cron_secret = os.environ.get("CRON_SECRET", "")

    if not cron_secret:
        logger.warning(
            "CRON_SECRET is not set — skipping appointment reminders. "
            "Set CRON_SECRET in .env to enable."
        )
        return

    url = f"{frontend_url}/api/cron/appointment-reminders"
    logger.info("Calling appointment reminders endpoint: %s", url)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={"x-cron-secret": cron_secret},
            )

        if response.status_code == 200:
            data = response.json()
            logger.info(
                "Appointment reminders processed — Sent: %d, Errors: %d",
                data.get("sent", 0),
                data.get("errors", 0),
            )
        else:
            logger.error(
                "Appointment reminders endpoint returned %d: %s",
                response.status_code,
                response.text[:200],
            )

    except httpx.ConnectError:
        logger.error(
            "Cannot connect to frontend at %s — is the Next.js server running?",
            frontend_url,
        )
    except Exception as e:
        logger.error("Error calling appointment reminders: %s", e, exc_info=True)
