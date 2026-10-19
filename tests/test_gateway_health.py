# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from follow_executor import gateway_health as health
from follow_executor import gateway_health_probe as probe
from follow_executor import gateway_login as login
from follow_executor.config import ConfigError, IBKRSettings
from follow_executor.local import private_write

SETTINGS = IBKRSettings("127.0.0.1", 4002, 71, "DU1234567", "paper", 15)
PROMPT = "2026-10-18 14:00:00:123 IBC: detected dialog entitled: Second Factor Authentication; event=Opened"
SUCCESS = "2026-10-18 14:00:00:123 IBC: Login has completed"
VERSION = "2026-10-18 14:00:00:123 IBC: version: 3.24.2"


class HealthMonitorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.now, self.wall = 100.0, 10000.0
        self.result = "healthy"
        self.workers = []
        self.output = io.StringIO()
        redirect = contextlib.redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        self.login = login.LoginRecovery(self.directory, "owned", clock=lambda: self.now)
        self.monitor = self.new_monitor()
        self.addCleanup(lambda: self.monitor.close())

    def new_monitor(self):
        return health.HealthMonitor(self.directory, "owned", self.factory,
                                    clock=lambda: self.now, wall_clock=lambda: self.wall)

    def factory(self):
        worker = Mock()
        worker.poll.return_value = self.result
        self.workers.append(worker)
        return worker

    def authenticate(self):
        self.login.line(SUCCESS)
        self.monitor.tick(self.login)

    def sample(self, result):
        self.result = result
        self.now += health.INTERVAL
        self.wall += health.INTERVAL
        self.assertIsNone(self.monitor.tick(self.login))
        return self.monitor.tick(self.login)

    def test_ten_consecutive_api_failures_request_one_restart(self):
        self.authenticate()
        for _ in range(9):
            self.assertIsNone(self.sample("unavailable"))
        self.assertEqual(self.sample("unavailable"), 1)
        self.assertEqual(health.report(self.directory, "owned")["status"], "restarting")
        self.assertEqual(self.monitor.state["last_restart_epoch"], self.wall)
        self.assertEqual(self.monitor.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.login.state["attempts"], 0)

    def test_cooldown_survives_supervisor_restart_and_clock_rollback(self):
        self.authenticate()
        for _ in range(10):
            self.sample("unavailable")
        restarted_at = self.wall
        self.monitor = self.new_monitor()
        self.monitor.tick(self.login)
        for _ in range(10):
            self.assertIsNone(self.sample("unavailable"))
        self.assertEqual(self.monitor.state["status"], "cooldown")
        self.wall = restarted_at - 5000
        self.assertIsNone(self.sample("unavailable"))
        self.wall = restarted_at + health.COOLDOWN
        self.assertEqual(self.sample("unavailable"), 1)

    def test_healthy_and_monitor_errors_break_failure_streak(self):
        self.authenticate()
        for reset in ("healthy", "monitor_error", "account_mismatch"):
            for _ in range(9):
                self.assertIsNone(self.sample("unavailable"))
            self.assertIsNone(self.sample(reset))
            self.assertEqual(self.monitor.state["failures"], 0)
        self.assertEqual(self.monitor.state["last_restart_epoch"], 0)

    def test_no_api_work_or_restart_while_waiting_for_first_or_retry_approval(self):
        for event in (None, PROMPT):
            if event:
                self.login.line(event)
            for _ in range(20):
                self.now += 60
                self.assertIsNone(self.monitor.tick(self.login))
        retry = login.LoginRecovery(self.directory, "owned", clock=lambda: self.now)
        retry.begin_launch()
        retry.line(PROMPT)
        self.assertIsNone(self.monitor.tick(retry))
        self.assertEqual(self.workers, [])
        retry.attention()
        retry.authenticated = True  # A stale flag cannot bypass attention.
        self.assertIsNone(self.monitor.tick(retry))
        self.assertEqual(retry.state["attempts"], 2)

    def test_weekly_reauthentication_cancels_probe_and_discards_old_failures(self):
        self.authenticate()
        for _ in range(9):
            self.sample("unavailable")
        self.result = None
        self.now += 60
        self.monitor.tick(self.login)
        outstanding = self.workers[-1]
        self.login.line(VERSION)
        self.login.line(PROMPT)
        self.assertIsNone(self.monitor.tick(self.login))
        outstanding.close.assert_called_once()
        self.assertEqual(self.monitor.state["failures"], 0)
        self.assertEqual(self.monitor.state["status"], "waiting_for_login")
        self.authenticate()
        self.assertIsNone(self.sample("unavailable"))
        self.assertEqual(self.monitor.state["failures"], 1)

    def test_warm_restart_and_login_in_same_log_batch_still_reset_streak(self):
        self.authenticate()
        self.sample("unavailable")
        self.login.line(VERSION)
        self.login.line(SUCCESS)
        self.assertIsNone(self.monitor.tick(self.login))
        self.assertEqual(self.monitor.state["failures"], 0)
        self.assertIsNone(self.monitor.worker)

    def test_probe_launch_failure_does_not_restart_gateway_or_echo_error(self):
        self.authenticate()
        self.monitor.factory = Mock(side_effect=OSError("private-value"))
        self.now += 60
        self.assertIsNone(self.monitor.tick(self.login))
        self.assertEqual(self.monitor.state["status"], "monitor_error")
        self.assertNotIn("private-value", self.output.getvalue())

    def test_unsafe_state_cannot_reset_cooldown(self):
        for contents in ("[]", "broken", '{"version":true}'):
            private_write(self.monitor.path, contents)
            with self.assertRaises(ConfigError):
                self.new_monitor()
        self.monitor.save("healthy")
        self.monitor.path.chmod(0o644)
        with self.assertRaises(ConfigError):
            self.new_monitor()

    def test_supervisor_continues_to_process_approval_while_api_probe_is_pending(self):
        script = ("import sys,time;print(sys.argv[1],flush=True);time.sleep(.1);"
                  "print(sys.argv[2],flush=True);print(sys.argv[3],flush=True);time.sleep(5)")
        self.result = None
        with patch.object(health, "INTERVAL", 0), patch.object(login, "APPROVAL_SECONDS", .1):
            recovery = login.LoginRecovery(self.directory, "other")
            monitor = health.HealthMonitor(self.directory, "other", self.factory)
            process = subprocess.Popen([sys.executable, "-c", script, SUCCESS, VERSION, PROMPT],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                self.assertEqual(login.monitor(process, recovery, monitor), 1)
                self.assertTrue(self.workers)
                self.assertEqual(monitor.state["status"], "waiting_for_login")
            finally:
                monitor.close()
                process.terminate()
                process.wait(timeout=5)
                process.stdout.close()


class ProbeProcessTests(unittest.TestCase):
    def test_image_probe_mounts_only_configuration_readonly_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary)
            image = "sha256:" + "a" * 64
            (release / "RELEASE.json").write_text(json.dumps({
                "wheel_sha256": "abc", "executor_image": {
                    "id": image, "platform": "linux/arm64", "wheel_sha256": "abc"}}))
            with patch.object(health.subprocess, "Popen") as launch:
                worker = health.ProbeProcess(release / "executor.json", release)
            args = launch.call_args.args[0]
            self.assertEqual(args.count("--mount"), 1)
            self.assertIn(f"type=bind,source={release}/executor.json,target=/probe/executor.json,readonly", args)
            self.assertIn("--read-only", args)
            self.assertIn("/usr/bin/timeout", args)
            self.assertIn("20", args)
            self.assertIn(image, args)
            self.assertNotIn("/var/run/docker.sock:/var/run/docker.sock", str(args))
            self.assertNotIn("ibc.ini", str(args))
            self.assertNotIn("run", args[args.index(image) + 1:])
            self.assertTrue(worker.container.startswith("aq-gateway-health-"))

    def test_only_valid_probe_output_can_count_as_gateway_failure(self):
        for text, code, expected in (
            ('{"version":1,"status":"unavailable"}', 1, "unavailable"),
            ('{"version":1,"status":"healthy"}', 0, "healthy"),
            ('{"version":1,"status":"healthy"}', 1, "monitor_error"),
            ('{"version":1,"status":"unavailable"}', 125, "monitor_error"),
            ('{"version":true,"status":"unavailable"}', 1, "monitor_error"),
            ("private docker error", 125, "monitor_error"),
            ("[]", 1, "monitor_error"),
        ):
            with self.subTest(text=text):
                worker = health.ProbeProcess.__new__(health.ProbeProcess)
                worker.process = Mock(returncode=code)
                worker.process.poll.return_value = code
                worker.process.stdout = io.BytesIO(text.encode())
                self.assertEqual(worker.poll(), expected)


class ProbeTests(unittest.TestCase):
    def fake(self, *, ready=True, managed=True, conflict=False, connected=True, expected=True):
        app = Mock()
        app.ready, app.managed = threading.Event(), threading.Event()
        if ready:
            app.ready.set()
        if managed:
            app.managed.set()
        app.conflict = conflict
        app.accounts = {SETTINGS.account} if expected else {"DU7654321"}
        app.isConnected.return_value = connected
        return app

    def test_handshake_needs_both_callbacks_expected_account_and_active_socket(self):
        for options, expected in (
            ({}, "healthy"), ({"ready": False}, "unavailable"),
            ({"managed": False}, "unavailable"), ({"connected": False}, "unavailable"),
            ({"expected": False}, "account_mismatch"), ({"conflict": True}, "monitor_error"),
        ):
            with self.subTest(options=options):
                app = self.fake(**options)
                self.assertEqual(probe.probe(SETTINGS, factory=lambda app=app: app, timeout=.01), expected)
                app.disconnect.assert_called_once()
                app.placeOrder.assert_not_called()
                app.cancelOrder.assert_not_called()
                app.reqMktData.assert_not_called()

    def test_client_collision_and_nonlocal_endpoint_are_rejected_before_connect(self):
        factory = Mock()
        for settings in (replace(SETTINGS, host="remote"), replace(SETTINGS, client_id=9701)):
            self.assertEqual(probe.probe(settings, factory=factory), "monitor_error")
        factory.assert_not_called()

    def test_outbound_allowlist_blocks_orders_and_other_requests_in_both_wire_formats(self):
        try:
            from ibapi.client import PROTOBUF_MSG_ID, EClient
            from ibapi.message import OUT
        except ImportError:
            self.skipTest("official ibapi is not installed")
        app = probe.client()
        with patch.object(EClient, "sendMsg") as send, patch.object(EClient, "sendMsgProtoBuf") as protobuf:
            for name in ("PLACE_ORDER", "CANCEL_ORDER", "REQ_GLOBAL_CANCEL", "EXERCISE_OPTIONS",
                         "REQ_MKT_DATA", "REQ_POSITIONS"):
                code = int(getattr(OUT, name))
                with self.assertRaises(PermissionError):
                    app.sendMsg(code, "")
                with self.assertRaises(PermissionError):
                    app.sendMsgProtoBuf(code + PROTOBUF_MSG_ID, b"")
            send.assert_not_called()
            protobuf.assert_not_called()
            app.sendMsg(int(OUT.START_API), "")
            app.sendMsgProtoBuf(int(OUT.REQ_MANAGED_ACCTS) + PROTOBUF_MSG_ID, b"")
            send.assert_called_once()
            protobuf.assert_called_once()

    def test_legacy_and_protobuf_callbacks_and_broker_farm_outage(self):
        try:
            from ibapi.wrapper import EWrapper
        except ImportError:
            self.skipTest("official ibapi is not installed")
        app = probe.client()
        app.nextValidId(1)
        app.managedAccounts(SETTINGS.account)
        self.assertTrue(app.ready.is_set() and app.managed.is_set())
        app.ready.clear()
        app.managed.clear()
        for name, fields in (("nextValidIdProtoBuf", {"orderId": 2}),
                             ("managedAccountsProtoBuf", {"accountsList": SETTINGS.account})):
            message_type = next(value for value in getattr(EWrapper, name).__annotations__.values()
                                if hasattr(value, "DESCRIPTOR"))
            getattr(app, name)(message_type(**fields))
        self.assertTrue(app.ready.is_set() and app.managed.is_set())
        for code in (1100, 2103, 2105):
            app.error(-1, 0, code, "broker farm maintenance")
        self.assertFalse(app.conflict)
        app.error(-1, 0, 326, "reserved client already in use")
        self.assertTrue(app.conflict)
