# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""API recovery coordinated by the Gateway supervisor, never a second restart loop."""

from __future__ import annotations

import json
import math
import os
import re
import stat
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .config import ConfigError
from .local import private_write

INTERVAL = 60
FAILURES = 10
COOLDOWN = 1800
PROBE_TIMEOUT = 30
RESULTS = {"healthy", "unavailable", "account_mismatch", "monitor_error"}


class ProbeProcess:
    """Run one bounded, read-only probe without blocking Mobile event handling."""

    def __init__(self, config: Path, release: Path):
        self.process = None
        self.container = None
        self.started = time.monotonic()
        command = [sys.executable, "-I", "-m", "follow_executor.gateway_health_probe", "--config", str(config)]
        metadata_path = release / "RELEASE.json"
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        image = metadata.get("executor_image")
        if image:
            from .gateway_docker import DOCKER

            if (not re.fullmatch(r"sha256:[a-f0-9]{64}", image.get("id", ""))
                    or image.get("platform") != "linux/arm64"
                    or image.get("wheel_sha256") != metadata.get("wheel_sha256")):
                raise ConfigError("Invalid health probe image metadata")
            self.container = "aq-gateway-health-" + uuid.uuid4().hex
            command = DOCKER + [
                "run", "--rm", "--pull", "never", "--name", self.container,
                "--restart", "no", "--network", "host", "--read-only",
                "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges=true", "--pids-limit", "32",
                "--log-driver", "none", "--stop-timeout", "1",
                "--mount", f"type=bind,source={config},target=/probe/executor.json,readonly",
                # Also bounds lifetime if the supervisor/daemon connection dies.
                "--entrypoint", "/usr/bin/timeout", image["id"], "20",
                "/opt/venv/bin/python", "-I", "-m", "follow_executor.gateway_health_probe",
                "--config", "/probe/executor.json",
            ]
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def poll(self):
        if self.process.poll() is None:
            if time.monotonic() - self.started < PROBE_TIMEOUT:
                return None
            self.close()
            return "monitor_error"
        output = self.process.stdout.read(4097)
        try:
            value = json.loads(output) if len(output) <= 4096 else {}
            result = value.get("status")
            expected_exit = 0 if result == "healthy" else 1
            if (type(value.get("version")) is int and value["version"] == 1
                    and result in RESULTS and self.process.returncode == expected_exit):
                return result
        except (ValueError, TypeError, AttributeError):
            pass
        return "monitor_error"

    def close(self):
        if self.process:
            try:
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                self.process.stdout.close()
        if self.container:
            from .gateway_docker import DOCKER

            try:
                subprocess.run(DOCKER + ["container", "rm", "--force", self.container],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass  # The container's own 20-second deadline still applies.
            self.container = None


def read_state(directory: Path, identity: str):
    path = directory / "api-health.json"
    if not path.exists() and not path.is_symlink():
        return {"version": 1, "identity": identity, "status": "not_started",
                "failures": 0, "last_restart_epoch": 0}
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 8192:
            raise ValueError("unsafe health state")
        value = json.loads(path.read_text())
        if (type(value.get("version")) is not int or value["version"] != 1
                or value.get("identity") != identity
                or value.get("status") not in RESULTS | {"not_started", "waiting_for_login", "restarting", "cooldown"}
                or type(value.get("failures")) is not int or not 0 <= value["failures"] <= FAILURES
                or type(value.get("last_restart_epoch")) not in (int, float)
                or not math.isfinite(value["last_restart_epoch"]) or value["last_restart_epoch"] < 0):
            raise ValueError("invalid health state")
        return value
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ConfigError("Invalid private Gateway API health state; inspect api-health.json.") from exc


class HealthMonitor:
    def __init__(self, directory, identity, factory, *, clock=time.monotonic, wall_clock=time.time):
        self.path = directory / "api-health.json"
        self.state = read_state(directory, identity)
        self.state["failures"] = 0
        self.factory = factory
        self.clock, self.wall_clock = clock, wall_clock
        self.worker = None
        self.generation = None
        self.next_probe = clock() + INTERVAL
        self.waiting = False

    def save(self, status):
        changed = self.state["status"] != status
        self.state["status"] = status
        self.state["updated_utc"] = datetime.now(UTC).isoformat()
        private_write(self.path, json.dumps(self.state, indent=2) + "\n")
        if changed:
            messages = {
                "healthy": "API handshake recovered; trading readiness is checked separately.",
                "unavailable": "API handshake unavailable; monitoring before recovery.",
                "waiting_for_login": "API monitoring paused until login completes.",
                "monitor_error": "API monitor needs attention; check its image/configuration and reserved client ID 9701. Gateway was not restarted.",
                "account_mismatch": "API account check needs attention; verify the configured account. Gateway was not restarted.",
                "cooldown": "API remains unavailable; automatic recovery is in its 30-minute cooldown.",
                "restarting": "Ten consecutive API probes failed; restarting Gateway. Mobile approval may be required.",
            }
            print("Gateway: " + messages[status], flush=True)

    def close(self):
        if self.worker:
            self.worker.close()
            self.worker = None

    def tick(self, recovery):
        eligible = recovery.authenticated and recovery.state["phase"] == "idle"
        if not eligible or self.generation != recovery.generation:
            self.close()
            self.state["failures"] = 0
            self.next_probe = self.clock() + INTERVAL
            self.generation = recovery.generation
            if not eligible:
                if not self.waiting:
                    self.save("waiting_for_login")
                self.waiting = True
                return None
        self.waiting = False
        if self.worker:
            try:
                result = self.worker.poll()
            except (OSError, ValueError, subprocess.SubprocessError):
                result = "monitor_error"
            if result is None:
                return None
            self.close()
            self.next_probe = self.clock() + INTERVAL
            self.state["last_probe_utc"] = datetime.now(UTC).isoformat()
            if result == "unavailable":
                self.state["failures"] = min(FAILURES, self.state["failures"] + 1)
                if self.state["failures"] >= FAILURES:
                    now = self.wall_clock()
                    if now - self.state["last_restart_epoch"] < COOLDOWN:
                        self.save("cooldown")
                        return None
                    # Commit before returning to systemd, including across reboots.
                    self.state["last_restart_epoch"] = now
                    self.save("restarting")
                    return 1
            else:
                self.state["failures"] = 0
            self.save(result)
        elif self.clock() >= self.next_probe:
            try:
                self.worker = self.factory()
            except (OSError, ValueError, ConfigError):
                self.state["failures"] = 0
                self.save("monitor_error")
                self.next_probe = self.clock() + INTERVAL
        return None


def report(directory, identity):
    state = read_state(directory, identity)
    fields = {"status", "failures", "last_restart_epoch", "updated_utc", "last_probe_utc"}
    return {key: value for key, value in state.items() if key in fields} | {
        "interval_seconds": INTERVAL, "failure_threshold": FAILURES,
        "restart_cooldown_seconds": COOLDOWN, "cached": True,
    }
