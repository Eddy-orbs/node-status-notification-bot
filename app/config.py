from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    status_json_url: str
    check_interval_seconds: int
    sqlite_db_path: str
    log_level: str


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")

    return Settings(
        telegram_bot_token=telegram_bot_token,
        status_json_url=os.getenv("STATUS_JSON_URL", "https://status.orbs.network/json").strip(),
        check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "1800")),
        sqlite_db_path=os.getenv("SQLITE_DB_PATH", "/app/data/app.db").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
