# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import json
import threading
from dataclasses import replace
from unittest.mock import Mock, patch

from executor_support import contract, target
from test_executor_service import ExecutorTestCase

from follow_executor.notifications import Notifications
from follow_executor.signal import Heartbeat


class ServiceNotificationsTests(ExecutorTestCase):
    def setUp(self):
        super().setUp()
        self.config = replace(self.config, discord_link_id='a' * 32)
        self.notifier = Notifications(self.config)
        self.addCleanup(self.notifier.close)
        self.executor.notifications = self.notifier
        self.health = {'connected': False, 'reconciled': False, 'market_data': 'idle'}
        self.broker.health = lambda: dict(self.health)
        self.broker.monitor_market_data = Mock()

    def events(self, topic=None):
        events = [json.loads(row[0]) for row in self.notifier.db.execute('SELECT payload FROM outbox ORDER BY id')]
        return [event for event in events if event.get('topic') == topic] if topic else events

    def settle_health(self, seconds=6):
        self.executor.step()
        self.clock.advance(seconds)
        self.executor.step()

    def test_recovery_requires_api_reconciliation_and_quotes_and_is_not_repeated(self):
        self.executor.step()
        self.executor.step()
        self.assertEqual([e['state'] for e in self.events('gateway')], ['api_unavailable'])
        self.health.update(connected=True)
        self.settle_health(31)
        self.assertEqual(self.events('gateway')[-1]['state'], 'reconciling')
        self.health.update(reconciled=True, market_data='pending')
        self.settle_health(31)
        self.assertEqual(self.events('gateway')[-1]['state'], 'market_data_waiting')
        self.health.update(market_data='ready')
        self.settle_health()
        self.assertEqual(self.events('gateway')[-1]['state'], 'ready')
        self.assertEqual(self.events('gateway')[-1]['previous'], 'market_data_waiting')
        count = len(self.events('gateway'))
        self.settle_health()
        self.assertEqual(len(self.events('gateway')), count)
        self.assertNotIn('DU1234567', json.dumps(self.events()))

    def test_short_recovery_does_not_clear_a_persistent_outage(self):
        self.executor.step()
        self.health.update(connected=True, reconciled=True, market_data='ready')
        self.executor.step()
        self.clock.advance(1)
        self.health.update(connected=False)
        self.executor.step()
        self.assertEqual([e['state'] for e in self.events('gateway')], ['api_unavailable'])

    def test_position_mismatch_blocks_ready_and_halt_is_announced_once(self):
        self.health.update(connected=True, reconciled=True, market_data='ready')
        self.executor._service_started = True
        self.broker.positions[contract().con_id] = 1
        self.broker.contracts[contract().con_id] = contract()
        self.settle_health()
        self.settle_health()
        self.assertEqual(self.events('gateway')[-1]['state'], 'reconciliation_required')
        self.assertEqual([e['state'] for e in self.events('executor')].count('halted'), 1)
        self.assertNotIn('ready', [e['state'] for e in self.events('gateway')])

    def test_feed_outage_before_first_heartbeat_and_during_gateway_outage(self):
        self.broker.connect_error = ConnectionError('private diagnostic text')
        self.executor.step()
        self.clock.advance(self.config.heartbeat_timeout_seconds + 1)
        self.executor.step()
        self.assertEqual(self.events('signal_feed')[-1]['state'], 'unavailable')
        self.executor.on_heartbeat(Heartbeat(self.config.stream, 1, self.clock()))
        self.executor.step()
        self.assertEqual(self.events('signal_feed')[-1]['state'], 'unavailable')
        self.executor.on_signal(target(1, 'exit', 'flat'))
        self.executor.step()
        self.assertEqual(self.events('signal_feed')[-1]['state'], 'ready')
        self.assertNotIn('private diagnostic text', json.dumps(self.events()))

    def test_outbox_reopen_preserves_status_deduplication(self):
        self.notifier.status('gateway', 'api_unavailable', self.clock())
        reopened = Notifications(self.config)
        try:
            reopened.status('gateway', 'api_unavailable', self.clock())
            self.assertEqual(len(self.events('gateway')), 1)
            reopened.status('gateway', 'ready', self.clock())
            self.assertEqual(len(self.events('gateway')), 2)
        finally:
            reopened.close()

    def test_heartbeat_cannot_keep_a_stalled_loop_alive_but_can_report_shutdown(self):
        with patch.object(self.notifier, 'transport', return_value={'accepted': True}) as send:
            self.notifier._last_pulse -= 61
            self.notifier.heartbeat()
            send.assert_not_called()
            self.notifier.pulse()
            self.notifier.heartbeat()
            self.assertEqual(send.call_args.args[1], 'heartbeat')
            self.assertTrue(send.call_args.args[2]['running'])
            self.notifier.status('executor', 'stopped', self.clock())
            self.notifier.heartbeat()
            self.assertFalse(send.call_args.args[2]['running'])

    def test_normal_shutdown_drains_started_and_stopped_messages_without_trading(self):
        delivered = []

        def transport(_config, path, body):
            delivered.append((path, body))
            return {'accepted': True}

        stop = threading.Event()
        stop.set()
        with patch.object(self.notifier, 'transport', side_effect=transport):
            self.executor.run(stop, acks_thread=False)
        events = [body['event'] for path, body in delivered if path == 'events']
        self.assertEqual([e['state'] for e in events], ['starting', 'stopped'])
        beats = [body for path, body in delivered if path == 'heartbeat']
        self.assertFalse(beats[-1]['running'])
        self.assertEqual(self.broker.placed('entry'), [])

    def test_bad_heartbeat_endpoint_does_not_hold_order_and_stop_delivery(self):
        delivered = []
        self.notifier.status('executor', 'stopped', self.clock())

        def transport(_config, path, body):
            if path == 'heartbeat':
                raise ConnectionError('unavailable')
            delivered.append(body)
            return {'accepted': True}

        stop = threading.Event()
        stop.set()
        with patch.object(self.notifier, 'transport', side_effect=transport):
            self.notifier.run(stop)
        self.assertEqual(delivered[0]['event']['state'], 'stopped')

    def test_quote_probe_failure_cannot_prevent_protective_orders(self):
        self.broker.monitor_market_data.side_effect = RuntimeError('health probe failed')
        self.executor.on_signal(target(1, 'entry'))
        self.settle()
        self.assertEqual(len(self.broker.placed('entry')), 1)
        self.assertEqual(len(self.broker.working('stop')), 1)
