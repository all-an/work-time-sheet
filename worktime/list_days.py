"""Create db.sqlite3 if needed and list every day: python -m worktime.list_days [DB_PATH]"""
import sys

from worktime import db
from worktime.calc import format_minutes


def _fmt(minutes) -> str:
    return "-" if minutes is None else format_minutes(minutes)


def main(argv: list) -> int:
    path = argv[0] if argv else db.DEFAULT_DB_PATH
    con = db.connect(path)
    entries = db.EntryRepository(con).list_all()
    print(f"{path}: {len(entries)} days")
    print("Date        In     Lunch out  Lunch in  Out    Site  Worked  Debt   Exceeding")
    for e in entries:
        print(
            f"{e.work_date}  {e.arrival or '-':<6} {e.lunch_out or '-':<10} "
            f"{e.lunch_in or '-':<9} {e.departure or '-':<6} {'yes' if e.on_site else 'no':<5} "
            f"{_fmt(e.worked_minutes):<7} {_fmt(e.debt_minutes):<6} {_fmt(e.exceeding_minutes)}"
        )
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
