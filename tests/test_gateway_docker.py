# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from follow_executor import gateway
from follow_executor import gateway_docker as docker
from follow_executor.config import ConfigError
from follow_executor.local import private_write


def settings(**overrides):
    return {"backend": "docker", "image": docker.IMAGE, "mode": "paper", "port": 4002,
            "timezone": "America/New_York", "daily_restart": "23:45", "sunday_restart": "12:00",
            "vnc": False, **overrides}


class DockerGatewayTests(unittest.TestCase):
    def test_configuration_needs_no_native_install_and_preserves_private_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "executor.json"
            directory = root / "gateway"
            output = io.StringIO()
            password = 'secret\\:=中'
            with (patch.object(gateway, "require_stopped"),
                  patch.object(docker, "require_engine"), patch.object(docker, "require_stopped"),
                  patch.object(docker, "prepare") as prepare,
                  patch.object(gateway, "gateway_runtime") as native,
                  patch.object(gateway, "ask", side_effect=lambda label, default, *choices: default),
                  patch.object(gateway.getpass, "getpass", side_effect=["private-login", password]),
                  patch.object(gateway, "run_command") as command,
                  patch.object(Path, "home", return_value=root), contextlib.redirect_stdout(output)):
                gateway.configure(config, directory, root / "release", backend="docker")
            prepare.assert_called_once()
            native.assert_not_called()
            saved = gateway.load_settings(directory)
            self.assertEqual(saved, settings())
            self.assertIn("IbPassword=" + gateway.property_value(password), (directory / "ibc.ini").read_text())
            unit = (root / ".config/systemd/user" / gateway.SERVICE).read_text()
            self.assertNotIn("follow-gateway-desktop", unit)
            self.assertIn("ExecStopPost=", unit)
            self.assertIn("Restart=always", unit)
            self.assertNotIn("--restart always", unit)
            command.assert_called_once_with(["systemctl", "--user", "daemon-reload"])
            for public in (unit, json.dumps(saved), output.getvalue(), str(command.call_args_list)):
                self.assertNotIn(password, public)
                self.assertNotIn("private-login", public)
            self.assertEqual((directory / "ibc.ini").stat().st_mode & 0o777, 0o600)

    def test_configuration_keeps_selected_backend_and_schedule_on_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "gateway"
            old = settings(timezone="UTC", sunday_restart="13:00", daily_restart="22:30")
            private_write(directory / "gateway.json", json.dumps(old))
            private_write(directory / "ibc.ini", gateway.ibc_config("old", "old", old))
            with (patch.object(gateway, "require_stopped"),
                  patch.object(docker, "require_engine"), patch.object(docker, "require_stopped"),
                  patch.object(docker, "prepare"), patch.object(gateway, "run_command"),
                  patch.object(gateway, "ask", side_effect=lambda label, default, *choices: default),
                  patch.object(gateway.getpass, "getpass", side_effect=["new", "new"]),
                  patch.object(Path, "home", return_value=root), contextlib.redirect_stdout(io.StringIO())):
                gateway.configure(root / "executor.json", directory, root / "release")
            self.assertEqual(gateway.load_settings(directory), old)

    def test_runtime_exposes_only_selected_mode_on_loopback_with_no_password_environment(self):
        for mode, forwarded in (("paper", 4004), ("live", 4003)):
            with self.subTest(mode=mode):
                current = settings(mode=mode, port=4500)
                args = docker.run_arguments(Path("/private/executor.json"), current)
                self.assertIn(f"127.0.0.1:4500:{forwarded}", args)
                self.assertEqual(args.count("--publish"), 1)
                self.assertIn("CUSTOM_CONFIG=yes", args)
                self.assertIn("TWOFA_TIMEOUT_ACTION=exit", args)
                self.assertIn("--cap-drop", args)
                self.assertIn("no-new-privileges=true", args)
                self.assertEqual(args[-1], docker.IMAGE)
                self.assertNotIn("TWS_PASSWORD", " ".join(args))
                self.assertEqual(args[args.index("--restart") + 1], "no")
                ini = gateway.ibc_config("login", "password", current)
                self.assertIn(f"OverrideTwsApiPort={4002 if mode == 'paper' else 4001}\n", ini)
                self.assertIn("ExistingSessionDetectedAction=secondary", ini)
                self.assertIn("AcceptIncomingConnectionAction=reject", ini)
                self.assertIn("ReloginAfterSecondFactorAuthenticationTimeout=no", ini)
        args = docker.run_arguments(Path("/private/executor.json"), settings(vnc=True))
        self.assertIn("127.0.0.1:5901:5900", args)
        self.assertIn(f"VNC_SERVER_PASSWORD_FILE={docker.DATA}/vnc.password", args)

    def test_tampered_image_and_public_vnc_file_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            current = settings(vnc=True)
            private_write(directory / "gateway.json", json.dumps(current))
            private_write(directory / "ibc.ini", gateway.ibc_config("u", "p", current))
            private_write(directory / "vnc.password", "12345678\n")
            self.assertEqual(gateway.load_settings(directory), current)
            (directory / "vnc.password").chmod(0o644)
            with self.assertRaisesRegex(ConfigError, "private regular"):
                gateway.load_settings(directory)
            (directory / "vnc.password").chmod(0o600)
            private_write(directory / "gateway.json", json.dumps({**current, "image": "untrusted:latest"}))
            with self.assertRaisesRegex(ConfigError, "image differs"):
                gateway.load_settings(directory)

    def test_initializer_separates_host_credentials_from_container_uid(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "executor.json"
            label = json.dumps({docker.LABEL: docker.identity(path)})
            with patch.object(docker, "command", return_value=Mock(stdout=label)) as command:
                docker.initialize(path, directory, settings())
            args = command.call_args.args[0]
            self.assertEqual(args[args.index("--network") + 1], "none")
            self.assertIn(f"type=bind,source={directory}/ibc.ini,target=/input/ibc.ini,readonly", args)
            self.assertIn("install -m 600 -o 1000 -g 1000 /input/ibc.ini /data/ibc.ini", args[-1])
            self.assertIn("chmod 700 /data /data/settings", args[-1])
            self.assertIn("ReloginAfterSecondFactorAuthenticationTimeout=no", args[-1])
            self.assertEqual((directory / "docker-jts.ini").stat().st_mode & 0o777, 0o600)

    def test_existing_unmanaged_volume_is_not_overwritten(self):
        with patch.object(docker, "command", return_value=Mock(stdout='{}')) as command:
            with self.assertRaisesRegex(ConfigError, "not owned"):
                docker.initialize(Path("/private/executor.json"), Path("/private"), settings())
            self.assertFalse(any(call.args[0][0] == "run" for call in command.call_args_list))

    def test_previous_docker_retry_setting_is_accepted_without_reentering_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            current = settings()
            private_write(directory / "gateway.json", json.dumps(current))
            private_write(directory / "ibc.ini", gateway.ibc_config("u", "p", current).replace(
                "ReloginAfterSecondFactorAuthenticationTimeout=no", "ReloginAfterSecondFactorAuthenticationTimeout=yes"))
            self.assertEqual(gateway.load_settings(directory), current)

    def test_unmanaged_container_cannot_be_stopped(self):
        path = Path("/private/executor.json")
        with patch.object(docker, "command", side_effect=[
            Mock(stdout=docker.identity(path) + "\n"), Mock(stdout='{}\n{"Running":true}\n'),
        ]) as command:
            with self.assertRaisesRegex(ConfigError, "unmanaged"):
                docker.stop(path)
            self.assertFalse(any("stop" in call.args[0] for call in command.call_args_list))

    def test_stop_handles_automatic_removal_without_removing_persistent_volume(self):
        with (patch.object(docker, "container_state", side_effect=[{"Running": True}, None]),
              patch.object(docker, "command") as command):
            path = Path("/private/executor.json")
            docker.stop(path)
            command.assert_called_once_with(["container", "stop", "--time", "30", docker.identity(path)], timeout=45)

    def test_container_disappearing_during_inspection_is_not_an_error(self):
        path = Path("/private/executor.json")
        with patch.object(docker, "command", side_effect=[
            Mock(stdout=docker.identity(path) + "\n"), docker.DockerUnavailable("gone"), Mock(stdout=""),
        ]):
            self.assertIsNone(docker.container_state(path))

    def test_daemon_failure_during_inspection_remains_an_error(self):
        path = Path("/private/executor.json")
        with (patch.object(docker, "command", side_effect=[
            Mock(stdout=docker.identity(path) + "\n"), docker.DockerUnavailable("offline"),
            docker.DockerUnavailable("offline"),
        ]), self.assertRaises(docker.DockerUnavailable)):
            docker.container_state(path)

    def test_daemon_startup_failure_is_retryable_but_invalid_image_is_not(self):
        with (patch.object(docker, "require_engine", side_effect=docker.DockerUnavailable("not ready")),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(docker.launch(Path("/unused"), Path("/unused"), settings()), 1)
            with self.assertRaises(ConfigError):
                docker.launch(Path("/unused"), Path("/unused"), settings(image="latest"))

    def test_duplicate_native_gateway_is_refused_before_initialization(self):
        with (patch.object(docker, "require_engine"), patch.object(docker, "verify_image"),
              patch.object(docker, "stop"), patch.object(docker.socket, "socket") as sock,
              patch.object(docker, "initialize") as initialize):
            sock.return_value.__enter__.return_value.connect_ex.return_value = 0
            with self.assertRaisesRegex(ConfigError, "already in use"):
                docker.launch(Path("/unused"), Path("/unused"), settings())
            initialize.assert_not_called()

    def test_docker_errors_do_not_leak_output_and_use_only_local_engine(self):
        with patch.object(docker.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 1, stdout="secret", stderr="secret",
        )) as run:
            with self.assertRaises(docker.DockerUnavailable) as failure:
                docker.command(["inspect", "example"])
            self.assertNotIn("secret", str(failure.exception))
            self.assertEqual(run.call_args.args[0][:3], ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"])

    def test_older_docker_is_refused_for_loopback_binding(self):
        with (patch.object(docker.platform, "machine", return_value="aarch64"),
              patch.object(docker, "command", return_value=Mock(stdout="27.5.0\n")),
              self.assertRaisesRegex(ConfigError, "28 or newer")):
            docker.require_engine()
