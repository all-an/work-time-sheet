"""Review the seeded sheet data: python -m worktime.report_seed [DB_PATH]

Prints every day with worked, debt and exceeding, then a total per month, so
the numbers can be compared with the old sheets. Days that need attention
(open days, odd time ranges) are flagged. Read-only: the database is not changed.
"""
from __future__ import annotations

import sys
from datetime import date
from typing import List

from worktime import db
from worktime.calc import format_minutes
from worktime.models import Entry
from worktime.periods import MIN_ONSITE_PERCENT, month_range, summarize

# A morning block longer than this, or an arrival this late, is probably a typo.
MAX_MORNING_START = "10:30"


def flags_for(entry: Entry) -> List[str]:
    """Reasons to double check a day against the sheet."""
    flags = []
    if entry.worked_minutes is None:
        flags.append("open day, excluded from totals")
        return flags
    if entry.arrival and entry.arrival > MAX_MORNING_START:
        flags.append(f"late arrival {entry.arrival}")
    if entry.worked_minutes < 4 * 60:
        flags.append("under 4h worked")
    if entry.worked_minutes > 10 * 60:
        flags.append("over 10h worked")
    return flags


def months_in(entries: List[Entry]) -> List[date]:
    """First day of every month that has at least one entry, in order."""
    return sorted({date(e.work_date.year, e.work_date.month, 1) for e in entries})


def build_report(entries: List[Entry]) -> str:
    lines = ["Date        Worked  Debt    Exceeding  Site  Flags"]
    for e in entries:
        worked = "-" if e.worked_minutes is None else format_minutes(e.worked_minutes)
        debt = "-" if e.debt_minutes is None else format_minutes(e.debt_minutes)
        exceeding = "-" if e.exceeding_minutes is None else format_minutes(e.exceeding_minutes)
        flags = "; ".join(flags_for(e))
        lines.append(
            f"{e.work_date}  {worked:<7} {debt:<7} {exceeding:<10} "
            f"{'yes' if e.on_site else 'no':<5} {flags}".rstrip()
        )

    records = [db.to_day_record(e) for e in entries]
    for first in months_in(entries):
        start, end = month_range(first)
        s = summarize(records, start, end)
        open_days = sum(1 for e in entries if start <= e.work_date <= end and e.worked_minutes is None)
        percent = "n/a" if s.onsite_percent is None else f"{s.onsite_percent:.1f}%"
        lines += [
            "",
            f"Total {first:%b %Y}",
            f"  Days worked:  {s.days_worked} (open days: {open_days})",
            f"  On-site:      {s.onsite_days} of {s.days_worked} = {percent} "
            f"(target {MIN_ONSITE_PERCENT}%: {'met' if s.target_met else 'not met'})",
            f"  Worked:       {format_minutes(s.worked)}",
            f"  Debt:         {format_minutes(s.debt)}",
            f"  Exceeding:    {format_minutes(s.exceeding)}",
            f"  Balance:      {format_minutes(s.balance)}",
        ]
    return "\n".join(lines)


def main(argv: list) -> int:
    path = argv[0] if argv else db.DEFAULT_DB_PATH
    con = db.connect(path)
    print(build_report(db.EntryRepository(con).list_all()))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
