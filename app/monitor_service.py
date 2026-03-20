from __future__ import annotations

import logging
from typing import Any

import httpx
from telegram import Bot
from telegram.error import Forbidden

from app.models import MODE_MANAGER_ALL, STATUS_GREEN, STATUS_UNKNOWN, STATUS_YELLOW
from app.storage import Storage

logger = logging.getLogger(__name__)


def _is_user_blocked_error(exc: BaseException) -> bool:
    if not isinstance(exc, Forbidden):
        return False
    return "blocked" in str(exc).lower()


def _handle_alert_send_failure(
    storage: Storage, telegram_chat_id: int, exc: BaseException
) -> None:
    if _is_user_blocked_error(exc):
        logger.warning("user blocked bot: chat_id=%s", telegram_chat_id)
        try:
            storage.stop_monitoring(telegram_chat_id)
        except Exception:
            logger.exception(
                "Failed to set monitoring_enabled=false after user blocked bot: chat_id=%s",
                telegram_chat_id,
            )
        return
    logger.exception(
        "Failed to send alert message to %s: %s",
        telegram_chat_id,
        exc,
    )


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


def extract_all_node_statuses(payload: dict[str, Any]) -> dict[str, str]:
    nodes = payload.get("AllRegisteredNodes", {})
    if not isinstance(nodes, dict):
        return {}

    statuses: dict[str, str] = {}
    for node_address, node_payload in nodes.items():
        try:
            status = (
                node_payload.get("NodeServices", {})
                .get("Boyar", {})
                .get("Status", STATUS_UNKNOWN)
            )
            statuses[str(node_address).lower()] = status
        except Exception:
            statuses[str(node_address).lower()] = STATUS_UNKNOWN
    return statuses


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
            if user.monitoring_mode == MODE_MANAGER_ALL:
                previous_states = storage.get_manager_states(user.id)
                current_states = extract_all_node_statuses(payload)

                send_aborted_user_blocked = False
                for node_address, current_status in current_states.items():
                    if send_aborted_user_blocked:
                        break
                    last_status = previous_states.get(node_address, STATUS_UNKNOWN)
                    should_alert = (
                        last_status == STATUS_GREEN and current_status == STATUS_YELLOW
                    )
                    if not should_alert:
                        continue

                    message = (
                        "⚠️ Boyar Status Alert\n\n"
                        "Monitoring Mode: All Nodes\n"
                        f"Address: 0x{node_address}\n"
                        f"Status Change: {last_status} → {current_status}\n\n"
                        "Check status:\n"
                        "https://status.orbs.network"
                    )
                    try:
                        await bot.send_message(chat_id=user.telegram_chat_id, text=message)
                        logger.info(
                            "All-node alert sent: chat_id=%s address=%s %s->%s",
                            user.telegram_chat_id,
                            node_address,
                            last_status,
                            current_status,
                        )
                    except Exception as send_exc:
                        _handle_alert_send_failure(
                            storage, user.telegram_chat_id, send_exc
                        )
                        if _is_user_blocked_error(send_exc):
                            send_aborted_user_blocked = True

                storage.replace_manager_states(user.id, current_states)
                continue

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
                    _handle_alert_send_failure(storage, user.telegram_chat_id, send_exc)

            storage.update_last_status(user.id, current_status)
        except Exception as user_exc:
            logger.exception("Monitoring failed for user id=%s: %s", user.id, user_exc)
