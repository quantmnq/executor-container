# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""No-order maintenance gate: complete account-wide positions and open orders."""
from __future__ import annotations

from .config import ConfigError
from .ibkr import IBKRBroker
from .maintenance_state import journal_snapshot


class FlatAccountProbe(IBKRBroker):
    def __init__(self, settings, root):
        super().__init__(settings, root)
        self.account_positions = {}
        self.account_orders = {}

    def on_position(self, account, contract, position, average_cost):
        if account == self.settings.account:
            self.account_positions[int(contract.conId)] = float(position)

    def on_open_order(self, order_id, contract, order, order_state):
        if order.account in ("", self.settings.account) and not getattr(order, "whatIf", False):
            self.account_orders[order_id] = order_state.status not in ("Filled", "Cancelled", "ApiCancelled", "Inactive")

    def place(self, *args, **kwargs):
        raise ConfigError("Maintenance cannot place orders.")

    def cancel(self, *args, **kwargs):
        raise ConfigError("Maintenance cannot cancel orders.")

    def what_if(self, *args, **kwargs):
        raise ConfigError("Maintenance does not submit what-if orders.")


def check(config) -> dict:
    report = journal_snapshot(config)
    broker = FlatAccountProbe(config.ibkr, config.root)
    try:
        broker.connect()
        if config.ibkr.account not in broker.managed_accounts:
            raise ConfigError("The configured account is not managed by this Gateway login.")
        broker.refresh()
        broker.wait_for_snapshot()
        if any(broker.account_positions.values()) or any(broker.account_orders.values()):
            raise ConfigError("The account has positions or working orders; maintenance was refused.")
        report["account_flat"] = True
        report["orders_submitted"] = 0
        return report
    finally:
        broker.disconnect()
