from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
ETH_ADDRESS_KEY_RE = re.compile(r"^[a-f0-9]{40}$")

STATUS_GREEN = "Green"
STATUS_YELLOW = "Yellow"
STATUS_UNKNOWN = "UNKNOWN"


@dataclass
class User:
    id: int
    telegram_chat_id: int
    telegram_user_id: int
    username: Optional[str]
    address: str
    monitoring_enabled: bool
    last_status: str
    created_at: str
    updated_at: str


def is_valid_eth_address(address: str) -> bool:
    return bool(ETH_ADDRESS_RE.match(address.strip()))


def normalize_address(address: str) -> str:
    trimmed = address.strip()
    if not trimmed.lower().startswith("0x"):
        raise ValueError("Address must start with 0x")
    return trimmed[2:].lower()


def is_valid_normalized_address(address_key: str) -> bool:
    return bool(ETH_ADDRESS_KEY_RE.match(address_key))


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
