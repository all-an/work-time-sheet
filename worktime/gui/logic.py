"""GUI helpers that need no window: parsing, validation and display text.

Everything here is unit tested without opening Tkinter.
"""
from __future__ import annotations

import calendar
import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

from worktime.calc import DEFAULT_REQUIRED_MINUTES, calculate_day, format_minutes, parse_hhmm
from worktime.gui import strings
from worktime.models import DayRecord, Entry, PeriodSummary
from worktime.periods import MIN_ONSITE_PERCENT, month_range, semester_range, summarize, year_range

_LOOSE_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")
TIME_FIELDS = ("arrival", "lunch_out", "lunch_in", "departure")
MAX_MORNING_START = "10:30"
MIN_NORMAL_WORKED = 4 * 60
MAX_NORMAL_WORKED = 10 * 60


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


def default_required_minutes(entries: Iterable[Entry]) -> int:
    """Last used required_minutes from the newest entry, or 480 (08:00) if none."""
    latest: Optional[Entry] = None
    for entry in entries:
        if latest is None or entry.work_date >= latest.work_date:
            latest = entry
    return latest.required_minutes if latest is not None else DEFAULT_REQUIRED_MINUTES


def shift_month(year: int, month: int, delta: int) -> Tuple[int, int]:
    """Move (year, month) by delta months: (2026, 12, +1) -> (2027, 1)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


MIN_YEAR = 2000
MAX_YEAR = 2100


def parse_year(
    text: Optional[str], existing_years: Iterable[Union[int, str]] = ()
) -> int:
    """Parse a 4-digit year (2000-2100), or return max(existing_years) + 1 when blank."""
    raw = (text or "").strip()
    if not raw:
        existing = [int(y) for y in existing_years]
        if existing:
            candidate = max(existing) + 1
            if MIN_YEAR <= candidate <= MAX_YEAR:
                return candidate
        raise ValueError(f"Invalid year {text!r}: expected YYYY ({MIN_YEAR}-{MAX_YEAR})")
    if not raw.isdigit():
        raise ValueError(f"Invalid year {text!r}: expected YYYY ({MIN_YEAR}-{MAX_YEAR})")
    year = int(raw)
    if not (MIN_YEAR <= year <= MAX_YEAR):
        raise ValueError(f"Invalid year {text!r}: expected YYYY ({MIN_YEAR}-{MAX_YEAR})")
    return year


def year_choices(
    entries: Iterable[Entry],
    today: date,
    extra_years: Iterable[Union[int, str]] = (),
) -> List[int]:
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
    if entry.vacation:
        return "vacation"
    if entry.holiday:
        return "holiday"
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


def entry_warnings(
    arrival: Optional[str],
    lunch_out: Optional[str],
    lunch_in: Optional[str],
    departure: Optional[str],
    required: int = DEFAULT_REQUIRED_MINUTES,
) -> List[str]:
    """Non-blocking warnings for odd but technically valid entries."""
    t_arr, t_out, t_in, t_dep = (
        normalize_time(arrival),
        normalize_time(lunch_out),
        normalize_time(lunch_in),
        normalize_time(departure),
    )
    warnings: List[str] = []
    try:
        day = calculate_day(t_arr, t_out, t_in, t_dep, required)
    except ValueError:
        return warnings
    if t_arr and t_arr > MAX_MORNING_START:
        warnings.append(f"late arrival {t_arr}")
    if day.complete and day.worked is not None:
        if required >= MIN_NORMAL_WORKED and day.worked < MIN_NORMAL_WORKED:
            warnings.append("under 4h worked")
        if day.worked > MAX_NORMAL_WORKED:
            warnings.append("over 10h worked")
    return warnings


def preview_text(
    arrival: Optional[str],
    lunch_out: Optional[str],
    lunch_in: Optional[str],
    departure: Optional[str],
    required_text: Optional[str],
) -> str:
    """Live preview under the form. Returns the error message if the input is invalid."""
    try:
        required = parse_required(required_text)
        day = calculate_day(
            normalize_time(arrival),
            normalize_time(lunch_out),
            normalize_time(lunch_in),
            normalize_time(departure),
            required,
        )
    except ValueError as error:
        return str(error)
    if not day.complete:
        return strings.PREVIEW_INCOMPLETE
    text = strings.PREVIEW_TEMPLATE.format(
        worked=format_minutes(day.worked),
        debt=format_minutes(day.debt),
        exceeding=format_minutes(day.exceeding),
    )
    warnings = entry_warnings(arrival, lunch_out, lunch_in, departure, required)
    if warnings:
        return f"{text}   Warning: {'; '.join(warnings)}"
    return text


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
    vacation: bool = False,
    holiday: bool = False,
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
        vacation=vacation,
        holiday=holiday,
    )
    calculate_day(*times, entry.required_minutes)  # checks the order of the times
    return entry


@dataclass(frozen=True)
class InlineDayState:
    """Live validation and calculation result for one inline day row in the grid."""

    valid: bool
    empty: bool
    invalid_fields: Tuple[str, ...]
    worked_text: str
    debt_text: str
    exceeding_text: str
    state: str  # "empty", "open", "debt", "exceeding", "ok" or "invalid"
    error: Optional[str]
    warnings: Tuple[str, ...]
    entry_to_save: Optional[Entry]


def validate_inline_day(
    work_date: date,
    arrival: Optional[str],
    lunch_out: Optional[str],
    lunch_in: Optional[str],
    departure: Optional[str],
    on_site: bool,
    existing: Optional[Entry] = None,
    default_required: int = DEFAULT_REQUIRED_MINUTES,
    note: Optional[str] = None,
    vacation: bool = False,
    holiday: bool = False,
) -> InlineDayState:
    """Validate inline grid fields for `work_date` and compute live cell values."""
    normalized = [normalize_time(t) for t in (arrival, lunch_out, lunch_in, departure)]
    clean_note = (
        (note.strip() or None)
        if note is not None
        else (existing.note if existing is not None else None)
    )
    required = existing.required_minutes if existing is not None else default_required
    exact_times = existing.exact_times if existing is not None else True
    entry_id = existing.id if existing is not None else None

    invalid: List[str] = []
    first_error: Optional[str] = None
    parsed: List[Optional[int]] = [None, None, None, None]

    for idx, (name, val) in enumerate(zip(TIME_FIELDS, normalized)):
        if val is None:
            continue
        try:
            parsed[idx] = parse_hhmm(val)
        except ValueError as err:
            invalid.append(name)
            first_error = first_error or str(err)

    prev_name: Optional[str] = None
    prev_val = -1
    for name, val, minutes in zip(TIME_FIELDS, normalized, parsed):
        if minutes is None:
            continue
        if minutes < prev_val:
            if name not in invalid:
                invalid.append(name)
            first_error = first_error or f"{name} ({val}) is earlier than {prev_name}"
        else:
            prev_name, prev_val = name, minutes

    if invalid:
        return InlineDayState(
            valid=False,
            empty=False,
            invalid_fields=tuple(invalid),
            worked_text="",
            debt_text="",
            exceeding_text="",
            state="invalid",
            error=first_error,
            warnings=(),
            entry_to_save=None,
        )

    if all(t is None for t in normalized) and clean_note is None and not on_site and not vacation and not holiday:
        return InlineDayState(
            valid=True,
            empty=True,
            invalid_fields=(),
            worked_text="",
            debt_text="",
            exceeding_text="",
            state="empty",
            error=None,
            warnings=(),
            entry_to_save=None,
        )

    day = calculate_day(*normalized, required=required)
    warnings = tuple(entry_warnings(*normalized, required=required))
    if vacation or holiday:
        state = "vacation" if vacation else "holiday"
        worked_str = debt_str = exceeding_str = ""
        warnings = ()
    elif not day.complete:
        state = "open"
        worked_str = strings.OPEN_DAY
        debt_str = ""
        exceeding_str = ""
    else:
        worked_str = format_minutes(day.worked)
        debt_str = format_minutes(day.debt)
        exceeding_str = format_minutes(day.exceeding)
        if day.debt:
            state = "debt"
        elif day.exceeding:
            state = "exceeding"
        else:
            state = "ok"

    entry_to_save = Entry(
        work_date=work_date,
        arrival=normalized[0],
        lunch_out=normalized[1],
        lunch_in=normalized[2],
        departure=normalized[3],
        required_minutes=required,
        on_site=on_site,
        exact_times=exact_times,
        note=clean_note,
        id=entry_id,
        worked_minutes=day.worked,
        debt_minutes=day.debt,
        exceeding_minutes=day.exceeding,
        vacation=vacation,
        holiday=holiday,
    )
    return InlineDayState(
        valid=True,
        empty=False,
        invalid_fields=(),
        worked_text=worked_str,
        debt_text=debt_str,
        exceeding_text=exceeding_str,
        state=state,
        error=None,
        warnings=warnings,
        entry_to_save=entry_to_save,
    )


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


def cumulative_balance(records: Iterable[DayRecord], end: date) -> int:
    """Running net balance (exceeding - debt) of all completed days up to `end` (inclusive)."""
    total = 0
    for record in records:
        if record.work_date <= end and record.summary.complete and not record.vacation and not record.holiday:
            total += (record.summary.exceeding or 0) - (record.summary.debt or 0)
    return total


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


def running_balance_breakdown(
    records: List[DayRecord], start: date, end: date, target_percent: int
) -> List[Tuple[str, ...]]:
    """Monthly breakdown between start and end with a 9th column: cumulative carry-over balance."""
    rows = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        first, last = month_range(date(year, month, 1))
        s = summarize(records, first, last, target_percent)
        cum = cumulative_balance(records, last)
        rows.append((
            f"{calendar.month_name[month]} {year}",
            str(s.days_worked),
            f"{s.onsite_days} / {s.remote_days}",
            "n/a" if s.onsite_percent is None else f"{s.onsite_percent:.1f}%",
            format_minutes(s.worked),
            format_minutes(s.debt),
            format_minutes(s.exceeding),
            format_minutes(s.balance),
            format_minutes(cum),
        ))
        year, month = shift_month(year, month, 1)
    return rows


def export_period_csv(entries: Iterable[Entry], start: date, end: date) -> str:
    """Format entries with start <= work_date <= end as CSV text."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(strings.CSV_COLUMNS)
    selected = sorted(
        (e for e in entries if start <= e.work_date <= end),
        key=lambda e: e.work_date,
    )
    for entry in selected:
        writer.writerow([
            format_date(entry.work_date),
            entry.arrival or "",
            entry.lunch_out or "",
            entry.lunch_in or "",
            entry.departure or "",
            required_text(entry.required_minutes),
            strings.YES if entry.on_site else strings.NO,
            strings.YES if entry.exact_times else strings.NO,
            minutes_text(entry.worked_minutes) or (strings.OPEN_DAY if any(
                (entry.arrival, entry.lunch_out, entry.lunch_in, entry.departure)
            ) else ""),
            minutes_text(entry.debt_minutes),
            minutes_text(entry.exceeding_minutes),
            entry.note or "",
        ])
    return buf.getvalue()


def write_period_csv(
    path: Union[str, Path], entries: Iterable[Entry], start: date, end: date
) -> int:
    """Write the CSV for [start, end] to `path`. Returns the number of exported entries."""
    selected = [e for e in entries if start <= e.work_date <= end]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(export_period_csv(selected, start, end), encoding="utf-8")
    return len(selected)


def default_backup_name(today: date) -> str:
    """Default filename for a database backup."""
    return f"worktime-backup-{today.isoformat()}.sqlite3"


def default_csv_name(kind: str, start: date) -> str:
    """Default filename for a period CSV export."""
    if kind == PERIOD_MONTH:
        return f"worktime-{start.year}-{start.month:02d}.csv"
    if kind == PERIOD_SEMESTER:
        half = "H1" if start.month <= 6 else "H2"
        return f"worktime-{start.year}-{half}.csv"
    return f"worktime-{start.year}.csv"


# -- 6-month projection ---------------------------------------------------


@dataclass(frozen=True)
class WeekProjectionRow:
    """One remaining week in the 6-month projection table."""

    week_label: str
    workdays: int
    onsite_days: int
    remote_days: int
    daily_minutes: int
    weekly_minutes: int
    projected_onsite_percent: float
    projected_balance: int


@dataclass(frozen=True)
class SemesterProjection:
    """Projection for a 6-month semester based on completed entries so far."""

    start: date
    end: date
    as_of: date
    days_worked: int
    onsite_days: int
    remote_days: int
    current_onsite_percent: Optional[float]
    current_balance: int
    remaining_workdays: int
    remaining_weeks: int
    projected_total_days: int
    projected_onsite_target: int
    onsite_still_needed: int
    onsite_days_per_week: float
    recommended_onsite_per_week: int
    extra_minutes_per_day: int
    daily_minutes_needed: int
    weekly_minutes_needed: int
    schedule_suggestion: str
    achievable_onsite: bool
    weekly_plan: Tuple[WeekProjectionRow, ...]


def suggested_schedule(
    daily_minutes: int,
    arrival: str = "09:00",
    lunch_out: str = "12:00",
    lunch_in: str = "13:00",
) -> str:
    """Sample daily clock times for `daily_minutes` of work, e.g. '09:00-12:00, 13:00-18:01'."""
    morning = parse_hhmm(lunch_out) - parse_hhmm(arrival)
    afternoon = max(0, daily_minutes - morning)
    departure_total = min(23 * 60 + 59, parse_hhmm(lunch_in) + afternoon)
    departure = required_text(departure_total)
    return f"{arrival}-{lunch_out}, {lunch_in}-{departure}"


def build_semester_projection(
    records: Iterable[DayRecord],
    semester_day: date,
    today: date,
    min_percent: int = MIN_ONSITE_PERCENT,
    required_per_day: int = DEFAULT_REQUIRED_MINUTES,
) -> SemesterProjection:
    """Project how many on-site days/week and daily hours are needed to meet the 6-month targets."""
    record_list = list(records)
    start, end = semester_range(semester_day)
    summary = summarize(record_list, start, end, min_percent)
    completed_dates = {
        r.work_date for r in record_list if start <= r.work_date <= end and r.summary.complete
    }
    # Vacation and holiday days are not workdays: they are neither worked nor left to work.
    ignored_dates = {r.work_date for r in record_list if r.vacation or r.holiday}

    remaining_days: List[date] = []
    if today <= end:
        cursor = max(start, today)
        while cursor <= end:
            if cursor.weekday() < 5 and cursor not in completed_dates and cursor not in ignored_dates:
                remaining_days.append(cursor)
            cursor += timedelta(days=1)

    week_groups: List[List[date]] = []
    for day in remaining_days:
        monday = day - timedelta(days=day.weekday())
        if not week_groups or (week_groups[-1][0] - timedelta(days=week_groups[-1][0].weekday())) != monday:
            week_groups.append([day])
        else:
            week_groups[-1].append(day)

    remaining_workdays = len(remaining_days)
    remaining_weeks = len(week_groups)
    projected_total_days = summary.days_worked + remaining_workdays
    projected_onsite_target = (projected_total_days * min_percent + 99) // 100
    onsite_still_needed = max(0, projected_onsite_target - summary.onsite_days)
    achievable_onsite = onsite_still_needed <= remaining_workdays

    if remaining_workdays > 0:
        onsite_days_per_week = onsite_still_needed * 5 / remaining_workdays
        recommended_onsite_per_week = min(5, math.ceil(onsite_days_per_week))
    else:
        onsite_days_per_week = 0.0
        recommended_onsite_per_week = 0

    debt_to_recover = max(0, -summary.balance)
    if remaining_workdays > 0 and debt_to_recover > 0:
        extra_minutes_per_day = (debt_to_recover + remaining_workdays - 1) // remaining_workdays
    else:
        extra_minutes_per_day = 0

    daily_minutes_needed = required_per_day + extra_minutes_per_day
    weekly_minutes_needed = daily_minutes_needed * 5
    schedule = suggested_schedule(daily_minutes_needed)

    target_to_place = min(onsite_still_needed, remaining_workdays)
    placed_onsite = 0
    seen_workdays = 0
    running_days = summary.days_worked
    running_onsite = summary.onsite_days
    running_balance = summary.balance
    plan: List[WeekProjectionRow] = []

    for week in week_groups:
        w_days = len(week)
        seen_workdays += w_days
        desired_cum = round(target_to_place * seen_workdays / remaining_workdays)
        w_onsite = min(w_days, max(0, desired_cum - placed_onsite))
        placed_onsite += w_onsite
        w_remote = w_days - w_onsite
        running_days += w_days
        running_onsite += w_onsite
        running_balance += w_days * extra_minutes_per_day
        proj_pct = running_onsite * 100 / running_days if running_days else 0.0
        label = f"{format_date(week[0])} - {format_date(week[-1])}"
        plan.append(
            WeekProjectionRow(
                week_label=label,
                workdays=w_days,
                onsite_days=w_onsite,
                remote_days=w_remote,
                daily_minutes=daily_minutes_needed,
                weekly_minutes=daily_minutes_needed * w_days,
                projected_onsite_percent=proj_pct,
                projected_balance=running_balance,
            )
        )

    return SemesterProjection(
        start=start,
        end=end,
        as_of=today,
        days_worked=summary.days_worked,
        onsite_days=summary.onsite_days,
        remote_days=summary.remote_days,
        current_onsite_percent=summary.onsite_percent,
        current_balance=summary.balance,
        remaining_workdays=remaining_workdays,
        remaining_weeks=remaining_weeks,
        projected_total_days=projected_total_days,
        projected_onsite_target=projected_onsite_target,
        onsite_still_needed=onsite_still_needed,
        onsite_days_per_week=onsite_days_per_week,
        recommended_onsite_per_week=recommended_onsite_per_week,
        extra_minutes_per_day=extra_minutes_per_day,
        daily_minutes_needed=daily_minutes_needed,
        weekly_minutes_needed=weekly_minutes_needed,
        schedule_suggestion=schedule,
        achievable_onsite=achievable_onsite,
        weekly_plan=tuple(plan),
    )


def projection_stats(
    proj: SemesterProjection, target_percent: int = MIN_ONSITE_PERCENT
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Return (onsite_card_lines, hours_card_lines) for the Projection tab."""
    cur_pct = "n/a" if proj.current_onsite_percent is None else f"{proj.current_onsite_percent:.1f}%"
    if proj.remaining_workdays == 0:
        pace = "No remaining workdays in this semester"
    elif proj.onsite_still_needed == 0:
        pace = f"0 days/week needed ({target_percent}% target already met)"
    elif not proj.achievable_onsite:
        shortfall = proj.onsite_still_needed - proj.remaining_workdays
        pace = f"5 days/week (100% on-site; still {shortfall} day(s) short)"
    else:
        pace = (
            f"{proj.recommended_onsite_per_week} day(s)/week on-site "
            f"(exact average: {proj.onsite_days_per_week:.1f} days/week)"
        )

    onsite_lines = [
        (
            strings.PROJ_WORKED_SO_FAR,
            f"{proj.days_worked} days ({proj.onsite_days} on-site, {proj.remote_days} remote — {cur_pct})",
        ),
        (
            strings.PROJ_REMAINING_DAYS,
            f"{proj.remaining_workdays} workdays across {proj.remaining_weeks} week(s)",
        ),
        (
            strings.PROJ_TOTAL_PROJECTED,
            f"{proj.projected_total_days} days (need {proj.projected_onsite_target} on-site for {target_percent}%)",
        ),
        (strings.PROJ_ONSITE_NEEDED, f"{proj.onsite_still_needed} more on-site day(s)"),
        (strings.PROJ_ONSITE_PACE, pace),
    ]

    if proj.extra_minutes_per_day > 0:
        extra_str = f"+{format_minutes(proj.extra_minutes_per_day)} / day to clear debt"
    else:
        extra_str = "0h00 / day (no debt to recover)"

    hours_lines = [
        (strings.PROJ_CURRENT_BALANCE, format_minutes(proj.current_balance)),
        (strings.PROJ_EXTRA_PER_DAY, extra_str),
        (strings.PROJ_DAILY_TARGET, f"{format_minutes(proj.daily_minutes_needed)} / day"),
        (strings.PROJ_WEEKLY_TARGET, f"{format_minutes(proj.weekly_minutes_needed)} / 5-day week"),
        (strings.PROJ_SCHEDULE, proj.schedule_suggestion),
    ]
    return onsite_lines, hours_lines


def projection_table_rows(proj: SemesterProjection) -> List[Tuple[str, ...]]:
    """Display rows for the weekly projection table."""
    return [
        (
            row.week_label,
            str(row.workdays),
            f"{row.onsite_days} on-site / {row.remote_days} remote",
            f"{format_minutes(row.daily_minutes)} ({proj.schedule_suggestion})",
            format_minutes(row.weekly_minutes),
            f"{row.projected_onsite_percent:.1f}%",
            format_minutes(row.projected_balance),
        )
        for row in proj.weekly_plan
    ]


# -- week CSV import (Friday button) --------------------------------------

_WEEKDAY_OFFSETS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}
_TRUTHY = {"yes", "true", "1", "sim", "on-site", "onsite", "y"}
_FALSY = {"no", "false", "0", "nao", "não", "remote", "n"}


def is_friday(work_date: date) -> bool:
    """True when `work_date` is a Friday (weekday 4)."""
    return work_date.weekday() == 4


def _parse_csv_date(raw: str) -> date:
    value = raw.strip()
    if "/" in value:
        return parse_date(value)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Invalid date {raw!r}: expected dd/mm/yyyy or YYYY-MM-DD") from None


def parse_week_csv(
    csv_text: str,
    friday: date,
    default_required: int = DEFAULT_REQUIRED_MINUTES,
) -> List[Entry]:
    """Parse a week CSV exported from the external system into validated Entry objects.

    Supports rows with an explicit Date column (dd/mm/yyyy or YYYY-MM-DD), a Day
    column (Mon..Fri), or positional rows mapped to Monday..Friday of `friday`'s week.
    """
    monday = friday - timedelta(days=friday.weekday())
    lines = [line for line in (csv_text or "").splitlines() if line.strip()]
    if not lines:
        raise ValueError("The CSV file is empty")

    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    if not reader.fieldnames:
        raise ValueError("The CSV file has no header row")

    entries: List[Entry] = []
    for row_idx, raw_row in enumerate(reader):
        norm = {
            re.sub(r"[\s\-]+", "_", (k or "").strip().lower()): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }
        raw_date = norm.get("date") or norm.get("work_date") or ""
        raw_day = (norm.get("day") or norm.get("weekday") or "").lower()
        if raw_date:
            work_date = _parse_csv_date(raw_date)
        elif raw_day in _WEEKDAY_OFFSETS:
            work_date = monday + timedelta(days=_WEEKDAY_OFFSETS[raw_day])
        else:
            if row_idx > 6:
                raise ValueError("Week CSV without dates cannot have more than 7 rows")
            work_date = monday + timedelta(days=row_idx)

        arrival = normalize_time(norm.get("arrival"))
        lunch_out = normalize_time(norm.get("lunch_out"))
        lunch_in = normalize_time(norm.get("lunch_in"))
        departure = normalize_time(norm.get("departure"))
        for value in (arrival, lunch_out, lunch_in, departure):
            if value is not None:
                parse_hhmm(value)

        raw_req = norm.get("required") or norm.get("required_hours") or ""
        required = parse_required(raw_req) if raw_req else default_required

        raw_site = (norm.get("on_site") or norm.get("presencial") or norm.get("site") or "").lower()
        on_site = raw_site in _TRUTHY

        raw_exact = (norm.get("exact_times") or norm.get("exact") or "").lower()
        exact_times = False if raw_exact in _FALSY else True

        note = (norm.get("note") or norm.get("notes") or "").strip() or None

        if all(t is None for t in (arrival, lunch_out, lunch_in, departure)) and note is None and not on_site:
            continue

        calculate_day(arrival, lunch_out, lunch_in, departure, required)
        entries.append(
            Entry(
                work_date=work_date,
                arrival=arrival,
                lunch_out=lunch_out,
                lunch_in=lunch_in,
                departure=departure,
                required_minutes=required,
                on_site=on_site,
                exact_times=exact_times,
                note=note,
            )
        )
    if not entries:
        raise ValueError("No valid day entries found in the CSV file")
    return entries
