# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from executor_support import STREAM, Leader, canonical, payload, target, write_config
from test_executor_feed import RelayHarness

from follow_executor.cli import main
from follow_executor.config import ConfigError, load_config
from follow_executor.journal import Journal
from follow_executor.signal import SignalError, parse_heartbeat, parse_target

REPOSITORY = Path(__file__).resolve().parents[1]

# Synthetic contract example; no historical subscriber signal is published here.
EXAMPLE_ENTRY = canonical({
    "cause": "entry", "changed": ["entry", "exit_plan", "leg", "position"],
    "emitted_at": "2026-10-01T18:10:07.157008+00:00",
    "instrument": {"contract_month": "202612", "currency": "USD", "exchange": "CME",
                   "last_trade_date": "20261218", "root": "MNQ"},
    "schema": "signal.v1", "seq": 1, "strategy": {"profile": "example-profile"},
    "stream": "sessioncycle.mnq",
    "target": {
        "entry": {"atr": 20.25, "deadline": "2026-10-01T18:11:07.157008+00:00",
                  "reference_price": None, "session": "2026-10-01",
                  "signal_time": "2026-10-01T18:10:00+00:00", "stop_atr": 2.0,
                  "trailing": {"activation_atr": 1.0, "distance_atr": 1.5, "enabled": True}},
        "exit_plan": {"cancel_stop_at": "2026-10-02T13:29:00+00:00",
                      "flatten_at": "2026-10-02T13:30:00+00:00", "rule": "next_rth_open"},
        "leg": "drift", "position": "long", "protective_stop": None,
    },
})


class SignalContractTests(unittest.TestCase):
    def test_example_entry_event_parses(self) -> None:
        signal = parse_target(EXAMPLE_ENTRY, STREAM)
        self.assertEqual((signal.seq, signal.position, signal.direction, signal.leg, signal.contract_month),
                         (1, "long", 1, "drift", "202612"))
        self.assertIsNone(signal.stop)
        self.assertIsNone(signal.entry.reference_price)
        self.assertEqual(signal.entry.deadline, datetime(2026, 10, 1, 18, 11, 7, 157008, tzinfo=UTC))
        self.assertEqual(signal.exit_plan.cancel_stop_at, datetime(2026, 10, 2, 13, 29, tzinfo=UTC))
        self.assertEqual(signal.trade_key, "2026-10-01T18:10:00+00:00|drift|long")
        self.assertEqual(signal.payload, EXAMPLE_ENTRY)

    def test_flat_targets_and_off_tick_stops(self) -> None:
        flat = target(9, "exit", "flat")
        self.assertEqual((flat.direction, flat.trade_key, flat.entry), (0, None, None))
        self.assertEqual(target(2, "x", stop=30452.8).stop, 30452.75)
        self.assertEqual(target(2, "x", "short", stop=30452.8).stop, 30453.0)

    def test_contract_violations_are_refused(self) -> None:
        good = json.loads(payload(1, "entry"))
        cases = {
            "schema": dict(good, schema="signal.v2"),
            "stream": dict(good, stream="other"),
            "seq": dict(good, seq=0),
            "position": dict(good, target=dict(good["target"], position="both")),
            "month": dict(good, instrument=dict(good["instrument"], contract_month="2026-12")),
            "exchange": dict(good, instrument=dict(good["instrument"], exchange="EUREX")),
            "stop": dict(good, target=dict(good["target"], protective_stop={"price": -1})),
            "naive time": dict(good, emitted_at="2026-10-01T18:10:07"),
        }
        for name, value in cases.items():
            with self.assertRaises(SignalError, msg=name):
                parse_target(canonical(value), STREAM)

    def test_heartbeats(self) -> None:
        beat = parse_heartbeat({"schema": "signal.v1.heartbeat", "stream": STREAM, "latest_seq": 8,
                                "sent_at": "2026-10-02T05:05:10+00:00"}, STREAM)
        self.assertEqual(beat.latest_seq, 8)
        with self.assertRaises(SignalError):
            parse_heartbeat({"schema": "signal.v1", "stream": STREAM, "latest_seq": 8}, STREAM)


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.key = Leader().public_key

    def test_example_configuration_is_valid(self) -> None:
        config = load_config(REPOSITORY / "deploy/executor.example.json")
        self.assertEqual((config.root, config.quantity, config.ibkr.account_type), ("MNQ", 1, "paper"))
        self.assertEqual(config.leader_public_key, "zesvLFF3vT/hPtfal4i+m6K35v+cO9x4+jOXFLH6Xp4=")

    def test_defaults_and_limits(self) -> None:
        config = write_config(self.root, self.key)
        self.assertEqual((config.max_margin_fraction, config.clock_exit_grace_seconds), (0.5, 30.0))
        self.assertEqual(config.multiplier, 2.0)
        bad = {
            "paper flag on a live account": {"ibkr": {"port": 4001, "account": "U1234567", "account_type": "paper"}},
            "live flag on a paper account": {"ibkr": {"port": 4001, "account": "DU1234567", "account_type": "live"}},
            "size above its cap": {"instrument": {"root": "MNQ", "quantity": 11}},
            "unknown root": {"instrument": {"root": "ES", "quantity": 1}},
            "plain http to a public host": {"relay_url": "http://relay.quantmnq.com"},
            "relative journal": {"journal_path": "executor.sqlite3"},
            "bad key": {"leader_public_key": "not-a-key"},
            "unknown key": {"surprise": 1},
        }
        for name, change in bad.items():
            with self.assertRaises(ConfigError, msg=name):
                write_config(self.root, self.key, **change)


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.leader = Leader()

    def run_cli(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(args))
        return code, output.getvalue()

    def test_check_verifies_the_relay_state_without_a_broker(self) -> None:
        relay = RelayHarness(self.leader, self.root)
        self.addCleanup(relay.close)
        config = write_config(self.root, self.leader.public_key,
                              relay_url=f"http://127.0.0.1:{relay.follower_port}")
        config.token_path.write_text(relay.follower_token)
        relay.publish(payload(1, "entry"))
        code, output = self.run_cli("check", "--config", str(self.root / "executor.json"), "--skip-broker")
        report = json.loads(output)
        self.assertEqual(code, 0, report["problems"])
        self.assertEqual(report["relay_latest"]["seq"], 1)
        self.assertEqual(report["leader_key_id"], self.leader.key_id)

        config.token_path.write_text("wrong-token")
        code, output = self.run_cli("check", "--config", str(self.root / "executor.json"), "--skip-broker")
        self.assertEqual(code, 1)
        self.assertIn("401", json.loads(output)["problems"][0])

    def test_status_and_resume(self) -> None:
        config = write_config(self.root, self.leader.public_key)
        path = str(self.root / "executor.json")
        _code, output = self.run_cli("resume", "--config", path)
        self.assertIn("not halted", output)
        journal = Journal(config.journal_path)
        journal.record_signal(1, payload(1, "entry"))
        journal.halt("test halt")
        journal.close()
        code, output = self.run_cli("status", "--config", path)
        self.assertEqual(code, 0)
        status = json.loads(output)
        self.assertEqual((status["halt"], status["last_seq"], status["target"]["leg"]), ("test halt", 1, "drift"))
        code, output = self.run_cli("resume", "--config", path)
        self.assertEqual(code, 0)
        self.assertIn("resume requested", output)
        journal = Journal(config.journal_path)
        self.assertIsNotNone(journal.get_state("resume_requested"))
        journal.close()

    def test_bad_configuration_exits_2(self) -> None:
        (self.root / "bad.json").write_text("{}")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["status", "--config", str(self.root / "bad.json")]), 2)


class LoggingTests(unittest.TestCase):
    def test_the_cli_keeps_ibapi_wire_logging_out_of_the_journal(self) -> None:
        import logging

        logging.getLogger("ibapi").setLevel(logging.NOTSET)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            config = write_config(Path(directory), Leader().public_key)
            main(["status", "--config", str(config.journal_path.parent / "executor.json")])
        self.assertEqual(logging.getLogger("ibapi").level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
