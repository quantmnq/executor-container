# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from executor_support import (
    ATR,
    T0,
    Clock,
    FakeBroker,
    Leader,
    RecordingAcks,
    contract,
    target,
    write_config,
)

from follow_executor.broker import MarginEstimate
from follow_executor.executor import Executor
from follow_executor.journal import Journal
from follow_executor.signal import round_down

PREOPEN = datetime(2026, 10, 2, 13, 29, tzinfo=UTC)
OPEN = datetime(2026, 10, 2, 13, 30, tzinfo=UTC)


class ExecutorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.leader = Leader()
        self.clock = Clock()
        self.broker = FakeBroker()
        self.acks = RecordingAcks()
        self.make()

    def make(self, **config_changes) -> None:
        self.config = write_config(Path(self.directory.name), self.leader.public_key, **config_changes)
        self.journal = Journal(self.config.journal_path)
        self.addCleanup(self.journal.close)
        self.executor = Executor(self.config, broker=self.broker, journal=self.journal,
                                 acks=self.acks, clock=self.clock)

    def settle(self, steps: int = 6) -> None:
        for _ in range(steps):
            self.executor.step()
            self.clock.advance(0.1)

    def status(self, signal) -> str | None:
        return self.journal.trade_status(signal.trade_key)

    def position(self) -> int:
        return sum(self.broker.positions.values())


class DriftLifecycleTests(ExecutorTestCase):
    def test_entry_stops_trailing_preopen_cancel_and_exit_follow_the_leader(self) -> None:
        entry = target(1, "entry")
        self.executor.on_signal(entry)
        self.settle()
        (placed,) = self.broker.placed("entry")
        self.assertEqual((placed.action, placed.order_type, placed.quantity), ("BUY", "MKT", 2))
        self.assertEqual(self.position(), 2)
        self.assertEqual(self.status(entry), "entered")
        (stop,) = self.broker.working("stop")
        self.assertEqual(stop.stop_price, round_down(self.broker.market - ATR * 11.5))

        self.executor.on_signal(target(2, "protective_stop_installed", stop=30452.75))
        self.settle()
        self.assertEqual(self.broker.working("stop")[0].stop_price, 30452.75)
        self.executor.on_signal(target(3, "protective_stop_tightened", stop=30706.5))
        self.settle()
        self.assertEqual(self.broker.working("stop")[0].stop_price, 30706.5)
        self.assertEqual(len(self.broker.placed("stop")), 1)

        self.clock.now = PREOPEN
        self.settle()
        self.assertEqual(self.broker.working("stop"), [])
        self.executor.on_signal(target(4, "preopen_stop_cancelled", stop=None))
        self.settle()
        self.assertEqual(self.broker.working("stop"), [])
        self.assertEqual(self.position(), 2)

        self.clock.now = OPEN + timedelta(seconds=1)
        self.executor.on_signal(target(5, "exit_started", "flat", emitted=self.clock.now))
        self.settle()
        (exit_order,) = self.broker.placed("exit")
        self.assertEqual((exit_order.action, exit_order.quantity), ("SELL", 2))
        self.assertEqual(self.position(), 0)
        self.assertIsNone(self.journal.halt_reason())
        self.assertEqual(self.journal.expected_positions(), {})
        self.assertEqual(self.journal.entry_price(entry.trade_key), self.broker.market)

    def test_acknowledgements_never_carry_size_price_or_account(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        kinds = self.acks.kinds()
        for kind in ("received", "submitted", "filled", "state"):
            self.assertIn(kind, kinds)
        for _kind, _seq, detail in self.acks.sent:
            text = repr(detail)
            self.assertNotIn("DU1234567", text)
            self.assertFalse(set(detail) & {"quantity", "price", "account", "fill_price"})


class EntryGuardTests(ExecutorTestCase):
    def test_late_joiner_stays_flat(self) -> None:
        self.clock.now = T0 + timedelta(seconds=61)
        entry = target(1, "entry")
        self.executor.on_signal(entry)
        self.settle()
        self.assertEqual(self.broker.placed("entry"), [])
        self.assertEqual(self.status(entry), "missed")
        self.assertIn("missed", self.acks.kinds())

    def test_stop_out_inside_the_entry_window_never_re_enters(self) -> None:
        entry = target(1, "entry")
        self.executor.on_signal(entry)
        self.settle()
        self.broker.trigger_stop()
        self.settle()
        self.assertEqual(self.position(), 0)
        self.assertEqual(len(self.broker.placed("entry")), 1)
        self.assertIsNone(self.journal.halt_reason())

    def test_margin_ceiling_refuses_the_entry(self) -> None:
        self.broker.margin = MarginEstimate(60_000.0, 100_000.0)
        entry = target(1, "entry")
        self.executor.on_signal(entry)
        self.settle()
        self.assertEqual(self.broker.placed("entry"), [])
        self.assertEqual(self.status(entry), "refused")

    def test_unavailable_margin_check_refuses_rather_than_guesses(self) -> None:
        self.broker.what_if_error = TimeoutError("no answer")
        entry = target(1, "entry")
        self.executor.on_signal(entry)
        self.settle()
        self.assertEqual(self.broker.placed("entry"), [])
        self.assertEqual(self.status(entry), "refused")

    def test_stop_risk_ceiling_refuses_the_entry(self) -> None:
        self.make(risk={"max_quantity": 10, "max_stop_risk_usd": 1000})
        entry = target(1, "entry")
        self.executor.on_signal(entry)
        self.settle()
        self.assertEqual(self.status(entry), "refused")  # 2 MNQ x $2 x 327 points = $1,309

    def test_margin_estimate_is_cached_between_entries(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        what_ifs = [call for call in self.broker.calls if call[0] == "what_if"]
        self.assertEqual(len(what_ifs), 1)


class SafetyTests(ExecutorTestCase):
    def test_unknown_position_halts_and_resume_adopts_then_aligns_to_target(self) -> None:
        con_id = contract().con_id
        self.broker.contracts[con_id] = contract()
        self.broker.positions[con_id] = 1
        self.settle(3)
        self.clock.advance(6)
        self.settle(2)
        self.assertIn("differs from the executor's record", self.journal.halt_reason())
        self.assertEqual(self.broker.placed("exit"), [])
        self.assertIn("error", self.acks.kinds())

        self.journal.set_state("resume_requested", "now")
        self.executor.on_signal(target(1, "exit", "flat"))
        self.settle()
        self.assertIsNone(self.journal.halt_reason())
        self.assertEqual(len(self.broker.placed("exit")), 1)
        self.assertEqual(self.position(), 0)

    def test_an_order_from_another_client_halts(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        stop_id = self.broker.working("stop")[0].order_id
        from dataclasses import replace

        self.broker.orders[99] = replace(self.broker.orders[stop_id], order_id=99, order_ref="", client_id=0)
        self.settle(2)
        self.assertIn("order 99", self.journal.halt_reason())

    def test_unacknowledged_order_halts_after_five_seconds(self) -> None:
        self.broker.acknowledge = False
        self.executor.on_signal(target(1, "entry"))
        self.settle(2)
        self.assertIsNone(self.journal.halt_reason())
        self.clock.advance(6)
        self.settle(1)
        self.assertIn("not acknowledged", self.journal.halt_reason())
        self.assertEqual(len(self.broker.placed("entry")), 1)

    def test_refused_stop_move_closes_the_position(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        self.broker.reject["modify"] = (201, "Order rejected - stop price above market")
        signal = target(2, "protective_stop_installed", stop=30900.0)
        self.executor.on_signal(signal)
        self.settle(10)
        self.assertEqual(self.status(signal), "closed")
        self.assertEqual(self.position(), 0)
        self.assertIn("rejected", self.acks.kinds())

    def test_rejected_exit_halts_and_the_stop_is_repaired(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        self.executor.on_signal(target(2, "protective_stop_installed", stop=30452.75))
        self.settle()
        self.broker.reject["exit"] = (201, "Order rejected")
        self.executor.on_signal(target(3, "exit_started", "flat"))
        self.settle(10)
        self.assertIn("exit order", self.journal.halt_reason())
        self.assertEqual(self.position(), 2)
        # Halted: the cancelled stop is not repaired because the target is flat.
        self.assertEqual(self.broker.working("stop"), [])

    def test_halted_executor_repairs_a_missing_stop_on_a_held_position(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        self.executor.on_signal(target(2, "protective_stop_installed", stop=30452.75))
        self.settle()
        self.journal.halt("operator test")
        stop_id = self.broker.working("stop")[0].order_id
        self.broker.cancel(stop_id)
        self.settle(3)
        (stop,) = self.broker.working("stop")
        self.assertEqual(stop.stop_price, 30452.75)
        self.assertEqual(len(self.broker.placed("entry")), 1)


class FeedLossTests(ExecutorTestCase):
    def test_exit_plan_fallback_closes_when_the_leaders_exit_never_arrives(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        self.executor.on_signal(target(2, "protective_stop_installed", stop=30452.75))
        self.settle()
        self.clock.now = OPEN + timedelta(seconds=29)
        self.settle(2)
        self.assertEqual(self.position(), 2)
        self.clock.now = OPEN + timedelta(seconds=31)
        self.settle()
        self.assertEqual(self.position(), 0)
        self.assertEqual(self.journal.trade_status(target(1, "entry").trade_key), "closed")
        # The leader's late exit changes nothing.
        self.executor.on_signal(target(3, "exit_started", "flat"))
        self.settle()
        self.assertEqual(len(self.broker.placed("exit")), 1)

    def test_restart_resumes_from_the_journal(self) -> None:
        self.executor.on_signal(target(1, "entry"))
        self.settle()
        self.executor.on_signal(target(2, "protective_stop_installed", stop=30452.75))
        self.settle()
        restarted = Executor(self.config, broker=self.broker, journal=self.journal,
                             acks=self.acks, clock=self.clock)
        self.assertEqual(restarted.resume_after(), 2)
        self.assertEqual(restarted.target.seq, 2)
        for _ in range(4):
            restarted.step()
            self.clock.advance(0.1)
        self.assertEqual(len(self.broker.placed("entry")), 1)
        self.assertEqual(len(self.broker.placed("stop")), 1)
        self.assertIsNone(self.journal.halt_reason())

    def test_heartbeat_ahead_of_the_journal_requests_a_replay(self) -> None:
        from follow_executor.signal import Heartbeat

        self.executor.on_heartbeat(Heartbeat("sessioncycle.mnq", 3, T0))
        self.assertTrue(self.executor.feed_behind)


class ContinuationTests(ExecutorTestCase):
    def test_gap_to_drift_keeps_the_long_and_moves_the_stop(self) -> None:
        plan = {"rule": "session_close", "flatten_at": "2026-10-01T19:55:00+00:00"}
        gap_time = datetime(2026, 10, 1, 13, 35, tzinfo=UTC)
        self.clock.now = gap_time + timedelta(seconds=7)
        gap = target(1, "entry", leg="gap", plan=plan, signal_time=gap_time, emitted=self.clock.now)
        self.executor.on_signal(gap)
        self.settle()
        self.executor.on_signal(target(2, "protective_stop_installed", leg="gap", plan=plan,
                                       signal_time=gap_time, emitted=self.clock.now, stop=30300.0))
        self.settle()
        self.clock.now = datetime(2026, 10, 1, 19, 55, 7, tzinfo=UTC)
        self.settle(2)
        self.assertEqual(self.position(), 2)
        drift = target(3, "gap_drift_continuation", stop=30100.0, emitted=self.clock.now)
        self.executor.on_signal(drift)
        self.settle()
        self.assertEqual(self.position(), 2)
        self.assertEqual(self.broker.working("stop")[0].stop_price, 30100.0)
        self.assertEqual(self.broker.placed("exit"), [])
        self.assertEqual(self.status(drift), "entered")
        self.clock.now = datetime(2026, 10, 1, 19, 56, tzinfo=UTC)
        self.settle(2)
        self.assertEqual(self.position(), 2)



class GatewayOutageLoggingTests(ExecutorTestCase):
    def test_an_outage_warns_once_and_its_recovery_is_logged(self) -> None:
        self.broker.connect_error = ConnectionError("Couldn't connect to TWS")
        with self.assertLogs("follow_executor.executor", level="INFO") as logs:
            for _ in range(5):
                self.executor.step()
                self.clock.advance(11)
            self.broker.connect_error = None
            self.executor.step()
            self.broker.connected = False
            self.broker.connect_error = ConnectionError("Couldn't connect to TWS")
            self.clock.advance(11)
            self.executor.step()
        warnings = [r for r in logs.records if r.levelname == "WARNING" and "IBKR unavailable" in r.getMessage()]
        self.assertEqual(len(warnings), 2)
        self.assertIn("IBKR unavailable", warnings[0].getMessage())
        restored = [r.getMessage() for r in logs.records if "restored" in r.getMessage()]
        self.assertEqual(restored, ["IBKR connection restored after 55 s"])


if __name__ == "__main__":
    unittest.main()
