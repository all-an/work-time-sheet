"""Print a month summary for a hard-coded list of days: python -m worktime.demo_periods"""
from datetime import date

from worktime.calc import calculate_day, format_minutes
from worktime.models import DayRecord
from worktime.periods import MIN_ONSITE_PERCENT, month_range, summarize

# (date, arrival, lunch_out, lunch_in, departure, on_site)
SAMPLE = [
    (date(2026, 10, 1), "09:47", "11:47", "12:51", "17:30", False),
    (date(2026, 10, 2), "09:00", "12:00", "13:00", "18:00", True),
    (date(2026, 10, 5), "09:00", "12:00", "13:00", "17:00", True),
    (date(2026, 10, 6), "09:00", None, None, None, True),
]


def main() -> int:
    records = [
        DayRecord(d, on_site, calculate_day(a, lo, li, dep))
        for d, a, lo, li, dep, on_site in SAMPLE
    ]
    start, end = month_range(SAMPLE[0][0])
    s = summarize(records, start, end)
    print(f"Period:       {start} to {end}")
    print(f"Days worked:  {s.days_worked} (on-site {s.onsite_days}, remote {s.remote_days})")
    print(f"On-site:      {s.onsite_percent:.1f}% (target {MIN_ONSITE_PERCENT}%)")
    print(f"Worked:       {format_minutes(s.worked)}")
    print(f"Debt:         {format_minutes(s.debt)}")
    print(f"Exceeding:    {format_minutes(s.exceeding)}")
    print(f"Balance:      {format_minutes(s.balance)}")
    print(f"Target met:   {'yes' if s.target_met else 'no'}")
    print(f"On-site days needed: {s.onsite_days_needed}; remote days spare: {s.remote_days_spare}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
