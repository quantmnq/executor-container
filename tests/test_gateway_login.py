# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from follow_executor import gateway, gateway_docker
from follow_executor import gateway_login as login
from follow_executor.config import ConfigError
from follow_executor.local import private_write


def event(message):
    return "2026-10-18 14:00:00:123 IBC: " + message


PROMPT = event("detected dialog entitled: Second Factor Authentication; event=Opened")
SUCCESS = event("Login has completed")
VERSION = event("version: 3.24.2")


class LoginRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.now = 1000.0
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def recovery(self):
        return login.LoginRecovery(self.directory, "test-gateway", clock=lambda: self.now)

    def test_one_retry_then_persistent_attention_survives_process_restarts(self):
        first = self.recovery()
        self.assertIsNone(first.begin_launch())
        first.line(PROMPT)
        self.now += 299
        self.assertIsNone(first.expired())
        self.now += 1
        self.assertEqual(first.expired(), 1)
        second = self.recovery()
        self.assertIsNone(second.begin_launch())
        second.line(PROMPT)
        self.assertEqual(second.state["attempts"], 2)
        self.now += 300
        self.assertEqual(second.expired(), 2)
        third = self.recovery()
        self.assertEqual(third.begin_launch(), 2)
        self.assertTrue(third.report()["attention_required"])
        self.assertEqual(third.path.stat().st_mode & 0o777, 0o600)
        login.reset(self.directory, "test-gateway")
        self.assertIsNone(self.recovery().begin_launch())

    def test_crash_or_reboot_does_not_refill_budget_even_before_replacement_prompt(self):
        first = self.recovery()
        first.begin_launch()
        first.line(PROMPT)
        second = self.recovery()
        second.begin_launch()  # killed before the next prompt: reservation is durable
        third = self.recovery()
        self.assertEqual(third.begin_launch(), 2)
        self.assertEqual(third.state["attempts"], 2)

    def test_success_disarms_timer_and_new_weekly_jvm_gets_its_own_budget(self):
        recovery = self.recovery()
        recovery.begin_launch()
        recovery.line(PROMPT)
        recovery.line(SUCCESS)
        self.now += 10000
        self.assertIsNone(recovery.expired())
        recovery.line(PROMPT)  # stray dialog from a logged-in JVM must not restart it
        self.assertIsNone(recovery.expired())
        self.assertEqual(recovery.state["phase"], "idle")
        recovery.line(VERSION)
        recovery.line(PROMPT)
        self.assertEqual(recovery.state["attempts"], 1)
        self.now += 300
        self.assertEqual(recovery.expired(), 1)

    def test_success_on_retry_clears_persistent_budget(self):
        first = self.recovery()
        first.line(PROMPT)
        second = self.recovery()
        second.begin_launch()
        second.line(PROMPT)
        second.line(SUCCESS)
        self.assertEqual(self.recovery().state["phase"], "idle")
        self.assertEqual(self.recovery().state["attempts"], 0)

    def test_internal_retries_cannot_bypass_budget_or_extend_deadline_with_focus_events(self):
        recovery = self.recovery()
        recovery.line(PROMPT)
        original = recovery.deadline
        self.now += 10
        recovery.line(PROMPT.replace("Opened", "Activated"))
        self.assertEqual(recovery.deadline, original)
        recovery.line(VERSION)
        recovery.line(PROMPT)
        self.assertEqual(recovery.state["attempts"], 2)
        self.assertEqual(recovery.line(PROMPT), 2)

    def test_exit_during_second_attempt_stops_instead_of_spawning_another_login(self):
        self.recovery().line(PROMPT)
        second = self.recovery()
        second.begin_launch()
        self.assertEqual(second.exited(0), 2)
        self.assertTrue(self.recovery().report()["attention_required"])

    def test_timeout_is_not_armed_without_a_real_approval_event(self):
        recovery = self.recovery()
        recovery.begin_launch()
        for line in ("secret-user", "IbPassword=private-password", "Login has completed",
                     "example: " + PROMPT, "example: " + SUCCESS):
            recovery.line(line)
        self.now += 10000
        self.assertIsNone(recovery.expired())
        self.assertEqual(self.output.getvalue(), "")
        self.assertFalse(recovery.path.exists())

    def test_invalid_or_public_state_does_not_silently_reset_retry_limit(self):
        path = self.directory / "login-recovery.json"
        for content in ('broken', '[]', '{"version":1}', '{"version":true}'):
            private_write(path, content)
            with self.assertRaises(ConfigError):
                self.recovery()
        path.unlink()
        self.recovery().line(PROMPT)
        path.chmod(0o644)
        with self.assertRaises(ConfigError):
            self.recovery()
        path.unlink()
        path.symlink_to(self.directory / "missing")
        with self.assertRaises(ConfigError):
            self.recovery()

    def test_stream_timeout_and_secret_filtering_with_a_real_child_process(self):
        script = "import sys,time;print('private-password',flush=True);print(sys.argv[1],flush=True);time.sleep(30)"
        process = subprocess.Popen([sys.executable, "-c", script, PROMPT], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        try:
            with patch.object(login, "APPROVAL_SECONDS", 0.05):
                recovery = login.LoginRecovery(self.directory, "test-gateway")
                self.assertEqual(login.monitor(process, recovery), 1)
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
        self.assertNotIn("private-password", self.output.getvalue())

    def test_stream_handles_split_lines_and_oversized_output_without_losing_login(self):
        script = ("import sys,time;sys.stdout.write('x'*70000+'\\n');sys.stdout.flush();"
                  "sys.stdout.write(sys.argv[1][:20]);sys.stdout.flush();time.sleep(.05);"
                  "sys.stdout.write(sys.argv[1][20:]+'\\n'+sys.argv[2]+'\\n');sys.stdout.flush()")
        with subprocess.Popen([sys.executable, "-c", script, PROMPT, SUCCESS], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as process:
            recovery = self.recovery()
            self.assertEqual(login.monitor(process, recovery), 0)
        self.assertEqual(recovery.state["phase"], "idle")
        self.assertNotIn("xxxx", self.output.getvalue())

    def test_explicit_start_resets_only_a_stopped_docker_gateway(self):
        config = self.directory / "executor.json"
        identity = gateway_docker.identity(config)
        directory = self.directory / "gateway"
        recovery = login.LoginRecovery(directory, identity)
        recovery.line(PROMPT)
        recovery.attention()
        unit = self.directory / ".config/systemd/user" / gateway.SERVICE
        unit.parent.mkdir(parents=True)
        unit.touch()
        with (patch.object(Path, "home", return_value=self.directory),
              patch.object(gateway, "load_settings", return_value={"backend": "docker"}),
              patch.object(gateway, "service_state", return_value="active"),
              patch.object(gateway, "run_command"), patch.object(gateway_docker, "require_stopped") as stopped):
            gateway.dispatch(config, "start")
            stopped.assert_not_called()
        self.assertEqual(login.LoginRecovery(directory, identity).state["phase"], "attention")
        with (patch.object(Path, "home", return_value=self.directory),
              patch.object(gateway, "load_settings", return_value={"backend": "docker"}),
              patch.object(gateway, "service_state", return_value="failed"),
              patch.object(gateway, "run_command"), patch.object(gateway_docker, "require_stopped") as stopped):
            gateway.dispatch(config, "start")
            stopped.assert_called_once_with(config)
        self.assertEqual(login.LoginRecovery(directory, identity).state["phase"], "idle")
