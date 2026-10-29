# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Rebuild notification-only round trips from the executor's durable fills."""

from decimal import Decimal

from .broker import MULTIPLIERS


def fill_identity(exec_id):
    base, dot, revision = exec_id.rpartition(".")
    corrected = bool(dot and base.count(".") >= 2 and revision.isdecimal())
    return base if corrected else exec_id


def positions(executions, orders, root, roots=None):
    """Return each round trip's latest state, including corrected closed trades.

    Each contract is its own round trip; ``roots`` maps a contract ID to NQ or
    MNQ for a two-contract book, otherwise every contract is ``root``.
    Journal row order preserves a correction's original place in the history.
    Cash flows use Decimal; only the final USD result is rounded to cents.
    No state here is used to place orders or reconcile broker positions.
    """
    active, summaries = {}, {}
    roots = roots or {}
    for fill in executions:
        order = orders.get(fill["order_id"])
        if order is None or order["con_id"] != fill["con_id"]:
            continue
        con_id = fill["con_id"]
        sign = 1 if fill["side"] == "BOT" else -1
        remaining = fill["quantity"]
        price = Decimal(str(fill["price"]))
        base = fill_identity(fill["exec_id"])
        fingerprint = [fill["exec_id"], fill["quantity"], fill["price"], fill["side"]]
        part = 0
        while remaining:
            cycle = active.get(con_id)
            if cycle is None:
                # An exit with no recorded entry must never invent an entry price.
                unknown = order["purpose"] != "entry" and part == 0
                key = f"position:{con_id}:{base}:{part}"
                cycle = {"key": key, "direction": -sign if unknown else sign,
                         "quantity": order["quantity"] if unknown else 0,
                         "average": None if unknown else Decimal(0),
                         "cash": Decimal(0), "closed": 0, "exit_value": Decimal(0),
                         "fills": {}, "unknown": unknown}
                active[con_id] = cycle
            cycle["fills"][base] = fingerprint
            opening = sign == cycle["direction"]
            amount = remaining if opening else min(remaining, cycle["quantity"])
            if opening:
                total = cycle["quantity"] + amount
                if cycle["average"] is not None:
                    cycle["average"] = (cycle["average"] * cycle["quantity"] + price * amount) / total
                cycle["quantity"] = total
            else:
                cycle["quantity"] -= amount
                cycle["closed"] += amount
                cycle["exit_value"] += price * amount
            cycle["cash"] -= sign * price * amount
            remaining -= amount
            flat = cycle["quantity"] == 0
            summary = {
                "position": "FLAT" if flat else "LONG" if cycle["direction"] == 1 else "SHORT",
                "quantity": cycle["closed"] if flat else cycle["quantity"],
                "price": float(cycle["exit_value"] / cycle["closed"]) if flat else (
                    float(cycle["average"]) if cycle["average"] is not None else None),
                "con_id": con_id, "order_id": fill["order_id"],
                "side": "BUY" if sign == 1 else "SELL", "purpose": order["purpose"],
                "broker_time": fill["time"],
            }
            if flat:
                multiplier = Decimal(str(MULTIPLIERS[roots.get(con_id, root)]))
                pnl = None if cycle["unknown"] else float((cycle["cash"] * multiplier).quantize(Decimal("0.01")))
                summary["gross_pnl"] = pnl
                del active[con_id]
            summaries[cycle["key"]] = {"event": summary, "fills": dict(cycle["fills"])}
            part += 1
    return summaries
