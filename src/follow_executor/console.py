# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Private setup console: a loopback-only browser front end for follow-stack.

The console runs in the foreground of the customer's SSH session and listens
only on 127.0.0.1. The customer reaches it through the same SSH connection
(``ssh -L``), so it adds no inbound port. Every action runs the existing
``follow-stack`` code in a child process; the console never re-implements a
check, a confirmation or a file write.

Request rules: a one-time token from the terminal is exchanged for an HttpOnly,
SameSite=Strict cookie; every request must name the loopback Host; every POST
must carry a matching Origin and the session's CSRF token. Answers containing
secrets go to the child's stdin and are never logged or kept.
"""

from __future__ import annotations

import hmac
import http.server
import json
import os
import pwd
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit

from . import console_page
from .config import ConfigError

IDLE_SECONDS = 30 * 60
MAX_BODY = 64 * 1024
MAX_LINES = 4000
COOKIE = "follow_console"
CONSOLE_MARK = "@@follow-console "
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SETUP_ACTIONS = ("setup", "start", "reboot")
# Read-only or service commands the dashboard may run; no prompts, no secrets.
COMMANDS: dict[str, tuple[str, ...]] = {
    "check": ("check",),
    "status": ("status",),
    "service-status": ("service-status",),
    "stop": ("stop",),
    "doctor": ("doctor",),
    "gateway-status": ("gateway", "status"),
    "gateway-start": ("gateway", "start"),
}
NUMBER = re.compile(r"\d{1,6}(\.\d{1,6})?|\.\d{1,6}")
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self'; "
                                "connect-src 'self'; img-src 'self'; base-uri 'none'; "
                                "form-action 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class Job:
    """One child process whose output the page polls."""

    def __init__(self, job_id: str, label: str, args: list[str], stdin: bytes | None,
                 *, detached: bool = False):
        self.id = job_id
        self.label = label
        self.lines: list[str] = []
        self.events: list[dict] = []
        self.exit: int | None = None
        self.started = time.time()
        self.process = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=detached, env=child_environment(),
        )
        self.detached = detached
        if self.process.stdin is not None:
            try:
                if stdin:
                    self.process.stdin.write(stdin)
            except BrokenPipeError:
                pass
            finally:
                self.process.stdin.close()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            line = ANSI.sub("", raw.decode("utf-8", "replace").rstrip("\r\n"))
            if line.startswith(CONSOLE_MARK):
                try:
                    event = json.loads(line[len(CONSOLE_MARK):])
                except json.JSONDecodeError:
                    event = None
                if isinstance(event, dict):
                    self.events.append(event)
                    continue
            self.lines.append(line)
            if len(self.lines) > MAX_LINES:
                del self.lines[: len(self.lines) - MAX_LINES]
        self.process.stdout.close()
        self.exit = self.process.wait()

    @property
    def done(self) -> bool:
        return self.exit is not None

    def cancel(self) -> None:
        if self.done:
            return
        try:
            if self.detached:
                os.killpg(self.process.pid, signal.SIGTERM)
            else:
                self.process.terminate()
        except ProcessLookupError:
            pass

    def view(self, after: int = 0) -> dict:
        after = max(0, min(after, len(self.lines)))
        return {"id": self.id, "label": self.label, "lines": self.lines[after:], "next": len(self.lines),
                "events": list(self.events), "done": self.done, "exit": self.exit,
                "report": json_report(self.lines) if self.done else None}


def command_args(name: str, body: dict) -> list[str]:
    """The follow-stack arguments for a dashboard command; values are validated here
    for a clear message and again by the executor's own checks."""
    if name in COMMANDS:
        return list(COMMANDS[name])
    if name == "settings":
        sizing = body.get("sizing")
        if sizing == "balance":
            fraction = str(body.get("fraction", "")).strip()
            if not NUMBER.fullmatch(fraction) or not 0 < float(fraction) <= 1:
                raise ConfigError("Enter a leverage fraction above 0 and at most 1.")
            args = ["settings", "--leverage-fraction", fraction]
            price = str(body.get("nq_price") or "").strip()
            if price:
                if not NUMBER.fullmatch(price) or float(price) <= 0:
                    raise ConfigError("Enter the approximate NQ price as a positive number, or leave it empty.")
                args += ["--preview-nq-price", price]
            return args
        if sizing in ("MNQ", "NQ"):
            quantity = str(body.get("quantity", "")).strip()
            if not re.fullmatch(r"[1-9]\d{0,2}", quantity):
                raise ConfigError("Enter a whole number of contracts.")
            return ["settings", "--root", sizing, "--quantity", quantity]
        raise ConfigError("Choose balance sizing or a fixed MNQ or NQ size.")
    if name == "discord-link":
        if body.get("agree") != "LINK":
            raise ConfigError("Type LINK to agree to the Discord data sharing.")
        return ["discord", "link", "--agree", "LINK"]
    if name in ("discord-status", "discord-enable", "discord-unlink"):
        return ["discord", name.removeprefix("discord-")]
    if name == "resume":
        if body.get("confirm") != "RESUME":
            raise ConfigError("Type RESUME to request halt recovery.")
        return ["resume"]
    raise ConfigError("Unknown command.")


def child_environment() -> dict:
    env = dict(os.environ)
    # The console's terminal is not the child's: never let a child wait on it.
    env.pop("SSH_ASKPASS", None)
    return env


def json_report(lines: list[str]) -> object:
    """The JSON object a command printed (check, status), if any."""
    start = next((i for i, line in enumerate(lines) if line == "{"), None)
    if start is None:
        return None
    end = next((i for i in range(len(lines) - 1, start, -1) if lines[i] == "}"), None)
    if end is None:
        return None
    try:
        return json.loads("\n".join(lines[start:end + 1]))
    except json.JSONDecodeError:
        return None


class Console:
    def __init__(self, stack, port: int, *, launcher: list[str] | None = None,
                 facts: Callable[[], dict] | None = None):
        if not 1024 <= port <= 65535:
            raise ConfigError("Choose a console port from 1024 to 65535.")
        self.stack = stack
        self.port = port
        self.token: str | None = secrets.token_urlsafe(32)
        self.session: str | None = None
        self.csrf: str | None = None
        self.lock = threading.Lock()
        self.job: Job | None = None
        self.logs: Job | None = None
        self.jobs: dict[str, Job] = {}
        self.last_seen = time.monotonic()
        self.readiness: dict | None = None
        self.launcher = launcher or [sys.executable, "-I", "-S", "-u",
                                     str(stack.release / "scripts/stack-bootstrap.py")]
        self.facts = facts or stack.facts
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {f"http://{host}" for host in self.hosts}

    # Session ---------------------------------------------------------------
    def open_session(self, token: object) -> tuple[str, str] | None:
        with self.lock:
            if (self.token is None or not isinstance(token, str)
                    or not hmac.compare_digest(token.encode(), self.token.encode())):
                return None
            self.token = None  # one use only
            self.session = secrets.token_urlsafe(32)
            self.csrf = secrets.token_urlsafe(32)
            return self.session, self.csrf

    def authenticated(self, cookie_header: str | None) -> bool:
        if self.session is None or not cookie_header:
            return False
        for part in cookie_header.split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and hmac.compare_digest(value.encode(), self.session.encode()):
                return True
        return False

    # Jobs ------------------------------------------------------------------
    def start_job(self, label: str, args: list[str], stdin: bytes | None = None) -> Job:
        with self.lock:
            if self.job is not None and not self.job.done:
                raise ConfigError(f"'{self.job.label}' is still running. Wait for it to finish.")
            job = Job(secrets.token_hex(8), label, [*self.launcher, *args], stdin)
            self.job = job
            self.jobs[job.id] = job
            if len(self.jobs) > 50:
                for old in list(self.jobs)[:-50]:
                    if self.jobs[old].done:
                        del self.jobs[old]
            return job

    def run_action(self, action: str, answers: object) -> Job:
        if action not in SETUP_ACTIONS:
            raise ConfigError("Unknown setup action.")
        if not isinstance(answers, dict):
            raise ConfigError("Answers must be an object.")
        data = json.dumps(answers).encode()
        if len(data) > MAX_BODY:
            raise ConfigError("Answers are too large.")
        return self.start_job(action, ["console-run", action], data)

    def run_command(self, name: str, body: dict | None = None) -> Job:
        return self.start_job(name, command_args(name, body or {}))

    def start_logs(self, which: str) -> Job:
        args = {"executor": ["logs"], "gateway": ["gateway", "logs"]}.get(which)
        if args is None:
            raise ConfigError("Unknown log.")
        with self.lock:
            if self.logs is not None:
                self.logs.cancel()
            job = Job(secrets.token_hex(8), f"{which} logs", [*self.launcher, *args], None, detached=True)
            self.logs = job
            self.jobs[job.id] = job
            return job

    def state(self) -> dict:
        job = self.job
        if job is not None and job.done and job.label == "check":
            report = json_report(job.lines)
            if isinstance(report, dict):
                self.readiness = {"passed": job.exit == 0, "at": job.started}
        if (job is not None and job.done and job.label == "setup"
                and any(event.get("step") == "readiness" for event in job.events)):
            self.readiness = {"passed": job.exit == 0, "at": job.started}
        if job is not None and job.done and job.exit == 0 and job.label in ("settings", "discord-enable"):
            self.readiness = None  # saved settings changed; check again before starting
        return {"facts": self.facts(), "readiness": self.readiness,
                "job": None if job is None else {"id": job.id, "label": job.label, "done": job.done},
                "release": self.stack.release.name}

    def shutdown(self) -> None:
        for job in (self.logs,):
            if job is not None:
                job.cancel()


class Handler(http.server.BaseHTTPRequestHandler):
    console: Console
    server_version = "follow-console"
    sys_version = ""

    def log_message(self, format: str, *args) -> None:
        pass  # Keep the SSH window quiet; never log requests.

    # Responses ---------------------------------------------------------------
    def send(self, status: int, body: bytes, content_type: str, headers: dict | None = None) -> None:
        self.send_response(status)
        for name, value in {**SECURITY_HEADERS, **(headers or {})}.items():
            self.send_header(name, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, value: object, status: int = HTTPStatus.OK, headers: dict | None = None) -> None:
        self.send(status, json.dumps(value).encode(), "application/json; charset=utf-8", headers)

    def fail(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status)

    # Checks ------------------------------------------------------------------
    def host_allowed(self) -> bool:
        return self.headers.get("Host", "") in self.console.hosts

    def origin_allowed(self) -> bool:
        return self.headers.get("Origin", "") in self.console.origins

    def csrf_allowed(self) -> bool:
        token = self.headers.get("X-Console-CSRF", "")
        csrf = self.console.csrf
        return bool(csrf) and hmac.compare_digest(token.encode(), csrf.encode())

    def read_json(self) -> object:
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ConfigError("Send JSON.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ConfigError("Invalid request length.") from None
        if not 0 <= length <= MAX_BODY:
            raise ConfigError("Request is too large.")
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise ConfigError("Invalid JSON.") from None

    # Routes ------------------------------------------------------------------
    def do_GET(self) -> None:
        if not self.host_allowed():
            return self.fail(HTTPStatus.MISDIRECTED_REQUEST, "Open the console at 127.0.0.1.")
        self.console.last_seen = time.monotonic()
        url = urlsplit(self.path)
        assets = {"/": ("text/html; charset=utf-8", console_page.HTML),
                  "/app.css": ("text/css; charset=utf-8", console_page.CSS),
                  "/app.js": ("text/javascript; charset=utf-8", console_page.JS)}
        if url.path in assets:
            content_type, text = assets[url.path]
            return self.send(HTTPStatus.OK, text.encode(), content_type)
        if not url.path.startswith("/api/"):
            return self.fail(HTTPStatus.NOT_FOUND, "Not found.")
        if not self.console.authenticated(self.headers.get("Cookie")):
            return self.fail(HTTPStatus.UNAUTHORIZED, "session")
        if url.path == "/api/session":
            return self.send_json({"csrf": self.console.csrf})
        if url.path == "/api/state":
            return self.send_json(self.console.state())
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{16})", url.path)
        if match:
            job = self.console.jobs.get(match[1])
            if job is None:
                return self.fail(HTTPStatus.NOT_FOUND, "Unknown job.")
            after = parse_qs(url.query).get("after", ["0"])[0]
            return self.send_json(job.view(int(after) if after.isdecimal() else 0))
        return self.fail(HTTPStatus.NOT_FOUND, "Not found.")

    def do_POST(self) -> None:
        if not self.host_allowed():
            return self.fail(HTTPStatus.MISDIRECTED_REQUEST, "Open the console at 127.0.0.1.")
        if not self.origin_allowed():
            return self.fail(HTTPStatus.FORBIDDEN, "Cross-origin request refused.")
        self.console.last_seen = time.monotonic()
        url = urlsplit(self.path)
        try:
            body = self.read_json()
            if url.path == "/api/session":
                opened = self.console.open_session(body.get("token") if isinstance(body, dict) else None)
                if opened is None:
                    return self.fail(HTTPStatus.UNAUTHORIZED, "token")
                session, csrf = opened
                return self.send_json({"csrf": csrf}, headers={
                    "Set-Cookie": f"{COOKIE}={session}; HttpOnly; SameSite=Strict; Path=/"})
            if not self.console.authenticated(self.headers.get("Cookie")):
                return self.fail(HTTPStatus.UNAUTHORIZED, "session")
            if not self.csrf_allowed():
                return self.fail(HTTPStatus.FORBIDDEN, "Missing or invalid CSRF token.")
            if not isinstance(body, dict):
                raise ConfigError("Send a JSON object.")
            if url.path == "/api/run":
                job = self.console.run_action(str(body.get("action", "")), body.get("answers", {}))
            elif url.path == "/api/command":
                job = self.console.run_command(str(body.get("name", "")), body)
            elif url.path == "/api/logs":
                job = self.console.start_logs(str(body.get("which", "executor")))
            elif (match := re.fullmatch(r"/api/jobs/([0-9a-f]{16})/cancel", url.path)):
                job = self.console.jobs.get(match[1])
                if job is None or job is not self.console.logs:
                    raise ConfigError("Only a log view can be closed.")
                job.cancel()
            else:
                return self.fail(HTTPStatus.NOT_FOUND, "Not found.")
            return self.send_json({"job": job.id})
        except ConfigError as exc:
            return self.fail(HTTPStatus.CONFLICT, str(exc))


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # On Linux this only skips TIME_WAIT; a second listener on the port is still refused.
    allow_reuse_address = True


def make_server(console: Console) -> Server:
    handler = type("ConsoleHandler", (Handler,), {"console": console})
    try:
        return Server(("127.0.0.1", console.port), handler)
    except OSError as exc:
        raise ConfigError(f"Port {console.port} on 127.0.0.1 is in use. Close the other console, "
                          "or start this one with --port and forward that port instead.") from exc


def reconnect_command(launcher, user: str, port: int) -> str:
    remote = f"{launcher} console" + ("" if port == 8765 else f" --port {port}")
    return f"ssh -i YOUR_KEY -t -L {port}:127.0.0.1:{port} -L 5901:127.0.0.1:5901 {user}@YOUR_VM '{remote}'"


def serve(stack, *, port: int = 8765) -> int:
    console = Console(stack, port)
    server = make_server(console)
    user = pwd.getpwuid(os.getuid()).pw_name
    launcher = stack.release / "follow-stack"
    print("Auto Quant setup console is running on this VM at 127.0.0.1 only.", flush=True)
    print("Keep this window open; closing it stops the console. Setup never starts trading by itself.")
    print()
    print("Open this private link in the browser on your computer (use it once; do not share it):")
    print(f"  http://127.0.0.1:{port}/#token={console.token}")
    print()
    print("If the page does not load, you connected without port forwarding. Close this window and reconnect:")
    print(f"  {reconnect_command(launcher, user, port)}")
    print("Type passwords and tokens only into the console page, never into chat.", flush=True)

    def stop(*_args) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    def idle_watch() -> None:
        while True:
            time.sleep(30)
            busy = console.job is not None and not console.job.done
            if not busy and time.monotonic() - console.last_seen > IDLE_SECONDS:
                print("Closing the console after 30 idle minutes. Run it again to continue.", flush=True)
                stop()
                return

    for signum in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(signum, stop)
    threading.Thread(target=idle_watch, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        console.shutdown()
        server.server_close()
    print("Setup console closed. Services keep their current state.")
    return 0
