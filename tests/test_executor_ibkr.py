# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
from __future__ import annotations

import unittest

from executor_support import ACCOUNT, contract

from follow_executor.broker import OrderRequest
from follow_executor.config import IBKRSettings

try:
    from ibapi.contract import Contract, ContractDetails
    from ibapi.execution import Execution
    from ibapi.order import Order
    from ibapi.order_state import OrderState
except ImportError:  # pragma: no cover - ibapi is installed by followers, not from PyPI
    Contract = None

SETTINGS = IBKRSettings("127.0.0.1", 4002, 71, ACCOUNT, "paper", 2.0)


def ib_contract(symbol: str = "MNQ", con_id: int = 2026121) -> Contract:
    value = Contract()
    value.conId, value.symbol, value.secType = con_id, symbol, "FUT"
    value.exchange, value.currency, value.multiplier = "CME", "USD", "2"
    value.lastTradeDateOrContractMonth = "20261218"
    return value


def ib_order(order_type: str = "STP", ref: str = "fx:stop:2", what_if: bool = False) -> Order:
    order = Order()
    order.account, order.action, order.orderType = ACCOUNT, "SELL", order_type
    order.totalQuantity, order.orderRef, order.clientId = 2, ref, 71
    order.auxPrice = 30452.75 if order_type == "STP" else order.auxPrice
    order.whatIf = what_if
    return order


def ib_state(status: str = "Submitted", **margin: str) -> OrderState:
    state = OrderState()
    state.status = status
    for key, value in margin.items():
        setattr(state, key, value)
    return state


class StubApp:
    """Stands in for EClient: records requests and answers some of them."""

    def __init__(self, broker) -> None:
        self.broker = broker
        self.calls: list[tuple] = []
        self.what_if_state = ib_state("PreSubmitted", initMarginAfter="2345.6", equityWithLoanAfter="100000.0")

    def isConnected(self) -> bool:
        return True

    def placeOrder(self, order_id, contract, order) -> None:
        self.calls.append(("placeOrder", order_id, contract, order))
        if order.whatIf:
            self.broker.on_open_order(order_id, contract, order, self.what_if_state)

    def cancelOrder(self, order_id, cancel) -> None:
        self.calls.append(("cancelOrder", order_id))

    def reqContractDetails(self, request_id, query) -> None:
        details = ContractDetails()
        details.contract = ib_contract()
        self.broker._details[request_id].append(details)
        self.broker._detail_events[request_id].set()

    def disconnect(self) -> None:
        pass


@unittest.skipIf(Contract is None, "ibapi is not installed")
class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        from follow_executor.ibkr import IBKRBroker

        self.updates = 0
        self.broker = IBKRBroker(SETTINGS, "MNQ", on_update=self.count)
        self.app = StubApp(self.broker)
        self.broker._app = self.app
        self.broker._ready.set()
        self.broker._next_id = 10

    def count(self) -> None:
        self.updates += 1

    def test_positions_are_filtered_to_the_account_and_root(self) -> None:
        self.broker.on_position(ACCOUNT, ib_contract(), 2.0, 61561.25)
        self.broker.on_position("DU0000001", ib_contract(), 5.0, 1.0)
        self.broker.on_position(ACCOUNT, ib_contract("NQ", 7), 1.0, 1.0)
        state = self.broker.state()
        self.assertEqual(state.positions, {2026121: 2})
        self.assertEqual(state.average_prices, {2026121: 30780.625})
        self.assertEqual(state.contracts[2026121].contract_month, "202612")
        self.assertGreater(self.updates, 0)

    def test_orders_merge_status_and_unseen_ones_become_absent(self) -> None:
        self.broker.on_order_status(5, "PreSubmitted", 0)
        self.broker.on_open_order(5, ib_contract(), ib_order(), ib_state("PreSubmitted"))
        order = self.broker.state().orders[5]
        self.assertEqual((order.purpose, order.stop_price, order.working, order.client_id),
                         ("stop", 30452.75, True, 71))
        self.broker.on_order_status(5, "Filled", 2)
        self.assertFalse(self.broker.state().orders[5].working)

        self.broker.on_open_order(6, ib_contract(), ib_order(ref="fx:stop:3"), ib_state())
        self.broker._open_seen = set()
        self.broker.on_open_order_end()
        self.assertEqual(self.broker.state().orders[6].status, "Absent")

    def test_executions_are_filtered_and_kept_once(self) -> None:
        execution = Execution()
        execution.execId, execution.acctNumber, execution.orderId = "0001.0002.01.01", ACCOUNT, 5
        execution.side, execution.shares, execution.price = "SLD", 2, 30452.75
        execution.orderRef, execution.time = "fx:stop:2", "20261002 09:00:00"
        self.broker.on_execution(ib_contract(), execution)
        self.broker.on_execution(ib_contract(), execution)
        other = Execution()
        other.acctNumber = "DU0000001"
        self.broker.on_execution(ib_contract(), other)
        (item,) = self.broker.state().executions
        self.assertEqual((item.side, item.quantity, item.signed_quantity), ("SLD", 2, -2))

    def test_orders_are_built_with_account_reference_and_prices(self) -> None:
        stop = OrderRequest("stop", contract(), "SELL", "STP", 2, "fx:stop:2", stop_price=30452.75,
                            tif="GTC", outside_rth=True)
        order_id = self.broker.place(stop)
        _kind, placed_id, ib_contract_sent, order = self.app.calls[-1]
        self.assertEqual(order_id, placed_id)
        self.assertEqual((order.account, order.orderType, order.auxPrice, order.tif, order.outsideRth,
                          order.orderRef, order.totalQuantity, order.transmit),
                         (ACCOUNT, "STP", 30452.75, "GTC", True, "fx:stop:2", 2, True))
        self.assertEqual((ib_contract_sent.conId, ib_contract_sent.exchange), (2026121, "CME"))
        limit = OrderRequest("entry", contract(), "BUY", "LMT", 2, "fx:entry:1", limit_price=30790.25)
        self.broker.place(limit)
        self.assertEqual(self.app.calls[-1][3].lmtPrice, 30790.25)
        self.broker.place(stop, order_id)
        self.assertEqual(self.app.calls[-1][1], order_id)

    def test_errors_become_rejections_only_for_known_orders(self) -> None:
        order_id = self.broker.place(OrderRequest("exit", contract(), "SELL", "MKT", 2, "fx:exit:4"))
        self.broker.on_error(order_id, 2109, "outside RTH ignored")
        self.broker.on_error(order_id, 202, "Order Canceled")
        self.broker.on_error(999, 201, "someone else's order")
        self.broker.on_error(order_id, 201, "Order rejected - reason: margin")
        self.broker.on_error(order_id, 161, "Cancel attempted when order is not in a cancellable state")
        rejections = self.broker.state().rejections
        self.assertEqual([(r.code, r.cancel_refused) for r in rejections], [(201, False), (161, True)])
        self.assertLess(rejections[0].seq, rejections[1].seq)
        self.broker.on_error(-1, 1100, "Connectivity between IB and TWS has been lost")
        self.assertFalse(self.broker.is_connected)

    def test_failed_connection_attempts_are_not_logged_as_warnings(self) -> None:
        message = "Couldn't connect to TWS. Confirm that API is enabled\nand the port matches."
        with self.assertNoLogs("follow_executor.ibkr", level="WARNING"):
            self.broker.on_error(-1, 502, message)
            self.broker.on_error(-1, 504, "Not connected")
        with self.assertLogs("follow_executor.ibkr", level="WARNING"):
            self.broker.on_error(-1, 1100, "Connectivity between IB and TWS has been lost")

    def test_what_if_reads_margin_and_never_records_an_order(self) -> None:
        request = OrderRequest("entry", contract(), "BUY", "MKT", 2, "fx:whatif:0")
        estimate = self.broker.what_if(request)
        self.assertEqual((estimate.init_margin_after, estimate.equity_with_loan_after), (2345.6, 100000.0))
        self.assertTrue(self.app.calls[-1][3].whatIf)
        self.assertEqual(self.broker.state().orders, {})
        self.app.what_if_state = ib_state("PreSubmitted", initMarginAfter="1.7976931348623157E308",
                                          equityWithLoanAfter="100000.0")
        with self.assertRaises(RuntimeError):
            self.broker.what_if(request)

    def test_contract_resolution_needs_exactly_one_match(self) -> None:
        resolved = self.broker.resolve("MNQ", "202612")
        self.assertEqual((resolved.con_id, resolved.multiplier, resolved.last_trade_date),
                         (2026121, 2.0, "20261218"))


class ExecutionCorrectionTests(unittest.TestCase):
    def test_a_corrected_execution_replaces_its_original(self) -> None:
        import tempfile
        from pathlib import Path

        from follow_executor.broker import Execution as Fill
        from follow_executor.journal import Journal

        with tempfile.TemporaryDirectory() as directory:
            journal = Journal(Path(directory) / "j.sqlite3")
            first = Fill("0001f4e8.6578a1b2.01.01", 5, 2026121, "BOT", 2, 30780.25, "fx:entry:1", "t")
            self.assertTrue(journal.record_execution(first))
            self.assertFalse(journal.record_execution(first))
            corrected = Fill("0001f4e8.6578a1b2.01.02", 5, 2026121, "BOT", 1, 30780.25, "fx:entry:1", "t")
            self.assertFalse(journal.record_execution(corrected))
            self.assertEqual(journal.expected_positions(), {2026121: 1})
            self.assertFalse(journal.record_execution(first))
            self.assertEqual(journal.expected_positions(), {2026121: 1})
            journal.close()


if __name__ == "__main__":
    unittest.main()

@unittest.skipIf(Contract is None, "ibapi is not installed")
class HealthAdapterTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import Mock

        from follow_executor.ibkr import IBKRBroker

        self.broker = IBKRBroker(SETTINGS, "MNQ")
        self.callbacks = self.broker._app
        self.app = Mock()
        self.app.isConnected.return_value = True
        self.broker._app = self.app
        self.broker._ready.set()

    def subscription(self):
        self.broker.monitor_market_data([contract()])
        return self.app.reqMktData.call_args.args[0]

    def test_safety_snapshot_id_requires_positions_orders_and_executions(self):
        self.assertFalse(self.broker.state().snapshot_complete)
        self.broker.refresh()
        first = self.broker.state().snapshot_id
        self.callbacks.positionEnd()
        self.callbacks.openOrderEnd()
        self.assertFalse(self.broker.state().snapshot_complete)
        self.broker.refresh()  # An in-flight request is not replaced.
        self.assertEqual(self.broker.state().snapshot_id, first)
        self.callbacks.execDetailsEnd(self.broker._execution_request_id)
        self.assertTrue(self.broker.state().snapshot_complete)
        self.broker.refresh()
        self.assertGreater(self.broker.state().snapshot_id, first)
        self.assertFalse(self.broker.state().snapshot_complete)

    def ready_quote(self, req_id):
        self.callbacks.marketDataType(req_id, 1)
        self.callbacks.tickPrice(req_id, 1, 20150.25, None)

    def test_live_subscription_needs_data_type_and_valid_quote(self):
        req_id = self.subscription()
        self.assertEqual(self.app.reqMktData.call_args.args[3:5], (False, False))
        self.assertEqual(self.broker.health()["market_data"], "pending")
        self.callbacks.marketDataType(req_id, 1)
        for value in (-1, 0, float('nan')):
            self.callbacks.tickPrice(req_id, 1, value, None)
        self.callbacks.tickPrice(req_id, 9, 20150, None)  # Closing price is not live confirmation.
        self.assertEqual(self.broker.health()["market_data"], "pending")
        self.ready_quote(req_id)
        self.assertEqual(self.broker.health()["market_data"], "ready")
        self.app.placeOrder.assert_not_called()

    def test_farm_restoration_requires_a_new_subscription_and_new_quotes(self):
        req_id = self.subscription()
        self.ready_quote(req_id)
        self.broker.on_error(-1, 2103, 'Market data farm is disconnected:usfarm')
        self.broker.on_error(-1, 2104, 'Market data farm connection is OK:eufarm')
        self.assertEqual(self.broker.health()["market_data"], "unavailable")
        self.broker.on_error(-1, 2104, 'Market data farm connection is OK:usfarm')
        replacement = self.subscription()
        self.assertNotEqual(req_id, replacement)
        self.ready_quote(req_id)  # A late callback from the old request cannot confirm recovery.
        self.assertEqual(self.broker.health()["market_data"], "pending")
        self.ready_quote(replacement)
        self.assertEqual(self.broker.health()["market_data"], "ready")
        self.broker.on_error(-1, 2108, 'Inactive but available on demand:usfarm')
        self.assertEqual(self.broker.health()["market_data"], "ready")

    def test_denied_delayed_and_changed_contracts_never_claim_live_readiness(self):
        req_id = self.subscription()
        self.broker.on_error(req_id, 354, 'Subscription missing for a private account')
        self.assertEqual(self.broker.health()["market_data"], "denied")
        self.assertEqual(self.broker.market_data_errors(), [354])
        self.broker.on_error(req_id, 10197, 'Competing session with private account details')
        self.assertEqual(self.broker.market_data_errors(), [10197])
        self.assertEqual(self.broker.state().rejections, ())
        self.callbacks.marketDataType(req_id, 3)
        self.callbacks.tickPrice(req_id, 66, 20150, None)
        self.assertEqual(self.broker.health()["market_data"], "delayed")
        self.broker.monitor_market_data([contract('202703')])
        replacement = self.app.reqMktData.call_args.args[0]
        self.app.cancelMktData.assert_called_with(req_id)
        self.ready_quote(req_id)
        self.assertEqual(self.broker.health()["market_data"], "pending")
        self.ready_quote(replacement)
        self.assertEqual(self.broker.health()["market_data"], "ready")
        self.assertEqual(self.broker.market_data_errors(), [])

    def test_reconciliation_and_data_loss_reset_readiness(self):
        req_id = self.subscription()
        self.ready_quote(req_id)
        self.broker._positions_end.set()
        self.broker._orders_end.set()
        self.assertFalse(self.broker.health()["reconciled"])
        self.broker._execution_request_id = 9
        self.callbacks.execDetailsEnd(9)
        self.assertTrue(self.broker.health()["reconciled"])
        self.broker.on_error(-1, 1101, 'Restored, data lost')
        self.assertFalse(self.broker.health()["connected"])
        self.assertFalse(self.broker.health()["reconciled"])
        self.assertEqual(self.broker._market_requests, {})

    def test_incomplete_periodic_snapshot_does_not_emit_false_recovery(self):
        from unittest.mock import patch

        self.broker._reconciled = True
        with patch('follow_executor.ibkr.time.monotonic', return_value=100):
            self.broker.refresh()
            self.assertTrue(self.broker.health()["reconciled"])
        with patch('follow_executor.ibkr.time.monotonic', return_value=107):
            self.assertFalse(self.broker.health()["reconciled"])
