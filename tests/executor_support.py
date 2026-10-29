# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Shared fixtures for the executor tests: signed payloads, a fake broker and a clock."""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from follow_executor.broker import (
    MULTIPLIERS,
    BrokerState,
    Execution,
    FutureContract,
    MarginEstimate,
    OrderRequest,
    OrderView,
    Rejection,
)
from follow_executor.config import load_config
from follow_executor.signal import parse_target

STREAM = "sessioncycle.mnq"
ACCOUNT = "DU1234567"
CLIENT_ID = 71
SIGNAL_TIME = datetime(2026, 10, 1, 19, 55, tzinfo=UTC)
T0 = datetime(2026, 10, 1, 19, 55, 7, 157008, tzinfo=UTC)
ATR = 28.464285714285715


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Leader:
    """Signs envelopes exactly as oci-quant's signal_signing does."""

    def __init__(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.public_key = base64.b64encode(raw).decode()
        self.key_id = hashlib.sha256(raw).hexdigest()[:16]

    def envelope(self, text: str) -> dict[str, str]:
        return {"key_id": self.key_id, "payload": text,
                "sig": base64.b64encode(self.key.sign(text.encode())).decode()}

    def heartbeat(self, latest: int, sent_at: datetime = T0) -> dict[str, str]:
        return self.envelope(canonical({"schema": "signal.v1.heartbeat", "stream": STREAM,
                                        "latest_seq": latest, "sent_at": sent_at.isoformat()}))


def payload(
    seq: int,
    cause: str,
    position: str = "long",
    *,
    leg: str = "drift",
    stop: float | None = None,
    emitted: datetime = T0,
    signal_time: datetime = SIGNAL_TIME,
    deadline: datetime | None = None,
    reference: float | None = None,
    atr: float = ATR,
    stop_atr: float = 11.5,
    plan: dict[str, str] | None | str = "next_open",
    month: str = "202612",
    sizing: dict[str, float] | None = None,
) -> str:
    """A payload shaped like the live runner's (see the relay's seq 1 and 2)."""

    instrument = {"root": "MNQ", "exchange": "CME", "currency": "USD",
                  "contract_month": month, "last_trade_date": f"{month}18"}
    if position == "flat":
        target: dict[str, Any] = {"position": "flat", "leg": None, "entry": None,
                                  "protective_stop": None, "exit_plan": None}
    else:
        if plan == "next_open":
            plan = {"rule": "next_rth_open", "cancel_stop_at": "2026-10-02T13:29:00+00:00",
                    "flatten_at": "2026-10-02T13:30:00+00:00"}
        target = {
            "position": position,
            "leg": leg,
            "entry": {
                "session": signal_time.date().isoformat(),
                "signal_time": signal_time.isoformat(),
                "deadline": (deadline or emitted + timedelta(seconds=60)).isoformat(),
                "reference_price": reference,
                "atr": atr,
                "stop_atr": stop_atr,
                "trailing": {"enabled": True, "activation_atr": 2.0, "distance_atr": 7.5},
            },
            "protective_stop": None if stop is None else {"price": stop},
            "exit_plan": plan,
        }
        if sizing is not None:
            target["sizing"] = sizing
    return canonical({
        "schema": "signal.v1", "stream": STREAM, "seq": seq, "emitted_at": emitted.isoformat(),
        "cause": cause, "changed": [], "strategy": {"profile": "simpler-lower-dd-r334"},
        "instrument": instrument, "target": target,
    })


def target(*args: Any, **kwargs: Any):
    return parse_target(payload(*args, **kwargs), STREAM)


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> datetime:
        self.now += timedelta(seconds=seconds)
        return self.now


def contract(month: str = "202612", root: str = "MNQ") -> FutureContract:
    return FutureContract(int(month) * 10 + (1 if root == "MNQ" else 2), root, month, f"{month}18",
                          MULTIPLIERS[root])


class FakeBroker:
    """In-memory IBKR stand-in: market orders fill at once, stops rest until triggered."""

    def __init__(self, root: str = "MNQ") -> None:
        self.root = root
        self.connected = False
        self.accounts: tuple[str, ...] = (ACCOUNT,)
        self.positions: dict[int, int] = {}
        self.average: dict[int, float] = {}
        self.contracts: dict[int, FutureContract] = {}
        self.orders: dict[int, OrderView] = {}
        self.executions: list[Execution] = []
        self.rejections: list[Rejection] = []
        self.market = 30780.25
        self.margin = MarginEstimate(5_000.0, 100_000.0)
        self.margins: dict[str, MarginEstimate] = {}
        self.what_if_error: Exception | None = None
        self.net_liq = 250_000.0
        self.net_liq_error: Exception | None = None
        self.acknowledge = True
        self.auto_fill = True
        self.reject: dict[str, tuple[int, str]] = {}
        self.calls: list[tuple[str, Any]] = []
        self.connect_error: Exception | None = None
        self.snapshot_id = 0
        self.snapshot_complete = True
        self._ids = itertools.count(1)
        self._execs = itertools.count(1)
        self._rejection_seq = itertools.count(1)

    # Broker interface
    @property
    def is_connected(self) -> bool:
        return self.connected

    @property
    def managed_accounts(self) -> tuple[str, ...]:
        return self.accounts

    def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def wait_for_snapshot(self) -> None:
        pass

    def refresh(self) -> None:
        self.snapshot_id += 1

    def resolve(self, root: str, contract_month: str) -> FutureContract:
        value = contract(contract_month, root)
        self.contracts[value.con_id] = value
        return value

    def state(self) -> BrokerState:
        return BrokerState(
            connected=self.connected, positions=dict(self.positions), average_prices=dict(self.average),
            contracts=dict(self.contracts), orders=dict(self.orders), executions=tuple(self.executions),
            rejections=tuple(self.rejections),
            snapshot_id=self.snapshot_id, snapshot_complete=self.snapshot_complete,
        )

    def place(self, request: OrderRequest, order_id: int | None = None) -> int:
        if order_id is not None:
            self.calls.append(("modify", request))
            if "modify" in self.reject:
                self._reject(order_id, *self.reject.pop("modify"))
                return order_id
            order = self.orders[order_id]
            self.orders[order_id] = replace(order, stop_price=request.stop_price,
                                            quantity=order.filled + request.quantity)
            return order_id
        oid = next(self._ids)
        self.calls.append(("place", request))
        if request.purpose in self.reject:
            self._reject(oid, *self.reject.pop(request.purpose))
            return oid
        if not self.acknowledge:
            return oid
        self.contracts[request.contract.con_id] = request.contract
        self.orders[oid] = OrderView(
            order_id=oid, con_id=request.contract.con_id, root=request.contract.root,
            action=request.action, order_type=request.order_type, quantity=request.quantity, filled=0,
            status="Submitted", order_ref=request.order_ref, client_id=CLIENT_ID,
            stop_price=request.stop_price, limit_price=request.limit_price,
        )
        marketable = request.order_type == "MKT" or (
            request.order_type == "LMT"
            and (self.market <= request.limit_price if request.action == "BUY" else self.market >= request.limit_price)
        )
        if self.auto_fill and marketable:
            self.fill(oid)
        return oid

    def cancel(self, order_id: int) -> None:
        self.calls.append(("cancel", order_id))
        order = self.orders.get(order_id)
        if order is None or not order.working:
            self._reject(order_id, 161, "Cancel attempted when order is not in a cancellable state",
                         cancel_refused=True)
            return
        self.orders[order_id] = replace(order, status="Cancelled")

    def what_if(self, request: OrderRequest) -> MarginEstimate:
        self.calls.append(("what_if", request))
        if self.what_if_error is not None:
            raise self.what_if_error
        return self.margins.get(request.contract.root, self.margin)

    def net_liquidation(self) -> float:
        self.calls.append(("net_liquidation", None))
        if self.net_liq_error is not None:
            raise self.net_liq_error
        return self.net_liq

    # Test controls
    def fill(self, order_id: int, quantity: int | None = None, price: float | None = None) -> None:
        order = self.orders[order_id]
        quantity = order.remaining if quantity is None else quantity
        price = (order.stop_price if order.order_type == "STP" else self.market) if price is None else price
        signed = quantity if order.action == "BUY" else -quantity
        before = self.positions.get(order.con_id, 0)
        after = before + signed
        if after and (before == 0 or (before > 0) == (signed > 0)):
            total = abs(before) * self.average.get(order.con_id, 0.0) + quantity * price
            self.average[order.con_id] = total / abs(after)
        elif not after:
            self.average.pop(order.con_id, None)
        self.positions[order.con_id] = after
        filled = order.filled + quantity
        self.orders[order_id] = replace(order, filled=filled,
                                        status="Filled" if filled >= order.quantity else "Submitted")
        self.executions.append(Execution(f"e{next(self._execs)}", order_id, order.con_id,
                                         "BOT" if order.action == "BUY" else "SLD", quantity, price,
                                         order.order_ref, "20261001 15:55:08"))

    def working(self, purpose: str) -> list[OrderView]:
        return [o for o in self.orders.values() if o.working and o.purpose == purpose]

    def trigger_stop(self, root: str | None = None) -> None:
        (stop,) = [order for order in self.working("stop") if root is None or order.root == root]
        self.fill(stop.order_id)

    def held(self) -> dict[str, int]:
        """Positions by root, such as {"NQ": 1, "MNQ": 7}."""
        held: dict[str, int] = {}
        for con_id, quantity in self.positions.items():
            if quantity:
                root = self.contracts[con_id].root
                held[root] = held.get(root, 0) + quantity
        return held

    def placed(self, purpose: str) -> list[OrderRequest]:
        return [req for kind, req in self.calls if kind == "place" and req.purpose == purpose]

    def _reject(self, order_id: int, code: int, message: str, *, cancel_refused: bool = False) -> None:
        self.rejections.append(Rejection(next(self._rejection_seq), order_id, code, message, cancel_refused))


class RecordingAcks:
    def __init__(self) -> None:
        self.sent: list[tuple[str, int | None, dict[str, Any]]] = []

    def send(self, kind: str, seq: int | None, detail: dict[str, Any]) -> None:
        self.sent.append((kind, seq, detail))

    def kinds(self) -> list[str]:
        return [kind for kind, _seq, _detail in self.sent]


def write_config(directory: Path, public_key: str, relay_url: str = "https://relay.example.com", **changes: Any):
    token = directory / "relay.token"
    token.write_text("follower-token\n")
    raw: dict[str, Any] = {
        "relay_url": relay_url,
        "stream": STREAM,
        "leader_public_key": public_key,
        "token_path": str(token),
        "journal_path": str(directory / "executor.sqlite3"),
        "ibkr": {"host": "127.0.0.1", "port": 4002, "client_id": CLIENT_ID, "account": ACCOUNT,
                 "account_type": "paper"},
        "instrument": {"root": "MNQ", "quantity": 2},
        "risk": {"max_quantity": 10, "max_entry_slippage_points": 10, "max_margin_fraction": 0.5},
        "feed": {"heartbeat_timeout_seconds": 30, "clock_exit_grace_seconds": 30},
    }
    for dotted, value in changes.items():
        section, _, key = dotted.partition("__")
        if key:
            raw.setdefault(section, {})[key] = value
        else:
            raw[section] = value
    path = directory / "executor.json"
    path.write_text(json.dumps(raw))
    return load_config(path)
