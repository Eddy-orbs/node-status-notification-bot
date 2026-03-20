from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application, CommandHandler

from app.bot_handlers import (
    resume_command,
    set_command,
    start_command,
    status_command,
    stop_command,
)
from app.config import load_settings
from app.monitor_service import run_monitoring_cycle
from app.storage import Storage


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def post_init(application: Application) -> None:
    settings = application.bot_data["settings"]
    storage = application.bot_data["storage"]

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_monitoring_cycle,
        "interval",
        seconds=settings.check_interval_seconds,
        kwargs={
            "storage": storage,
            "bot": application.bot,
            "status_json_url": settings.status_json_url,
        },
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logging.getLogger(__name__).info(
        "Scheduler started. interval=%s sec", settings.check_interval_seconds
    )


async def post_shutdown(application: Application) -> None:
    scheduler = application.bot_data.get("scheduler")
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def run() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    storage = Storage(settings.sqlite_db_path)

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.bot_data["settings"] = settings
    application.bot_data["storage"] = storage
    application.bot_data["status_json_url"] = settings.status_json_url

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("set", set_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("resume", resume_command))

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run()
