"""GUI helpers that need no window: parsing, validation and display text.

Everything here is unit tested without opening Tkinter.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Tuple, Union

from worktime.calc import DEFAULT_REQUIRED_MINUTES, calculate_day, format_minutes, parse_hhmm
from worktime.gui import strings
from worktime.models import DayRecord, Entry, PeriodSummary
from worktime.periods import month_range, semester_range, summarize, year_range

_LOOSE_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def format_date(value: date) -> str:
    """Display format: dd/mm/yyyy."""
    return value.strftime("%d/%m/%Y")


def parse_date(text: str) -> date:
    """'21/10/2026' -> date. Raises ValueError with a readable message."""
    try:
        return datetime.strptime((text or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        raise ValueError(f"Invalid date {text!r}: expected dd/mm/yyyy") from None


def normalize_time(text: Optional[str]) -> Optional[str]:
    """'' -> None, ' 9:05 ' -> '09:05'. Anything else is left for validation."""
    value = (text or "").strip()
    if not value:
        return None
    match = _LOOSE_TIME.match(value)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    return value


def parse_required(text: Optional[str]) -> int:
    """'' -> 480 (08:00 default), '04:00' -> 240."""
    value = normalize_time(text)
    if value is None:
        return DEFAULT_REQUIRED_MINUTES
    return parse_hhmm(value)


def required_text(minutes: int) -> str:
    """480 -> '08:00', for the 'Required hours' field."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def shift_month(year: int, month: int, delta: int) -> Tuple[int, int]:
    """Move (year, month) by delta months: (2026, 12, +1) -> (2027, 1)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def year_choices(entries: Iterable[Entry], today: date, extra_years: Iterable[Union[int, str]] = ()) -> List[int]:
    """Years offered by the year picker: every year with data, plus around today."""
    years = {today.year - 1, today.year, today.year + 1}
    years.update(entry.work_date.year for entry in entries)
    years.update(int(y) for y in extra_years)
    return sorted(years)


def minutes_text(minutes: Optional[int]) -> str:
    """Minutes for a table cell: '6h39', or '' while the day is incomplete."""
    return "" if minutes is None else format_minutes(minutes)


@dataclass(frozen=True)
class DayRow:
    """One line of the month table."""

    work_date: date
    entry: Optional[Entry]
    weekday: str
    is_weekend: bool
    state: str  # "empty", "open", "debt", "exceeding" or "ok"
    cells: Tuple[str, ...]  # date, day, arrival, lunch out, lunch in, departure, site, worked, debt, exceeding, note


def _state(entry: Optional[Entry]) -> str:
    if entry is None:
        return "empty"
    if entry.worked_minutes is None:
        return "open"
    if entry.debt_minutes:
        return "debt"
    if entry.exceeding_minutes:
        return "exceeding"
    return "ok"


def build_month_rows(year: int, month: int, entries: Iterable[Entry]) -> List[DayRow]:
    """One row for every calendar day of the month, with its entry if there is one."""
    by_date: Dict[date, Entry] = {entry.work_date: entry for entry in entries}
    rows = []
    for number in range(1, calendar.monthrange(year, month)[1] + 1):
        day = date(year, month, number)
        entry = by_date.get(day)
        weekday = day.strftime("%a")
        if entry is None:
            cells = (format_date(day), weekday, "", "", "", "", "", "", "", "", "")
        else:
            cells = (
                format_date(day),
                weekday,
                entry.arrival or "",
                entry.lunch_out or "",
                entry.lunch_in or "",
                entry.departure or "",
                strings.YES if entry.on_site else strings.NO,
                minutes_text(entry.worked_minutes) or strings.OPEN_DAY,
                minutes_text(entry.debt_minutes),
                minutes_text(entry.exceeding_minutes),
                entry.note or "",
            )
        rows.append(DayRow(day, entry, weekday, day.weekday() >= 5, _state(entry), cells))
    return rows


def totals_text(summary: PeriodSummary, target_percent: int) -> Tuple[str, str]:
    """Two display lines for a month: the totals, and the on-site target status."""
    percent = "n/a" if summary.onsite_percent is None else f"{summary.onsite_percent:.1f}%"
    totals = strings.TOTALS_TEMPLATE.format(
        month=calendar.month_name[summary.start.month],
        year=summary.start.year,
        days=summary.days_worked,
        onsite=summary.onsite_days,
        remote=summary.remote_days,
        percent=percent,
        worked=format_minutes(summary.worked),
        debt=format_minutes(summary.debt),
        exceeding=format_minutes(summary.exceeding),
        balance=format_minutes(summary.balance),
    )
    if summary.days_worked == 0:
        target = strings.TARGET_NO_DAYS.format(target=target_percent)
    elif summary.target_met:
        target = strings.TARGET_MET.format(target=target_percent, spare=summary.remote_days_spare)
    else:
        target = strings.TARGET_NOT_MET.format(
            target=target_percent, needed=summary.onsite_days_needed
        )
    return totals, target


def preview_text(
    arrival: Optional[str],
    lunch_out: Optional[str],
    lunch_in: Optional[str],
    departure: Optional[str],
    required_text: Optional[str],
) -> str:
    """Live preview under the form. Returns the error message if the input is invalid."""
    try:
        day = calculate_day(
            normalize_time(arrival),
            normalize_time(lunch_out),
            normalize_time(lunch_in),
            normalize_time(departure),
            parse_required(required_text),
        )
    except ValueError as error:
        return str(error)
    if not day.complete:
        return strings.PREVIEW_INCOMPLETE
    return strings.PREVIEW_TEMPLATE.format(
        worked=format_minutes(day.worked),
        debt=format_minutes(day.debt),
        exceeding=format_minutes(day.exceeding),
    )


def build_entry(
    date_text: str,
    arrival: Optional[str],
    lunch_out: Optional[str],
    lunch_in: Optional[str],
    departure: Optional[str],
    required_text: Optional[str],
    on_site: bool,
    exact_times: bool,
    note: Optional[str],
    entry_id: Optional[int] = None,
) -> Entry:
    """Turn the form fields into a validated Entry. Raises ValueError if invalid."""
    times = tuple(normalize_time(t) for t in (arrival, lunch_out, lunch_in, departure))
    for value in times:
        if value is not None:
            parse_hhmm(value)
    entry = Entry(
        work_date=parse_date(date_text),
        arrival=times[0],
        lunch_out=times[1],
        lunch_in=times[2],
        departure=times[3],
        required_minutes=parse_required(required_text),
        on_site=on_site,
        exact_times=exact_times,
        note=(note or "").strip() or None,
        id=entry_id,
    )
    calculate_day(*times, entry.required_minutes)  # checks the order of the times
    return entry


# -- dashboard ------------------------------------------------------------

PERIOD_MONTH = "month"
PERIOD_SEMESTER = "semester"
PERIOD_YEAR = "year"
SEMESTER_FIRST_MONTHS = (1, 7)  # Jan-Jun starts in month 1, Jul-Dec in month 7


def period_bounds(kind: str, day: date) -> Tuple[date, date]:
    """First and last day of the month, semester or year that contains `day`."""
    if kind == PERIOD_MONTH:
        return month_range(day)
    if kind == PERIOD_SEMESTER:
        return semester_range(day)
    if kind == PERIOD_YEAR:
        return year_range(day)
    raise ValueError(f"Unknown period kind {kind!r}")


def period_title(kind: str, start: date) -> str:
    """'October 2026', 'Jul-Dec 2026' or '2026'."""
    if kind == PERIOD_MONTH:
        return f"{calendar.month_name[start.month]} {start.year}"
    if kind == PERIOD_SEMESTER:
        first, last = (1, 6) if start.month <= 6 else (7, 12)
        return f"{calendar.month_abbr[first]}-{calendar.month_abbr[last]} {start.year}"
    return str(start.year)


@dataclass(frozen=True)
class PieSlice:
    """One slice of a pie chart. Angles are in degrees for Tk: start 90 is the top,
    a negative extent goes clockwise."""

    label: str
    value: int
    percent: float
    start: float
    extent: float


def pie_slices(parts: List[Tuple[str, int]]) -> List[PieSlice]:
    """Split a circle in proportion to the values, clockwise from the top.

    A zero total gives slices with no extent (nothing to draw).
    """
    total = sum(value for _, value in parts)
    slices = []
    start = 90.0
    for label, value in parts:
        percent = value * 100 / total if total else 0.0
        extent = -360.0 * value / total if total else 0.0
        slices.append(PieSlice(label, value, percent, start, extent))
        start += extent
    return slices


def stats_lines(summary: PeriodSummary, target_percent: int) -> List[Tuple[str, str]]:
    """(label, value) pairs for the dashboard cards."""
    percent = "n/a" if summary.onsite_percent is None else f"{summary.onsite_percent:.1f}%"
    return [
        (strings.STAT_DAYS, str(summary.days_worked)),
        (strings.STAT_ONSITE, str(summary.onsite_days)),
        (strings.STAT_REMOTE, str(summary.remote_days)),
        (strings.STAT_PERCENT, percent),
        (strings.STAT_TARGET, totals_text(summary, target_percent)[1]),
        (strings.STAT_WORKED, format_minutes(summary.worked)),
        (strings.STAT_DEBT, format_minutes(summary.debt)),
        (strings.STAT_EXCEEDING, format_minutes(summary.exceeding)),
        (strings.STAT_BALANCE, format_minutes(summary.balance)),
    ]


def month_breakdown(
    records: List[DayRecord], start: date, end: date, target_percent: int
) -> List[Tuple[str, ...]]:
    """One table row per calendar month between start and end (inclusive)."""
    rows = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        first, last = month_range(date(year, month, 1))
        s = summarize(records, first, last, target_percent)
        rows.append((
            f"{calendar.month_name[month]} {year}",
            str(s.days_worked),
            f"{s.onsite_days} / {s.remote_days}",
            "n/a" if s.onsite_percent is None else f"{s.onsite_percent:.1f}%",
            format_minutes(s.worked),
            format_minutes(s.debt),
            format_minutes(s.exceeding),
            format_minutes(s.balance),
        ))
        year, month = shift_month(year, month, 1)
    return rows
