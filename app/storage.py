from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from app.models import MODE_MANAGER_ALL, MODE_SINGLE, STATUS_UNKNOWN, User, now_iso

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
                    monitoring_mode TEXT NOT NULL DEFAULT 'single',
                    last_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_user_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manager_monitor_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    node_address TEXT NOT NULL,
                    last_status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, node_address),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

    @staticmethod
    def _has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(row["name"] == column_name for row in rows)

    def _ensure_user_columns(self, conn: sqlite3.Connection) -> None:
        if not self._has_column(conn, "users", "monitoring_mode"):
            conn.execute(
                "ALTER TABLE users ADD COLUMN monitoring_mode TEXT NOT NULL DEFAULT 'single'"
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
                        monitoring_mode = ?,
                        last_status = ?,
                        updated_at = ?
                    WHERE telegram_chat_id = ?
                    """,
                    (
                        telegram_user_id,
                        username,
                        address,
                        MODE_SINGLE,
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
                        monitoring_mode,
                        last_status,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        telegram_chat_id,
                        telegram_user_id,
                        username,
                        address,
                        MODE_SINGLE,
                        baseline_status,
                        timestamp,
                        timestamp,
                    ),
                )
            user_row = conn.execute(
                "SELECT id FROM users WHERE telegram_chat_id = ?",
                (telegram_chat_id,),
            ).fetchone()
            if user_row is not None:
                conn.execute(
                    "DELETE FROM manager_monitor_states WHERE user_id = ?",
                    (user_row["id"],),
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
                    monitoring_mode = ?,
                    last_status = ?,
                    updated_at = ?
                WHERE telegram_chat_id = ?
                """,
                (MODE_SINGLE, baseline_status, timestamp, telegram_chat_id),
            )
            return cursor.rowcount > 0

    def set_monitoring_enabled(self, telegram_chat_id: int, enabled: bool) -> bool:
        timestamp = now_iso()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE users
                SET monitoring_enabled = ?,
                    updated_at = ?
                WHERE telegram_chat_id = ?
                """,
                (1 if enabled else 0, timestamp, telegram_chat_id),
            )
            return cursor.rowcount > 0

    def enable_manager_monitoring(
        self,
        telegram_chat_id: int,
        telegram_user_id: int,
        username: str | None,
        baseline_states: dict[str, str],
    ) -> None:
        timestamp = now_iso()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, address FROM users WHERE telegram_chat_id = ?",
                (telegram_chat_id,),
            ).fetchone()
            if existing:
                user_id = existing["id"]
                conn.execute(
                    """
                    UPDATE users
                    SET telegram_user_id = ?,
                        username = ?,
                        monitoring_enabled = 1,
                        monitoring_mode = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (telegram_user_id, username, MODE_MANAGER_ALL, timestamp, user_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO users (
                        telegram_chat_id,
                        telegram_user_id,
                        username,
                        address,
                        monitoring_enabled,
                        monitoring_mode,
                        last_status,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        telegram_chat_id,
                        telegram_user_id,
                        username,
                        "",
                        MODE_MANAGER_ALL,
                        STATUS_UNKNOWN,
                        timestamp,
                        timestamp,
                    ),
                )
                user_id = cursor.lastrowid

            conn.execute(
                "DELETE FROM manager_monitor_states WHERE user_id = ?",
                (user_id,),
            )
            for node_address, node_status in baseline_states.items():
                conn.execute(
                    """
                    INSERT INTO manager_monitor_states (user_id, node_address, last_status, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, node_address, node_status, timestamp),
                )

    def disable_manager_monitoring(
        self,
        telegram_chat_id: int,
        *,
        activate_single: bool,
        single_baseline: str | None,
    ) -> None:
        """Exit manager_all mode; optionally re-enable single-address monitoring with baseline."""
        timestamp = now_iso()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE telegram_chat_id = ?",
                (telegram_chat_id,),
            ).fetchone()
            if row is None:
                return
            user_id = row["id"]
            conn.execute(
                "DELETE FROM manager_monitor_states WHERE user_id = ?",
                (user_id,),
            )
            if activate_single and single_baseline is not None:
                conn.execute(
                    """
                    UPDATE users
                    SET monitoring_mode = ?,
                        monitoring_enabled = 1,
                        last_status = ?,
                        updated_at = ?
                    WHERE telegram_chat_id = ?
                    """,
                    (MODE_SINGLE, single_baseline, timestamp, telegram_chat_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET monitoring_mode = ?,
                        monitoring_enabled = 0,
                        updated_at = ?
                    WHERE telegram_chat_id = ?
                    """,
                    (MODE_SINGLE, timestamp, telegram_chat_id),
                )

    def get_manager_states(self, user_id: int) -> dict[str, str]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT node_address, last_status
                FROM manager_monitor_states
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchall()
        return {row["node_address"]: row["last_status"] for row in rows}

    def replace_manager_states(self, user_id: int, states: dict[str, str]) -> None:
        timestamp = now_iso()
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM manager_monitor_states WHERE user_id = ?",
                (user_id,),
            )
            for node_address, node_status in states.items():
                conn.execute(
                    """
                    INSERT INTO manager_monitor_states (user_id, node_address, last_status, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, node_address, node_status, timestamp),
                )

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
            monitoring_mode=row["monitoring_mode"] or MODE_SINGLE,
            last_status=row["last_status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
