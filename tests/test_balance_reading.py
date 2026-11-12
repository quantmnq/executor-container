# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Balance sizing's mid-bar NetLiquidation reading and the Nasdaq cash-session calendar."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from executor_support import Clock, FakeBroker, Leader, target, write_config
from test_balance_sizing import LEG, PRICE, BookTestCase, band

from follow_executor.cash_session import (
    CLOSE,
    EARLY_CLOSE,
    OPEN,
    bar_start,
    early_closes,
    holidays,
    in_cash_session,
    session_hours,
)
from follow_executor.executor import Executor
from follow_executor.journal import Journal

EASTERN = ZoneInfo("America/New_York")
# Thursday 1 October 2026, 13:02 EDT: two minutes into the 13:00 bar.
WINDOW = datetime(2026, 10, 1, 17, 2, tzinfo=UTC)
BAR_CLOSE = datetime(2026, 10, 1, 17, 5, tzinfo=UTC)
TIMEOUT = "TimeoutError: timed out waiting for NetLiquidation"


class BlockingBroker(FakeBroker):
    """A reading-thread NetLiquidation read waits until the test releases it."""

    def __init__(self) -> None:
        super().__init__()
        self.reading_started = threading.Event()
        self.release = threading.Event()

    def net_liquidation(self) -> float:
        if threading.current_thread().name == "balance-reading":
            self.reading_started.set()
            if not self.release.wait(10):
                raise TimeoutError("the test never released the reading")
        return super().net_liquidation()


class Statuses:
    """Records every service status the executor would announce."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def status(self, topic: str, state: str, now: datetime, **_options) -> None:
        self.calls.append((topic, state))

    def observe(self, *_args) -> None:
        pass

    def pulse(self) -> None:
        pass


class ReadingTestCase(BookTestCase):
    def use(self, broker: FakeBroker) -> None:
        broker.market = PRICE
        self.broker = broker
        self.restart()

    def reads(self) -> int:
        return self.broker.calls.count(("net_liquidation", None))

    def step_at(self, moment: datetime) -> None:
        """One loop step at ``moment``, then one more to journal a reading it started."""
        self.clock.now = moment
        self.executor.on_heartbeat(SimpleNamespace(latest_seq=self.journal.last_seq()))
        self.executor.step()
        job = self.executor._reading_job
        if job is not None:
            self.assertTrue(job.done.wait(5))
            self.executor.step()

    def enter(self, moment: datetime, seq: int = 1, **kwargs):
        self.clock.now = moment
        signal = self.entry(seq, signal_time=moment, emitted=moment, **kwargs)
        self.executor.on_signal(signal)
        return signal

    def exit(self, seq: int) -> None:
        self.executor.on_signal(target(seq, "exit", "flat", emitted=self.clock.now))
        self.settle(10)
        self.assertEqual(self.broker.held(), {})

    def logged(self, kind: str) -> list[dict]:
        rows = reversed(self.journal.recent("log", 500))
        return [json.loads(row["detail"]) for row in rows if row["kind"] == kind]

    def sized(self, signal) -> dict:
        return self.executor._balance_trades()[signal.trade_key]


class MidBarReadingTests(ReadingTestCase):
    def test_entry_uses_the_mid_bar_reading_without_a_second_read(self) -> None:
        self.step_at(WINDOW)
        self.assertEqual(self.reads(), 1)
        (reading,) = self.logged("balance_reading")
        self.assertEqual(reading["net_liquidation"], 250_000.0)
        self.assertEqual(reading["taken_at"], WINDOW.isoformat())
        self.assertEqual(reading["bar"], "2026-10-01T13:00:00-04:00")
        self.assertIn("seconds", reading)

        self.broker.net_liq = 100_000.0  # a direct read would size a smaller book
        signal = self.enter(BAR_CLOSE)
        self.settle()
        self.assertEqual(self.reads(), 1)
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        record = self.sized(signal)
        self.assertEqual(record["net_liquidation"], 250_000.0)
        self.assertEqual(record["net_liquidation_source"], "mid_bar_reading")
        self.assertEqual(record["reading_age_seconds"], 180.0)
        self.assertNotIn("reading_unused", record)
        (size,) = self.logged("balance_size")
        self.assertEqual(size["net_liquidation_source"], "mid_bar_reading")
        self.assertEqual(size["reading_age_seconds"], 180.0)

    def test_a_fill_after_the_reading_forces_a_direct_read(self) -> None:
        self.step_at(WINDOW)
        first = self.enter(WINDOW + timedelta(seconds=20))
        self.settle()
        self.assertEqual(self.sized(first)["net_liquidation_source"], "mid_bar_reading")
        self.exit(2)
        self.assertEqual(self.reads(), 1)  # flat again, but this bar already had its reading

        self.broker.net_liq = 100_000.0
        second = self.enter(BAR_CLOSE, 3)
        self.settle()
        self.assertEqual(self.reads(), 2)
        record = self.sized(second)
        self.assertEqual(record["net_liquidation"], 100_000.0)
        self.assertEqual(record["net_liquidation_source"], "direct_read")
        self.assertEqual(record["reading_unused"], "an execution was recorded after the reading")
        self.assertNotIn("reading_age_seconds", record)

    def test_a_reading_360_s_old_is_still_used(self) -> None:
        self.step_at(WINDOW)
        signal = self.enter(WINDOW + timedelta(seconds=360))
        self.settle()
        self.assertEqual(self.reads(), 1)
        self.assertEqual(self.sized(signal)["reading_age_seconds"], 360.0)

    def test_a_reading_older_than_360_s_forces_a_direct_read(self) -> None:
        self.step_at(WINDOW)
        signal = self.enter(WINDOW + timedelta(seconds=360.5))
        self.settle()
        self.assertEqual(self.reads(), 2)
        record = self.sized(signal)
        self.assertEqual(record["net_liquidation_source"], "direct_read")
        self.assertEqual(record["reading_unused"], "the reading is 360.5 s old, outside 0-360 s")

    def test_one_reading_per_bar_only_in_the_window_and_the_cash_session(self) -> None:
        def reads_at(*wall_time: int) -> int:
            before = self.reads()
            self.step_at(datetime(*wall_time, tzinfo=EASTERN))
            return self.reads() - before

        # The 13:00 bar: only from 2:00 to before 3:00 into it, and only once.
        self.assertEqual(reads_at(2026, 10, 1, 13, 1, 59), 0)
        self.assertEqual(reads_at(2026, 10, 1, 13, 2, 0), 1)
        self.assertEqual(reads_at(2026, 10, 1, 13, 2, 30), 0)
        self.assertEqual(reads_at(2026, 10, 1, 13, 2, 59, 999_999), 0)
        self.assertEqual(reads_at(2026, 10, 1, 13, 3, 0), 0)
        self.assertEqual(reads_at(2026, 10, 1, 13, 4, 0), 0)
        self.assertEqual(reads_at(2026, 10, 1, 13, 7, 30), 1)  # the next bar
        # The cash session opens at 09:30 and closes at 16:00 US Eastern.
        self.assertEqual(reads_at(2026, 10, 2, 9, 27, 0), 0)
        self.assertEqual(reads_at(2026, 10, 2, 9, 32, 0), 1)
        self.assertEqual(reads_at(2026, 10, 2, 15, 57, 0), 1)
        self.assertEqual(reads_at(2026, 10, 2, 16, 2, 0), 0)
        self.assertEqual(reads_at(2026, 10, 2, 20, 2, 0), 0)
        # No session on a weekend or a holiday; early closes end at 13:00.
        self.assertEqual(reads_at(2026, 10, 3, 10, 2, 0), 0)  # Saturday
        self.assertEqual(reads_at(2026, 11, 26, 10, 2, 0), 0)  # Thanksgiving Day
        self.assertEqual(reads_at(2026, 11, 27, 12, 57, 0), 1)  # the day after closes early
        self.assertEqual(reads_at(2026, 11, 27, 13, 2, 0), 0)
        self.assertEqual(reads_at(2026, 12, 24, 13, 2, 0), 0)
        self.assertEqual(reads_at(2026, 12, 28, 13, 2, 0), 1)
        self.assertEqual(len(self.logged("balance_reading")), 6)

    def test_no_reading_while_holding(self) -> None:
        self.enter(WINDOW - timedelta(seconds=90))
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        self.assertEqual(self.reads(), 1)  # the entry's own direct read
        for second in (0, 20, 40, 59):
            self.step_at(WINDOW + timedelta(seconds=second))
        self.assertEqual(self.reads(), 1)
        self.clock.now = WINDOW + timedelta(seconds=70)  # flat again only after the window
        self.exit(2)
        self.step_at(WINDOW + timedelta(minutes=5))
        self.assertEqual(self.reads(), 2)

    def test_no_reading_with_working_orders_or_an_incomplete_reconciliation(self) -> None:
        self.broker.snapshot_complete = False
        self.step_at(WINDOW)
        self.assertEqual(self.reads(), 0)
        self.broker.snapshot_complete = True
        self.step_at(WINDOW + timedelta(seconds=30))  # this bar's reading was never taken
        self.assertEqual(self.reads(), 1)

        self.broker.auto_fill = False
        self.enter(BAR_CLOSE + timedelta(seconds=60), deadline=BAR_CLOSE + timedelta(minutes=5))
        self.settle()
        self.assertEqual(len(self.broker.working("entry")), 2)
        self.assertEqual(self.broker.held(), {})
        for second in (0, 30):
            self.step_at(WINDOW + timedelta(minutes=5, seconds=second))
        self.assertEqual(self.reads(), 1)

    def test_a_failed_reading_is_journaled_without_an_alert_and_the_entry_reads_directly(self) -> None:
        statuses = Statuses()
        self.executor.notifications = statuses
        self.broker.net_liq_error = TimeoutError("timed out waiting for NetLiquidation")
        with self.assertNoLogs("follow_executor", level="WARNING"):
            self.step_at(WINDOW)
        (failed,) = self.logged("balance_reading_failed")
        self.assertEqual(failed["error"], TIMEOUT)
        self.assertEqual(failed["taken_at"], WINDOW.isoformat())
        self.assertEqual(self.logged("balance_reading"), [])
        self.assertEqual([kind for kind in self.acks.kinds() if kind != "state"], [])
        self.assertEqual({state for _topic, state in statuses.calls}, {"ready"})
        self.assertIsNone(self.journal.halt_reason())
        self.assertEqual(json.loads(self.journal.get_state("sizing_health"))["status"], "unavailable")

        self.broker.net_liq_error = None
        signal = self.enter(BAR_CLOSE)
        self.settle()
        self.assertEqual(self.reads(), 2)
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        record = self.sized(signal)
        self.assertEqual(record["net_liquidation_source"], "direct_read")
        self.assertEqual(record["reading_unused"], f"the last reading failed ({TIMEOUT})")

    def test_a_slow_reading_never_delays_a_signal_a_stop_move_or_the_stop_after_a_fill(self) -> None:
        self.use(BlockingBroker())
        self.clock.now = WINDOW
        self.executor.step()
        self.assertTrue(self.broker.reading_started.wait(5))
        started = time.monotonic()

        signal = self.enter(WINDOW + timedelta(seconds=10))
        self.settle()
        self.assertEqual(self.broker.held(), {"NQ": 1, "MNQ": 7})
        self.assertEqual([stop[:2] for stop in self.stops()], [("MNQ", 7), ("NQ", 1)])
        self.executor.on_signal(target(2, "protective_stop_installed", stop=20900.0, leg=LEG,
                                       reference=PRICE, sizing=band(), signal_time=signal.entry.signal_time,
                                       emitted=self.clock.now))
        self.settle()
        self.assertEqual(self.stops(), [("MNQ", 7, 20900.0), ("NQ", 1, 20900.0)])
        self.assertLess(time.monotonic() - started, 2)
        job = self.executor._reading_job
        self.assertFalse(job.done.is_set())  # all of that while IBKR had not answered
        record = self.sized(signal)
        self.assertEqual(record["net_liquidation_source"], "direct_read")
        self.assertEqual(record["reading_unused"], "a reading was in progress")

        # The late reading is journaled, but fills followed its start, so no entry uses it.
        self.broker.release.set()
        self.assertTrue(job.done.wait(5))
        self.executor.step()
        self.assertEqual(len(self.logged("balance_reading")), 1)
        self.assertEqual(self.executor._reading_unused(self.clock.now),
                         "an execution was recorded after the reading")

    def test_reconnect_clears_the_reading(self) -> None:
        self.step_at(WINDOW)
        self.assertIsNone(self.executor._reading_unused(WINDOW + timedelta(seconds=60)))
        self.broker.connected = False
        self.step_at(WINDOW + timedelta(seconds=30))
        self.assertTrue(self.broker.connected)  # reconnected in the same step
        signal = self.enter(BAR_CLOSE)
        self.settle()
        self.assertEqual(self.reads(), 2)
        self.assertEqual(self.sized(signal)["reading_unused"],
                         "the reading was cleared when the IBKR connection was lost")

    def test_a_reading_in_flight_across_a_reconnect_is_discarded(self) -> None:
        self.use(BlockingBroker())
        self.clock.now = WINDOW
        self.executor.step()
        self.assertTrue(self.broker.reading_started.wait(5))
        job = self.executor._reading_job
        self.broker.connected = False
        self.clock.now = WINDOW + timedelta(seconds=5)
        self.executor.step()
        self.broker.release.set()
        self.assertTrue(job.done.wait(5))
        self.executor.step()
        (failed,) = self.logged("balance_reading_failed")
        self.assertEqual(failed["error"], "the reading was cleared when the IBKR connection was lost")
        self.assertEqual(self.logged("balance_reading"), [])
        self.assertIsNone(self.executor._reading)

    def test_restart_starts_without_a_reading(self) -> None:
        self.step_at(WINDOW)
        self.restart()
        signal = self.enter(BAR_CLOSE)
        self.settle()
        self.assertEqual(self.reads(), 2)
        self.assertEqual(self.sized(signal)["reading_unused"], "no reading since the executor started")


class FixedSizeReadingTests(unittest.TestCase):
    def test_no_reading_without_balance_sizing(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        config = write_config(Path(directory.name), Leader().public_key)
        journal = Journal(config.journal_path)
        self.addCleanup(journal.close)
        broker = FakeBroker()
        clock = Clock(WINDOW - timedelta(minutes=1))
        executor = Executor(config, broker=broker, journal=journal, clock=clock)
        for _ in range(40):  # 20 minutes across four reading windows
            executor.step()
            clock.advance(30)
        self.assertNotIn(("net_liquidation", None), broker.calls)
        self.assertIsNone(executor._reading_job)
        self.assertEqual([row for row in journal.recent("log", 100)
                          if row["kind"].startswith("balance_reading")], [])


class CashSessionTests(unittest.TestCase):
    def test_full_holidays_and_early_closes(self) -> None:
        self.assertEqual(sorted(holidays(2026)), [
            date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
            date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
            date(2026, 11, 26), date(2026, 12, 25),
        ])
        self.assertEqual(sorted(early_closes(2026)), [date(2026, 11, 27), date(2026, 12, 24)])
        # 2025: Good Friday in April, the national day of mourning and three early closes.
        self.assertIn(date(2025, 4, 18), holidays(2025))
        self.assertIn(date(2025, 1, 9), holidays(2025))
        self.assertEqual(sorted(early_closes(2025)),
                         [date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24)])

    def test_weekend_holidays_are_observed_on_the_nearest_weekday(self) -> None:
        observed = holidays(2027)
        self.assertIn(date(2027, 6, 18), observed)  # Juneteenth on a Saturday
        self.assertIn(date(2027, 7, 5), observed)  # Independence Day on a Sunday
        self.assertIn(date(2027, 12, 24), observed)  # Christmas Day on a Saturday
        self.assertEqual(sorted(early_closes(2027)), [date(2027, 11, 26)])
        # New Year's Day on a Saturday closes no Friday.
        self.assertNotIn(date(2027, 12, 31), observed)
        self.assertNotIn(date(2028, 1, 1), holidays(2028))
        self.assertIn(date(2028, 7, 3), early_closes(2028))

    def test_session_hours_follow_the_calendar(self) -> None:
        self.assertEqual(session_hours(date(2026, 11, 12)), (OPEN, CLOSE))
        self.assertEqual(session_hours(date(2026, 11, 27)), (OPEN, EARLY_CLOSE))
        self.assertIsNone(session_hours(date(2026, 11, 26)))
        self.assertIsNone(session_hours(date(2026, 11, 14)))

    def test_session_is_in_us_eastern_time_through_daylight_saving(self) -> None:
        self.assertTrue(in_cash_session(datetime(2026, 7, 1, 13, 30, tzinfo=UTC)))  # 09:30 EDT
        self.assertFalse(in_cash_session(datetime(2026, 12, 1, 13, 30, tzinfo=UTC)))  # 08:30 EST
        self.assertTrue(in_cash_session(datetime(2026, 12, 1, 14, 30, tzinfo=UTC)))
        self.assertTrue(in_cash_session(datetime(2026, 11, 27, 17, 59, 59, tzinfo=UTC)))
        self.assertFalse(in_cash_session(datetime(2026, 11, 27, 18, 0, tzinfo=UTC)))  # 13:00 EST
        self.assertFalse(in_cash_session(datetime(2026, 12, 1, 21, 0, tzinfo=UTC)))  # 16:00 EST

    def test_bars_start_on_five_minute_us_eastern_boundaries(self) -> None:
        start = bar_start(datetime(2026, 11, 12, 15, 47, 42, tzinfo=UTC))
        self.assertEqual(start, datetime(2026, 11, 12, 10, 45, tzinfo=EASTERN))
        self.assertEqual(start.utcoffset(), timedelta(hours=-5))


if __name__ == "__main__":
    unittest.main()
