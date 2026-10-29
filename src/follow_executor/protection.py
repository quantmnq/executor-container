# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Durable deadlines for positions without a broker-confirmed protective stop."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

from .broker import BrokerState
from .journal import Journal
from .signal import NEXT_OPEN_RULES, Target

ENTRY_PROTECTION_SECONDS = 30
REPLACEMENT_PROTECTION_SECONDS = 60
PLANNED_EXIT_GRACE_SECONDS = 30


def fully_protected(state: BrokerState, con_id: int, position: int) -> bool:
    """A submitted stop must cover exactly the remaining position, on its exit side."""
    return any(
        order.con_id == con_id
        and order.order_type == "STP"
        and order.action == ("SELL" if position > 0 else "BUY")
        and order.status in {"PreSubmitted", "Submitted"}
        and order.remaining == abs(position)
        and order.stop_price is not None
        and math.isfinite(order.stop_price)
        and order.stop_price > 0
        for order in state.orders.values()
    )


class ProtectionWatch:
    """Use journal-owned exposure, including fills awaiting their position callback.

    Deadlines start when missing coverage is observed; subsequent partial fills,
    rejected repairs, signal changes and process restarts cannot extend them.
    An expired deadline latches until the emergency exit is reconciled as flat.
    """

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.records: dict[str, dict] = json.loads(journal.get_state("protection_watch") or "{}")

    def save(self) -> None:
        self.journal.set_state("protection_watch", json.dumps(self.records, sort_keys=True))

    def planned_cancellation(
        self, state: BrokerState, order_id: int, target: Target | None,
        now: datetime, client_id: int, grace_seconds: float,
    ) -> None:
        """Record evidence only after our scheduled cancel request was sent.

        Never exempt a pre-existing protection failure, a manual cancellation,
        an invalid schedule, or new exposure added after this request.
        """
        order = state.orders.get(order_id)
        plan = target.exit_plan if target is not None else None
        if (order is None or order.purpose != "stop" or order.client_id != client_id
                or plan is None or plan.rule not in NEXT_OPEN_RULES
                or plan.cancel_stop_at is None or plan.flatten_at is None
                or plan.flatten_at - plan.cancel_stop_at != timedelta(seconds=60)
                or not plan.cancel_stop_at <= now < plan.flatten_at):
            return
        con_id = order.con_id
        position = state.positions.get(con_id, 0)
        contract = state.contracts.get(con_id)
        record = self.records.get(str(con_id))
        if (not position or contract is None or record is None or record["closing"]
                or record["deadline"] is not None
                or self.journal.expected_positions().get(con_id) != position
                or target.contract_month != contract.contract_month
                or target.direction != (1 if position > 0 else -1)
                or order.status not in {"Submitted", "PreSubmitted"}
                or order.order_type != "STP" or order.remaining != abs(position)
                or order.action != ("SELL" if position > 0 else "BUY")
                or not fully_protected(state, con_id, position)):
            return
        record["planned_cancel"] = {
            "order_id": order_id, "position": position, "trade_key": target.trade_key,
            "contract_month": target.contract_month,
            "signal_seq": target.seq, "requested_at": now.isoformat(),
            "cancel_stop_at": plan.cancel_stop_at.isoformat(),
            "flatten_at": plan.flatten_at.isoformat(),
            "deadline": (plan.flatten_at + timedelta(
                seconds=min(grace_seconds, PLANNED_EXIT_GRACE_SECONDS))).isoformat(),
        }
        self.save()
        self.journal.log("planned_stop_cancel", {"con_id": con_id, **record["planned_cancel"]})

    def cancel_refused(self, order_id: int) -> None:
        for record in self.records.values():
            if record.get("planned_cancel", {}).get("order_id") == order_id:
                del record["planned_cancel"]
                self.save()

    @staticmethod
    def _planned_deadline(record: dict, state: BrokerState, position: int, target: Target | None) -> str | None:
        evidence = record.get("planned_cancel")
        plan = target.exit_plan if target is not None else None
        if (not evidence or plan is None or plan.rule not in NEXT_OPEN_RULES
                or target.trade_key != evidence["trade_key"]
                or target.contract_month != evidence["contract_month"]
                or position != evidence["position"]
                or plan.cancel_stop_at is None or plan.flatten_at is None
                or plan.cancel_stop_at.isoformat() != evidence["cancel_stop_at"]
                or plan.flatten_at.isoformat() != evidence["flatten_at"]):
            return None
        order = state.orders.get(evidence["order_id"])
        cancelled = (order is not None and order.status in {"Cancelled", "ApiCancelled"})
        absent = state.snapshot_complete and (order is None or order.status == "Absent")
        if not cancelled and not absent:
            return None
        return evidence["deadline"]

    def force_close(self, con_id: int, now: datetime, reason: str, trade_key: str | None,
                    *, position_offset: int = 0) -> None:
        record = self.records.setdefault(str(con_id), {
            "position": 0, "protected": False, "deadline": now.isoformat(),
            "reason": reason, "closing": False, "trade_keys": [],
        })
        record["closing"] = True
        record["reason"] = reason
        # A verified-flat snapshot can precede an orphan fill even when a manual
        # close left the old journal balance unmatched. Only close our subsequent
        # fills; do not adopt unrelated exposure or rewrite the account baseline.
        record["position_offset"] = position_offset
        if trade_key and trade_key not in record["trade_keys"]:
            record["trade_keys"].append(trade_key)
        self.save()
        self.journal.log("protection_exit", {"con_id": con_id, "reason": reason})

    def observe(self, state: BrokerState, now: datetime, target: Target | None = None) -> list[int]:
        before = json.dumps(self.records, sort_keys=True)
        expected = self.journal.expected_positions()
        for key in list(self.records):
            # A missing execution/position callback must not erase a timer.
            if (not expected.get(int(key)) and not self.records[key]["closing"]
                    and not state.positions.get(int(key))):
                del self.records[key]
        for con_id, position in expected.items():
            key = str(con_id)
            record = self.records.get(key)
            if record is None:
                entries = [order for order in self.journal.notification_orders().values()
                           if order["con_id"] == con_id and order["purpose"] == "entry"]
                trade = entries[-1]["trade_key"] if entries else None
                record = {"position": 0, "protected": False, "deadline": None,
                          "reason": "entry protection timeout", "closing": False,
                          "trade_keys": [trade] if trade else []}
                self.records[key] = record
            if record["closing"]:
                continue
            # Older journals have only deadline/reason; preserve their deadlines.
            record.setdefault("base_deadline", record["deadline"])
            record.setdefault("base_reason", record["reason"])
            previous = record["position"]
            added = previous * position <= 0 or abs(position) > abs(previous)
            covered = fully_protected(state, con_id, position)
            evidence = record.get("planned_cancel")
            if added:
                record.pop("planned_cancel", None)
            if covered:
                record["base_deadline"] = None
                # A replacement restores protection and consumes the exemption.
                original = state.orders.get(evidence["order_id"]) if evidence else None
                if evidence and (original is None or not original.working):
                    record.pop("planned_cancel", None)
            elif record["base_deadline"] is None:
                seconds = ENTRY_PROTECTION_SECONDS if added else REPLACEMENT_PROTECTION_SECONDS
                record["base_deadline"] = (now + timedelta(seconds=seconds)).isoformat()
                record["base_reason"] = ("entry protection timeout" if added
                                         else "stop replacement timeout")
            elif added:
                # More fills cannot buy extra time for already unprotected contracts.
                deadline = now + timedelta(seconds=ENTRY_PROTECTION_SECONDS)
                if deadline < datetime.fromisoformat(record["base_deadline"]):
                    record["base_deadline"] = deadline.isoformat()
                    record["base_reason"] = "entry protection timeout"
            record["deadline"] = record["base_deadline"]
            record["reason"] = record["base_reason"]
            planned = self._planned_deadline(record, state, position, target)
            if planned and not covered and record["base_reason"] != "entry protection timeout":
                record["deadline"] = planned
                record["reason"] = "planned exit timeout"
            record["position"] = position
            record["protected"] = covered
            if record["deadline"] and now >= datetime.fromisoformat(record["deadline"]):
                record["closing"] = True
                self.journal.log("protection_timeout", {"con_id": con_id, **record})
        if json.dumps(self.records, sort_keys=True) != before:
            self.save()
        return [int(key) for key, record in self.records.items() if record["closing"]]

    def finish(self, con_id: int) -> None:
        del self.records[str(con_id)]
        self.save()
