"""Month, semester and year ranges, and period summaries. No GUI, no database."""
from __future__ import annotations

import calendar
from datetime import date
from typing import Iterable, Tuple

from worktime.models import DayRecord, PeriodSummary

MIN_ONSITE_PERCENT = 50


def month_range(day: date) -> Tuple[date, date]:
    """First and last day (inclusive) of the calendar month of `day`."""
    last = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, 1), date(day.year, day.month, last)


def semester_range(day: date) -> Tuple[date, date]:
    """First and last day (inclusive) of the semester: Jan-Jun or Jul-Dec."""
    if day.month <= 6:
        return date(day.year, 1, 1), date(day.year, 6, 30)
    return date(day.year, 7, 1), date(day.year, 12, 31)


def year_range(day: date) -> Tuple[date, date]:
    """First and last day (inclusive) of the calendar year of `day`."""
    return date(day.year, 1, 1), date(day.year, 12, 31)


def onsite_days_needed(onsite: int, total: int, min_percent: int = MIN_ONSITE_PERCENT) -> int:
    """Smallest number of extra on-site days so that onsite/total >= min_percent.

    Integer arithmetic only, so exactly 50% is never lost to rounding.
    Returns 0 when there are no completed days yet.
    """
    if total == 0:
        return 0
    extra = 0
    while (onsite + extra) * 100 < min_percent * (total + extra):
        extra += 1
    return extra


def remote_days_spare(onsite: int, total: int, min_percent: int = MIN_ONSITE_PERCENT) -> int:
    """How many more remote days fit before the percentage drops below target.

    Returns 0 when the target is not met or there are no completed days.
    """
    if total == 0 or onsite * 100 < min_percent * total:
        return 0
    return (onsite * 100) // min_percent - total


def summarize(
    records: Iterable[DayRecord],
    start: date,
    end: date,
    min_percent: int = MIN_ONSITE_PERCENT,
) -> PeriodSummary:
    """Sum the completed days between start and end (both inclusive)."""
    days = onsite = worked = debt = exceeding = 0
    for record in records:
        if not (start <= record.work_date <= end) or not record.summary.complete or record.vacation:
            continue
        days += 1
        onsite += 1 if record.on_site else 0
        worked += record.summary.worked
        debt += record.summary.debt
        exceeding += record.summary.exceeding
    return PeriodSummary(
        start=start,
        end=end,
        days_worked=days,
        onsite_days=onsite,
        remote_days=days - onsite,
        onsite_percent=onsite * 100 / days if days else None,
        worked=worked,
        debt=debt,
        exceeding=exceeding,
        balance=exceeding - debt,
        target_met=days > 0 and onsite * 100 >= min_percent * days,
        onsite_days_needed=onsite_days_needed(onsite, days, min_percent),
        remote_days_spare=remote_days_spare(onsite, days, min_percent),
    )
