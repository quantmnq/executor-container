# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Private IBC setup and a supervised Gateway launcher with read-only API monitoring."""

from __future__ import annotations

import getpass
import json
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timedelta
from datetime import time as wall_time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import ConfigError, load_config
from .local import exclusive, private_write
from .setup import ask

SERVICE = "follow-gateway.service"
IBC_VERSION = "3.24.2"
GATEWAY_VERSION = "1051"


def run_command(args, **kwargs):
    result = subprocess.run(args, check=False, **kwargs)
    if result.returncode:
        raise ConfigError(f"{args[0]} failed (exit {result.returncode})")
    return result


def service_state(name: str) -> str:
    return run_command(
        ["systemctl", "--user", "show", name, "-p", "ActiveState", "--value"],
        capture_output=True, text=True,
    ).stdout.strip()


def require_stopped(name: str) -> None:
    if service_state(name) not in ("inactive", "failed"):
        raise ConfigError(f"Stop {name} before changing Gateway setup; wait until flat first")


def parse_time(value: str):
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ConfigError("Use a 24-hour time such as 12:00")
    hour, minute = map(int, value.split(":"))
    return wall_time(hour, minute)


def validate_schedule(zone: str, sunday: str, daily: str) -> None:
    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError("Use an IANA timezone such as UTC or America/Los_Angeles") from exc
    sunday_time, daily_time = parse_time(sunday), parse_time(daily)
    if sunday_time == daily_time:
        raise ConfigError("Choose different daily and Sunday restart times")
    # Check a full DST cycle, including weekends when US/Europe transitions differ.
    today = datetime.now(tz).date()
    for offset in range(740):
        day = today + timedelta(days=offset)
        if day.weekday() != 6:
            continue
        appointment = datetime.combine(day, sunday_time, tz)
        # Skip ambiguous/nonexistent local times; never silently move a 2FA appointment.
        alternate = appointment.replace(fold=1)
        if (alternate.utcoffset() != appointment.utcoffset()
                or appointment.astimezone(ZoneInfo("UTC")).astimezone(tz) != appointment):
            raise ConfigError("Sunday time overlaps a daylight-saving clock change; choose another time")
        reset = datetime.combine(day, parse_time("01:15"), ZoneInfo("America/New_York"))
        if appointment <= reset:
            raise ConfigError(
                "Sunday login must be after 01:15 US Eastern throughout the year; "
                "choose a later local time (for example 12:00 in UTC)"
            )


def safe_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if re.search(r'[\s%"\\$`]', str(path)):
        raise ConfigError("Use paths without whitespace, quotes, percent signs or shell metacharacters")
    return path


def gateway_runtime(path: Path) -> Path:
    jars = list((path / "jars").glob("jts4launch-*.jar"))
    if len(jars) != 1 or jars[0].name != f"jts4launch-{GATEWAY_VERSION}.jar":
        raise ConfigError("This release supports native ARM64 Gateway 10.51; use the supplied desktop helper")
    for name in ("ibgateway.vmoptions", ".install4j/i4jparams.conf", ".install4j/i4jruntime.jar"):
        if not (path / name).is_file():
            raise ConfigError("Incomplete standalone Gateway installation")
    if not os.access(path, os.W_OK):
        raise ConfigError("Gateway must be installed in a directory writable by your Ubuntu login user")
    java = path / "jre/bin/java"
    output = run_command([str(java), "-XshowSettings:properties", "-version"],
                         capture_output=True, text=True)
    properties = output.stdout + output.stderr
    if not re.search(r"java\.specification\.version = 25\b", properties):
        raise ConfigError("Use Gateway's bundled Java 25 runtime")
    if not re.search(r"os\.arch = aarch64\b", properties):
        raise ConfigError("Use the native ARM64 Gateway installer")
    return java.parent


def property_value(value: str) -> str:
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ConfigError("Credentials must be nonempty single-line values")
    # Java Properties.load reads ISO-8859-1 plus escapes. Encode even punctuation
    # so '=', ':', backslashes and leading spaces cannot change the parsed value.
    encoded = value.encode("utf-16-be")
    return "".join(f"\\u{int.from_bytes(encoded[i:i+2], 'big'):04x}"
                   for i in range(0, len(encoded), 2))


def ibc_config(username: str, password: str, settings: dict) -> str:
    values = {
        "IbLoginId": property_value(username), "IbPassword": property_value(password),
        "TradingMode": settings["mode"], "SecondFactorDevice": "IBKR Mobile",
        "ReloginAfterSecondFactorAuthenticationTimeout": "no" if settings.get("backend") == "docker" else "yes",
        "SecondFactorAuthenticationTimeout": "180",
        "SecondFactorAuthenticationExitInterval": "60",
        "ExistingSessionDetectedAction": "secondary",
        "AcceptNonBrokerageAccountWarning": "yes" if settings["mode"] == "paper" else "no",
        "ReadOnlyLogin": "no", "ReadOnlyApi": "no",
        "OverrideTwsApiPort": str(
            (4002 if settings["mode"] == "paper" else 4001)
            if settings.get("backend") == "docker" else settings["port"]
        ),
        "TrustedTwsApiClientIPs": "127.0.0.1", "AcceptIncomingConnectionAction": "reject",
        "CommandServerPort": "0", "LogStructureWhen": "never",
        "AutoRestartTime": parse_time(settings["daily_restart"]).strftime("%I:%M %p"),
        "ColdRestartTime": settings["sunday_restart"],
    }
    return "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"


def unit_text(executor_path: Path, release: Path, zone: str, backend: str = "native", *,
              launcher: Path | None = None) -> str:
    # Quotes and systemd specifiers are excluded by safe_path/ZoneInfo validation.
    desktop = ("Requires=follow-gateway-desktop.service\n"
               "After=follow-gateway-desktop.service network-online.target")
    command = f'"{launcher or release / ".venv/bin/follow-executor"}" gateway --config "{executor_path}"'
    stop = ""
    if backend == "docker":
        desktop = "After=network-online.target\nStartLimitIntervalSec=0"
        stop = (
            f'ExecStop={command} container-stop\n'
            f'ExecStopPost={command} container-stop\n'
        )
    return f"""[Unit]
Description=Auto Quant IB Gateway with IBC
{desktop}

[Service]
Type=simple
ExecStart={command} run
{stop}\
Environment=DISPLAY=:1
Environment="XAUTHORITY=%h/.Xauthority"
Environment="TZ={zone}"
UMask=0077
Restart={"always" if backend == "docker" else "on-failure"}
RestartSec=60
RestartPreventExitStatus=2
TimeoutStopSec=90
KillMode=control-group
NoNewPrivileges=true

[Install]
WantedBy=default.target
"""


def load_settings(directory: Path, *, check_consistency: bool = True) -> dict:
    for name in ("gateway.json", "ibc.ini"):
        path = directory / name
        if not path.exists() and not path.is_symlink():
            raise ConfigError(f"Gateway configuration is incomplete: {name} is missing. "
                              "Rerun Gateway setup in your terminal.")
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ConfigError(f"{name} must be a private regular file (mode 0600)")
    settings = json.loads((directory / "gateway.json").read_text())
    if settings.get("backend", "native") not in ("native", "docker"):
        raise ConfigError("Unknown Gateway backend")
    if not check_consistency:
        return settings
    if settings.get("backend") == "docker":
        from . import gateway_docker

        gateway_docker.validate_settings(settings)
        if settings["vnc"]:
            vnc = directory / "vnc.password"
            if vnc.is_symlink() or not vnc.is_file() or vnc.stat().st_mode & 0o077:
                raise ConfigError("vnc.password must be a private regular file (mode 0600)")
    # Refuse incomplete saves or hand-edited mismatches, especially paper/live.
    expected = dict(line.split("=", 1) for line in ibc_config("check", "check", settings).splitlines())
    actual = dict(line.split("=", 1) for line in (directory / "ibc.ini").read_text().splitlines()
                  if "=" in line and not line.startswith(("#", "!")))
    for key, value in expected.items():
        if (settings.get("backend") == "docker" and key == "ReloginAfterSecondFactorAuthenticationTimeout"
                and actual.get(key) in ("yes", "no")):
            continue  # Older profiles are normalised to 'no' in the container's private copy.
        if key not in ("IbLoginId", "IbPassword") and actual.get(key) != value:
            raise ConfigError("Gateway settings are inconsistent; rerun './follow gateway configure'")
    return settings


def recovery_password() -> str:
    print("Choose a separate recovery desktop password: exactly 8 printable ASCII "
          "characters, with no spaces (for example, letters and digits).")
    print("This is not your IBKR password. Press Ctrl+C to pause setup.")
    while True:
        password = getpass.getpass("Recovery desktop password (hidden): ")
        if len(password) != 8 or not all(33 <= ord(c) <= 126 for c in password):
            print("Use exactly 8 printable ASCII characters with no spaces. Try again.")
            continue
        if password != getpass.getpass("Confirm recovery desktop password: "):
            print("Recovery passwords do not match. Enter both again.")
            continue
        return password


def configure(executor_path: Path, directory: Path, release: Path, *,
              backend: str | None = None, vnc: bool | None = None,
              launcher: Path | None = None) -> int:
    require_stopped("follow-executor.service")
    require_stopped(SERVICE)
    with ExitStack() as locks:
        locks.enter_context(exclusive(executor_path.with_suffix(executor_path.suffix + ".lock")))
        locks.enter_context(exclusive(directory / "gateway.lock"))
        current = load_config(executor_path) if executor_path.exists() else None
        if current:
            locks.enter_context(exclusive(current.journal_path.with_suffix(current.journal_path.suffix + ".lock")))
        old = load_settings(directory, check_consistency=False) if (directory / "gateway.json").exists() else {}
        backend = backend or old.get("backend", "native")
        if backend not in ("native", "docker"):
            raise ConfigError("Unknown Gateway backend")
        if backend != "docker" and vnc is not None:
            raise ConfigError("--vnc/--no-vnc applies to the Docker backend only")
        if backend == "docker" or old.get("backend") == "docker":
            from . import gateway_docker

            gateway_docker.require_engine()
            gateway_docker.require_stopped(executor_path)
        if backend == "docker":
            gateway_docker.prepare()
            gateway_settings = {"backend": "docker", "image": gateway_docker.IMAGE,
                                "vnc": old.get("vnc", False) if vnc is None else vnc}
        else:
            ibc = release / f"vendor/ibc-{IBC_VERSION}"
            if not (ibc / "IBC.jar").is_file():
                raise ConfigError("Run ./install.sh to install IBC first")
            gateway_settings = {"backend": "native"}
        print("IBC stores your IBKR login locally in a private file on this VM.")
        print("It initiates login; you still approve authentication in IBKR Mobile.")
        print("Use a dedicated Gateway username; keep a different username for phone trading.")
        print("A phone trading login with the same username can disconnect this Gateway session.")
        print("First complete docs/IBKR_ACCOUNT_SETUP.md, including the paper-login check.")
        print("Close any manually launched Gateway before starting IBC. Use an IB Key / Mobile account.")
        if backend == "native":
            gateway = safe_path(ask("Gateway installation directory", old.get(
                "gateway_path", str(Path.home() / "Jts/ibgateway/1051"))))
            java = gateway_runtime(gateway)
            gateway_settings.update(gateway_path=str(gateway), java_path=str(java))
        mode = current.ibkr.account_type if current else ask("Account mode", old.get("mode", "paper"), ("paper", "live"))
        if mode == "live" and input("Type LIVE to enable automatic real-account login: ").strip() != "LIVE":
            raise ConfigError("Gateway setup cancelled")
        port = current.ibkr.port if current else (4002 if mode == "paper" else 4001)
        if current and current.ibkr.host != "127.0.0.1":
            raise ConfigError("IBC automation requires Gateway on 127.0.0.1")
        zone = ask("Schedule timezone (IANA name)", old.get("timezone", "America/New_York"))
        daily = ask("Daily automatic restart (HH:MM, choose outside active trading)", old.get("daily_restart", "23:45"))
        sunday = ask("Sunday mobile approval time (HH:MM)", old.get("sunday_restart", "12:00"))
        validate_schedule(zone, sunday, daily)
        settings = {**gateway_settings, "mode": mode, "port": port,
                    "timezone": zone, "daily_restart": daily, "sunday_restart": sunday}
        vnc_password = None
        if backend == "docker":
            gateway_docker.validate_settings(settings)
            if settings["vnc"]:
                vnc_password = recovery_password()
        username = getpass.getpass("IBKR login username (hidden): ")
        password = getpass.getpass("IBKR password (hidden): ")
        content = ibc_config(username, password, settings)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        private_write(directory / "ibc.ini", content)
        if vnc_password is not None:
            private_write(directory / "vnc.password", vnc_password + "\n")
        elif backend == "docker":
            (directory / "vnc.password").unlink(missing_ok=True)
        private_write(directory / "gateway.json", json.dumps(settings, indent=2) + "\n")
        unit = Path.home() / ".config/systemd/user" / SERVICE
        private_write(unit, unit_text(executor_path, release, zone, backend, launcher=launcher))
        run_command(["systemctl", "--user", "daemon-reload"])
    print(f"Saved. Sunday approval: {sunday} {zone}; daily restart: {daily} {zone}.")
    command = "./follow-stack" if launcher else "./follow"
    print(f"Run '{command} gateway start' and approve IBKR Mobile. Use '{command} check' to verify readiness.")
    if backend == "native" or settings.get("vnc"):
        print("Private recovery desktop: SSH-forward port 5901 and connect your viewer to localhost::5901.")
    else:
        print("If a dialog needs attention, stop while flat and configure again with --vnc. See docs/GATEWAY_DOCKER.md.")
    print("Gateway setup does not start the trading executor.")
    return 0


def launch(executor_path: Path, directory: Path, release: Path) -> int:
    with exclusive(directory / "gateway.lock"):
        settings = load_settings(directory)
        validate_schedule(settings["timezone"], settings["sunday_restart"], settings["daily_restart"])
        if executor_path.exists():
            current = load_config(executor_path)
            if (current.ibkr.account_type != settings["mode"] or current.ibkr.port != settings["port"]
                    or current.ibkr.host != "127.0.0.1"):
                raise ConfigError("Gateway mode/port differs from executor; rerun './follow gateway configure'")
        if settings.get("backend") == "docker":
            from . import gateway_docker

            return gateway_docker.launch(executor_path, directory, settings, release=release)
        gateway = safe_path(settings["gateway_path"])
        java = gateway_runtime(gateway)
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", settings["port"])) == 0:
                raise ConfigError("Gateway API port is already in use; close the other Gateway first")
        for _ in range(30):
            if subprocess.run(["xdpyinfo", "-display", ":1"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise ConfigError("Private desktop :1 is unavailable; check follow-gateway-desktop.service")
        # Upstream expects Jts/ibgateway/VERSION even for a custom installation path.
        runtime = directory / "runtime"
        link = runtime / "ibgateway" / GATEWAY_VERSION
        link.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise ConfigError("Unexpected file in Gateway runtime layout")
        link.symlink_to(gateway, target_is_directory=True)
        tws_settings = directory / "settings"
        tws_settings.mkdir(mode=0o700, exist_ok=True)
        ibc = release / f"vendor/ibc-{IBC_VERSION}"
        env = dict(os.environ, TZ=settings["timezone"])
        # Do not inherit unrelated JVM command injection; use the bundled JVM.
        for key in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
            env.pop(key, None)
        command = ["/bin/bash", str(ibc / "scripts/ibcstart.sh"), GATEWAY_VERSION, "--gateway",
                   f"--tws-path={runtime}", f"--tws-settings-path={tws_settings}",
                   f"--ibc-path={ibc}", f"--ibc-ini={directory / 'ibc.ini'}",
                   f"--java-path={java}", f"--mode={settings['mode']}", "--on2fatimeout=restart"]
        # No username/password in argv, environment or generated service files.
        return subprocess.run(command, env=env, check=False).returncode


def dispatch(executor_path: Path, action: str, *,
             backend: str | None = None, vnc: bool | None = None,
             launcher: Path | None = None) -> int:
    executor_path = safe_path(str(executor_path))
    directory = executor_path.parent / "gateway"
    launcher = safe_path(str(launcher)) if launcher else None
    release = launcher.parent if launcher else safe_path(str(Path(sys.prefix).parent))
    command = "./follow-stack" if launcher else "./follow"
    if action != "configure" and (backend is not None or vnc is not None):
        raise ConfigError("Backend and recovery-desktop options apply only to 'gateway configure'")
    if action == "container-stop":
        from . import gateway_docker

        gateway_docker.stop(executor_path)
        return 0
    if action == "configure":
        return configure(executor_path, directory, release, backend=backend, vnc=vnc, launcher=launcher)
    if action == "run":
        return launch(executor_path, directory, release)
    if action == "status":
        settings = load_settings(directory)
        report = {**settings, "backend": settings.get("backend", "native"), "service": service_state(SERVICE)}
        if settings.get("backend") == "docker":
            from . import gateway_docker

            state = gateway_docker.container_state(executor_path)
            report["container"] = state.get("Status", "unknown") if state else "absent"
            report["settings_volume"] = gateway_docker.volume_name(executor_path, settings)
            report["desktop"] = "SSH tunnel to localhost:5901" if settings["vnc"] else "disabled"
            from .gateway_login import LoginRecovery

            report["login_recovery"] = LoginRecovery(directory, gateway_docker.identity(executor_path)).report()
            from .gateway_health import report as health_report

            report["api_health"] = health_report(directory, gateway_docker.identity(executor_path))
        print(json.dumps(report, indent=2))
        print(f"Service state is not proof of broker authentication. Verify with '{command} check' while stopped.")
        return 0
    if action == "logs":
        return subprocess.run(["journalctl", "--user", "-u", SERVICE, "-f"], check=False).returncode
    if action == "refresh":
        if not (directory / "gateway.json").exists():
            return 0
        require_stopped(SERVICE)
        settings = load_settings(directory)
        validate_schedule(settings["timezone"], settings["sunday_restart"], settings["daily_restart"])
        private_write(Path.home() / ".config/systemd/user" / SERVICE,
                      unit_text(executor_path, release, settings["timezone"], settings.get("backend", "native"),
                                launcher=launcher))
        run_command(["systemctl", "--user", "daemon-reload"])
        return 0
    if action == "stop":
        require_stopped("follow-executor.service")
        with ExitStack() as locks:
            locks.enter_context(exclusive(executor_path.with_suffix(executor_path.suffix + ".lock")))
            if executor_path.exists():
                current = load_config(executor_path)
                locks.enter_context(exclusive(current.journal_path.with_suffix(current.journal_path.suffix + ".lock")))
            run_command(["systemctl", "--user", "disable", "--now", SERVICE])
            if (directory / "gateway.json").exists():
                settings = load_settings(directory, check_consistency=False)
                if settings.get("backend") == "docker":
                    from . import gateway_docker

                    gateway_docker.stop(executor_path)
        print("Gateway stopped; this does not close broker positions or cancel orders.")
        return 0
    settings = load_settings(directory)
    if not (Path.home() / ".config/systemd/user" / SERVICE).exists():
        raise ConfigError("Run './follow gateway configure' first")
    if settings.get("backend") == "docker" and service_state(SERVICE) in ("inactive", "failed"):
        from . import gateway_docker, gateway_login

        with exclusive(directory / "gateway.lock"):
            require_stopped(SERVICE)
            gateway_docker.require_stopped(executor_path)
            gateway_login.reset(directory, gateway_docker.identity(executor_path))
    run_command(["systemctl", "--user", "enable", "--now", SERVICE])
    print("Gateway service started. Approve IBKR Mobile when prompted; allow time for login.")
    print(f"Check '{command} gateway logs'; run '{command} check' while the executor is stopped to verify readiness.")
    return 0
