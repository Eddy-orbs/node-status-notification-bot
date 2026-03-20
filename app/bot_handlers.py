from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.models import STATUS_UNKNOWN, is_valid_normalized_address, normalize_address
from app.monitor_service import extract_boyar_status, fetch_status_json
from app.storage import Storage

logger = logging.getLogger(__name__)


def _address_exists_in_registered_nodes(payload: dict, normalized_address: str) -> bool:
    nodes = payload.get("AllRegisteredNodes", {})
    if not isinstance(nodes, dict):
        return False
    if normalized_address in nodes:
        return True
    # Fallback for unexpected key casing in upstream JSON.
    return normalized_address.lower() in {str(key).lower() for key in nodes.keys()}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return

    text = (
        "Hello. This is the Orbs Node status monitoring bot.\n\n"
        "Register address:\n"
        "/set address 0x1234...\n\n"
        "Check current status:\n"
        "/status\n\n"
        "Resume monitoring:\n"
        "/resume\n\n"
        "Stop monitoring:\n"
        "/stop"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode="Markdown",
    )


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.effective_user is None:
        return

    storage: Storage = context.application.bot_data["storage"]
    status_json_url: str = context.application.bot_data["status_json_url"]

    args = context.args
    if len(args) != 2 or args[0].lower() != "address":
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Usage: /set address <ethereum_address>",
        )
        return

    raw_address = args[1]
    try:
        address = normalize_address(raw_address)
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Invalid address format. It must start with 0x.",
        )
        return

    if not is_valid_normalized_address(address):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Invalid address format. Example: 0x1234... (0x + 40 hex).",
        )
        return

    logger.info(
        "Address normalized for chat_id=%s raw=%s normalized=%s",
        update.effective_chat.id,
        raw_address.strip(),
        address,
    )

    payload = await fetch_status_json(status_json_url)
    baseline_status = STATUS_UNKNOWN
    address_exists = False
    if payload is not None:
        address_exists = _address_exists_in_registered_nodes(payload, address)
        baseline_status = extract_boyar_status(payload, address)

    try:
        storage.upsert_user_address(
            telegram_chat_id=update.effective_chat.id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
            address=address,
            baseline_status=baseline_status,
        )
        if not address_exists:
            storage.stop_monitoring(update.effective_chat.id)
    except Exception as exc:
        logger.exception("Failed to store user address: %s", exc)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while saving. Please try again in a moment.",
        )
        return

    if not address_exists:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "Address saved, but this address was not found in the current Orbs status data.\n"
                "Monitoring is currently OFF.\n"
                "Please verify the address and try again later."
            ),
        )
        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "Address has been registered.\n"
            f"Address: {address}\n"
            f"Current Node status (baseline): {baseline_status}\n"
            "No alert is sent immediately after registration."
        ),
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return

    storage: Storage = context.application.bot_data["storage"]

    try:
        changed = storage.stop_monitoring(update.effective_chat.id)
    except Exception as exc:
        logger.exception("Failed to stop monitoring: %s", exc)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while stopping monitoring. Please try again in a moment.",
        )
        return

    if changed:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Monitoring has been stopped.",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="There is no registered target to monitor.",
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return

    storage: Storage = context.application.bot_data["storage"]
    chat_id = update.effective_chat.id
    logger.info("/status called: chat_id=%s", chat_id)

    try:
        user = storage.get_user_by_chat_id(chat_id)
    except Exception as exc:
        logger.exception("Failed to read status for chat_id=%s: %s", chat_id, exc)
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while checking status. Please try again in a moment.",
        )
        return

    if user is None:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Address: (not set)\nMonitoring: OFF",
        )
        return

    monitoring_label = "ON" if user.monitoring_enabled else "OFF"
    last_status = "N/A" if not user.last_status or user.last_status == STATUS_UNKNOWN else user.last_status
    display_address = f"0x{user.address}" if user.address else "(not set)"
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"Address: {display_address}\n"
            f"Monitoring: {monitoring_label}\n"
            f"Last Status: {last_status}"
        ),
    )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return

    storage: Storage = context.application.bot_data["storage"]
    status_json_url: str = context.application.bot_data["status_json_url"]
    chat_id = update.effective_chat.id

    try:
        user = storage.get_user_by_chat_id(chat_id)
    except Exception as exc:
        logger.exception("Failed to load user for /resume chat_id=%s: %s", chat_id, exc)
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while resuming monitoring. Please try again in a moment.",
        )
        return

    if user is None or not user.address:
        await context.bot.send_message(
            chat_id=chat_id,
            text="No registered address found. Please register first with /set address 0x...",
        )
        return

    payload = await fetch_status_json(status_json_url)
    baseline_status = STATUS_UNKNOWN
    address_exists = False
    if payload is not None:
        address_exists = _address_exists_in_registered_nodes(payload, user.address)
        baseline_status = extract_boyar_status(payload, user.address)

    if not address_exists:
        try:
            storage.stop_monitoring(chat_id)
        except Exception as exc:
            logger.exception("Failed to keep monitoring OFF for chat_id=%s: %s", chat_id, exc)
            await context.bot.send_message(
                chat_id=chat_id,
                text="An error occurred while resuming monitoring. Please try again in a moment.",
            )
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "This address was not found in the current Orbs status data.\n"
                "Monitoring remains OFF.\n"
                "Please verify the address and try again later."
            ),
        )
        return

    try:
        updated = storage.resume_monitoring(chat_id, baseline_status)
    except Exception as exc:
        logger.exception("Failed to resume monitoring for chat_id=%s: %s", chat_id, exc)
        await context.bot.send_message(
            chat_id=chat_id,
            text="An error occurred while resuming monitoring. Please try again in a moment.",
        )
        return

    if not updated:
        await context.bot.send_message(
            chat_id=chat_id,
            text="No registered address found. Please register first with /set address 0x...",
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "Monitoring has resumed.\n"
            f"Current Node status: {baseline_status}\n"
            "(This status will be used as the baseline for change detection.)"
        ),
    )
