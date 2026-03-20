from __future__ import annotations

import logging
from typing import Any

import httpx
from telegram import Bot

from app.models import STATUS_GREEN, STATUS_UNKNOWN, STATUS_YELLOW
from app.storage import Storage

logger = logging.getLogger(__name__)


def extract_boyar_status(payload: dict[str, Any], address: str) -> str:
    try:
        status = (
            payload.get("AllRegisteredNodes", {})
            .get(address, {})
            .get("NodeServices", {})
            .get("Boyar", {})
            .get("Status", STATUS_UNKNOWN)
        )
        logger.debug("JSON lookup address=%s status=%s", address, status)
        return status
    except Exception:
        return STATUS_UNKNOWN


async def fetch_status_json(url: str) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                return data
            logger.warning("Status JSON is not an object")
            return None
    except Exception as exc:
        logger.exception("Failed to fetch status JSON: %s", exc)
        return None


async def run_monitoring_cycle(storage: Storage, bot: Bot, status_json_url: str) -> None:
    users = storage.list_active_users()
    if not users:
        logger.debug("No active users, skipping cycle")
        return

    payload = await fetch_status_json(status_json_url)
    if payload is None:
        logger.warning("Skipping cycle due to missing payload")
        return

    for user in users:
        try:
            current_status = extract_boyar_status(payload, user.address)
            last_status = user.last_status or STATUS_UNKNOWN

            should_alert = last_status == STATUS_GREEN and current_status == STATUS_YELLOW
            if should_alert:
                message = (
                    "⚠️ Node Status Check Required\n\n"
                    f"Address: 0x{user.address}\n"
                    f"Status: {current_status}\n\n"
                    "Check status:\n"
                    "https://status.orbs.network"
                )
                try:
                    await bot.send_message(chat_id=user.telegram_chat_id, text=message)
                    logger.info(
                        "Alert sent: chat_id=%s address=%s %s->%s",
                        user.telegram_chat_id,
                        user.address,
                        last_status,
                        current_status,
                    )
                except Exception as send_exc:
                    logger.exception(
                        "Failed to send Telegram message to %s: %s",
                        user.telegram_chat_id,
                        send_exc,
                    )

            storage.update_last_status(user.id, current_status)
        except Exception as user_exc:
            logger.exception("Monitoring failed for user id=%s: %s", user.id, user_exc)
