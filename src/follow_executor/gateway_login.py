# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Bounded Mobile approval recovery, independent of broker/order APIs."""

from __future__ import annotations

import json
import os
import re
import selectors
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

from .config import ConfigError
from .local import private_write

APPROVAL_SECONDS = 300
MAX_ATTEMPTS = 2
ATTENTION = "Gateway login needs attention. When ready to approve, run 'gateway start' again."
IBC_LINE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\d{3} IBC: (.*)$")


class LoginRecovery:
    def __init__(self, directory: Path, identity: str, *, clock=time.monotonic):
        self.path = directory / "login-recovery.json"
        self.identity = identity
        self.clock = clock
        self.state = self.read()
        self.deadline = None
        self.reserved = False
        self.authenticated = False
        self.generation = 0

    def read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {"version": 1, "identity": self.identity, "phase": "idle", "attempts": 0}
        try:
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 8192:
                raise ValueError("unsafe recovery file")
            value = json.loads(self.path.read_text())
            if (type(value.get("version")) is not int or value["version"] != 1
                    or value.get("identity") != self.identity
                    or value.get("phase") not in ("idle", "pending", "attention")
                    or type(value.get("attempts")) is not int
                    or not 0 <= value["attempts"] <= MAX_ATTEMPTS
                    or (value["phase"] == "idle") != (value["attempts"] == 0)):
                raise ValueError("invalid recovery state")
            return value
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise ConfigError("Invalid Gateway login recovery state; inspect the private configuration.") from exc

    def save(self, phase, attempts):
        self.state = {"version": 1, "identity": self.identity, "phase": phase,
                      "attempts": attempts, "updated_utc": datetime.now(UTC).isoformat()}
        private_write(self.path, json.dumps(self.state, indent=2) + "\n")

    def attention(self):
        self.save("attention", max(1, self.state["attempts"]))
        print(ATTENTION, flush=True)
        return 2  # The generated systemd unit has RestartPreventExitStatus=2.

    def begin_launch(self):
        """Reserve a retry before spawning; crashes/reboots cannot replenish it."""
        if self.state["phase"] == "attention":
            print(ATTENTION, flush=True)
            return 2
        if self.state["phase"] == "pending":
            if self.state["attempts"] >= MAX_ATTEMPTS:
                return self.attention()
            self.save("pending", self.state["attempts"] + 1)
            self.reserved = True
            self.deadline = self.clock() + APPROVAL_SECONDS
            print("Gateway: starting the one permitted fresh login. Approve the new Mobile request.", flush=True)
        return None

    def line(self, line):
        """Only accept pinned IBC events; never forward arbitrary credential-bearing output."""
        match = IBC_LINE.fullmatch(line)
        if not match:
            return None
        message = match[1]
        if re.fullmatch(r"version: \d+\.\d+\.\d+", message):
            # A new JVM (including the weekly cold restart) may require approval.
            # Retain any outstanding budget across an internal IBC restart.
            self.authenticated = False
            self.generation += 1
        elif message == "Login has completed":
            self.save("idle", 0)
            self.deadline = None
            self.reserved = False
            self.authenticated = True
            print("Gateway: login completed; verify account and quote readiness before trading.", flush=True)
        elif message == "detected dialog entitled: Second Factor Authentication; event=Opened":
            if self.authenticated:
                return None  # Never restart a logged-in JVM for a later stray dialog.
            if self.reserved:
                self.reserved = False
            else:
                attempts = self.state["attempts"] + 1
                if attempts > MAX_ATTEMPTS:
                    return self.attention()
                self.save("pending", attempts)
            self.deadline = self.clock() + APPROVAL_SECONDS
            print(f"Gateway: waiting for Mobile approval (attempt {self.state['attempts']} of {MAX_ATTEMPTS}, "
                  f"up to {APPROVAL_SECONDS // 60} minutes).", flush=True)
        return None

    def expired(self):
        if self.deadline is None or self.clock() < self.deadline:
            return None
        if self.state["attempts"] >= MAX_ATTEMPTS:
            return self.attention()
        print("Gateway: Mobile approval timed out. Stopping this login; the service will retry once after 60 seconds.",
              flush=True)
        return 1

    def exited(self, code):
        if self.state["phase"] == "pending" and self.state["attempts"] >= MAX_ATTEMPTS:
            return self.attention()
        return code

    def report(self):
        return {"phase": self.state["phase"], "attempts": self.state["attempts"],
                "max_attempts": MAX_ATTEMPTS, "approval_timeout_seconds": APPROVAL_SECONDS,
                "attention_required": self.state["phase"] == "attention"}


def reset(directory: Path, identity: str):
    """Only an explicit start, with service and owned container stopped, calls this."""
    recovery = LoginRecovery(directory, identity)
    recovery.save("idle", 0)


def monitor(process, recovery, health=None):
    """Consume only the current container's stream, with bounded buffering and timeouts."""
    buffer = b""
    discarding = False
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            for key, _ in selector.select(timeout=0.5):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                for piece in chunk.splitlines(keepends=True):
                    # A huge/unrecognised log line cannot hide the timer or exhaust memory.
                    if len(buffer) + len(piece) > 65536:
                        buffer = b""
                        discarding = True
                    if not discarding:
                        buffer += piece
                    if piece.endswith(b"\n"):
                        if not discarding:
                            decision = recovery.line(buffer.decode("utf-8", errors="replace").rstrip("\r\n"))
                            if decision is not None:
                                return decision
                        buffer = b""
                        discarding = False
            decision = recovery.expired()
            if decision is not None:
                return decision
            code = process.poll()
            if code is not None and not selector.get_map():
                return recovery.exited(code)
            if health is not None:
                decision = health.tick(recovery)
                if decision is not None:
                    return decision
