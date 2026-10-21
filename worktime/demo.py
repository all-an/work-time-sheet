"""Try the calculation: python -m worktime.demo ARRIVAL LUNCH_OUT LUNCH_IN DEPARTURE [REQUIRED_HH:MM]

Example: python -m worktime.demo 09:47 11:47 12:51 17:30
"""
import sys

from worktime.calc import DEFAULT_REQUIRED_MINUTES, calculate_day, format_minutes, parse_hhmm


def main(argv: list) -> int:
    if len(argv) not in (4, 5):
        print(__doc__)
        return 2
    required = parse_hhmm(argv[4]) if len(argv) == 5 else DEFAULT_REQUIRED_MINUTES
    try:
        day = calculate_day(argv[0], argv[1], argv[2], argv[3], required)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    print(f"Required:  {format_minutes(day.required)}")
    print(f"Worked:    {format_minutes(day.worked)}")
    print(f"Debt:      {format_minutes(day.debt)}")
    print(f"Exceeding: {format_minutes(day.exceeding)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
