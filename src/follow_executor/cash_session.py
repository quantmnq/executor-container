# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""The Nasdaq cash session: 09:30-16:00 US Eastern, or 13:00 on early-close days.

The exchange calendar follows the published rules: weekends and the ten full
holidays (a Saturday holiday is observed on Friday and a Sunday holiday on
Monday, except that New Year's Day on a Saturday closes no Friday), early closes
on 3 July when it falls Monday to Thursday, the day after Thanksgiving and
24 December when it falls Monday to Thursday, and closures the exchange announced
outside those rules.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EASTERN_ZONE = "America/New_York"
OPEN = time(9, 30)
CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
# Closures announced outside the holiday rules, such as national days of mourning.
UNSCHEDULED_CLOSURES = frozenset({date(2025, 1, 9)})
MONDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = 0, 3, 4, 5, 6


class CalendarUnavailable(RuntimeError):
    """The system time-zone database has no US Eastern zone."""


@cache
def eastern() -> ZoneInfo:
    try:
        return ZoneInfo(EASTERN_ZONE)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise CalendarUnavailable(f"time zone {EASTERN_ZONE} is unavailable: {exc}") from exc


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (the anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 19 * m) // 433
    month = (h + m - 7 * n + 90) // 25
    return date(year, month, (h + m - 7 * n + 33 * month + 19) % 32)


def _observed(day: date) -> date:
    if day.weekday() == SATURDAY:
        return day - timedelta(days=1)
    if day.weekday() == SUNDAY:
        return day + timedelta(days=1)
    return day


@cache
def holidays(year: int) -> frozenset[date]:
    days = {
        _nth_weekday(year, 1, MONDAY, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, MONDAY, 3),  # Washington's Birthday
        _easter(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, MONDAY),  # Memorial Day
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, MONDAY, 1),  # Labor Day
        _nth_weekday(year, 11, THURSDAY, 4),  # Thanksgiving Day
        _observed(date(year, 12, 25)),  # Christmas Day
    }
    new_year = date(year, 1, 1)
    if new_year.weekday() != SATURDAY:
        days.add(_observed(new_year))
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))  # Juneteenth
    return frozenset(days | {day for day in UNSCHEDULED_CLOSURES if day.year == year})


@cache
def early_closes(year: int) -> frozenset[date]:
    days = {_nth_weekday(year, 11, THURSDAY, 4) + timedelta(days=1)}
    for day in (date(year, 7, 3), date(year, 12, 24)):
        if day.weekday() <= THURSDAY:
            days.add(day)
    return frozenset(days - holidays(year))


def session_hours(day: date) -> tuple[time, time] | None:
    """The day's cash-session open and close in US Eastern time, or None when closed."""
    if day.weekday() >= SATURDAY or day in holidays(day.year):
        return None
    return OPEN, EARLY_CLOSE if day in early_closes(day.year) else CLOSE


def in_cash_session(moment: datetime) -> bool:
    local = moment.astimezone(eastern())
    hours = session_hours(local.date())
    return hours is not None and hours[0] <= local.time() < hours[1]


def bar_start(moment: datetime, minutes: int = 5) -> datetime:
    """The start of the US Eastern ``minutes`` bar holding ``moment``."""
    local = moment.astimezone(eastern())
    return local.replace(minute=local.minute - local.minute % minutes, second=0, microsecond=0)
