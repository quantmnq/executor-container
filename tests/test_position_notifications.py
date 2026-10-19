# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import unittest

from follow_executor.position_notifications import positions


def fill(index, side, quantity, price, purpose='entry', con_id=123):
    return {'exec_id': f'e{index}', 'order_id': index, 'con_id': con_id,
            'side': side, 'quantity': quantity, 'price': price, 'time': '20261014-18:30:45'}, {
                'order_id': index, 'con_id': con_id, 'purpose': purpose, 'quantity': quantity}


def project(*items, root='MNQ'):
    return list(positions([f for f, _ in items], {o['order_id']: o for _, o in items}, root).values())


class PositionNotificationTests(unittest.TestCase):
    def test_long_short_profit_loss_and_breakeven_in_usd(self):
        for side, exit_side, entry, exit_price, root, expected in (
            ('BOT', 'SLD', 20150.25, 20160.25, 'MNQ', 40),
            ('SLD', 'BOT', 20160.25, 20150.25, 'MNQ', 40),
            ('BOT', 'SLD', 20160.25, 20150.25, 'NQ', -400),
            ('SLD', 'BOT', 20150.25, 20160.25, 'NQ', -400),
            ('BOT', 'SLD', 20150.25, 20150.25, 'MNQ', 0),
        ):
            with self.subTest(side=side, root=root, expected=expected):
                result = project(fill(1, side, 2, entry), fill(2, exit_side, 2, exit_price, 'exit'), root=root)
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['event']['position'], 'FLAT')
                self.assertEqual(result[0]['event']['gross_pnl'], expected)

    def test_partial_entries_exits_and_scale_in_use_all_cash_flows(self):
        result = project(fill(1, 'BOT', 2, 100), fill(2, 'SLD', 1, 110, 'exit'),
                         fill(3, 'BOT', 1, 120), fill(4, 'SLD', 2, 130, 'exit'))
        event = result[0]['event']
        self.assertEqual(event['position'], 'FLAT')
        self.assertEqual(event['quantity'], 3)
        self.assertEqual(event['gross_pnl'], 100)

    def test_reversal_finishes_one_round_trip_and_opens_another(self):
        result = project(fill(1, 'BOT', 2, 100), fill(2, 'SLD', 3, 110))
        self.assertEqual([item['event']['position'] for item in result], ['FLAT', 'SHORT'])
        self.assertEqual(result[0]['event']['gross_pnl'], 40)
        self.assertEqual(result[1]['event']['quantity'], 1)
        self.assertEqual(result[1]['event']['price'], 110)

    def test_separate_contracts_and_successive_trades_never_mix_cost_basis(self):
        result = project(fill(1, 'BOT', 2, 100), fill(2, 'SLD', 1, 200, con_id=456),
                         fill(3, 'SLD', 2, 110, 'exit'), fill(4, 'BOT', 1, 190, 'exit', con_id=456),
                         fill(5, 'SLD', 1, 300), fill(6, 'BOT', 1, 310, 'exit'))
        self.assertEqual([item['event']['gross_pnl'] for item in result], [40, 20, -20])

    def test_correction_reprices_closed_round_trip_without_counting_twice(self):
        entry, order = fill(1, 'BOT', 2, 100)
        entry['exec_id'] = '0001.0002.0003.02'
        entry['price'] = 105
        result = project((entry, order), fill(2, 'SLD', 2, 110, 'exit'))
        self.assertEqual(result[0]['event']['gross_pnl'], 20)
        self.assertEqual(result[0]['event']['quantity'], 2)

    def test_missing_entry_basis_is_unavailable_and_partial_exit_is_not_flat(self):
        close, order = fill(1, 'SLD', 1, 110, 'exit')
        order['quantity'] = 2
        result = project((close, order))
        self.assertEqual(result[0]['event']['position'], 'LONG')
        self.assertIsNone(result[0]['event']['price'])
        close['quantity'] = 2
        result = project((close, order))
        self.assertEqual(result[0]['event']['position'], 'FLAT')
        self.assertIsNone(result[0]['event']['gross_pnl'])

    def test_unknown_orders_are_not_customer_trades(self):
        execution, _ = fill(1, 'BOT', 2, 100)
        self.assertEqual(positions([execution], {}, 'MNQ'), {})
