# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""The relay's Server-Sent Events feed: verified targets and heartbeats."""

from __future__ import annotations

import http.client
import json
import logging
import socket
import ssl
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from urllib.parse import urlparse

from follow_executor.crypto import Verifier

from .signal import Heartbeat, SignalError, Target, parse_heartbeat, parse_target

LOGGER = logging.getLogger(__name__)
MAX_BACKOFF_SECONDS = 30.0
REFUSED_BACKOFF_SECONDS = 60.0


@dataclass(frozen=True)
class SseEvent:
    kind: str
    event_id: str | None
    data: str


def parse_sse(lines: Iterable[str]) -> Iterator[SseEvent]:
    """Dispatch events per the SSE specification (fields id, event, data)."""

    kind, event_id, data = "message", None, []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data:
                yield SseEvent(kind, event_id, "\n".join(data))
            kind, event_id, data = "message", None, []
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if name == "event":
            kind = value
        elif name == "data":
            data.append(value)
        elif name == "id":
            event_id = value


class FeedRefused(RuntimeError):
    """The relay refused this follower's token."""


class SignalFeed:
    def __init__(
        self,
        *,
        relay_url: str,
        stream: str,
        token: str,
        verifier: Verifier,
        after: Callable[[], int | None],
        on_signal: Callable[[Target], None],
        on_heartbeat: Callable[[Heartbeat], None],
        ca_file: str | None = None,
        read_timeout: float = 45.0,
    ) -> None:
        parsed = urlparse(relay_url)
        self._https = parsed.scheme == "https"
        self._host = parsed.hostname or ""
        self._port = parsed.port or (443 if self._https else 80)
        self._path = f"{parsed.path.rstrip('/')}/v1/streams/{stream}/events"
        self._stream = stream
        self._token = token
        self._verifier = verifier
        self._after = after
        self._on_signal = on_signal
        self._on_heartbeat = on_heartbeat
        self._context = ssl.create_default_context(cafile=ca_file) if self._https else None
        self._read_timeout = read_timeout
        self._socket: socket.socket | None = None
        self._lock = threading.Lock()
        self.connected = threading.Event()
        self.rejected_envelopes = 0
        self._failing = False

    def run(self, stop: threading.Event) -> None:
        backoff = 1.0
        while not stop.is_set():
            try:
                self._session(stop)
                backoff = 1.0
            except FeedRefused as exc:
                LOGGER.error("relay refused the follower token: %s", exc)
                stop.wait(REFUSED_BACKOFF_SECONDS)
                continue
            except Exception as exc:  # noqa: BLE001 - reconnect on any feed failure
                if not self._failing and not stop.is_set():
                    LOGGER.warning("feed disconnected: %s: %s", type(exc).__name__, exc)
                self._failing = True
            finally:
                self.connected.clear()
            if stop.is_set():
                break
            stop.wait(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    def reconnect(self) -> None:
        """Drop the current connection; ``run`` reconnects after the last seq."""

        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def _session(self, stop: threading.Event) -> None:
        connection: http.client.HTTPConnection
        if self._https:
            connection = http.client.HTTPSConnection(
                self._host, self._port, timeout=self._read_timeout, context=self._context
            )
        else:
            connection = http.client.HTTPConnection(self._host, self._port, timeout=self._read_timeout)
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        after = self._after()
        if after:
            headers["Last-Event-ID"] = str(after)
        try:
            connection.request("GET", self._path, headers=headers)
            response = connection.getresponse()
            if response.status in (401, 403):
                raise FeedRefused(f"HTTP {response.status} {response.read(200).decode(errors='replace')}")
            if response.status != 200:
                raise ConnectionError(f"relay answered HTTP {response.status}")
            with self._lock:
                self._socket = connection.sock
            self.connected.set()
            self._failing = False
            LOGGER.info("feed connected after seq %s", after or "none (latest only)")
            lines = (raw.decode("utf-8") for raw in iter(response.readline, b""))
            for event in parse_sse(lines):
                if stop.is_set():
                    break
                self._dispatch(event)
            raise ConnectionError("relay closed the stream")
        finally:
            with self._lock:
                self._socket = None
            connection.close()

    def _dispatch(self, event: SseEvent) -> None:
        if event.kind not in ("signal", "heartbeat"):
            return
        try:
            envelope = json.loads(event.data)
            payload = self._verifier.verify(envelope)
            if event.kind == "heartbeat":
                self._on_heartbeat(parse_heartbeat(payload, self._stream))
                return
            target = parse_target(envelope["payload"], self._stream)
            if event.event_id is not None and event.event_id != str(target.seq):
                raise SignalError(f"event id {event.event_id} does not match seq {target.seq}")
        except (ValueError, KeyError, TypeError) as exc:
            self.rejected_envelopes += 1
            LOGGER.error("rejected a %s envelope: %s", event.kind, exc)
            return
        self._on_signal(target)
