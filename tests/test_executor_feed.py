# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from aiohttp import web
from executor_support import STREAM, FakeBroker, Leader, payload, write_config

from follow_executor.crypto import Verifier
from follow_executor.executor import Executor
from follow_executor.feed import SignalFeed, SseEvent, parse_sse
from follow_executor.journal import Journal


class ParserTests(unittest.TestCase):
    def test_sse_fields_comments_multiline_data_and_crlf(self) -> None:
        lines = ["retry: 3000\r\n", "\r\n", ": keepalive\n", "\n", "id: 7\n", "event: signal\n",
                 "data: {\"a\":\n", "data: 1}\n", "\n", "event: heartbeat\n", "data:x\n", "\n"]
        self.assertEqual(list(parse_sse(lines)), [SseEvent("signal", "7", "{\"a\":\n1}"),
                                                  SseEvent("heartbeat", None, "x")])


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.leader = Leader()
        self.signals: list = []
        self.heartbeats: list = []
        self.feed = SignalFeed(relay_url="http://127.0.0.1:1", stream=STREAM, token="t",
                               verifier=Verifier(self.leader.public_key), after=lambda: None,
                               on_signal=self.signals.append, on_heartbeat=self.heartbeats.append)

    def frame(self, envelope: dict, kind: str = "signal", event_id: str | None = "1") -> SseEvent:
        return SseEvent(kind, event_id, json.dumps(envelope))

    def test_only_verified_contract_valid_signals_are_delivered(self) -> None:
        good = self.leader.envelope(payload(1, "entry"))
        self.feed._dispatch(self.frame(good))
        self.assertEqual([t.seq for t in self.signals], [1])
        tampered = dict(good, payload=good["payload"].replace("drift", "level"))
        other_key = Leader().envelope(payload(1, "entry"))
        wrong_stream = self.leader.envelope(payload(1, "entry").replace(STREAM, "other.stream"))
        for bad, event_id in ((tampered, "1"), (other_key, "1"), (wrong_stream, "1"), (good, "2")):
            self.feed._dispatch(self.frame(bad, event_id=event_id))
        self.assertEqual(len(self.signals), 1)
        self.assertEqual(self.feed.rejected_envelopes, 4)
        self.feed._dispatch(self.frame(self.leader.heartbeat(1), "heartbeat", None))
        self.assertEqual(self.heartbeats[0].latest_seq, 1)


class RelayHarness:
    """Test-only HTTP fixture implementing the public follower wire contract."""

    def __init__(self, leader: Leader, directory: Path) -> None:
        self.leader = leader
        self.follower_token = "test-follower-token"
        self.publisher_token = "test-publisher-token"
        self.events: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.follower_port = asyncio.run_coroutine_threadsafe(self._start(), self.loop).result(10)
        self.publisher_port = self.follower_port

    async def _start(self) -> int:
        app = web.Application()
        app.router.add_get("/v1/streams/{stream}/state", self._state)
        app.router.add_get("/v1/streams/{stream}/events", self._events)
        app.router.add_post("/v1/streams/{stream}/{kind}", self._publish)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        return site._server.sockets[0].getsockname()[1]

    def _authorize(self, request) -> None:
        if request.headers.get("Authorization") != f"Bearer {self.follower_token}":
            raise web.HTTPUnauthorized()

    async def _state(self, request):
        self._authorize(request)
        if not self.events:
            raise web.HTTPNotFound()
        return web.json_response(self.events[-1])

    @staticmethod
    def _frame(kind, envelope):
        event_id = ""
        if kind == "signal":
            event_id = f"id: {json.loads(envelope['payload'])['seq']}\n"
        return f"{event_id}event: {kind}\ndata: {json.dumps(envelope)}\n\n".encode()

    async def _events(self, request):
        self._authorize(request)
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        try:
            after = request.headers.get("Last-Event-ID")
            replay = self.events[-1:] if after is None else [
                e for e in self.events if json.loads(e["payload"])["seq"] > int(after)]
            for envelope in replay:
                await response.write(self._frame("signal", envelope))
            while True:
                try:
                    frame = await asyncio.wait_for(queue.get(), 0.1)
                except TimeoutError:
                    frame = b": keepalive\n\n"
                if frame is None:
                    break
                await response.write(frame)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.subscribers.discard(queue)
        return response

    async def _publish(self, request):
        if request.headers.get("Authorization") != f"Bearer {self.publisher_token}":
            raise web.HTTPUnauthorized()
        body = await request.json()
        kind = "signal" if request.match_info["kind"] == "events" else "heartbeat"
        envelopes = body["envelopes"] if kind == "signal" else [body["envelope"]]
        for envelope in envelopes:
            Verifier(self.leader.public_key).verify(envelope)
            if kind == "signal":
                self.events.append(envelope)
            for queue in self.subscribers:
                queue.put_nowait(self._frame(kind, envelope))
        return web.json_response({"stored_through": len(self.events)})

    def post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.publisher_port}/v1/streams/{STREAM}/{path}",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.publisher_token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def publish(self, text: str) -> int:
        return self.post("events", {"envelopes": [self.leader.envelope(text)]})["stored_through"]

    def close(self) -> None:
        async def stop() -> None:
            for queue in list(self.subscribers):
                queue.put_nowait(None)
            await self.runner.cleanup()

        asyncio.run_coroutine_threadsafe(stop(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()


class TimedBroker(FakeBroker):
    """Records placement times and wakes the executor as IBKR's callbacks do."""

    def __init__(self) -> None:
        super().__init__()
        self.place_times: list[float] = []
        self.on_update = lambda: None

    def place(self, request, order_id=None):
        self.place_times.append(time.monotonic())
        result = super().place(request, order_id)
        self.on_update()
        return result

    def cancel(self, order_id):
        super().cancel(order_id)
        self.on_update()


def wait_for(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


class EndToEndTests(unittest.TestCase):
    """Signed events through HTTP/SSE into the executor and a fake broker."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.leader = Leader()
        self.relay = RelayHarness(self.leader, Path(self.directory.name))
        self.addCleanup(self.relay.close)
        self.broker = TimedBroker()
        root = Path(self.directory.name)
        self.config = write_config(root, self.leader.public_key,
                                   relay_url=f"http://127.0.0.1:{self.relay.follower_port}")
        self.config.token_path.write_text(self.relay.follower_token)
        self.journal = Journal(self.config.journal_path)
        self.addCleanup(self.journal.close)

    def start(self) -> tuple[Executor, threading.Event, threading.Thread]:
        executor = Executor(self.config, broker=self.broker, journal=self.journal)
        self.broker.on_update = executor.wake.set
        feed = SignalFeed(relay_url=self.config.relay_url, stream=STREAM, token=self.config.token(),
                          verifier=Verifier(self.leader.public_key), after=executor.resume_after,
                          on_signal=executor.on_signal, on_heartbeat=executor.on_heartbeat)
        stop = threading.Event()
        thread = threading.Thread(target=executor.run, args=(stop,), kwargs={"feed": feed}, daemon=True)
        thread.start()
        self.assertTrue(wait_for(feed.connected.is_set))
        return executor, stop, thread

    def entry(self, seq: int, cause: str = "entry", **kwargs) -> str:
        now = datetime.now(UTC)
        return payload(seq, cause, emitted=now, signal_time=now.replace(microsecond=0), plan=None, **kwargs)

    def test_live_entry_reaches_the_broker_quickly_and_replays_after_a_restart(self) -> None:
        executor, stop, thread = self.start()
        latencies = []
        published = time.monotonic()
        self.relay.publish(self.entry(1))
        self.assertTrue(wait_for(lambda: self.broker.placed("entry")))
        latencies.append(self.broker.place_times[0] - published)
        self.assertTrue(wait_for(lambda: self.broker.working("stop")))
        self.relay.post("heartbeat", {"envelope": self.leader.heartbeat(1)})
        self.assertTrue(wait_for(lambda: executor.last_heartbeat_at is not None))

        stop.set()
        executor.wake.set()
        thread.join(5)
        entry_text = json.loads(self.entry(2, "protective_stop_installed", stop=30452.75))
        entry_text["target"]["entry"] = json.loads(self.journal.latest_payload())["target"]["entry"]
        self.relay.publish(json.dumps(entry_text, sort_keys=True, separators=(",", ":")))
        tightened = dict(entry_text, seq=3, cause="protective_stop_tightened")
        tightened["target"] = dict(entry_text["target"], protective_stop={"price": 30706.5})
        self.relay.publish(json.dumps(tightened, sort_keys=True, separators=(",", ":")))

        self.broker.connected = False
        executor, stop, thread = self.start()
        self.assertTrue(wait_for(lambda: self.journal.last_seq() == 3))
        self.assertTrue(wait_for(lambda: self.broker.working("stop")
                                 and self.broker.working("stop")[0].stop_price == 30706.5))
        self.assertEqual(len(self.broker.placed("entry")), 1)

        flat = payload(4, "exit_started", "flat", emitted=datetime.now(UTC))
        published = time.monotonic()
        self.relay.publish(flat)
        self.assertTrue(wait_for(lambda: self.broker.placed("exit")))
        exit_latency = self.broker.place_times[-1] - published
        self.assertEqual(sum(self.broker.positions.values()), 0)
        stop.set()
        executor.wake.set()
        thread.join(5)
        self.assertIsNone(self.journal.halt_reason())
        print(f"\n  relay publish to entry order: {latencies[0] * 1000:.1f} ms; "
              f"publish to exit order: {exit_latency * 1000:.1f} ms")
        self.assertLess(latencies[0], 0.5)
        self.assertLess(exit_latency, 0.5)


if __name__ == "__main__":
    unittest.main()
