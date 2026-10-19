# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import patch

from executor_support import target
from test_executor_service import ExecutorTestCase

from follow_executor.executor import Executor
from follow_executor.notifications import Notifications


class NotificationTests(ExecutorTestCase):
    def setUp(self):
        super().setUp()
        self.config = replace(self.config, discord_link_id="a" * 32)
        self.notifier = Notifications(self.config)
        self.addCleanup(self.notifier.close)
        self.executor.notifications = self.notifier

    def events(self):
        return [json.loads(row[0]) for row in self.notifier.db.execute("SELECT payload FROM outbox ORDER BY id")]

    def enter(self):
        self.executor.on_signal(target(1, "entry"))
        self.settle()

    def test_entry_is_long_and_stop_changes_cancellations_and_rejections_are_silent(self):
        self.enter()
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.events()[0]["kind"], "position")
        self.assertEqual(self.events()[0]["position"], "LONG")
        self.assertEqual((self.events()[0]["quantity"], self.events()[0]["price"]), (2, self.broker.market))
        self.executor.on_signal(target(2, "protective_stop_tightened", stop=30706.5))
        self.settle()
        stop = self.broker.working("stop")[0]
        self.broker._reject(stop.order_id, 161, 'private diagnostic', cancel_refused=True)
        self.broker.cancel(stop.order_id)
        self.notifier.observe(self.broker.state(), self.journal, self.clock())
        self.assertEqual(len(self.events()), 1)
        self.assertNotIn("DU1234567", json.dumps(self.events()))
        self.assertNotIn("private diagnostic", json.dumps(self.events()))

    def test_restart_does_not_repeat_positions(self):
        self.enter()
        self.executor = Executor(self.config, broker=self.broker, journal=self.journal,
                                 notifications=self.notifier, clock=self.clock)
        self.settle()
        self.assertEqual(len(self.events()), 1)

    def test_network_failure_keeps_same_event_for_retry(self):
        self.enter()
        first = self.events()[0]
        with patch.object(self.notifier, "transport", side_effect=TimeoutError), self.assertRaises(TimeoutError):
            self.notifier.send_one()
        self.assertEqual(self.events()[0], first)
        with patch.object(self.notifier, "transport", return_value={"accepted": True}) as send:
            self.assertTrue(self.notifier.send_one())
            self.assertEqual(send.call_args.args[2]["event"]["event_id"], first["event_id"])
        self.assertEqual(self.events(), [])

    def test_outbox_survives_database_reopen(self):
        self.enter()
        reopened = Notifications(self.config)
        try:
            self.assertEqual(reopened.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)
            reopened.observe(self.broker.state(), self.journal, self.clock())
            self.assertEqual(len(self.events()), 1)
        finally:
            reopened.close()

    def test_stop_execution_is_flat_with_gross_loss(self):
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.orders[stop.order_id] = replace(stop, status="Absent")
        self.notifier.observe(self.broker.state(), self.journal, self.clock())
        self.assertEqual(len(self.events()), 1)
        self.broker.orders[stop.order_id] = stop
        self.broker.trigger_stop()
        self.settle()
        flat = self.events()[-1]
        self.assertEqual(flat["position"], "FLAT")
        self.assertEqual(flat["quantity"], 2)
        self.assertAlmostEqual(flat["gross_pnl"], (stop.stop_price - self.broker.market) * 2 * 2)
        self.assertLess(flat["gross_pnl"], 0)

    def test_partial_fills_and_corrections_update_average_without_duplicate_trades(self):
        self.broker.auto_fill = False
        self.enter()
        entry = self.broker.working("entry")[0]
        self.broker.fill(entry.order_id, 1, 20150.25)
        fill = replace(self.broker.executions[-1], exec_id="0001.0002.0003.01")
        self.broker.executions[-1] = fill
        self.settle()
        self.broker.fill(entry.order_id, 1, 20150.75)
        self.settle()
        self.assertEqual([e["quantity"] for e in self.events()], [1, 2])
        self.assertEqual(self.events()[-1]["price"], 20150.5)
        self.broker.executions.append(replace(fill, exec_id="0001.0002.0003.02", price=20151.25))
        self.settle()
        self.assertTrue(self.events()[-1]["corrected"])
        self.assertEqual(self.events()[-1]["quantity"], 2)
        self.assertEqual(self.events()[-1]["price"], 20151.0)
        count = len(self.events())
        self.settle()
        self.assertEqual(len(self.events()), count)

    def test_first_enable_seeds_entry_history_then_reports_the_close(self):
        self.executor.notifications = None
        self.enter()
        state = self.broker.state()
        self.notifier.observe(replace(state, executions=()), self.journal, self.clock())
        self.notifier.observe(state, self.journal, self.clock())
        self.assertEqual(self.events(), [])
        self.executor.notifications = self.notifier
        stop = self.broker.working("stop")[0]
        self.broker.trigger_stop()
        self.settle()
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.events()[0]["position"], "FLAT")
        self.assertAlmostEqual(self.events()[0]["gross_pnl"], (stop.stop_price - self.broker.market) * 4)

    def test_partial_exit_is_not_flat_and_final_pnl_includes_both_exits(self):
        self.enter()
        stop = self.broker.working("stop")[0]
        self.broker.fill(stop.order_id, 1, self.broker.market + 10)
        self.settle()
        self.assertEqual(self.events()[-1]["position"], "LONG")
        self.assertEqual(self.events()[-1]["quantity"], 1)
        self.broker.fill(stop.order_id, 1, self.broker.market + 20)
        self.settle()
        flat = self.events()[-1]
        self.assertEqual(flat["position"], "FLAT")
        self.assertEqual(flat["gross_pnl"], 60)
        self.assertEqual(flat["price"], self.broker.market + 15)
        self.assertEqual(sum(e['position'] == 'FLAT' for e in self.events()), 1)

    def test_entry_rejection_does_not_announce_a_position(self):
        self.broker.reject['entry'] = (201, 'private broker diagnostic')
        self.enter()
        self.assertEqual(self.events(), [])

    def test_closed_trade_correction_reissues_flat_with_recomputed_profit(self):
        self.broker.auto_fill = False
        self.enter()
        self.broker.fill(self.broker.working('entry')[0].order_id)
        revised = replace(self.broker.executions[0], exec_id='0001.0002.0003.01')
        self.broker.executions[0] = revised
        self.settle()
        self.broker.trigger_stop()
        self.settle()
        old_pnl = self.events()[-1]['gross_pnl']
        corrected = replace(revised, exec_id='0001.0002.0003.02', price=revised.price + 1)
        self.broker.executions.append(corrected)
        self.settle()
        self.assertTrue(self.events()[-1]['corrected'])
        self.assertEqual(self.events()[-1]['position'], 'FLAT')
        self.assertEqual(self.events()[-1]['gross_pnl'], old_pnl - 4)

    def test_unchanged_fills_do_not_rescan_trade_history_on_every_loop(self):
        self.enter()
        with patch.object(self.journal, 'notification_executions', wraps=self.journal.notification_executions) as read:
            self.settle()
            read.assert_not_called()
