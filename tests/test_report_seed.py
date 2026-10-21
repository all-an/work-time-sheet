import sqlite3
import unittest
from datetime import date

from worktime import db
from worktime.models import Entry
from worktime.report_seed import build_report, flags_for, months_in


def seeded_entries():
    con = sqlite3.connect(":memory:")
    db.migrate(con)
    entries = db.EntryRepository(con).list_all()
    con.close()
    return entries


class FlagTests(unittest.TestCase):
    def test_open_day_is_flagged(self):
        self.assertEqual(flags_for(Entry(date(2026, 10, 21), arrival="08:30")),
                         ["open day, excluded from totals"])

    def test_normal_day_has_no_flags(self):
        entry = Entry(date(2026, 10, 2), "09:00", "12:00", "13:00", "18:00", worked_minutes=480)
        self.assertEqual(flags_for(entry), [])

    def test_22_sep_typo_is_flagged(self):
        by_date = {e.work_date: e for e in seeded_entries()}
        self.assertIn("late arrival 11:38", flags_for(by_date[date(2026, 9, 22)]))

    def test_short_and_long_days(self):
        short = Entry(date(2026, 1, 1), arrival="09:00", worked_minutes=239)
        long_ = Entry(date(2026, 1, 1), arrival="09:00", worked_minutes=601)
        self.assertIn("under 4h worked", flags_for(short))
        self.assertIn("over 10h worked", flags_for(long_))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.entries = seeded_entries()
        self.report = build_report(self.entries)

    def test_months_found(self):
        self.assertEqual(months_in(self.entries), [date(2026, 9, 1), date(2026, 10, 1)])

    def test_one_row_per_day_plus_header(self):
        day_rows = [l for l in self.report.splitlines() if l[:4] == "2026"]
        self.assertEqual(len(day_rows), 32)

    def test_oct_1_row(self):
        row = next(l for l in self.report.splitlines() if l.startswith("2026-10-01"))
        self.assertIn("6h39", row)   # 2h00 + 4h39
        self.assertIn("1h21", row)   # debt

    def test_sep_totals_by_hand(self):
        # 18 days, 7 on-site, worked 8666 min = 144h26, debt 352 = 5h52,
        # exceeding 378 = 6h18, balance +26 = 0h26
        section = self.report.split("Total Sep 2026")[1].split("Total Oct 2026")[0]
        self.assertIn("Days worked:  18 (open days: 0)", section)
        self.assertIn("On-site:      7 of 18 = 38.9% (target 50%: not met)", section)
        self.assertIn("Worked:       144h26", section)
        self.assertIn("Debt:         5h52", section)
        self.assertIn("Exceeding:    6h18", section)
        self.assertIn("Balance:      0h26", section)

    def test_oct_totals_by_hand(self):
        # 13 complete days (21 Oct is open), 5 on-site, worked 6185 min = 103h05,
        # debt 371 = 6h11, exceeding 316 = 5h16, balance -55 = -0h55
        section = self.report.split("Total Oct 2026")[1]
        self.assertIn("Days worked:  13 (open days: 1)", section)
        self.assertIn("On-site:      5 of 13 = 38.5% (target 50%: not met)", section)
        self.assertIn("Worked:       103h05", section)
        self.assertIn("Debt:         6h11", section)
        self.assertIn("Exceeding:    5h16", section)
        self.assertIn("Balance:      -0h55", section)

    def test_empty_database_gives_header_only(self):
        self.assertEqual(build_report([]), "Date        Worked  Debt    Exceeding  Site  Flags")


if __name__ == "__main__":
    unittest.main()
