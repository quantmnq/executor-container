# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Offline process fixture; mounted into test containers, never shipped in images.

The fake broker persists across executor processes to model broker-owned orders.
Pickle is used only for this test's locally generated, disposable fixture state.
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "/tests")

from executor_support import (
    Clock,
    FakeBroker,
    Leader,
    target,
    write_config,
)

from follow_executor.cli import main
from follow_executor.executor import Executor
from follow_executor.journal import Journal

STATE = Path("/state")
BROKER = STATE / "fake-broker.pickle"


def save(path: Path, contents: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(contents)
    temporary.replace(path)


if sys.argv[1] == "init":
    os.umask(0o077)
    write_config(Path("/config"), Leader().public_key,
                 journal_path="/state/executor.sqlite3", feed__send_acks=False)
    raise SystemExit(0)

if sys.argv[1] == "halt":
    journal = Journal(STATE / "executor.sqlite3")
    journal.halt("container recovery test")
    journal.close()
    raise SystemExit(0)

broker = pickle.loads(BROKER.read_bytes()) if BROKER.exists() else FakeBroker()
broker.connected = False
clock = Clock()


class ObservedExecutor(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, clock=clock)

    def step(self):
        clock.advance(0.25)
        if (STATE / "outage").exists():
            broker.connected = False
            broker.connect_error = ConnectionError("simulated broker outage")
        else:
            broker.connect_error = None
        if (STATE / "flatten").exists():
            self.on_signal(target(2, "exit_started", "flat"))
        result = super().step()
        save(BROKER, pickle.dumps(broker))
        snapshot = {
            "run": os.environ["TEST_RUN"], "connected": broker.connected,
            "entries": len(broker.placed("entry")), "stops": len(broker.placed("stop")),
            "working_stops": len(broker.working("stop")),
            "position": sum(broker.positions.values()),
            "expected_position": sum(self.journal.expected_positions().values()),
            "seq": self.journal.last_seq(), "halt": self.journal.halt_reason(),
        }
        save(STATE / "snapshot.json", json.dumps(snapshot).encode())
        return result


class Feed:
    def __init__(self, **kwargs):
        self.on_signal = kwargs["on_signal"]

    def run(self, stop):
        # Every replacement receives the same entry, exercising replay protection.
        self.on_signal(target(1, "entry"))
        stop.wait()

    def reconnect(self):
        pass


with (
    patch("follow_executor.ibkr.IBKRBroker", lambda *a, **k: broker),
    patch("follow_executor.executor.Executor", ObservedExecutor),
    patch("follow_executor.feed.SignalFeed", Feed),
):
    code = main(["run", "--config", "/config/executor.json"])
if code == 0:
    save(STATE / "clean-stop", os.environ["TEST_RUN"].encode())
raise SystemExit(code)
