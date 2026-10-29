# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Opt-in confirmed broker notifications with a durable, independent outbox."""

from __future__ import annotations

import json
import logging
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from .config import ConfigError
from .position_notifications import positions

LOGGER = logging.getLogger(__name__)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(config, path, body=None):
    context = ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file else None)
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    req = urllib.request.Request(
        config.relay_url + "/v1/discord/" + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        headers={"Authorization": "Bearer " + config.token(), "Content-Type": "application/json"},
    )
    with opener.open(req, timeout=5) as response:
        return json.loads(response.read(16384))


def database_path(config):
    return config.journal_path.with_suffix(".notifications.sqlite3")



class Notifications:
    def __init__(self, config, *, transport=request):
        self.config, self.transport = config, transport
        self._lock = threading.RLock()
        self.db = sqlite3.connect(database_path(config), check_same_thread=False, timeout=0.1)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY, payload TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0);
        """)
        with self.db:
            if self._get("link") != config.discord_link_id:
                self.db.execute("DELETE FROM seen")
                self.db.execute("DELETE FROM outbox")
                self._set("link", config.discord_link_id)
        self._warned = False
        self._status_pending = {}
        self._session = str(uuid4())
        self._heartbeat_sequence = 0
        self._running = True
        self._last_pulse = time.monotonic()
        self._positions_revision = None

    def pulse(self):
        """Only the executor loop renews liveness; a stuck loop cannot look healthy."""
        self._last_pulse = time.monotonic()

    def status(self, topic, state, now, *, announce_initial=True, debounce=0, force=False):
        try:
            with self._lock, self.db:
                if topic == "executor":
                    self._running = state != "stopped"
                key = "health:" + topic
                previous = self._get(key)
                if previous == state and not force:
                    self._status_pending.pop(topic, None)
                    return
                pending = self._status_pending.get(topic)
                if pending is None or pending[0] != state:
                    pending = self._status_pending[topic] = (state, now)
                if (now - pending[1]).total_seconds() < debounce:
                    return
                self._set(key, state)
                self._status_pending.pop(topic, None)
                if previous is not None or announce_initial:
                    self._enqueue({"kind": "service_status", "topic": topic, "state": state,
                                   "previous": previous, "account_type": self.config.ibkr.account_type,
                                   "root": self.config.root, "occurred_at": now.isoformat()})
        except Exception as exc:  # noqa: BLE001 - alerts cannot interrupt order management
            LOGGER.error("Cannot queue service notification (%s)", type(exc).__name__)

    def heartbeat(self):
        if self._running and time.monotonic() - self._last_pulse > 60:
            return  # Let the relay detect a process whose trading loop is stuck.
        self._heartbeat_sequence += 1
        result = self.transport(self.config, "heartbeat", {
            "link_id": self.config.discord_link_id, "session_id": self._session,
            "sequence": self._heartbeat_sequence, "running": self._running,
            "account_type": self.config.ibkr.account_type, "root": self.config.root,
        })
        if result.get("accepted") is not True:
            raise ValueError("service heartbeat not acknowledged")

    def close(self):
        self.db.close()

    def _get(self, key):
        row = self.db.execute("SELECT value FROM seen WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO seen VALUES (?,?)", (key, json.dumps(value)))

    def _enqueue(self, event):
        event["event_id"] = str(uuid4())
        self.db.execute("INSERT INTO outbox(payload) VALUES (?)", (json.dumps(event, allow_nan=False),))

    def observe(self, state, journal, now, cause=None):
        """Never raise into the trading loop. No HTTP occurs on this thread."""
        try:
            with self._lock, self.db:
                revision = self._observe(state, journal, now, cause)
            self._positions_revision = revision
            self._warned = False
        except Exception as exc:  # noqa: BLE001 - notifications must never interrupt trading
            if not self._warned:
                LOGGER.error("Cannot queue Discord notifications (%s); trading continues", type(exc).__name__)
                self._warned = True

    def _observe(self, state, journal, now, cause):
        revision = (id(journal), journal.notification_revision())
        if revision == self._positions_revision:
            return revision
        initial = not self._get("positions_initialized")
        # A balance book reports each contract separately, e.g. LONG 1 NQ and LONG 5 MNQ.
        roots = {int(con_id): root for con_id, root in
                 json.loads(journal.get_state("contract_roots") or "{}").items()}
        roots.update({con_id: contract.root for con_id, contract in state.contracts.items()})
        summaries = positions(journal.notification_executions(), journal.notification_orders(),
                              self.config.root, roots)
        for key, summary in summaries.items():
            previous = self._get(key)
            if previous == summary:
                continue
            self._set(key, summary)
            if initial:
                continue  # Seed history on first enable/upgrade; never announce old trades.
            corrected = bool(previous and any(
                base in summary["fills"] and summary["fills"][base] != fill
                for base, fill in previous["fills"].items()
            ))
            body = dict(summary["event"])
            contract = state.contracts.get(body["con_id"])
            body.update(kind="position", corrected=corrected,
                        account_type=self.config.ibkr.account_type,
                        root=roots.get(body["con_id"], self.config.root),
                        contract_month=contract.contract_month if contract else None,
                        occurred_at=now.isoformat())
            if not body.get("broker_time"):
                body.pop("broker_time", None)
            self._enqueue(body)
        self._set("positions_initialized", True)
        return revision

    def send_one(self):
        with self._lock:
            row = self.db.execute("SELECT * FROM outbox WHERE sent=0 ORDER BY id LIMIT 1").fetchone()
        if row is None:
            return False
        result = self.transport(self.config, "events", {
            "link_id": self.config.discord_link_id, "event": json.loads(row["payload"]),
        })
        if result.get("accepted") is not True:
            raise ValueError("notification service did not acknowledge the event")
        with self._lock, self.db:
            # Retain only the event fingerprint after server acceptance.
            self.db.execute("DELETE FROM outbox WHERE id=?", (row["id"],))
        return True

    def run(self, stop):
        delay = 1.0
        next_heartbeat = 0.0
        deadline = None
        shutdown_heartbeat = False
        heartbeat_failed = False
        while True:
            if stop.is_set():
                if deadline is None:
                    deadline = time.monotonic() + 6
                if time.monotonic() >= deadline:
                    return
            try:
                if time.monotonic() >= next_heartbeat or (stop.is_set() and not shutdown_heartbeat):
                    next_heartbeat = time.monotonic() + 30
                    shutdown_heartbeat = stop.is_set()
                    try:
                        self.heartbeat()
                        heartbeat_failed = False
                    except Exception as exc:  # noqa: BLE001 - heartbeat failures must not hold order DMs
                        if not heartbeat_failed:
                            LOGGER.warning("Service heartbeat unavailable (%s)", type(exc).__name__)
                        heartbeat_failed = True
                if not self.send_one():
                    if stop.is_set():
                        return
                    stop.wait(0.5)
                delay = 1.0
            except Exception as exc:  # noqa: BLE001 - retain the outbox for retry
                if stop.is_set():
                    return
                if delay == 1:
                    LOGGER.warning("Discord delivery pending (%s); trading continues", type(exc).__name__)
                stop.wait(delay)
                delay = min(60, delay * 2)


def configure(path: Path, config, action):
    from .local import exclusive, private_write

    with exclusive(config.journal_path.with_suffix(config.journal_path.suffix + ".lock")):
        if action == "status":
            print(json.dumps(request(config, "status"), indent=2))
            return 0
        if action == "link":
            print("Discord notifications share instrument, position, quantity, entry/exit prices, gross profit/loss, service/Gateway "
                  "health, liveness heartbeats and event times "
                  "with Auto Quant and Discord. IBKR credentials and account ID are not included.")
            if input("Type LINK to agree and pair your Discord account: ").strip() != "LINK":
                raise ConfigError("Discord pairing cancelled")
            result = request(config, "link", {})
            print("Join the Auto Quant Discord server, then use AQ Bot's command:")
            print(f"/link code:{result['code']}")
            print("Code expires in 10 minutes. After receiving the test DM, run './follow discord enable'.")
            return 0
        raw = json.loads(path.read_text())
        if action == "enable":
            status = request(config, "status")
            if not status.get("ready"):
                raise ConfigError("link Discord and receive its test DM before enabling notifications")
            if not status.get("health_notifications") or not status.get("position_notifications"):
                raise ConfigError("Ask Auto Quant to update its notification service before enabling this release")
            raw["notifications"] = {"discord_link_id": status["link_id"]}
        else:
            request(config, "unlink", {})
            raw.pop("notifications", None)
        private_write(path, json.dumps(raw, indent=2) + "\n")
        print("Discord notifications enabled for the next start." if action == "enable"
              else "Discord unlinked; pending server messages cancelled.")
    return 0
