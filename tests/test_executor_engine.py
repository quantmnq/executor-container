# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from executor_support import ATR, SIGNAL_TIME, STOP_ATR, T0, contract, target

from follow_executor.broker import OrderView
from follow_executor.engine import Cancel, Halt, MarkTrade, Modify, Place, View, decide
from follow_executor.signal import round_down, round_up

CONTRACT = contract()
FILL = 30532.8125


def order(order_id: int, purpose: str, *, action: str = "SELL", order_type: str = "STP",
          quantity: int = 2, filled: int = 0, stop: float | None = 30452.75, con_id: int | None = None):
    return OrderView(order_id, con_id or CONTRACT.con_id, "MNQ", action, order_type, quantity, filled,
                     "Submitted", f"fx:{purpose}:1", 71, stop_price=stop if order_type == "STP" else None)


def view(signal, **changes) -> View:
    base = View(now=T0 + timedelta(seconds=1), target=signal, quantity=2, slippage_points=10.0,
                clock_exit_grace=timedelta(seconds=30), target_contract=CONTRACT)
    return replace(base, **changes)


def held(signal, **changes) -> View:
    defaults = {"position": 2, "position_contract": CONTRACT, "trade_status": "entered",
                "entry_price": FILL}
    return view(signal, **{**defaults, **changes})


class EntryTests(unittest.TestCase):
    def test_flat_follower_enters_at_market_while_reference_price_is_null(self) -> None:
        signal = target(1, "entry")
        actions = decide(view(signal))
        self.assertEqual(actions[0], MarkTrade(signal.trade_key, "entering", "entry"))
        place = actions[1]
        self.assertIsInstance(place, Place)
        self.assertEqual((place.request.action, place.request.order_type, place.request.quantity),
                         ("BUY", "MKT", 2))
        self.assertEqual(place.request.order_ref, "fx:entry:1")

    def test_reference_price_gives_a_capped_marketable_limit_on_the_tick(self) -> None:
        long = decide(view(target(1, "entry", reference=30780.1)))[1].request
        self.assertEqual((long.order_type, long.limit_price), ("LMT", 30790.25))
        short = decide(view(target(1, "entry", "short", leg="bounce", reference=30780.1)))[1].request
        self.assertEqual((short.action, short.limit_price), ("SELL", 30770.0))

    def test_entry_deadline_and_trade_history_block_entries(self) -> None:
        signal = target(1, "entry")
        late = view(signal, now=signal.entry.deadline + timedelta(microseconds=1))
        self.assertEqual(decide(late), [MarkTrade(signal.trade_key, "missed", "entry deadline passed")])
        for status in ("entering", "entered", "missed", "refused", "rejected", "closed"):
            self.assertEqual(decide(view(signal, trade_status=status)), [], status)

    def test_entry_needs_a_resolved_contract(self) -> None:
        self.assertEqual(decide(view(target(1, "entry"), target_contract=None)), [])

    def test_a_working_entry_is_not_duplicated_and_is_cancelled_after_the_deadline(self) -> None:
        signal = target(1, "entry", reference=30780.0)
        entry = order(5, "entry", action="BUY", order_type="LMT")
        trades = {5: signal.trade_key}
        self.assertEqual(decide(view(signal, entries=(entry,), order_trades=trades, trade_status="entering")), [])
        late = view(signal, entries=(entry,), order_trades=trades, trade_status="entering",
                    now=signal.entry.deadline + timedelta(seconds=1))
        self.assertEqual(decide(late), [Cancel(5, "entry window closed")])

    def test_partial_fill_at_the_deadline_is_protected_and_the_rest_cancelled(self) -> None:
        signal = target(1, "entry", reference=30780.0)
        entry = order(5, "entry", action="BUY", order_type="LMT", filled=1)
        actions = decide(view(signal, entries=(entry,), order_trades={5: signal.trade_key},
                              trade_status="entering", position=1, position_contract=CONTRACT,
                              entry_price=30780.0, now=signal.entry.deadline + timedelta(seconds=1)))
        self.assertEqual(actions[0], Cancel(5, "entry window closed"))
        self.assertEqual(actions[1], MarkTrade(signal.trade_key, "entered", "position held"))
        self.assertEqual((actions[2].request.order_type, actions[2].request.quantity), ("STP", 1))


class StopTests(unittest.TestCase):
    def test_provisional_stop_from_the_followers_fill_until_the_leader_stop_arrives(self) -> None:
        actions = decide(held(target(1, "entry"), trade_status="entering"))
        self.assertEqual(actions[0].status, "entered")
        stop = actions[1].request
        self.assertEqual(stop.stop_price, round_down(FILL - ATR * STOP_ATR))
        self.assertEqual(stop.stop_price, 30452.75)  # 80 points below the fill, rounded down
        self.assertEqual((stop.action, stop.tif, stop.outside_rth), ("SELL", "GTC", True))

    def test_published_stop_is_followed_in_either_direction(self) -> None:
        current = order(7, "stop", stop=30452.75)
        tighter = decide(held(target(7, "protective_stop_tightened", stop=30706.5), stops=(current,)))
        self.assertEqual(tighter, [Modify(7, tighter[0].request)])
        self.assertEqual(tighter[0].request.stop_price, 30706.5)
        self.assertEqual(tighter[0].request.order_ref, "fx:stop:1")
        looser = decide(held(target(9, "gap_drift_continuation", stop=30100.0), stops=(current,)))
        self.assertEqual(looser[0].request.stop_price, 30100.0)

    def test_matching_stop_needs_no_action_and_quantity_drift_is_corrected(self) -> None:
        signal = target(2, "protective_stop_installed", stop=30452.75)
        self.assertEqual(decide(held(signal, stops=(order(7, "stop"),))), [])
        resized = decide(held(signal, stops=(order(7, "stop", quantity=1),)))
        self.assertEqual(resized[0].request.quantity, 2)

    def test_stop_is_cancelled_at_the_pre_open_time_on_the_followers_clock(self) -> None:
        signal = target(7, "protective_stop_tightened", stop=30706.5)
        at = datetime(2026, 10, 2, 13, 29, tzinfo=UTC)
        self.assertEqual(decide(held(signal, stops=(order(7, "stop"),), now=at)),
                         [Cancel(7, "pre-open stop cancellation")])
        self.assertEqual(decide(held(signal, now=at)), [])

    def test_duplicate_and_stray_stops_are_cancelled(self) -> None:
        signal = target(2, "protective_stop_installed", stop=30452.75)
        self.assertEqual(decide(held(signal, stops=(order(7, "stop"), order(8, "stop")))),
                         [Cancel(8, "duplicate stop")])
        stray = order(9, "stop", con_id=CONTRACT.con_id + 10)
        self.assertEqual(decide(held(signal, stops=(stray,))), [Cancel(9, "stop on another contract")])


class ExitTests(unittest.TestCase):
    def test_flat_target_cancels_the_stop_before_the_market_exit(self) -> None:
        flat = target(10, "exit", "flat")
        self.assertEqual(decide(held(flat, stops=(order(7, "stop"),))), [Cancel(7, "target flat")])
        (place,) = decide(held(flat))
        self.assertEqual((place.request.purpose, place.request.action, place.request.order_type,
                          place.request.quantity), ("exit", "SELL", "MKT", 2))
        self.assertEqual(decide(held(flat, exits=(order(11, "exit", order_type="MKT"),))), [])
        self.assertEqual(decide(view(flat)), [])

    def test_exit_plan_fallback_waits_for_the_grace_then_closes_once(self) -> None:
        signal = target(7, "protective_stop_tightened", stop=30706.5)
        flatten = datetime(2026, 10, 2, 13, 30, tzinfo=UTC)
        self.assertEqual(decide(held(signal, now=flatten + timedelta(seconds=29))), [])
        due = flatten + timedelta(seconds=30)
        actions = decide(held(signal, now=due))
        self.assertEqual(actions[0], MarkTrade(signal.trade_key, "closing", "exit plan fallback"))
        self.assertEqual(actions[1].request.purpose, "exit")
        self.assertEqual(decide(view(signal, now=due, trade_status="closing")),
                         [MarkTrade(signal.trade_key, "closed", "flat after executor exit")])
        self.assertEqual(decide(view(signal, now=due, trade_status="closed")), [])

    def test_gap_session_close_fallback_does_not_pre_empt_the_leaders_decision(self) -> None:
        plan = {"rule": "session_close", "flatten_at": "2026-10-01T17:00:00+00:00"}
        gap = target(3, "protective_stop_installed", leg="gap", stop=30000.0, plan=plan,
                     signal_time=datetime(2026, 10, 1, 14, 0, tzinfo=UTC))
        at_decision = datetime(2026, 10, 1, 17, 0, 7, tzinfo=UTC)
        self.assertEqual(decide(held(gap, stops=(order(7, "stop", stop=30000.0),), now=at_decision)), [])
        drift = target(4, "gap_drift_continuation", stop=30100.0)
        actions = decide(held(drift, stops=(order(7, "stop", stop=30000.0),), trade_status=None,
                              now=at_decision + timedelta(seconds=1)))
        self.assertEqual(actions[0], MarkTrade(drift.trade_key, "entered", "position held"))
        self.assertEqual(actions[1].request.stop_price, 30100.0)

    def test_stop_refused_closes_the_trade(self) -> None:
        signal = target(7, "protective_stop_tightened", stop=30706.5)
        self.assertEqual(decide(held(signal, trade_status="closing"))[0].request.purpose, "exit")

    def test_opposite_position_is_closed_first(self) -> None:
        signal = target(1, "entry")
        self.assertEqual(decide(view(signal, position=-2, position_contract=CONTRACT,
                                     stops=(order(7, "stop", action="BUY"),))),
                         [Cancel(7, "opposite position")])
        (place,) = decide(view(signal, position=-2, position_contract=CONTRACT))
        self.assertEqual((place.request.purpose, place.request.action), ("exit", "BUY"))

    def test_a_position_larger_than_configured_halts(self) -> None:
        actions = decide(held(target(2, "protective_stop_installed", stop=30452.75), position=3))
        self.assertIsInstance(actions[-1], Halt)


class ShortLegTests(unittest.TestCase):
    def test_bounce_short_enters_sells_and_protects_above(self) -> None:
        plan = {"rule": "session_close", "flatten_at": "2026-10-01T17:00:00+00:00"}
        short = target(1, "entry", "short", leg="bounce", plan=plan,
                       signal_time=SIGNAL_TIME - timedelta(hours=2), emitted=T0 - timedelta(hours=2))
        entry = decide(view(short, now=T0 - timedelta(hours=2)))[1].request
        self.assertEqual((entry.action, entry.order_type), ("SELL", "MKT"))
        stop = decide(view(short, position=-2, position_contract=CONTRACT, trade_status="entering",
                           entry_price=30000.0, now=T0 - timedelta(hours=2)))[1].request
        self.assertEqual((stop.action, stop.stop_price), ("BUY", round_up(30000.0 + ATR * STOP_ATR)))


if __name__ == "__main__":
    unittest.main()
