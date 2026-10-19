# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Durable executor state: signals, trades, orders, executions and halts."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .broker import Execution

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS signals (
    seq INTEGER PRIMARY KEY,
    received_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    trade_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    trade_key TEXT,
    purpose TEXT NOT NULL,
    con_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL,
    order_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    placed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    exec_id TEXT PRIMARY KEY,
    order_id INTEGER NOT NULL,
    con_id INTEGER NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    time TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Journal:
    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._notification_revision = 0
        self._db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # Signals ---------------------------------------------------------------

    def record_signal(self, seq: int, payload: str) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO signals(seq, received_at, payload) VALUES (?, ?, ?)",
                (seq, utc_now(), payload),
            )
            return cursor.rowcount == 1

    def last_seq(self) -> int:
        row = self._db.execute("SELECT max(seq) FROM signals").fetchone()
        return int(row[0] or 0)

    def latest_payload(self) -> str | None:
        row = self._db.execute("SELECT payload FROM signals ORDER BY seq DESC LIMIT 1").fetchone()
        return None if row is None else str(row["payload"])

    # Trades ----------------------------------------------------------------

    def trade_status(self, trade_key: str | None) -> str | None:
        if trade_key is None:
            return None
        row = self._db.execute(
            "SELECT status FROM trades WHERE trade_key = ?", (trade_key,)
        ).fetchone()
        return None if row is None else str(row["status"])

    def mark_trade(self, trade_key: str, status: str, reason: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO trades(trade_key, status, reason, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(trade_key) DO UPDATE SET status = excluded.status, "
                "reason = excluded.reason, updated_at = excluded.updated_at",
                (trade_key, status, reason, utc_now()),
            )

    # Orders and executions -------------------------------------------------

    def record_order(
        self,
        order_id: int,
        *,
        trade_key: str | None,
        purpose: str,
        con_id: int,
        action: str,
        order_type: str,
        quantity: int,
        price: float | None,
        order_ref: str,
    ) -> None:
        now = utc_now()
        with self._lock:
            self._db.execute(
                "INSERT INTO orders(order_id, trade_key, purpose, con_id, action, order_type, "
                "quantity, price, order_ref, status, placed_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?) "
                "ON CONFLICT(order_id) DO UPDATE SET quantity = excluded.quantity, "
                "price = excluded.price, updated_at = excluded.updated_at",
                (order_id, trade_key, purpose, con_id, action, order_type, quantity, price,
                 order_ref, now, now),
            )
            self._notification_revision += 1

    def set_order_status(self, order_id: int, status: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ? AND status != ?",
                (status, utc_now(), order_id, status),
            )

    def order_trades(self) -> dict[int, str | None]:
        return {
            int(row["order_id"]): row["trade_key"]
            for row in self._db.execute("SELECT order_id, trade_key FROM orders")
        }

    def notification_orders(self) -> dict[int, dict[str, Any]]:
        with self._lock:
            return {row["order_id"]: dict(row) for row in self._db.execute("SELECT * FROM orders")}

    def notification_revision(self) -> int:
        with self._lock:
            return self._notification_revision

    def notification_executions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._db.execute("SELECT * FROM executions ORDER BY rowid")]

    def record_execution(self, execution: Execution) -> bool:
        """Record a fill once; an IBKR correction (``.01`` -> ``.02``) replaces its original."""

        base, dot, _ = execution.exec_id.rpartition(".")
        with self._lock:
            if dot and base.count(".") >= 2:
                original = self._db.execute(
                    "SELECT exec_id FROM executions WHERE exec_id LIKE ? AND exec_id != ?",
                    (f"{base}.%", execution.exec_id),
                ).fetchone()
                if original is not None:
                    if original["exec_id"] > execution.exec_id:
                        return False
                    self._db.execute(
                        "UPDATE executions SET exec_id = ?, quantity = ?, price = ?, side = ? "
                        "WHERE exec_id = ?",
                        (execution.exec_id, execution.quantity, execution.price, execution.side,
                         original["exec_id"]),
                    )
                    self._notification_revision += 1
                    return False
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO executions(exec_id, order_id, con_id, side, quantity, "
                "price, time, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (execution.exec_id, execution.order_id, execution.con_id, execution.side,
                 execution.quantity, execution.price, execution.time, utc_now()),
            )
            if cursor.rowcount:
                self._notification_revision += 1
            return cursor.rowcount == 1

    def entry_price(self, trade_key: str) -> float | None:
        row = self._db.execute(
            "SELECT sum(e.quantity * e.price) / sum(e.quantity) FROM executions e "
            "JOIN orders o ON o.order_id = e.order_id "
            "WHERE o.trade_key = ? AND o.purpose = 'entry'",
            (trade_key,),
        ).fetchone()
        return None if row[0] is None else float(row[0])

    def expected_positions(self) -> dict[int, int]:
        """Baseline plus every recorded execution of this executor's orders since it."""

        baseline = self.get_state("baseline")
        positions: dict[int, int] = {}
        after = 0
        if baseline is not None:
            data = json.loads(baseline)
            positions = {int(con_id): int(qty) for con_id, qty in data["positions"].items()}
            after = int(data["after_rowid"])
        for row in self._db.execute(
            "SELECT con_id, side, quantity FROM executions WHERE rowid > ?", (after,)
        ):
            signed = int(row["quantity"]) * (1 if row["side"] == "BOT" else -1)
            positions[int(row["con_id"])] = positions.get(int(row["con_id"]), 0) + signed
        return {con_id: qty for con_id, qty in positions.items() if qty}

    def set_baseline(self, positions: dict[int, int]) -> None:
        with self._lock:
            row = self._db.execute("SELECT coalesce(max(rowid), 0) FROM executions").fetchone()
            self.set_state(
                "baseline",
                json.dumps({"positions": {str(k): v for k, v in positions.items() if v},
                            "after_rowid": int(row[0]), "at": utc_now()}),
            )

    # State, halts and log --------------------------------------------------

    def get_state(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_state(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO state(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def delete_state(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM state WHERE key = ?", (key,))

    def halt_reason(self) -> str | None:
        return self.get_state("halt")

    def halt(self, reason: str) -> bool:
        with self._lock:
            if self.halt_reason() is not None:
                return False
            self.set_state("halt", reason)
            self.log("halt", {"reason": reason})
            return True

    def clear_halt(self) -> None:
        with self._lock:
            self.delete_state("halt")
            self.delete_state("resume_requested")
            self.log("resume", {})

    def log(self, kind: str, detail: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO log(at, kind, detail) VALUES (?, ?, ?)",
                (utc_now(), kind, json.dumps(detail, sort_keys=True, default=str)),
            )

    def recent(self, table: str, limit: int = 10) -> list[dict[str, Any]]:
        order = {"signals": "seq", "trades": "updated_at", "orders": "order_id",
                 "executions": "rowid", "log": "id"}[table]
        return [
            dict(row)
            for row in self._db.execute(
                f"SELECT * FROM {table} ORDER BY {order} DESC LIMIT ?", (limit,)
            )
        ]
