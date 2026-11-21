"""Plain data classes shared across the app."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class DaySummary:
    """Result of calculating one day. All durations are integer minutes.

    worked, debt and exceeding are None while the day is incomplete.
    """

    complete: bool
    required: int
    worked: Optional[int] = None
    debt: Optional[int] = None
    exceeding: Optional[int] = None


@dataclass(frozen=True)
class Entry:
    """One row of the entries table. Times are 'HH:MM' text or None.

    worked_minutes, debt_minutes and exceeding_minutes are calculated by the
    database; they are filled when an entry is read and ignored when written.
    """

    work_date: date
    arrival: Optional[str] = None
    lunch_out: Optional[str] = None
    lunch_in: Optional[str] = None
    departure: Optional[str] = None
    required_minutes: int = 480
    on_site: bool = False
    exact_times: bool = True
    note: Optional[str] = None
    id: Optional[int] = None
    worked_minutes: Optional[int] = None
    debt_minutes: Optional[int] = None
    exceeding_minutes: Optional[int] = None
    vacation: bool = False


@dataclass(frozen=True)
class DayRecord:
    """One calculated day plus the data needed to build period summaries."""

    work_date: date
    on_site: bool
    summary: DaySummary
    vacation: bool = False


@dataclass(frozen=True)
class PeriodSummary:
    """Totals for a month, semester or year. Durations are integer minutes.

    Only complete days are counted. onsite_percent is None when there are no
    completed days. onsite_days_needed is how many more on-site days (taken
    as extra completed days) are needed to meet the target; remote_days_spare
    is how many more remote days can be added before the target is lost.
    """

    start: date
    end: date
    days_worked: int
    onsite_days: int
    remote_days: int
    onsite_percent: Optional[float]
    worked: int
    debt: int
    exceeding: int
    balance: int
    target_met: bool
    onsite_days_needed: int
    remote_days_spare: int
