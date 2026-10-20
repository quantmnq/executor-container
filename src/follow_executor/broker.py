# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Broker-neutral types the executor works with, and the broker interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

ORDER_REF_PREFIX = "fx:"
WORKING_STATUSES = frozenset(
    {"ApiPending", "PendingSubmit", "PreSubmitted", "Submitted", "PendingCancel"}
)
MULTIPLIERS = {"NQ": 20.0, "MNQ": 2.0}


@dataclass(frozen=True)
class FutureContract:
    con_id: int
    root: str
    contract_month: str
    last_trade_date: str
    multiplier: float


@dataclass(frozen=True)
class OrderRequest:
    purpose: str  # entry, stop or exit
    contract: FutureContract
    action: str  # BUY or SELL
    order_type: str  # MKT, LMT or STP
    quantity: int
    order_ref: str
    limit_price: float | None = None
    stop_price: float | None = None
    tif: str = "DAY"
    outside_rth: bool = False


@dataclass(frozen=True)
class OrderView:
    order_id: int
    con_id: int
    root: str
    action: str
    order_type: str
    quantity: int
    filled: int
    status: str
    order_ref: str
    client_id: int
    stop_price: float | None = None
    limit_price: float | None = None

    @property
    def working(self) -> bool:
        return self.status in WORKING_STATUSES

    @property
    def remaining(self) -> int:
        return max(self.quantity - self.filled, 0)

    @property
    def purpose(self) -> str | None:
        """Purpose encoded in this executor's order reference, if it is ours."""

        if not self.order_ref.startswith(ORDER_REF_PREFIX):
            return None
        return self.order_ref[len(ORDER_REF_PREFIX):].split(":", 1)[0] or None


@dataclass(frozen=True)
class Execution:
    exec_id: str
    order_id: int
    con_id: int
    side: str  # BOT or SLD
    quantity: int
    price: float
    order_ref: str
    time: str

    @property
    def signed_quantity(self) -> int:
        return self.quantity if self.side == "BOT" else -self.quantity


@dataclass(frozen=True)
class Rejection:
    """A broker refusal tied to one order; ``seq`` increases monotonically."""

    seq: int
    order_id: int
    code: int
    message: str
    cancel_refused: bool = False


@dataclass(frozen=True)
class BrokerState:
    """A consistent copy of the broker's view of the executor's root."""

    connected: bool
    positions: dict[int, int] = field(default_factory=dict)
    average_prices: dict[int, float] = field(default_factory=dict)
    contracts: dict[int, FutureContract] = field(default_factory=dict)
    orders: dict[int, OrderView] = field(default_factory=dict)
    executions: tuple[Execution, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    as_of: datetime | None = None
    snapshot_id: int = 0
    snapshot_complete: bool = True


@dataclass(frozen=True)
class MarginEstimate:
    init_margin_after: float
    equity_with_loan_after: float
    warning: str = ""


class Broker(Protocol):
    @property
    def is_connected(self) -> bool: ...

    @property
    def managed_accounts(self) -> tuple[str, ...]: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def refresh(self) -> None:
        """Re-request positions, every open order and today's executions."""

    def resolve(self, root: str, contract_month: str) -> FutureContract: ...

    def state(self) -> BrokerState: ...

    def place(self, request: OrderRequest, order_id: int | None = None) -> int:
        """Place a new order, or modify ``order_id``; return the order id."""

    def cancel(self, order_id: int) -> None: ...

    def what_if(self, request: OrderRequest) -> MarginEstimate: ...
