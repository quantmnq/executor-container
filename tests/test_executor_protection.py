# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from executor_support import contract, target
from test_executor_service import OPEN, PREOPEN, ExecutorTestCase

from follow_executor.engine import stop_request
from follow_executor.executor import Executor
from follow_executor.journal import Journal


class ProtectionDeadlineTests(ExecutorTestCase):
    def block_stops(self) -> None:
        original = self.broker.place

        def place(request, order_id=None):
            if request.purpose == "stop":
                raise ConnectionError("test: stop cannot be installed")
            return original(request, order_id)

        self.broker.place = place

    def enter(self, direction="long") -> None:
        self.executor.on_signal(target(1, "entry", direction, leg="bounce" if direction == "short" else "drift"))
        self.settle()

    def deadline(self) -> datetime:
        record = self.executor._protection.records[str(contract().con_id)]
        return datetime.fromisoformat(record["deadline"])

    def run_at_deadline(self) -> None:
        self.clock.now = self.deadline()
        self.settle(12)

    def restart(self) -> None:
        journal = Journal(self.config.journal_path)
        self.addCleanup(journal.close)
        self.journal = journal
        self.executor = Executor(self.config, broker=self.broker, journal=journal,
                                 acks=self.acks, clock=self.clock)

    def assert_exit(self, action, quantity=2) -> None:
        self.assertEqual([(order.action, order.quantity) for order in self.broker.placed("exit")],
                         [(action, quantity)])

    def test_long_without_a_stop_exits_at_thirty_seconds(self) -> None:
        self.block_stops()
        self.enter()
        deadline = self.deadline()
        self.assertGreater((deadline - self.clock.now).total_seconds(), 29)
        self.clock.advance(15)
        self.executor.step()
        self.assertEqual(self.broker.placed("exit"), [])
        self.clock.now = deadline - timedelta(milliseconds=1)
        self.executor.step()
        self.assertEqual(self.broker.placed("exit"), [])
        self.run_at_deadline()
        self.assert_exit("SELL")
        self.assertEqual(self.position(), 0)
        self.settle(12)
        self.assertEqual(len(self.broker.placed("entry")), 1)

    def test_short_without_a_stop_exits_at_thirty_seconds(self) -> None:
        self.block_stops()
        self.enter("short")
        self.run_at_deadline()
        self.assert_exit("BUY")
        self.assertEqual(self.position(), 0)

    def test_correct_stop_before_deadline_prevents_exit(self) -> None:
        original = self.broker.place
        self.block_stops()
        self.enter()
        self.clock.now = self.deadline() - timedelta(seconds=1)
        self.broker.place = original
        self.settle()
        self.clock.advance(60)
        self.settle()
        self.assertEqual(self.broker.placed("exit"), [])
        self.assertEqual(self.position(), 2)

    def test_pre_submitted_stop_counts_as_protection(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.orders[stop.order_id] = replace(stop, status="PreSubmitted")
        self.clock.advance(70)
        self.settle()
        self.assertIsNone(self.executor._protection.records[str(stop.con_id)]["deadline"])
        self.assertEqual(self.broker.placed("exit"), [])

    def test_wrong_quantity_side_contract_type_or_pending_stop_does_not_protect(self) -> None:
        # Inspect the timeout while normal repairs are blocked by an operator halt.
        for change in ({"quantity": 1}, {"quantity": 3}, {"action": "BUY"},
                       {"con_id": 999}, {"order_type": "LMT"},
                       {"status": "PendingSubmit"}, {"status": "ApiPending"}):
            with self.subTest(change=change):
                self.setUp()
                self.enter()
                stop = self.broker.working("stop")[0]
                self.broker.orders[stop.order_id] = replace(stop, **change)
                self.journal.halt("operator")
                self.executor.step()
                self.assertIsNotNone(self.executor._protection.records[str(stop.con_id)]["deadline"])

    def test_cancelled_long_stop_exits_after_sixty_seconds(self) -> None:
        self.enter()
        self.block_stops()
        self.broker.cancel(self.broker.working("stop")[0].order_id)
        cancelled_at = self.clock.now
        self.executor.step()
        self.assertEqual(self.deadline(), cancelled_at + timedelta(seconds=60))
        self.clock.now = cancelled_at + timedelta(seconds=59)
        self.executor.step()
        self.assertEqual(self.broker.placed("exit"), [])
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_cancelled_short_stop_exits_after_sixty_seconds(self) -> None:
        self.enter("short")
        self.block_stops()
        self.broker.cancel(self.broker.working("stop")[0].order_id)
        self.executor.step()
        self.run_at_deadline()
        self.assert_exit("BUY")

    def test_stop_replacement_clears_deadline_and_next_cancellation_gets_a_new_one(self) -> None:
        self.enter()
        original = self.broker.place
        self.block_stops()
        self.broker.cancel(self.broker.working("stop")[0].order_id)
        self.executor.step()
        first = self.deadline()
        self.clock.now = first - timedelta(seconds=1)
        self.broker.place = original
        self.settle()
        self.assertIsNone(self.executor._protection.records[str(contract().con_id)]["deadline"])
        self.clock.advance(30)
        self.block_stops()
        self.broker.cancel(self.broker.working("stop")[0].order_id)
        self.executor.step()
        self.assertGreater(self.deadline(), first)
        self.assertEqual(self.broker.placed("exit"), [])

    def test_planned_preopen_cancellation_uses_scheduled_exit_plus_grace(self) -> None:
        self.enter()
        self.clock.now = PREOPEN
        self.settle()
        self.assertEqual(self.broker.working("stop"), [])
        self.assertEqual(self.deadline(), OPEN + timedelta(seconds=30))
        self.clock.now = OPEN + timedelta(seconds=5)
        self.settle()
        self.assertEqual(self.broker.placed("exit"), [])
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_drift_rule_name_before_next_rth_open_keeps_the_planned_exception(self) -> None:
        cancel_at, flatten_at = OPEN - timedelta(minutes=3), OPEN - timedelta(minutes=2)
        plan = {"rule": "before_next_rth_open", "cancel_stop_at": cancel_at.isoformat(),
                "flatten_at": flatten_at.isoformat(), "minutes_before_open": "2"}
        self.executor.on_signal(target(1, "entry", plan=plan))
        self.settle()
        self.clock.now = cancel_at
        self.settle()
        self.assertEqual(self.broker.working("stop"), [])
        self.assertEqual(self.deadline(), flatten_at + timedelta(seconds=30))
        self.clock.now = flatten_at + timedelta(seconds=5)
        self.settle()
        self.assertEqual(self.broker.placed("exit"), [])
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_restart_preserves_entry_deadline(self) -> None:
        self.block_stops()
        self.enter()
        deadline = self.deadline()
        self.clock.advance(8)
        self.restart()
        self.assertEqual(self.deadline(), deadline)
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_restart_and_signal_change_do_not_reset_cancellation_deadline(self) -> None:
        self.enter()
        self.block_stops()
        self.broker.cancel(self.broker.working("stop")[0].order_id)
        self.executor.step()
        deadline = self.deadline()
        self.clock.advance(45)
        self.restart()
        self.executor.on_signal(target(2, "protective_stop_tightened", stop=30500))
        self.settle()
        self.assertEqual(self.deadline(), deadline)
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_disconnect_does_not_reset_an_existing_deadline(self) -> None:
        self.block_stops()
        self.enter()
        self.broker.disconnect()
        self.broker.connect_error = ConnectionError("offline")
        self.clock.advance(20)
        self.executor.step()
        self.assertEqual(self.broker.placed("exit"), [])
        self.broker.connect_error = None
        self.clock.advance(11)
        self.settle(12)
        self.assert_exit("SELL")

    def test_partial_entry_is_protected_at_actual_quantity_or_closed(self) -> None:
        self.broker.auto_fill = False
        self.block_stops()
        self.enter()
        entry = self.broker.working("entry")[0]
        self.broker.fill(entry.order_id, quantity=1)
        self.executor.step()
        self.broker.auto_fill = True
        self.run_at_deadline()
        self.assert_exit("SELL", 1)
        self.assertEqual(self.broker.orders[entry.order_id].status, "Cancelled")

    def test_more_partial_fills_do_not_extend_initial_deadline(self) -> None:
        self.broker.auto_fill = False
        self.block_stops()
        self.enter()
        entry = self.broker.working("entry")[0]
        self.broker.fill(entry.order_id, quantity=1)
        self.executor.step()
        deadline = self.deadline()
        self.clock.advance(8)
        self.broker.fill(entry.order_id, quantity=1)
        self.executor.step()
        self.assertEqual(self.deadline(), deadline)
        self.broker.auto_fill = True
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_fill_racing_entry_cancel_is_included_in_exit_quantity(self) -> None:
        self.broker.auto_fill = False
        self.block_stops()
        self.enter()
        entry = self.broker.working("entry")[0]
        self.broker.fill(entry.order_id, quantity=1)
        self.executor.step()
        cancel = self.broker.cancel

        def racing_cancel(oid):
            if oid == entry.order_id and self.broker.orders[oid].working:
                self.broker.fill(oid)
            cancel(oid)

        self.broker.cancel = racing_cancel
        self.broker.auto_fill = True
        self.run_at_deadline()
        self.assert_exit("SELL", 2)
        self.assertEqual(self.position(), 0)

    def test_incorrect_stop_filling_during_cancel_does_not_reverse_position(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.orders[stop.order_id] = replace(stop, quantity=1)
        self.journal.halt("operator")
        self.executor.step()
        cancel = self.broker.cancel

        def racing_cancel(oid):
            if oid == stop.order_id and self.broker.orders[oid].working:
                self.broker.fill(oid)
            cancel(oid)

        self.broker.cancel = racing_cancel
        self.run_at_deadline()
        self.assert_exit("SELL", 1)
        self.assertEqual(self.position(), 0)

    def test_no_duplicate_exit_while_it_is_working_including_restart(self) -> None:
        self.block_stops()
        self.enter()
        self.broker.auto_fill = False
        self.run_at_deadline()
        self.assert_exit("SELL")
        self.restart()
        self.clock.advance(30)
        self.settle(12)
        self.assert_exit("SELL")
        self.broker.fill(self.broker.working("exit")[0].order_id, quantity=1)
        self.settle(12)
        self.assert_exit("SELL")
        self.broker.fill(self.broker.working("exit")[0].order_id)
        self.settle(12)
        self.assertEqual(self.position(), 0)
        self.assertEqual(self.executor._protection.records, {})

    def test_halt_and_unacknowledged_stop_do_not_disable_timeout(self) -> None:
        place = self.broker.place

        def unacknowledged_stop(request, order_id=None):
            self.broker.acknowledge = request.purpose != "stop"
            return place(request, order_id)

        self.broker.place = unacknowledged_stop
        self.enter()
        self.clock.advance(6)
        self.executor.step()
        self.assertIn("not acknowledged", self.journal.halt_reason())
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_missing_target_does_not_disable_timeout(self) -> None:
        self.block_stops()
        self.enter()
        self.executor.target = None
        self.journal.halt("operator")
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_incomplete_snapshot_blocks_exit_until_reconciled(self) -> None:
        self.block_stops()
        self.enter()
        self.broker.snapshot_complete = False
        self.run_at_deadline()
        self.assertEqual(self.broker.placed("exit"), [])
        self.broker.snapshot_complete = True
        self.settle(12)
        self.assert_exit("SELL")

    def test_delayed_execution_callback_does_not_create_second_exit(self) -> None:
        self.block_stops()
        self.enter()
        self.broker.auto_fill = False
        self.run_at_deadline()
        exit_order = self.broker.working("exit")[0]
        self.broker.orders[exit_order.order_id] = replace(exit_order, filled=2, status="Filled")
        self.clock.advance(20)
        self.settle(12)
        self.assert_exit("SELL")
        self.broker.orders[exit_order.order_id] = exit_order
        self.broker.fill(exit_order.order_id)
        self.settle(12)
        self.assertEqual(self.position(), 0)

    def test_unowned_position_is_not_automatically_liquidated(self) -> None:
        value = contract()
        self.broker.contracts[value.con_id] = value
        self.broker.positions[value.con_id] = 1
        self.executor.step()
        self.clock.advance(100)
        self.settle(12)
        self.assertEqual(self.broker.placed("exit"), [])
        self.assertEqual(self.position(), 1)

    def test_partial_fill_with_matching_stop_does_not_exit(self) -> None:
        self.broker.auto_fill = False
        self.enter()
        self.broker.fill(self.broker.working("entry")[0].order_id, quantity=1)
        self.settle()
        self.assertEqual(self.broker.working("stop")[0].remaining, 1)
        self.clock.advance(31)
        self.settle()
        self.assertEqual(self.broker.placed("exit"), [])

    def test_oversized_stop_is_cancelled_before_market_exit(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.orders[stop.order_id] = replace(stop, quantity=3)
        self.journal.halt("operator")
        self.executor.step()
        self.run_at_deadline()
        self.assert_exit("SELL")
        self.assertEqual(self.broker.orders[stop.order_id].status, "Cancelled")
        self.assertEqual(self.position(), 0)

    def test_stray_stop_on_another_contract_is_cancelled_before_exit(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.orders[stop.order_id] = replace(stop, con_id=999)
        self.journal.halt("operator")
        self.executor.step()
        self.run_at_deadline()
        self.assert_exit("SELL")
        self.assertEqual(self.broker.working("stop"), [])

    def test_cancel_pending_order_cannot_race_market_exit(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.orders[stop.order_id] = replace(stop, quantity=1)
        self.journal.halt("operator")
        self.executor.step()

        def pending_cancel(oid):
            self.broker.orders[oid] = replace(self.broker.orders[oid], status="PendingCancel")

        self.broker.cancel = pending_cancel
        self.run_at_deadline()
        self.assertEqual(self.broker.placed("exit"), [])
        self.broker.orders[stop.order_id] = replace(stop, status="Cancelled")
        self.settle(12)
        self.assert_exit("SELL")

    def test_deadline_stays_latched_when_stop_arrives_late(self) -> None:
        place = self.broker.place
        self.block_stops()
        self.enter()
        self.clock.now = self.deadline()
        self.executor.step()
        from follow_executor.engine import stop_request

        place(stop_request(2, 30000, contract(), self.executor.target))
        self.settle(12)
        self.assert_exit("SELL")
        self.assertEqual(self.broker.working("stop"), [])

    def test_rejected_emergency_exit_is_retried_without_new_entry(self) -> None:
        self.block_stops()
        self.enter()
        self.broker.reject["exit"] = (201, "test rejection")
        self.run_at_deadline()
        self.assertEqual(self.position(), 2)
        self.assertEqual(len(self.broker.placed("exit")), 1)
        self.clock.advance(3)
        self.settle(12)
        self.assertEqual(self.position(), 0)
        self.assertEqual(len(self.broker.placed("exit")), 2)
        self.assertEqual(len(self.broker.placed("entry")), 1)

    def test_safety_snapshot_deferred_by_periodic_refresh_is_retried_immediately(self) -> None:
        self.block_stops()
        self.enter()
        refresh = self.broker.refresh

        def deferred_refresh():
            if self.broker.snapshot_complete:
                refresh()

        self.broker.refresh = deferred_refresh
        self.broker.snapshot_complete = False
        self.run_at_deadline()
        self.assertEqual(self.broker.placed("exit"), [])
        self.broker.snapshot_complete = True
        self.settle(12)
        self.assert_exit("SELL")

    def test_foreign_order_blocks_exit_until_reconciled(self) -> None:
        self.enter()
        self.block_stops()
        stop = self.broker.working("stop")[0]
        self.broker.orders[stop.order_id] = replace(stop, quantity=1, client_id=999)
        self.executor.step()
        self.run_at_deadline()
        self.assertEqual(self.broker.placed("exit"), [])
        self.assertEqual(self.broker.working("stop")[0].client_id, 999)
        self.broker.orders[stop.order_id] = replace(stop, status="Cancelled")
        self.settle(12)
        self.assert_exit("SELL")

    def test_initial_stop_pending_submission_does_not_satisfy_thirty_second_deadline(self) -> None:
        place = self.broker.place

        def pending_stop(request, order_id=None):
            oid = place(request, order_id)
            if request.purpose == "stop":
                self.broker.orders[oid] = replace(self.broker.orders[oid], status="PendingSubmit")
            return oid

        self.broker.place = pending_stop
        self.enter()
        self.assertGreater((self.deadline() - self.clock.now).total_seconds(), 29)
        self.assertLessEqual((self.deadline() - self.clock.now).total_seconds(), 30)
        self.run_at_deadline()
        self.assert_exit("SELL")
        self.assertEqual(self.broker.working("stop"), [])

    def test_planned_short_cancel_keeps_scheduled_exit_deadline(self) -> None:
        self.enter("short")
        self.clock.now = PREOPEN
        self.settle()
        self.assertEqual(self.deadline(), OPEN + timedelta(seconds=30))
        self.run_at_deadline()
        self.assert_exit("BUY")

    def test_planned_cancel_evidence_and_fixed_deadline_survive_restart(self) -> None:
        self.enter()
        self.clock.now = PREOPEN
        self.settle()
        self.clock.advance(65)
        self.restart()
        self.settle()
        self.assertEqual(self.broker.placed("exit"), [])
        self.assertEqual(self.deadline(), OPEN + timedelta(seconds=30))
        self.journal.halt("operator")
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_manual_cancel_near_open_does_not_get_planned_exception(self) -> None:
        self.enter()
        self.clock.now = PREOPEN + timedelta(seconds=2)
        self.broker.cancel(self.broker.working("stop")[0].order_id)
        self.executor.step()
        self.assertEqual(self.deadline(), self.clock.now + timedelta(seconds=60))
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_failed_planned_cancel_request_does_not_authorize_later_manual_cancel(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        cancel = self.broker.cancel

        def refused(oid):
            self.broker._reject(oid, 161, "cancel refused", cancel_refused=True)

        self.broker.cancel = refused
        self.clock.now = PREOPEN
        self.executor.step()
        self.journal.halt("operator")
        self.executor.step()
        self.broker.cancel = cancel
        cancel(stop.order_id)
        self.clock.advance(2)
        self.executor.step()
        self.assertEqual(self.deadline(), self.clock.now + timedelta(seconds=60))

    def test_invalid_long_cancel_window_gets_no_exception(self) -> None:
        self.enter()
        self.executor.on_signal(target(2, "reconciled", plan={
            "rule": "next_rth_open", "cancel_stop_at": (PREOPEN - timedelta(minutes=5)).isoformat(),
            "flatten_at": OPEN.isoformat(),
        }))
        self.clock.now = PREOPEN
        self.settle()
        self.assertLess(self.deadline(), OPEN + timedelta(seconds=1))

    def test_changing_the_plan_revokes_exception_without_restarting_sixty_seconds(self) -> None:
        self.enter()
        self.clock.now = PREOPEN
        self.settle()
        original_base = datetime.fromisoformat(
            self.executor._protection.records[str(contract().con_id)]["base_deadline"])
        self.clock.advance(40)
        self.executor.on_signal(target(2, "reconciled", plan={
            "rule": "next_rth_open", "cancel_stop_at": PREOPEN.isoformat(),
            "flatten_at": (OPEN + timedelta(hours=1)).isoformat(),
        }))
        self.executor.step()
        self.assertEqual(self.deadline(), original_base)
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_replacement_stop_consumes_the_planned_exception(self) -> None:
        self.enter()
        self.clock.now = PREOPEN
        self.settle()
        self.journal.halt("operator")
        oid = self.broker.place(stop_request(2, 30000, contract(), self.executor.target))
        self.settle()
        self.assertNotIn("planned_cancel", self.executor._protection.records[str(contract().con_id)])
        self.broker.cancel(oid)
        self.executor.step()
        self.assertEqual(self.deadline(), self.clock.now + timedelta(seconds=60))

    def test_entry_failure_near_planned_cancel_keeps_thirty_second_rule(self) -> None:
        self.clock.now = PREOPEN
        self.executor.on_signal(target(1, "entry", emitted=self.clock.now))
        self.settle()
        self.assertGreater((self.deadline() - self.clock.now).total_seconds(), 29)
        self.assertLessEqual((self.deadline() - self.clock.now).total_seconds(), 30)
        self.run_at_deadline()
        self.assert_exit("SELL")

    def test_planned_exit_grace_cannot_exceed_thirty_seconds(self) -> None:
        self.executor.config = replace(self.config, clock_exit_grace_seconds=300)
        self.enter()
        self.clock.now = PREOPEN
        self.settle()
        self.assertEqual(self.deadline(), OPEN + timedelta(seconds=30))
        self.run_at_deadline()
        self.assert_exit("SELL")

    def add_orphan_stop(self, direction="long"):
        request = stop_request(2 if direction == "long" else -2, 30000, contract(), self.executor.target)
        oid = self.broker.place(request)
        self.executor._record(oid, request, self.executor.target.trade_key if self.executor.target else None)
        return oid

    def test_flat_account_sell_stop_is_cancelled_without_market_order(self) -> None:
        oid = self.add_orphan_stop()
        self.settle(12)
        self.assertEqual(self.broker.orders[oid].status, "Cancelled")
        self.assertEqual(self.position(), 0)
        self.assertEqual(self.broker.placed("entry"), [])
        self.assertEqual(self.broker.placed("exit"), [])

    def test_flat_account_buy_stop_is_cancelled_even_while_halted(self) -> None:
        oid = self.add_orphan_stop("short")
        self.journal.halt("operator")
        self.settle(12)
        self.assertEqual(self.broker.orders[oid].status, "Cancelled")
        self.assertEqual(self.broker.placed("exit"), [])

    def test_orphan_cleanup_ignores_other_pending_ack_and_retries_cancel(self) -> None:
        from follow_executor.executor import Pending

        oid = self.add_orphan_stop()
        self.executor.pending[999] = Pending("place", self.clock.now, "entry")
        attempts = []

        def pending_cancel(order_id):
            attempts.append(order_id)
            self.broker.orders[order_id] = replace(self.broker.orders[order_id], status="PendingCancel")

        self.broker.cancel = pending_cancel
        self.settle(12)
        self.assertEqual(attempts, [oid])
        self.clock.advance(3)
        self.settle(3)
        self.assertEqual(attempts, [oid, oid])
        self.broker.orders[oid] = replace(self.broker.orders[oid], status="Cancelled")
        self.settle(12)
        self.assertEqual(self.executor._orphan_stops, {})

    def test_restart_during_orphan_cancellation_preserves_cleanup(self) -> None:
        oid = self.add_orphan_stop()

        def pending_cancel(order_id):
            self.broker.orders[order_id] = replace(self.broker.orders[order_id], status="PendingCancel")

        self.broker.cancel = pending_cancel
        self.settle()
        self.restart()
        self.settle()
        self.assertIn(str(oid), self.executor._orphan_stops)
        self.broker.orders[oid] = replace(self.broker.orders[oid], status="Cancelled")
        self.settle(12)
        self.assertEqual(self.executor._orphan_stops, {})
        self.assertEqual(self.broker.placed("exit"), [])

    def test_orphan_cancel_waits_for_complete_broker_snapshot(self) -> None:
        oid = self.add_orphan_stop()
        self.broker.snapshot_complete = False
        self.settle()
        self.assertTrue(self.broker.orders[oid].working)
        self.broker.snapshot_complete = True
        self.settle(12)
        self.assertEqual(self.broker.orders[oid].status, "Cancelled")

    def test_lagging_position_callback_does_not_cancel_a_valid_stop(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.positions[stop.con_id] = 0
        self.settle()
        self.assertTrue(self.broker.orders[stop.order_id].working)
        self.broker.positions[stop.con_id] = 2
        self.settle()
        self.assertTrue(self.broker.orders[stop.order_id].working)
        self.assertEqual(self.executor._orphan_stops, {})

    def test_manual_flatten_still_cancels_orphan_despite_journal_mismatch(self) -> None:
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.positions[stop.con_id] = 0  # An external manual close is not in our journal.
        self.settle()
        self.clock.advance(6)
        self.settle(12)
        self.assertEqual(self.broker.orders[stop.order_id].status, "Cancelled")
        self.assertIsNotNone(self.journal.halt_reason())
        self.assertEqual(self.broker.placed("exit"), [])

    def test_orphan_stop_fill_during_cancel_is_closed_without_reversal_loop(self) -> None:
        oid = self.add_orphan_stop()
        cancel = self.broker.cancel

        def racing_cancel(order_id):
            if order_id == oid and self.broker.orders[oid].working:
                self.broker.fill(oid)
            cancel(order_id)

        self.broker.cancel = racing_cancel
        self.settle(20)
        self.assert_exit("BUY")
        self.assertEqual(self.position(), 0)
        self.settle(12)
        self.assert_exit("BUY")

    def test_orphan_stops_and_pending_entry_are_cancelled_together(self) -> None:
        self.broker.auto_fill = False
        self.enter()
        entry = self.broker.working("entry")[0]
        oid = self.add_orphan_stop()
        self.settle(12)
        self.assertEqual(self.broker.orders[oid].status, "Cancelled")
        self.assertEqual(self.broker.orders[entry.order_id].status, "Cancelled")
        self.assertEqual(len(self.broker.placed("entry")), 1)
        self.assertEqual(self.broker.placed("exit"), [])

    def test_orphan_from_another_client_halts_without_cancelling_foreign_orders(self) -> None:
        oid = self.add_orphan_stop()
        self.broker.orders[oid] = replace(self.broker.orders[oid], client_id=999)
        self.settle(12)
        self.assertTrue(self.broker.orders[oid].working)
        self.assertIn("not placed by this executor", self.journal.halt_reason())
        self.assertEqual(self.broker.placed("exit"), [])

    def test_orphan_fill_after_manual_flatten_closes_only_the_new_owned_exposure(self) -> None:
        self.enter()
        oid = self.broker.working("stop")[0].order_id
        self.broker.positions[contract().con_id] = 0
        cancel = self.broker.cancel

        def racing_cancel(order_id):
            if order_id == oid and self.broker.orders[oid].working:
                self.broker.fill(oid)
            cancel(order_id)

        self.broker.cancel = racing_cancel
        self.settle()
        self.clock.advance(6)
        self.settle(20)
        self.assert_exit("BUY")
        self.assertEqual(self.position(), 0)
        self.assertIsNotNone(self.journal.halt_reason())

    def test_external_position_during_orphan_cancel_is_not_adopted(self) -> None:
        oid = self.add_orphan_stop()
        cancel = self.broker.cancel

        def external_trade(order_id):
            self.broker.positions[contract().con_id] = 1  # No executor fill.
            cancel(order_id)

        self.broker.cancel = external_trade
        self.settle(20)
        self.clock.advance(6)
        self.settle(12)
        self.assertEqual(self.broker.orders[oid].status, "Cancelled")
        self.assertEqual(self.position(), 1)
        self.assertEqual(self.broker.placed("exit"), [])
        self.assertIsNotNone(self.journal.halt_reason())

    def test_manual_flatten_and_resume_cancels_leftover_orphan_recovery_exit(self) -> None:
        self.enter()
        oid = self.broker.working("stop")[0].order_id
        self.broker.positions[contract().con_id] = 0
        self.broker.auto_fill = False
        cancel = self.broker.cancel

        def racing_cancel(order_id):
            if order_id == oid and self.broker.orders[oid].working:
                self.broker.fill(oid)
            cancel(order_id)

        self.broker.cancel = racing_cancel
        self.settle()
        self.clock.advance(6)
        self.settle(20)
        self.assertEqual(self.position(), -2)
        self.assertEqual(len(self.broker.working("exit")), 1)
        self.broker.positions[contract().con_id] = 0  # Operator closes the new short.
        self.journal.set_state("resume_requested", "now")
        self.settle(20)
        self.assertEqual(self.broker.working("exit"), [])
        self.assertEqual(self.position(), 0)
        self.assertEqual(self.executor._protection.records, {})
        self.assert_exit("BUY")
