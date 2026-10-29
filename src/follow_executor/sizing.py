# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Balance sizing: the leader's leverage band, scaled by the follower's fraction.

One unit is one MNQ (USD 2 per index point); one NQ is ten units. With ``E`` the
account's NetLiquidation and ``N = 2 x P`` one unit's notional at the leader's
NQ reference price ``P``, the first base is ``floor(target x f x E / N)``. Later
bases start from the last persisted base ``n``: reset when ``n x N`` exceeds
``hold_max x f x E``, otherwise add one unit at a time while ``(n + 1) x N``
stays within ``add_max x f x E``. A trade with the signal's ``weight`` trades
``round_half_up(base x weight)`` units as NQ plus an MNQ remainder, with no
minimum: a trade that rounds to 0 units is skipped. Decimal arithmetic on the decimal inputs keeps exact
boundaries exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from .signal import Sizing

UNIT_POINT_VALUE = Decimal(2)
UNITS_PER_NQ = 10
# The leader's current band, for previews only: trading always uses the weight and
# band carried by each signed signal.
LEADER_BAND = Sizing(1.0, 6.0, 5.88, 6.6)
# Example weights for previews. Each signal carries its own trade's weight.
PREVIEW_WEIGHTS = (1.0, 0.75, 0.5, 0.25)


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _units_within(limit: Decimal, notional: Decimal) -> int:
    """The largest whole number of units whose notional stays within ``limit``."""

    units = int((limit / notional).to_integral_value(rounding=ROUND_FLOOR))
    # Products of these short decimals are exact; the quotient may be rounded.
    while units > 0 and units * notional > limit:
        units -= 1
    while (units + 1) * notional <= limit:
        units += 1
    return max(units, 0)


def balance_base(previous: int | None, equity: float, price: float, fraction: float,
                 band: Sizing) -> int:
    notional = UNIT_POINT_VALUE * _decimal(price)
    scaled = _decimal(fraction) * _decimal(equity)
    if previous is None or previous * notional > _decimal(band.hold_max_leverage) * scaled:
        return _units_within(_decimal(band.target_leverage) * scaled, notional)
    return max(previous, _units_within(_decimal(band.add_max_leverage) * scaled, notional))


def leg_units(base: int, weight: float) -> int:
    """``round_half_up(base x weight)``; 0 means the trade is skipped."""
    if base < 1:
        return 0
    return int((base * _decimal(weight)).to_integral_value(rounding=ROUND_HALF_UP))


def split(units: int) -> dict[str, int]:
    nq, mnq = divmod(units, UNITS_PER_NQ)
    return {"NQ": nq, "MNQ": mnq}


def book_label(quantities: dict[str, int]) -> str:
    """``1 NQ + 5 MNQ``; zero parts are omitted and an empty book is ``flat``."""

    parts = [f"{abs(quantities[root])} {root}" for root in ("NQ", "MNQ") if quantities.get(root)]
    return " + ".join(parts) or "flat"


@dataclass(frozen=True)
class PreviewSize:
    weight: float
    units: int
    nq: int
    mnq: int

    @property
    def book(self) -> str:
        return book_label({"NQ": self.nq, "MNQ": self.mnq}) if self.units else "no entry (rounds to 0 contracts)"


def preview(fraction: float, equity: float, price: float,
            band: Sizing = LEADER_BAND) -> tuple[int, list[PreviewSize]]:
    """The first-entry split at each example weight for this balance and NQ price."""

    base = balance_base(None, equity, price, fraction, band)
    sizes = []
    for weight in PREVIEW_WEIGHTS:
        units = leg_units(base, weight)
        sizes.append(PreviewSize(weight, units, *split(units).values()))
    return base, sizes


def preview_text(fraction: float, equity: float, price: float, max_quantity: int) -> str:
    base, sizes = preview(fraction, equity, price)
    lines = [(f"Size preview at NetLiquidation ${equity:,.0f} and NQ {price:,.2f} "
              f"(leverage fraction {fraction:g}, leader band 6x / 5.88x / 6.6x):"),
             f"  base: {base} MNQ units"]
    for size in sizes:
        lines.append(f"  weight {size.weight:<4g} -> {size.book}")
    if base < 1:
        lines.append("  This balance is too small for one MNQ unit; entries would be refused.")
    elif any(not size.units for size in sizes):
        lines.append("  Weights marked 'no entry' round to 0 contracts at this balance; "
                     "trades with those weights are skipped.")
    elif any(size.nq > max_quantity for size in sizes):
        lines.append(f"  The largest sizes exceed risk.max_quantity {max_quantity} NQ per order "
                     "and would be refused; raise it or lower the fraction.")
    lines.append("  These weights are examples: each signal carries its trade's weight (above 0, "
                 "at most 1; 1 is the largest size), and the executor sizes at each new entry.")
    return "\n".join(lines)
