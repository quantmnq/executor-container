# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""signal.v1 targets and heartbeats, parsed from verified envelope payloads."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA = "signal.v1"
HEARTBEAT_SCHEMA = "signal.v1.heartbeat"
DIRECTIONS = {"flat": 0, "long": 1, "short": -1}
TICK = 0.25
CONTRACT_MONTH = re.compile(r"^\d{6}$")


class SignalError(ValueError):
    """A signed payload that does not satisfy the signal.v1 contract."""


@dataclass(frozen=True)
class Entry:
    session: str | None
    signal_time: datetime
    deadline: datetime
    reference_price: float | None
    atr: float | None
    stop_atr: float | None


@dataclass(frozen=True)
class ExitPlan:
    rule: str
    cancel_stop_at: datetime | None
    flatten_at: datetime | None


@dataclass(frozen=True)
class Target:
    seq: int
    stream: str
    cause: str
    emitted_at: datetime
    position: str
    leg: str | None
    contract_month: str | None
    entry: Entry | None
    stop: float | None
    exit_plan: ExitPlan | None
    payload: str

    @property
    def direction(self) -> int:
        return DIRECTIONS[self.position]

    @property
    def trade_key(self) -> str | None:
        """One leader trade: entry signal time, leg and side."""

        if self.position == "flat":
            return None
        anchor = "held" if self.entry is None else self.entry.signal_time.isoformat()
        return f"{anchor}|{self.leg or 'unknown'}|{self.position}"


@dataclass(frozen=True)
class Heartbeat:
    stream: str
    latest_seq: int
    sent_at: datetime


def round_down(price: float) -> float:
    return math.floor(price / TICK + 1e-9) * TICK


def round_up(price: float) -> float:
    return math.ceil(price / TICK - 1e-9) * TICK


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise SignalError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SignalError(f"{field} is not an ISO-8601 time") from exc
    if parsed.tzinfo is None:
        raise SignalError(f"{field} must carry a UTC offset")
    return parsed


def _optional_time(value: Any, field: str) -> datetime | None:
    return None if value is None else parse_time(value, field)


def _number(value: Any, field: str, *, optional: bool = True) -> float | None:
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise SignalError(f"{field} must be a positive number")
    return float(value)


def _object(value: Any, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SignalError(f"{field} must be an object or null")
    return value


def parse_target(payload_text: str, stream: str) -> Target:
    """Parse the exact signed payload text of one signal.v1 event."""

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise SignalError("payload is not JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise SignalError(f"payload schema is not {SCHEMA}")
    if payload.get("stream") != stream:
        raise SignalError(f"payload stream {payload.get('stream')!r} is not {stream!r}")
    seq = payload.get("seq")
    if type(seq) is not int or seq < 1:
        raise SignalError("seq must be a positive integer")
    cause = payload.get("cause")
    if not isinstance(cause, str) or not cause:
        raise SignalError("cause must be a non-empty string")
    emitted_at = parse_time(payload.get("emitted_at"), "emitted_at")

    instrument = _object(payload.get("instrument"), "instrument") or {}
    month = instrument.get("contract_month")
    if month is not None and (not isinstance(month, str) or not CONTRACT_MONTH.match(month)):
        raise SignalError("instrument.contract_month must be YYYYMM")
    for field, expected in (("exchange", "CME"), ("currency", "USD")):
        if instrument.get(field, expected) != expected:
            raise SignalError(f"instrument.{field} must be {expected}")

    target = _object(payload.get("target"), "target")
    if target is None:
        raise SignalError("target is missing")
    position = target.get("position")
    if position not in DIRECTIONS:
        raise SignalError("target.position must be flat, long or short")
    if position == "flat":
        return Target(seq, stream, cause, emitted_at, "flat", None, month, None, None, None, payload_text)
    if month is None:
        raise SignalError("a position target needs instrument.contract_month")

    leg = target.get("leg")
    if leg is not None and not isinstance(leg, str):
        raise SignalError("target.leg must be a string or null")

    entry = None
    raw_entry = _object(target.get("entry"), "target.entry")
    if raw_entry is not None:
        session = raw_entry.get("session")
        entry = Entry(
            session=session if isinstance(session, str) else None,
            signal_time=parse_time(raw_entry.get("signal_time"), "entry.signal_time"),
            deadline=parse_time(raw_entry.get("deadline"), "entry.deadline"),
            reference_price=_number(raw_entry.get("reference_price"), "entry.reference_price"),
            atr=_number(raw_entry.get("atr"), "entry.atr"),
            stop_atr=_number(raw_entry.get("stop_atr"), "entry.stop_atr"),
        )

    stop = None
    raw_stop = _object(target.get("protective_stop"), "target.protective_stop")
    if raw_stop is not None:
        price = _number(raw_stop.get("price"), "protective_stop.price", optional=False)
        assert price is not None
        # Leader stops are tick-aligned; an unaligned one is rounded away from the market.
        stop = round_down(price) if position == "long" else round_up(price)

    exit_plan = None
    raw_plan = _object(target.get("exit_plan"), "target.exit_plan")
    if raw_plan is not None:
        rule = raw_plan.get("rule")
        if not isinstance(rule, str):
            raise SignalError("exit_plan.rule must be a string")
        exit_plan = ExitPlan(
            rule=rule,
            cancel_stop_at=_optional_time(raw_plan.get("cancel_stop_at"), "exit_plan.cancel_stop_at"),
            flatten_at=_optional_time(raw_plan.get("flatten_at"), "exit_plan.flatten_at"),
        )

    return Target(seq, stream, cause, emitted_at, position, leg, month, entry, stop, exit_plan, payload_text)


def parse_heartbeat(payload: dict[str, Any], stream: str) -> Heartbeat:
    if payload.get("schema") != HEARTBEAT_SCHEMA or payload.get("stream") != stream:
        raise SignalError("not a heartbeat for this stream")
    latest = payload.get("latest_seq")
    if type(latest) is not int or latest < 0:
        raise SignalError("heartbeat latest_seq must be a non-negative integer")
    return Heartbeat(stream, latest, parse_time(payload.get("sent_at"), "sent_at"))
