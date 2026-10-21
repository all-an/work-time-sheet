"""Pure time calculations. No GUI and no database.

Rules (same as the SQL generated columns in migrations/0001):
  worked    = (lunch_out - arrival) + (departure - lunch_in)
  debt      = required - worked   when worked < required, else 0
  exceeding = worked - required   when worked > required, else 0
A day is complete only when all four times are present; otherwise
worked, debt and exceeding are None.
"""
from __future__ import annotations

import re
from typing import Optional

from worktime.models import DaySummary

DEFAULT_REQUIRED_MINUTES = 480  # 08:00

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_FIELDS = ("arrival", "lunch_out", "lunch_in", "departure")


def parse_hhmm(value: str) -> int:
    """'09:47' -> 587 (minutes since midnight). Strict HH:MM, 00:00-23:59."""
    match = _HHMM.match(value or "")
    if not match:
        raise ValueError(f"Invalid time {value!r}: expected HH:MM (00:00-23:59)")
    return int(match.group(1)) * 60 + int(match.group(2))


def format_minutes(minutes: int) -> str:
    """399 -> '6h39', -81 -> '-1h21', 480 -> '8h00'."""
    sign = "-" if minutes < 0 else ""
    hours, mins = divmod(abs(minutes), 60)
    return f"{sign}{hours}h{mins:02d}"


def validate_times(
    arrival: Optional[str],
    lunch_out: Optional[str],
    lunch_in: Optional[str],
    departure: Optional[str],
) -> None:
    """Raise ValueError if a time is malformed or the times are out of order.

    Missing (None or empty) times are allowed (incomplete day), but the ones
    that are present must not go backwards: arrival <= lunch_out <= lunch_in <= departure.
    """
    previous_name: Optional[str] = None
    previous_value = -1
    for name, raw in zip(_FIELDS, (arrival, lunch_out, lunch_in, departure)):
        if raw is None or raw == "":
            continue
        value = parse_hhmm(raw)
        if value < previous_value:
            raise ValueError(f"{name} ({raw}) is earlier than {previous_name}")
        previous_name, previous_value = name, value


def calculate_day(
    arrival: Optional[str],
    lunch_out: Optional[str],
    lunch_in: Optional[str],
    departure: Optional[str],
    required: int = DEFAULT_REQUIRED_MINUTES,
) -> DaySummary:
    """Calculate worked, debt and exceeding minutes for one day."""
    if required < 0:
        raise ValueError("required minutes cannot be negative")
    validate_times(arrival, lunch_out, lunch_in, departure)
    if not (arrival and lunch_out and lunch_in and departure):
        return DaySummary(complete=False, required=required)

    worked = (parse_hhmm(lunch_out) - parse_hhmm(arrival)) + (
        parse_hhmm(departure) - parse_hhmm(lunch_in)
    )
    return DaySummary(
        complete=True,
        required=required,
        worked=worked,
        debt=max(required - worked, 0),
        exceeding=max(worked - required, 0),
    )
