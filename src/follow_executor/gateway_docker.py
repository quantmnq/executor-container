# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Optional, digest-pinned Gateway container on the customer's local Docker engine.

systemd owns restart/stop behavior. Docker never starts a trading executor.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
from pathlib import Path

from .config import ConfigError
from .gateway_login import LoginRecovery, monitor
from .local import private_write

# GHCR index and ARM64 manifest verified on 2026-10-15. Never use a floating tag.
IMAGE_VERSION = "10.51.1c"
IMAGE = "ghcr.io/gnzsnz/ib-gateway@sha256:13229ab03b0f455bf41380172e69815b164f0b911345f471ccecdcff0cde90ca"
ARM64_DIGEST = "sha256:b3e4ebc891c6668f050ccf7f782a8f883676407b090d06efb17d85b5d0da5520"
DOCKER = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
LABEL = "com.autoquant.gateway"
DATA = "/home/ibgateway/auto-quant"


class DockerUnavailable(ConfigError):
    """An operational failure that systemd may retry without rewriting settings."""


def command(args: list[str], *, capture: bool = True, timeout: int = 30):
    try:
        result = subprocess.run(DOCKER + args, check=False, text=True,
                                capture_output=capture, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DockerUnavailable(
            "Local Docker is unavailable; see docs/GATEWAY_DOCKER.md. "
            "After installing Docker, reboot once to refresh service permissions."
        ) from exc
    if result.returncode:
        # Do not include Docker output: a caller may have inspected private state.
        raise DockerUnavailable(
            f"Docker {args[0]} failed (exit {result.returncode}); check local Docker "
            "access and docs/GATEWAY_DOCKER.md"
        )
    return result


def require_engine() -> None:
    if platform.machine() != "aarch64":
        raise ConfigError("The Gateway container pilot requires native Linux ARM64")
    version = command(["version", "--format", "{{.Server.Version}}"]).stdout.strip()
    if not version.split(".")[0].isdigit() or int(version.split(".")[0]) < 28:
        raise ConfigError("Use Docker Engine 28 or newer for localhost port isolation")


def prepare() -> None:
    require_engine()
    print(f"Downloading Gateway {IMAGE_VERSION} for ARM64; no login or trading is started.")
    command(["pull", "--platform", "linux/arm64", IMAGE], capture=False, timeout=900)
    verify_image()


def verify_image() -> None:
    metadata = json.loads(command(["image", "inspect", IMAGE]).stdout)[0]
    if (metadata.get("Architecture") != "arm64" or metadata.get("Os") != "linux"
            or metadata.get("Config", {}).get("User") != "1000:1000"):
        raise ConfigError("Unexpected Gateway image architecture or runtime user")


def identity(executor_path: Path) -> str:
    digest = hashlib.sha256(str(executor_path).encode()).hexdigest()[:16]
    return f"aq-gateway-{os.getuid()}-{digest}"


def container_state(executor_path: Path) -> dict | None:
    name = identity(executor_path)
    listing = ["container", "ls", "--all", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"]
    names = command(listing).stdout.splitlines()
    if name not in names:
        return None
    try:
        result = command(["container", "inspect", "--format",
                          '{{json .Config.Labels}}\n{{json .State}}', name])
    except DockerUnavailable:
        # An --rm container may disappear between listing and inspection.
        # A second successful listing distinguishes that from a daemon failure.
        if name not in command(listing).stdout.splitlines():
            return None
        raise
    labels, state = map(json.loads, result.stdout.splitlines())
    if not labels or labels.get(LABEL) != name:
        raise ConfigError("Gateway container name is occupied by an unmanaged container")
    return state


def require_stopped(executor_path: Path) -> None:
    state = container_state(executor_path)
    if state and state.get("Running"):
        raise ConfigError("A Gateway container is still running; use './follow gateway stop' first")


def stop(executor_path: Path) -> None:
    state = container_state(executor_path)
    if state is None:
        return
    name = identity(executor_path)
    if state.get("Running"):
        try:
            command(["container", "stop", "--time", "30", name], timeout=45)
        except DockerUnavailable:
            state = container_state(executor_path)
            if state and state.get("Running"):
                raise
    # --rm normally removes it; tolerate that race, but never hide daemon failures.
    if container_state(executor_path) is not None:
        try:
            command(["container", "rm", name])
        except DockerUnavailable:
            if container_state(executor_path) is not None:
                raise


def validate_settings(settings: dict) -> None:
    if settings.get("image") != IMAGE:
        raise ConfigError("Gateway image differs from this release; configure while stopped to select its pinned image")
    if settings.get("mode") not in ("paper", "live"):
        raise ConfigError("Invalid Gateway account mode")
    if type(settings.get("port")) is not int or not 1024 <= settings["port"] <= 65535:
        raise ConfigError("Invalid Gateway host port")
    if type(settings.get("vnc")) is not bool:
        raise ConfigError("Invalid Gateway recovery-desktop setting")
    if settings["vnc"] and settings["port"] == 5901:
        raise ConfigError("Gateway API and recovery desktop cannot share port 5901")


def write_seed(directory: Path, settings: dict) -> None:
    # The full account settings live in the Docker volume, outside release files.
    private_write(directory / "docker-jts.ini", (
        "[IBGateway]\nWriteDebug=false\nTrustedIPs=127.0.0.1\nApiOnly=true\n\n"
        f"[Logon]\nLocale=en\nTimeZone={settings['timezone']}\n"
        "displayedproxymsg=1\nUseSSL=true\ns3store=true\n\n[Communication]\n"
    ))


def bind(source: Path, target: str) -> list[str]:
    if "," in str(source):
        raise ConfigError("Docker Gateway paths cannot contain commas")
    return ["--mount", f"type=bind,source={source},target={target},readonly"]


def volume_name(executor_path: Path, settings: dict) -> str:
    return f"{identity(executor_path)}-{settings['mode']}-data"


def initialize(executor_path: Path, directory: Path, settings: dict) -> None:
    name = identity(executor_path)
    volume = volume_name(executor_path, settings)
    command(["volume", "create", "--label", f"{LABEL}={name}", volume])
    labels = json.loads(command(["volume", "inspect", "--format", "{{json .Labels}}", volume]).stdout)
    if not labels or labels.get(LABEL) != name:
        raise ConfigError("Gateway volume is not owned by this configuration")
    write_seed(directory, settings)
    mounts = bind(directory / "ibc.ini", "/input/ibc.ini")
    mounts += bind(directory / "docker-jts.ini", "/input/jts.ini")
    if settings["vnc"]:
        mounts += bind(directory / "vnc.password", "/input/vnc.password")
    # Only this short, network-disabled preparation runs as root. It copies the
    # private host files into a private volume for upstream's UID 1000, supporting
    # host accounts with other UIDs without making their credentials public.
    script = """set -eu
mkdir -p /data/settings
chown 1000:1000 /data /data/settings
chmod 700 /data /data/settings
install -m 600 -o 1000 -g 1000 /input/ibc.ini /data/ibc.ini
# The host watchdog owns bounded login retries, including for older saved profiles.
sed -i 's/^ReloginAfterSecondFactorAuthenticationTimeout=.*/ReloginAfterSecondFactorAuthenticationTimeout=no/' /data/ibc.ini
chown 1000:1000 /data/ibc.ini
chmod 600 /data/ibc.ini
if [ ! -f /data/settings/jts.ini ]; then
    install -m 600 -o 1000 -g 1000 /input/jts.ini /data/settings/jts.ini
else
    sed -i "s|^TimeZone=.*|TimeZone=$TIME_ZONE|" /data/settings/jts.ini
    chown 1000:1000 /data/settings/jts.ini
    chmod 600 /data/settings/jts.ini
fi
if [ -f /input/vnc.password ]; then
    install -m 600 -o 1000 -g 1000 /input/vnc.password /data/vnc.password
else
    rm -f /data/vnc.password
fi
"""
    command(["run", "--rm", "--pull", "never", "--platform", "linux/arm64",
             "--network", "none", "--user", "0:0", "--cap-drop", "ALL",
             "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER",
             "--security-opt", "no-new-privileges=true",
             "--mount", f"type=volume,source={volume},target=/data", *mounts,
             "--env", f"TIME_ZONE={settings['timezone']}",
             "--entrypoint", "/bin/sh", IMAGE, "-c", script], timeout=120)


def run_arguments(executor_path: Path, settings: dict) -> list[str]:
    name = identity(executor_path)
    port = 4004 if settings["mode"] == "paper" else 4003
    environment = {
        "CUSTOM_CONFIG": "yes", "TRADING_MODE": settings["mode"],
        "IBC_INI": f"{DATA}/ibc.ini", "TWS_SETTINGS_PATH": f"{DATA}/settings",
        "TIME_ZONE": settings["timezone"], "TZ": settings["timezone"],
        "TWOFA_TIMEOUT_ACTION": "exit",
    }
    args = ["run", "--rm", "--pull", "never", "--platform", "linux/arm64",
            "--name", name, "--label", f"{LABEL}={name}", "--restart", "no",
            "--user", "1000:1000", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges=true", "--stop-timeout", "30",
            "--log-driver", "local", "--log-opt", "max-size=10m", "--log-opt", "max-file=3",
            "--publish", f"127.0.0.1:{settings['port']}:{port}",
            "--mount", f"type=volume,source={volume_name(executor_path, settings)},target={DATA}"]
    if settings["vnc"]:
        args += ["--publish", "127.0.0.1:5901:5900"]
        environment["VNC_SERVER_PASSWORD_FILE"] = f"{DATA}/vnc.password"
    for key, value in environment.items():
        args += ["--env", f"{key}={value}"]
    return args + [IMAGE]


def launch(executor_path: Path, directory: Path, settings: dict, *, release: Path | None = None) -> int:
    validate_settings(settings)
    try:
        require_engine()
        verify_image()
        # Recover a container orphaned by a previous supervisor crash. The caller
        # holds the Gateway lock; labels must match before stop/removal is allowed.
        stop(executor_path)
        recovery = LoginRecovery(directory, identity(executor_path))
        if recovery.state["phase"] == "attention":
            return recovery.begin_launch()
        ports = [settings["port"]] + ([5901] if settings["vnc"] else [])
        for port in ports:
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise ConfigError(f"Local port {port} is already in use; close the other Gateway/desktop first")
        initialize(executor_path, directory, settings)
        decision = recovery.begin_launch()
        if decision is not None:
            return decision
        health = None
        if release is not None:
            from .gateway_health import HealthMonitor, ProbeProcess

            health = HealthMonitor(directory, identity(executor_path),
                                   lambda: ProbeProcess(executor_path, release))
        process = subprocess.Popen(DOCKER + run_arguments(executor_path, settings),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            return monitor(process, recovery, health)
        finally:
            if health is not None:
                health.close()
            try:
                stop(executor_path)
            finally:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()
    except DockerUnavailable as exc:
        print(str(exc), flush=True)
        return 1  # transient engine/network startup failures may retry at boot
