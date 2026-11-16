# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from follow_executor import cli, gateway, gateway_docker, stack
from follow_executor.answers import (
    ACCOUNT_PROMPTS,
    DISCORD_PROMPTS,
    HOST_PROMPTS,
    NeedInput,
    scripted,
)
from follow_executor.config import ConfigError
from follow_executor.console import (
    Console,
    command_args,
    json_report,
    make_server,
    reconnect_command,
)
from follow_executor.local import private_write

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "sha256:" + "c" * 64
ACCOUNT = {"mode": "paper", "account": "du1234567", "sizing": "balance",
           "leverage_fraction": "0.5", "token": "console-secret-token"}
GATEWAY = {"timezone": "America/New_York", "daily_restart": "23:45", "sunday_restart": "12:00",
           "vnc": True, "vnc_password": "vncpass1", "username": "console-gw-user",
           "password": "console-gw-password"}
SECRETS = ("console-secret-token", "vncpass1", "console-gw-user", "console-gw-password")


class ScriptedAnswerTests(unittest.TestCase):
    def test_every_known_prompt_matches_the_unchanged_source(self):
        # The console answers prompts by their opening words. A changed prompt in
        # setup.py, gateway.py or stack.py must fail here, not on a customer VM.
        source = "".join((ROOT / "src/follow_executor" / name).read_text()
                         for name in ("setup.py", "gateway.py", "stack.py", "notifications.py"))
        for opening, _group, _field in (*HOST_PROMPTS, *ACCOUNT_PROMPTS, *DISCORD_PROMPTS):
            if opening == "Type START ":
                continue  # built from the saved settings; covered by the start tests below
            self.assertIn(opening, source, opening)

    def test_answers_known_prompts_and_refuses_everything_else(self):
        answers = {"gateway": {"timezone": "Asia/Shanghai", "password": "pw"}, "docker_install": "y"}
        with scripted(HOST_PROMPTS, answers):
            self.assertEqual(input("Schedule timezone (IANA name) [America/New_York]: "), "Asia/Shanghai")
            import getpass
            self.assertEqual(getpass.getpass("IBKR password (hidden): "), "pw")
            self.assertEqual(input("Install Docker from its official Ubuntu repository using sudo? [y/N]: "), "y")
            with self.assertRaisesRegex(ConfigError, "cannot answer"):
                input("Delete everything? ")
            with self.assertRaises(NeedInput) as need:
                input("IBKR login username (hidden): ")
            self.assertEqual(need.exception.group, "gateway")
            with self.assertRaises(NeedInput) as need:
                input("Enable services after logout and reboot using sudo? [y/N]: ")
            self.assertEqual(need.exception.group, "linger")

    def test_a_rejected_answer_stops_instead_of_looping(self):
        with scripted(ACCOUNT_PROMPTS, {"sizing": "both"}):
            input("Sizing [balance]: ")
            with self.assertRaisesRegex(ConfigError, "not accepted"):
                input("Sizing [balance]: ")

    def test_optional_preview_questions_are_skipped(self):
        with scripted(ACCOUNT_PROMPTS, {}):
            self.assertEqual(input("Your current IBKR NetLiquidation in USD, for a size preview (Enter to skip): "), "")

    def test_prompts_are_restored_afterwards(self):
        import builtins
        import getpass
        before = builtins.input, getpass.getpass
        with contextlib.suppress(NeedInput), scripted(HOST_PROMPTS, {}):
            input("IBKR password: ")
        self.assertEqual((builtins.input, getpass.getpass), before)


class ConsoleSetupTests(unittest.TestCase):
    """The console's setup action drives the same Stack.setup() as the terminal."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.release = self.root / "release"
        self.release.mkdir()
        env = patch.dict(os.environ, HOME=str(self.root / "home"),
                         XDG_CONFIG_HOME=str(self.root / "config"),
                         XDG_STATE_HOME=str(self.root / "state"))
        env.start()
        self.addCleanup(env.stop)
        self.wizard = stack.Stack(self.release)
        (self.release / "RELEASE.json").write_text(json.dumps({
            "wheel_sha256": "abc",
            "executor_image": {"id": IMAGE, "platform": "linux/arm64", "wheel_sha256": "abc",
                               "archive": "images/executor.tar.gz", "archive_sha256": "abc"},
        }))
        self.calls = []

    def invoke(self, action, *options, stdin=None):
        self.calls.append((action, options, stdin))
        if action == "install":
            private_write(self.wizard.pin, IMAGE + "\n")
            private_write(self.wizard.unit_path, "test stopped unit")
        elif action == "configure":
            self.assertEqual(options, ("--answers-stdin",))
            with patch("sys.stdin", io.StringIO(stdin)):
                return cli.configure_from_console(self.wizard.config)
        return 0

    @contextlib.contextmanager
    def environment(self):
        output = io.StringIO()
        with (patch.object(stack, "host_check"), patch.object(stack, "docker_access"),
              patch.object(stack, "docker_group_configured", return_value=True),
              patch.object(stack, "lingering", return_value=True),
              patch.object(stack.shutil, "which", return_value="/usr/bin/docker"),
              patch.object(self.wizard, "require_idle"),
              patch.object(stack, "service_state", return_value="inactive"),
              patch.object(stack, "command", return_value=Mock(stdout="")),
              patch.object(self.wizard, "prepare_image"),
              patch.object(self.wizard, "invoke", side_effect=self.invoke),
              patch.object(gateway, "run_command",
                           return_value=subprocess.CompletedProcess([], 0, "inactive", "")),
              patch.object(gateway_docker, "require_engine"),
              patch.object(gateway_docker, "require_stopped"),
              patch.object(gateway_docker, "prepare"),
              patch("builtins.input", side_effect=AssertionError("terminal prompt reached")),
              patch("getpass.getpass", side_effect=AssertionError("terminal prompt reached")),
              contextlib.redirect_stdout(output)):
            yield output

    def run_console(self, action, answers):
        with self.environment() as output:
            code = self.wizard.console_run(action, answers)
        text = output.getvalue()
        events = [json.loads(line[len(stack.CONSOLE_MARK):]) for line in text.splitlines()
                  if line.startswith(stack.CONSOLE_MARK)]
        for secret in SECRETS:
            self.assertNotIn(secret, text)
        return code, events

    def test_console_walks_setup_one_screen_at_a_time_and_never_starts_trading(self):
        self.assertEqual(self.run_console("setup", {}), (10, [{"need": "account"}]))
        self.assertFalse(self.wizard.config.exists())

        code, events = self.run_console("setup", {"account": ACCOUNT})
        self.assertEqual((code, events), (10, [{"need": "gateway"}]))
        configure = next(call for call in self.calls if call[0] == "configure")
        self.assertNotIn("console-secret-token", " ".join(configure[1]))  # stdin only, never argv
        current = self.wizard.current_config()
        self.assertEqual((current.ibkr.account, current.size_label), ("DU1234567", "BALANCE 0.5"))
        self.assertEqual(current.token_path.read_text(), "console-secret-token\n")

        code, events = self.run_console("setup", {"gateway": GATEWAY})
        self.assertEqual((code, events), (10, [{"need": "gateway_ready"}]))
        escaped = "".join(f"\\u{ord(c):04x}" for c in "console-gw-user")
        self.assertIn(f"IbLoginId={escaped}\n", (self.wizard.gateway_dir / "ibc.ini").read_text())
        self.assertEqual((self.wizard.gateway_dir / "vnc.password").read_text(), "vncpass1\n")
        self.assertTrue(self.wizard.gateway_unit.exists())

        code, events = self.run_console("setup", {"gateway_ready": ""})
        self.assertEqual((code, events), (0, [{"step": "readiness"}]))
        self.assertEqual(self.calls[-1][:2], ("check", ("--quotes",)))
        self.assertNotIn("start", [call[0] for call in self.calls])

    def test_start_compares_the_typed_phrase_exactly(self):
        self.run_console("setup", {"account": ACCOUNT})
        self.run_console("setup", {"gateway": GATEWAY})
        code, _ = self.run_console("start", {"start_confirmation": "START PAPER BALANCE 0.50"})
        self.assertEqual(code, 3)
        self.assertNotIn("start", [call[0] for call in self.calls])
        code, _ = self.run_console("start", {"start_confirmation": "START PAPER BALANCE 0.5"})
        self.assertEqual(code, 0)
        self.assertEqual(self.calls[-1][0], "start")

    def test_incomplete_gateway_answers_save_nothing(self):
        self.run_console("setup", {"account": ACCOUNT})
        partial = {key: value for key, value in GATEWAY.items() if key != "password"}
        self.assertEqual(self.run_console("setup", {"gateway": partial}), (10, [{"need": "gateway"}]))
        self.assertFalse((self.wizard.gateway_dir / "gateway.json").exists())
        self.assertFalse((self.wizard.gateway_dir / "ibc.ini").exists())

    def test_bad_recovery_password_is_refused_once_without_looping(self):
        self.run_console("setup", {"account": ACCOUNT})
        with self.assertRaisesRegex(ConfigError, "recovery passwords"):
            self.run_console("setup", {"gateway": {**GATEWAY, "vnc_password": "short"}})
        self.assertFalse((self.wizard.gateway_dir / "gateway.json").exists())

    def test_live_account_needs_the_typed_confirmation(self):
        live = {**ACCOUNT, "mode": "live", "account": "U1234567"}
        with self.assertRaises(ConfigError):
            self.run_console("setup", {"account": live})
        self.assertFalse(self.wizard.config.exists())
        code, _ = self.run_console("setup", {"account": {**live, "live_confirmation": "LIVE U1234567"}})
        self.assertEqual(code, 10)
        self.assertEqual(self.wizard.current_config().ibkr.port, 4001)

    def test_docker_consent_is_asked_before_sudo_and_reboot_is_reported(self):
        with (self.environment(), patch.object(stack.shutil, "which", return_value=None)):
            self.assertEqual(self.wizard.console_run("setup", {}), 10)
        with (self.environment() as output, patch.object(stack.shutil, "which", return_value=None)):
            self.assertEqual(self.wizard.console_run("setup", {"docker_install": "y"}), 3)
        self.assertIn(stack.CONSOLE_MARK + '{"reboot": true}', output.getvalue())

    def test_facts_never_raise(self):
        with (patch.object(stack, "host_check", side_effect=ConfigError("not Ubuntu")),
              patch.object(stack.shutil, "which", return_value=None),
              patch.object(stack, "lingering", side_effect=OSError),
              patch.object(stack, "service_state", side_effect=OSError)):
            facts = self.wizard.facts()
        self.assertEqual(facts["host_problem"], "not Ubuntu")
        self.assertFalse(facts["docker_installed"])
        self.assertEqual(facts["executor_service"], "unknown")
        self.assertFalse(facts["config_saved"])


class DashboardCommandTests(unittest.TestCase):
    """Phase 2 dashboard actions reuse the executor CLI; the console only validates input."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        env = patch.dict(os.environ, XDG_STATE_HOME=str(self.root / "state"))
        env.start()
        self.addCleanup(env.stop)
        self.config = self.root / "config/executor.json"
        with (patch("sys.stdin", io.StringIO(json.dumps(ACCOUNT))),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(cli.configure_from_console(self.config), 0)

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main([*args, "--config", str(self.config)])
        return code, output.getvalue()

    def test_command_arguments_are_validated(self):
        self.assertEqual(command_args("settings", {"sizing": "balance", "fraction": "0.25", "nq_price": "21543.25"}),
                         ["settings", "--leverage-fraction", "0.25", "--preview-nq-price", "21543.25"])
        self.assertEqual(command_args("settings", {"sizing": "NQ", "quantity": "2"}),
                         ["settings", "--root", "NQ", "--quantity", "2"])
        self.assertEqual(command_args("discord-link", {"agree": "LINK"}), ["discord", "link", "--agree", "LINK"])
        self.assertEqual(command_args("resume", {"confirm": "RESUME"}), ["resume"])
        for name, body in (("settings", {"sizing": "balance", "fraction": "1.5"}),
                           ("settings", {"sizing": "balance", "fraction": "0.5; rm -rf /"}),
                           ("settings", {"sizing": "MNQ", "quantity": "0"}),
                           ("settings", {"sizing": "ES", "quantity": "1"}),
                           ("discord-link", {"agree": "yes"}),
                           ("resume", {}),
                           ("gateway-stop", {})):
            with self.assertRaises(ConfigError, msg=(name, body)):
                command_args(name, body)

    def test_sizing_change_shows_the_existing_preview_without_prompting(self):
        with (patch("follow_executor.setup.require_flat", return_value=100000.0),
              patch("builtins.input", side_effect=AssertionError("prompted"))):
            code, output = self.run_cli("settings", "--leverage-fraction", "0.25", "--preview-nq-price", "20000")
        self.assertEqual(code, 0, output)
        self.assertIn("Size preview at NetLiquidation $100,000 and NQ 20,000.00", output)
        self.assertEqual(json.loads(self.config.read_text())["sizing"]["leverage_fraction"], 0.25)

    def test_sizing_change_still_refuses_when_not_flat(self):
        with patch("follow_executor.setup.require_flat", side_effect=ConfigError("MNQ has positions")):
            code, output = self.run_cli("settings", "--leverage-fraction", "0.25", "--preview-nq-price", "20000")
        self.assertEqual(code, 2)
        self.assertIn("MNQ has positions", output)
        self.assertEqual(json.loads(self.config.read_text())["sizing"]["leverage_fraction"], 0.5)

    def test_discord_link_takes_the_typed_agreement(self):
        with patch("follow_executor.notifications.request", return_value={"code": "PAIR42"}) as request:
            code, output = self.run_cli("discord", "link", "--agree", "LINK")
        self.assertEqual(code, 0, output)
        self.assertIn("/link code:PAIR42", output)
        request.assert_called_once()
        with patch("follow_executor.notifications.request") as request:
            code, output = self.run_cli("discord", "link", "--agree", "OK")
        self.assertEqual(code, 2)
        request.assert_not_called()


FAKE_STACK = r"""
import json, sys, time
args = sys.argv[1:]
data = sys.stdin.read()
print("args " + json.dumps(args), flush=True)
if args[:1] == ["console-run"]:
    answers = json.loads(data or "{}")
    print("keys " + json.dumps(sorted(answers)), flush=True)
    print("@@follow-console " + json.dumps({"need": "gateway"}), flush=True)
    print("@@follow-console not-json", flush=True)
    sys.exit(10)
if args == ["check"]:
    print("{")
    print('  "problems": []')
    print("}")
    sys.exit(0)
if args == ["status"]:
    time.sleep(2)
"""


class ConsoleServerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        script = Path(directory.name) / "fake-stack.py"
        script.write_text(FAKE_STACK)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        fake_stack = SimpleNamespace(release=Path(directory.name))
        self.console = Console(fake_stack, self.port, launcher=[sys.executable, "-I", str(script)],
                               facts=lambda: {"config_saved": True})
        self.server = make_server(self.console)
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.cookie = ""
        self.csrf = ""

    def request(self, method, path, body=None, *, origin=True, host=None, csrf=True, cookie=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if method == "POST" and origin:
            headers["Origin"] = origin if isinstance(origin, str) else f"http://127.0.0.1:{self.port}"
        if csrf and self.csrf:
            headers["X-Console-CSRF"] = self.csrf
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        connection.request(method, path, None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            payload = data.decode()
        return response, payload

    def login(self):
        response, payload = self.request("POST", "/api/session", {"token": self.console.token})
        self.assertEqual(response.status, 200, payload)
        self.cookie = response.getheader("Set-Cookie").split(";")[0]
        self.csrf = payload["csrf"]
        return response

    def wait(self, job):
        for _ in range(100):
            _, view = self.request("GET", f"/api/jobs/{job}")
            if view["done"]:
                return view
            time.sleep(0.05)
        self.fail("job did not finish")

    def test_page_is_served_with_strict_headers(self):
        response, page = self.request("GET", "/")
        self.assertEqual(response.status, 200)
        self.assertIn("script-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
        self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
        self.assertIn('<script src="/app.js">', page)
        self.assertNotIn("http", page.replace("http-equiv", ""))  # nothing loaded from elsewhere

    def test_foreign_host_names_are_refused(self):
        response, _ = self.request("GET", "/", host=f"attacker.example:{self.port}")
        self.assertEqual(response.status, 421)

    def test_token_is_single_use_and_needs_the_console_origin(self):
        token = self.console.token
        response, _ = self.request("POST", "/api/session", {"token": token}, origin="http://attacker.example")
        self.assertEqual(response.status, 403)
        response, _ = self.request("POST", "/api/session", {"token": "wrong"})
        self.assertEqual(response.status, 401)
        response = self.login()
        cookie = response.getheader("Set-Cookie")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        response, _ = self.request("POST", "/api/session", {"token": token}, cookie=False)
        self.assertEqual(response.status, 401)
        response, state = self.request("GET", "/api/state")
        self.assertEqual(response.status, 200)
        self.assertEqual(state["facts"], {"config_saved": True})

    def test_api_needs_session_and_csrf(self):
        response, _ = self.request("GET", "/api/state")
        self.assertEqual(response.status, 401)
        self.login()
        response, _ = self.request("POST", "/api/command", {"name": "check"}, csrf=False)
        self.assertEqual(response.status, 403)
        response, _ = self.request("POST", "/api/command", {"name": "check"}, origin=False)
        self.assertEqual(response.status, 403)
        response, _ = self.request("POST", "/api/command", {"name": "rm -rf"})
        self.assertEqual(response.status, 409)
        response, refused = self.request("POST", "/api/command", {"name": "resume"})
        self.assertEqual(response.status, 409)
        self.assertIn("RESUME", refused["error"])

    def test_setup_answers_travel_on_stdin_and_events_are_parsed(self):
        self.login()
        response, started = self.request("POST", "/api/run", {
            "action": "setup", "answers": {"account": {"token": "server-secret-token"}}})
        self.assertEqual(response.status, 200, started)
        view = self.wait(started["job"])
        self.assertEqual(view["exit"], 10)
        self.assertEqual(view["events"], [{"need": "gateway"}])
        self.assertIn('args ["console-run", "setup"]', view["lines"])
        self.assertIn('keys ["account"]', view["lines"])
        self.assertIn("@@follow-console not-json", view["lines"])
        self.assertFalse(any("server-secret-token" in line for line in view["lines"]))

    def test_check_report_records_readiness(self):
        self.login()
        _, started = self.request("POST", "/api/command", {"name": "check"})
        view = self.wait(started["job"])
        self.assertEqual(view["report"], {"problems": []})
        _, state = self.request("GET", "/api/state")
        self.assertTrue(state["readiness"]["passed"])
        _, started = self.request("POST", "/api/command", {"name": "settings", "sizing": "MNQ", "quantity": "2"})
        self.assertEqual(self.wait(started["job"])["exit"], 0)
        _, state = self.request("GET", "/api/state")
        self.assertIsNone(state["readiness"])

    def test_one_action_at_a_time(self):
        self.login()
        _, started = self.request("POST", "/api/command", {"name": "status"})
        response, refused = self.request("POST", "/api/command", {"name": "check"})
        self.assertEqual(response.status, 409)
        self.assertIn("still running", refused["error"])
        self.wait(started["job"])

    def test_json_report_reads_the_printed_object(self):
        self.assertEqual(json_report(["noise", "{", '  "a": 1', "}", "trailing note"]), {"a": 1})
        self.assertIsNone(json_report(["{", "broken"]))

    def test_reconnect_command_keeps_a_non_default_port(self):
        self.assertEqual(
            reconnect_command("/kit/follow-stack", "ubuntu", 8765),
            "ssh -i YOUR_KEY -t -L 8765:127.0.0.1:8765 -L 5901:127.0.0.1:5901 ubuntu@YOUR_VM "
            "'/kit/follow-stack console'")
        self.assertEqual(
            reconnect_command("/kit/follow-stack", "ubuntu", 8766),
            "ssh -i YOUR_KEY -t -L 8766:127.0.0.1:8766 -L 5901:127.0.0.1:5901 ubuntu@YOUR_VM "
            "'/kit/follow-stack console --port 8766'")


if __name__ == "__main__":
    unittest.main()
