from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from app.models import User, now_iso

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_parent_dir()
        self._init_db()

    def _ensure_parent_dir(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_chat_id INTEGER NOT NULL UNIQUE,
                    telegram_user_id INTEGER NOT NULL,
                    username TEXT,
                    address TEXT NOT NULL,
                    monitoring_enabled INTEGER NOT NULL DEFAULT 1,
                    last_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def upsert_user_address(
        self,
        telegram_chat_id: int,
        telegram_user_id: int,
        username: str | None,
        address: str,
        baseline_status: str,
    ) -> None:
        timestamp = now_iso()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE telegram_chat_id = ?",
                (telegram_chat_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET telegram_user_id = ?,
                        username = ?,
                        address = ?,
                        monitoring_enabled = 1,
                        last_status = ?,
                        updated_at = ?
                    WHERE telegram_chat_id = ?
                    """,
                    (
                        telegram_user_id,
                        username,
                        address,
                        baseline_status,
                        timestamp,
                        telegram_chat_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users (
                        telegram_chat_id,
                        telegram_user_id,
                        username,
                        address,
                        monitoring_enabled,
                        last_status,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        telegram_chat_id,
                        telegram_user_id,
                        username,
                        address,
                        baseline_status,
                        timestamp,
                        timestamp,
                    ),
                )

    def stop_monitoring(self, telegram_chat_id: int) -> bool:
        timestamp = now_iso()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET monitoring_enabled = 0,
                    updated_at = ?
                WHERE telegram_chat_id = ?
                """,
                (timestamp, telegram_chat_id),
            )
            return cursor.rowcount > 0

    def resume_monitoring(self, telegram_chat_id: int, baseline_status: str) -> bool:
        timestamp = now_iso()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET monitoring_enabled = 1,
                    last_status = ?,
                    updated_at = ?
                WHERE telegram_chat_id = ?
                """,
                (baseline_status, timestamp, telegram_chat_id),
            )
            return cursor.rowcount > 0

    def list_active_users(self) -> list[User]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE monitoring_enabled = 1"
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def get_user_by_chat_id(self, telegram_chat_id: int) -> User | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE telegram_chat_id = ?",
                (telegram_chat_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def update_last_status(self, user_id: int, new_status: str) -> None:
        timestamp = now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE users
                SET last_status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (new_status, timestamp, user_id),
            )

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            telegram_chat_id=row["telegram_chat_id"],
            telegram_user_id=row["telegram_user_id"],
            username=row["username"],
            address=row["address"],
            monitoring_enabled=bool(row["monitoring_enabled"]),
            last_status=row["last_status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
