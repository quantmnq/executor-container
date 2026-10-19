# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Pure decisions: from the latest target and the broker's state to orders.

Trade statuses, per leader trade (``Target.trade_key``):

- ``entering``: an entry order was sent.
- ``entered``: a position for this trade was held.
- ``missed``: the entry deadline passed while flat.
- ``refused``: the margin or stop-risk check refused the entry.
- ``rejected``: the broker rejected the entry.
- ``closing``: the executor itself is exiting (exit-plan fallback, or a stop
  the broker refused).
- ``closed``: flat after an executor exit.

Any status blocks a new entry for that trade, so a follower never re-enters a
trade it has left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .broker import ORDER_REF_PREFIX, FutureContract, OrderRequest, OrderView
from .signal import Target, round_down, round_up

EXECUTOR_EXIT_STATUSES = frozenset({"closing", "closed"})


@dataclass(frozen=True)
class Place:
    request: OrderRequest
    trade_key: str | None


@dataclass(frozen=True)
class Modify:
    order_id: int
    request: OrderRequest


@dataclass(frozen=True)
class Cancel:
    order_id: int
    reason: str


@dataclass(frozen=True)
class MarkTrade:
    trade_key: str
    status: str
    reason: str


@dataclass(frozen=True)
class Halt:
    reason: str


Action = Place | Modify | Cancel | MarkTrade | Halt


@dataclass(frozen=True)
class View:
    now: datetime
    target: Target | None
    quantity: int
    slippage_points: float
    clock_exit_grace: timedelta
    position: int = 0
    position_contract: FutureContract | None = None
    target_contract: FutureContract | None = None
    stops: tuple[OrderView, ...] = ()
    entries: tuple[OrderView, ...] = ()
    exits: tuple[OrderView, ...] = ()
    order_trades: dict[int, str | None] = field(default_factory=dict)
    trade_status: str | None = None
    entry_price: float | None = None


def stop_cancel_due(target: Target | None, now: datetime) -> bool:
    plan = target.exit_plan if target is not None else None
    return bool(plan and plan.cancel_stop_at and now >= plan.cancel_stop_at)


def flatten_due(target: Target | None, now: datetime, grace: timedelta) -> bool:
    plan = target.exit_plan if target is not None else None
    return bool(plan and plan.flatten_at and now >= plan.flatten_at + grace)


def order_ref(purpose: str, target: Target | None) -> str:
    return f"{ORDER_REF_PREFIX}{purpose}:{0 if target is None else target.seq}"


def entry_request(view: View, target: Target, contract: FutureContract) -> OrderRequest:
    assert target.entry is not None
    action = "BUY" if target.direction > 0 else "SELL"
    reference = target.entry.reference_price
    if reference is None:
        return OrderRequest("entry", contract, action, "MKT", view.quantity, order_ref("entry", target))
    limit = (
        round_up(reference + view.slippage_points)
        if action == "BUY"
        else round_down(reference - view.slippage_points)
    )
    return OrderRequest(
        "entry", contract, action, "LMT", view.quantity, order_ref("entry", target), limit_price=limit
    )


def exit_request(position: int, contract: FutureContract, target: Target | None) -> OrderRequest:
    action = "SELL" if position > 0 else "BUY"
    return OrderRequest("exit", contract, action, "MKT", abs(position), order_ref("exit", target))


def stop_request(
    position: int, price: float, contract: FutureContract, target: Target | None, ref: str | None = None
) -> OrderRequest:
    return OrderRequest(
        "stop",
        contract,
        "SELL" if position > 0 else "BUY",
        "STP",
        abs(position),
        ref or order_ref("stop", target),
        stop_price=price,
        tif="GTC",
        outside_rth=True,
    )


def desired_stop(view: View, target: Target, direction: int) -> float | None:
    """The leader's stop; before it is known, one sized from the follower's own fill."""

    if stop_cancel_due(target, view.now):
        return None
    if target.stop is not None:
        return target.stop
    entry = target.entry
    if entry is not None and entry.atr and entry.stop_atr and view.entry_price:
        distance = entry.atr * entry.stop_atr
        if direction > 0:
            return round_down(view.entry_price - distance)
        return round_up(view.entry_price + distance)
    return None


def decide(view: View) -> list[Action]:
    target = view.target
    key = target.trade_key if target is not None else None
    direction = target.direction if target is not None else 0
    position = view.position
    actions: list[Action] = []
    flat_reason = "target flat"

    if direction and view.trade_status in EXECUTOR_EXIT_STATUSES:
        direction, flat_reason = 0, "executor exit"
    elif direction and flatten_due(target, view.now, view.clock_exit_grace):
        direction, flat_reason = 0, "exit plan fallback"
        if position or view.stops or view.entries:
            assert key is not None
            actions.append(MarkTrade(key, "closing", flat_reason))

    contract = view.position_contract if position else view.target_contract

    def entry_valid(order: OrderView) -> bool:
        return bool(
            direction
            and target is not None
            and target.entry is not None
            and view.order_trades.get(order.order_id) == key
            and view.now <= target.entry.deadline
        )

    stale_entries = [order for order in view.entries if not entry_valid(order)]
    actions += [Cancel(order.order_id, "entry window closed") for order in stale_entries]
    entry_working = len(view.entries) > len(stale_entries)
    if view.exits:
        return actions

    stray = [order for order in view.stops if contract is None or order.con_id != contract.con_id]
    if stray:
        return actions + [Cancel(order.order_id, "stop on another contract") for order in stray]

    if direction == 0:
        if view.stops:
            return actions + [Cancel(order.order_id, flat_reason) for order in view.stops]
        if stale_entries:
            return actions
        if position:
            assert contract is not None
            return actions + [Place(exit_request(position, contract, target), key)]
        if key is not None and view.trade_status == "closing":
            actions.append(MarkTrade(key, "closed", "flat after executor exit"))
        return actions

    assert target is not None and key is not None
    if position == 0:
        if view.stops and not entry_working:
            return actions + [Cancel(order.order_id, "no position") for order in view.stops]
        if entry_working or stale_entries or view.trade_status is not None:
            return actions
        if target.entry is None or view.now > target.entry.deadline:
            return actions + [MarkTrade(key, "missed", "entry deadline passed")]
        if view.target_contract is None:
            return actions
        return actions + [
            MarkTrade(key, "entering", "entry"),
            Place(entry_request(view, target, view.target_contract), key),
        ]

    assert contract is not None
    if (position > 0) != (direction > 0):
        if view.stops:
            return actions + [Cancel(order.order_id, "opposite position") for order in view.stops]
        if stale_entries:
            return actions
        return actions + [Place(exit_request(position, contract, target), key)]
    if abs(position) > view.quantity:
        return actions + [
            Halt(f"position {position} exceeds the configured quantity {view.quantity}")
        ]
    if view.trade_status in (None, "entering"):
        actions.append(MarkTrade(key, "entered", "position held"))

    stops = sorted(view.stops, key=lambda order: order.order_id)
    if len(stops) > 1:
        return actions + [Cancel(order.order_id, "duplicate stop") for order in stops[1:]]
    stop = stops[0] if stops else None
    price = desired_stop(view, target, direction)
    if price is None:
        if stop is not None and stop_cancel_due(target, view.now):
            actions.append(Cancel(stop.order_id, "pre-open stop cancellation"))
        return actions
    if stop is None:
        actions.append(Place(stop_request(position, price, contract, target), key))
    elif stop.stop_price != price or stop.remaining != abs(position):
        actions.append(
            Modify(stop.order_id, stop_request(position, price, contract, target, stop.order_ref))
        )
    return actions
