import sqlite3
import unittest

from tests.test_migrations import MIGRATIONS
from worktime.calc import (
    calculate_day, format_minutes, parse_hhmm, validate_times,
)


class ParseFormatTest(unittest.TestCase):
    def test_parse_valid(self):
        self.assertEqual(parse_hhmm("00:00"), 0)
        self.assertEqual(parse_hhmm("09:47"), 587)
        self.assertEqual(parse_hhmm("23:59"), 1439)

    def test_parse_invalid(self):
        for bad in ("", "9:47", "24:00", "12:60", "12-30", "abc", "12:5", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_hhmm(bad)

    def test_format(self):
        self.assertEqual(format_minutes(399), "6h39")
        self.assertEqual(format_minutes(480), "8h00")
        self.assertEqual(format_minutes(0), "0h00")
        self.assertEqual(format_minutes(-81), "-1h21")


class CalculateDayTest(unittest.TestCase):
    def test_exact_required_day(self):
        day = calculate_day("09:00", "12:00", "13:00", "18:00")
        self.assertEqual((day.worked, day.debt, day.exceeding), (480, 0, 0))
        self.assertTrue(day.complete)

    def test_short_day_has_debt(self):
        # 2h00 + 4h39 = 6h39 -> debt 1h21
        day = calculate_day("09:47", "11:47", "12:51", "17:30")
        self.assertEqual((day.worked, day.debt, day.exceeding), (399, 81, 0))

    def test_long_day_has_exceeding(self):
        # 3h10 + 6h50 = 10h00 -> exceeding 2h00
        day = calculate_day("08:20", "11:30", "12:40", "19:30")
        self.assertEqual((day.worked, day.debt, day.exceeding), (600, 0, 120))

    def test_custom_required_hours(self):
        day = calculate_day("09:00", "12:00", "13:00", "18:00", required=360)
        self.assertEqual((day.debt, day.exceeding), (0, 120))

    def test_lunch_break_not_counted(self):
        day = calculate_day("08:00", "12:00", "14:00", "18:00")  # 2h lunch
        self.assertEqual(day.worked, 480)

    def test_incomplete_day_has_no_totals(self):
        for times in (
            ("08:30", None, None, None),
            ("08:30", "12:00", None, None),
            ("08:30", None, None, "17:00"),
            (None, None, None, None),
            ("08:30", "", "", ""),
        ):
            with self.subTest(times=times):
                day = calculate_day(*times)
                self.assertFalse(day.complete)
                self.assertEqual((day.worked, day.debt, day.exceeding), (None, None, None))

    def test_negative_required_rejected(self):
        with self.assertRaises(ValueError):
            calculate_day("09:00", "12:00", "13:00", "18:00", required=-1)


class ValidateTimesTest(unittest.TestCase):
    def test_in_order_ok(self):
        validate_times("08:00", "12:00", "13:00", "17:00")
        validate_times("08:00", None, None, "17:00")
        validate_times(None, None, None, None)

    def test_equal_times_allowed(self):
        validate_times("08:00", "12:00", "12:00", "17:00")  # no lunch break

    def test_out_of_order_rejected(self):
        with self.assertRaisesRegex(ValueError, "departure"):
            validate_times("08:00", "12:00", "13:00", "12:30")
        with self.assertRaisesRegex(ValueError, "lunch_out"):
            validate_times("13:00", "12:00", "14:00", "17:00")

    def test_out_of_order_rejected_even_with_gaps(self):
        with self.assertRaises(ValueError):
            validate_times("17:00", None, None, "08:00")

    def test_bad_format_rejected(self):
        with self.assertRaises(ValueError):
            validate_times("8:00", "12:00", "13:00", "17:00")

    def test_calculate_rejects_out_of_order(self):
        with self.assertRaises(ValueError):
            calculate_day("09:00", "08:00", "13:00", "18:00")


class SqlParityTest(unittest.TestCase):
    """calc.py and the SQL generated columns must give identical results."""

    def test_python_matches_sql(self):
        con = sqlite3.connect(":memory:")
        con.executescript((MIGRATIONS / "0001_create_entries.sql").read_text(encoding="utf-8"))
        cases = [
            ("09:00", "12:00", "13:00", "18:00", 480),
            ("09:47", "11:47", "12:51", "17:30", 480),
            ("08:20", "11:30", "12:40", "19:30", 480),
            ("07:28", "11:44", "12:57", "18:00", 480),
            ("08:00", "12:00", "14:00", "18:00", 360),
            ("08:00", "12:00", "12:00", "16:00", 0),
            ("08:30", None, None, None, 480),
            ("08:30", "12:00", "13:00", None, 480),
        ]
        for i, (a, lo, li, d, req) in enumerate(cases):
            con.execute(
                "INSERT INTO entries (work_date, arrival, lunch_out, lunch_in, departure, required_minutes)"
                " VALUES (?, ?, ?, ?, ?, ?)", (f"2026-01-{i + 1:02d}", a, lo, li, d, req))
            sql = con.execute(
                "SELECT worked_minutes, debt_minutes, exceeding_minutes FROM entries WHERE work_date=?",
                (f"2026-01-{i + 1:02d}",)).fetchone()
            py = calculate_day(a, lo, li, d, req)
            with self.subTest(case=(a, lo, li, d, req)):
                self.assertEqual(sql, (py.worked, py.debt, py.exceeding))
        con.close()


if __name__ == "__main__":
    unittest.main()
