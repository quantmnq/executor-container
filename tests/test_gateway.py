# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from follow_executor import gateway
from follow_executor.config import ConfigError


class GatewayTests(unittest.TestCase):
    def test_recovery_password_retries_invalid_input_and_mismatch_privately(self):
        invalid = ["short", "too-long-password", "with spa", "abcdefgé", "abcdefg\t", "abcdefg\x7f"]
        output = io.StringIO()
        with (patch.object(gateway.getpass, "getpass", side_effect=[
                *invalid, "first123", "other123", "valid!23", "valid!23",
              ]) as prompt, contextlib.redirect_stdout(output)):
            self.assertEqual(gateway.recovery_password(), "valid!23")
        self.assertEqual(prompt.call_count, len(invalid) + 4)
        self.assertIn("do not match", output.getvalue())
        self.assertIn("Try again", output.getvalue())
        for secret in [*invalid, "first123", "other123", "valid!23"]:
            self.assertNotIn(secret, output.getvalue())

    def test_recovery_password_can_be_cancelled(self):
        for interruption in (KeyboardInterrupt, EOFError):
            with (self.subTest(interruption=interruption),
                  patch.object(gateway.getpass, "getpass", side_effect=["short", interruption]),
                  contextlib.redirect_stdout(io.StringIO()), self.assertRaises(interruption)):
                gateway.recovery_password()

    def test_missing_gateway_settings_are_not_reported_as_permissions_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaisesRegex(ConfigError, "gateway.json is missing"):
                gateway.load_settings(directory)
            (directory / "gateway.json").write_text("{}")
            (directory / "gateway.json").chmod(0o600)
            with self.assertRaisesRegex(ConfigError, "ibc.ini is missing"):
                gateway.load_settings(directory)
            (directory / "ibc.ini").symlink_to(directory / "absent")
            with self.assertRaisesRegex(ConfigError, "private regular file"):
                gateway.load_settings(directory)

    def test_schedule_covers_sunday_reset_and_dst(self):
        for zone, sunday in (("America/New_York", "12:00"), ("UTC", "12:00"), ("America/Los_Angeles", "09:00"),
                             ("Asia/Shanghai", "20:00"), ("Europe/London", "12:00")):
            gateway.validate_schedule(zone, sunday, "23:45")
        for zone, sunday, daily in (("UTC", "05:30", "23:45"),
                                    ("Asia/Shanghai", "10:00", "23:45"),
                                    ("America/New_York", "02:30", "23:45"),
                                    ("Missing/Zone", "12:00", "23:45"),
                                    ("UTC", "12:00", "12:00"),
                                    ("UTC", "25:00", "23:45")):
            with self.subTest(zone=zone, sunday=sunday), self.assertRaises(ConfigError):
                gateway.validate_schedule(zone, sunday, daily)

    def test_credentials_preserve_java_properties_special_characters(self):
        value = ' a=:#\\!中😀'
        escaped = gateway.property_value(value)
        decoded = bytes.fromhex(escaped.replace('\\u', '')).decode('utf-16-be')
        self.assertEqual(value, decoded)
        for invalid in ("", "pw\nAutoRestartTime=01:00 AM", "pw\r", "pw\x00"):
            with self.assertRaises(ConfigError):
                gateway.property_value(invalid)

    def test_wizard_writes_private_files_without_starting_service_or_logging_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "release"
            ibc = release / f"vendor/ibc-{gateway.IBC_VERSION}"
            ibc.mkdir(parents=True)
            (ibc / "IBC.jar").touch()
            executor_path = root / ".config/follow-executor/executor.json"
            directory = executor_path.parent / "gateway"
            secret = "not-a-real-password\\!:=中"
            output = io.StringIO()
            with (patch.object(gateway, "require_stopped"),
                  patch.object(gateway, "gateway_runtime", return_value=root / "java/bin"),
                  patch.object(gateway, "ask", side_effect=lambda label, default, *choices: default),
                  patch.object(gateway.getpass, "getpass", side_effect=["example-login", secret]),
                  patch.object(gateway, "run_command") as command,
                  patch.object(Path, "home", return_value=root),
                  contextlib.redirect_stdout(output)):
                gateway.configure(executor_path, directory, release)
            settings = gateway.load_settings(directory)
            self.assertEqual(settings["mode"], "paper")
            self.assertEqual(settings["port"], 4002)
            self.assertEqual(settings["timezone"], "America/New_York")
            self.assertEqual(settings["sunday_restart"], "12:00")
            self.assertEqual(settings["daily_restart"], "23:45")
            ini = (directory / "ibc.ini").read_text()
            self.assertIn("ColdRestartTime=12:00", ini)
            self.assertIn("AutoRestartTime=11:45 PM", ini)
            self.assertIn("ReloginAfterSecondFactorAuthenticationTimeout=yes", ini)
            self.assertIn("ExistingSessionDetectedAction=secondary", ini)
            self.assertIn("CommandServerPort=0", ini)
            self.assertIn(f"IbPassword={gateway.property_value(secret)}", ini)
            unit = (root / ".config/systemd/user/follow-gateway.service").read_text()
            for public in (output.getvalue(), unit, json.dumps(settings), str(command.call_args_list)):
                self.assertNotIn(secret, public)
                self.assertNotIn("example-login", public)
                self.assertNotIn(gateway.property_value(secret), public)
            command.assert_called_once_with(["systemctl", "--user", "daemon-reload"])
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual((directory / "ibc.ini").stat().st_mode & 0o777, 0o600)
            self.assertEqual((directory / "gateway.json").stat().st_mode & 0o777, 0o600)
            self.assertIn("RestartPreventExitStatus=2", unit)
            self.assertIn('Environment="TZ=America/New_York"', unit)
            (directory / "ibc.ini").write_text(ini.replace("TradingMode=paper", "TradingMode=live"))
            with self.assertRaises(ConfigError):
                gateway.load_settings(directory)

    def test_existing_credentials_with_public_permissions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "gateway.json").write_text("{}")
            (directory / "gateway.json").chmod(0o600)
            (directory / "ibc.ini").write_text("IbPassword=example")
            (directory / "ibc.ini").chmod(0o644)
            with self.assertRaises(ConfigError):
                gateway.load_settings(directory)

    def test_runtime_rejects_wrong_gateway_and_java(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "jars").mkdir()
            (path / "jars/jts4launch-1045.jar").touch()
            with self.assertRaises(ConfigError):
                gateway.gateway_runtime(path)
            (path / "jars/jts4launch-1045.jar").rename(path / "jars/jts4launch-1051.jar")
            (path / ".install4j").mkdir()
            for name in ("ibgateway.vmoptions", ".install4j/i4jparams.conf", ".install4j/i4jruntime.jar"):
                (path / name).touch()
            with patch.object(gateway, "run_command") as command:
                command.return_value.stdout = ""
                command.return_value.stderr = "java.specification.version = 17\nos.arch = aarch64"
                with self.assertRaises(ConfigError):
                    gateway.gateway_runtime(path)
                command.return_value.stderr = "java.specification.version = 25\nos.arch = aarch64"
                self.assertEqual(gateway.gateway_runtime(path), path / "jre/bin")

    def test_configure_refuses_running_executor_before_requesting_credentials(self):
        with patch.object(gateway, "service_state", return_value="active"), \
                patch.object(gateway.getpass, "getpass") as secret:
            with self.assertRaises(ConfigError):
                gateway.configure(Path("/unused/executor.json"), Path("/unused/gateway"), Path("/unused"))
            secret.assert_not_called()

    def test_launcher_refuses_duplicate_gateway_on_api_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = {"timezone": "UTC", "sunday_restart": "12:00", "daily_restart": "23:45",
                        "gateway_path": str(root / "gateway"), "port": 4002, "mode": "paper"}
            with (patch.object(gateway, "load_settings", return_value=settings),
                  patch.object(gateway, "gateway_runtime", return_value=root / "java/bin"),
                  patch.object(gateway.socket, "socket") as socket,
                  patch.object(gateway.subprocess, "run") as run):
                socket.return_value.__enter__.return_value.connect_ex.return_value = 0
                with self.assertRaisesRegex(ConfigError, "already in use"):
                    gateway.launch(root / "executor.json", root / "private", root / "release")
                run.assert_not_called()

    def test_launcher_uses_upstream_restart_loop_and_persistent_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = {"timezone": "Asia/Shanghai", "sunday_restart": "20:00", "daily_restart": "23:45",
                        "gateway_path": str(root / "gateway"), "port": 4002, "mode": "paper"}
            with (patch.object(gateway, "load_settings", return_value=settings),
                  patch.object(gateway, "gateway_runtime", return_value=root / "java/bin"),
                  patch.object(gateway.socket, "socket") as socket,
                  patch.object(gateway.subprocess, "run") as run):
                socket.return_value.__enter__.return_value.connect_ex.return_value = 1
                run.return_value.returncode = 0
                self.assertEqual(gateway.launch(root / "executor.json", root / "private", root / "release"), 0)
                args, kwargs = run.call_args
                command = args[0]
                self.assertIn("--mode=paper", command)
                self.assertIn("--on2fatimeout=restart", command)
                self.assertIn(f"--ibc-ini={root}/private/ibc.ini", command)
                self.assertIn(f"--tws-settings-path={root}/private/settings", command)
                self.assertFalse(any(arg.startswith(("--pw=", "--user=")) for arg in command))
                self.assertEqual(kwargs["env"]["TZ"], "Asia/Shanghai")
                self.assertEqual((root / "private/runtime/ibgateway/1051").readlink(), root / "gateway")
