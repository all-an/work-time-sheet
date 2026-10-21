import sqlite3
import unittest
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "worktime" / "migrations"


def migrated_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    for sql_file in sorted(MIGRATIONS.glob("*.sql")):
        con.executescript(sql_file.read_text(encoding="utf-8"))
    return con


class SeedMigrationTest(unittest.TestCase):
    def setUp(self):
        self.con = migrated_db()

    def tearDown(self):
        self.con.close()

    def test_row_counts(self):
        count = lambda like: self.con.execute(
            "SELECT COUNT(*) FROM entries WHERE work_date LIKE ?", (like,)).fetchone()[0]
        self.assertEqual(count("2026-09-%"), 18)
        self.assertEqual(count("2026-10-%"), 14)

    def test_swapped_dates_were_fixed(self):
        dates = {r[0] for r in self.con.execute("SELECT work_date FROM entries")}
        for d in ("2026-10-02", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-12"):
            self.assertIn(d, dates)
        self.assertNotIn("2026-01-10", dates)
        self.assertNotIn("2026-12-10", dates)

    def test_oct_1_uses_010_oct_values(self):
        row = self.con.execute(
            "SELECT arrival, lunch_out, lunch_in, departure, on_site FROM entries "
            "WHERE work_date='2026-10-01'").fetchone()
        self.assertEqual(row, ("09:47", "11:47", "12:51", "17:30", 0))

    def test_on_site_and_exact_flags(self):
        row = self.con.execute(
            "SELECT on_site, exact_times FROM entries WHERE work_date='2026-09-07'").fetchone()
        self.assertEqual(row, (1, 0))   # Sim + Hora aproximada
        row = self.con.execute(
            "SELECT on_site, exact_times FROM entries WHERE work_date='2026-09-15'").fetchone()
        self.assertEqual(row, (0, 1))   # Nao + Hora real

    def test_incomplete_day_has_only_arrival(self):
        row = self.con.execute(
            "SELECT arrival, lunch_out, lunch_in, departure FROM entries "
            "WHERE work_date='2026-10-21'").fetchone()
        self.assertEqual(row, ("08:30", None, None, None))

    def _calc(self, date):
        return self.con.execute(
            "SELECT worked_minutes, debt_minutes, exceeding_minutes FROM entries "
            "WHERE work_date=?", (date,)).fetchone()

    def test_exact_required_day_has_no_debt_or_exceeding(self):
        # 09:00-12:00 + 13:00-18:00 = 3h + 5h = 480 min
        self.assertEqual(self._calc("2026-09-07"), (480, 0, 0))

    def test_short_day_stores_debt(self):
        # 09:47-11:47 (2h00) + 12:51-17:30 (4h39) = 399 min, debt 81 (1h21)
        self.assertEqual(self._calc("2026-10-01"), (399, 81, 0))

    def test_long_day_stores_exceeding(self):
        # 08:20-11:30 (190) + 12:40-19:30 (410) = 600 min, exceeding 120
        self.assertEqual(self._calc("2026-09-17"), (600, 0, 120))

    def test_incomplete_day_has_null_calculated_columns(self):
        self.assertEqual(self._calc("2026-10-21"), (None, None, None))

    def test_calculated_columns_follow_updates(self):
        self.con.execute("UPDATE entries SET departure='16:30' WHERE work_date='2026-09-07'")
        self.assertEqual(self._calc("2026-09-07"), (390, 90, 0))
        self.con.execute("UPDATE entries SET required_minutes=360 WHERE work_date='2026-09-07'")
        self.assertEqual(self._calc("2026-09-07"), (390, 0, 30))

    def test_calculated_columns_cannot_be_written(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.con.execute("UPDATE entries SET debt_minutes=5 WHERE work_date='2026-09-07'")

    def test_sum_ignores_incomplete_days(self):
        debt, exc = self.con.execute(
            "SELECT SUM(debt_minutes), SUM(exceeding_minutes) FROM entries "
            "WHERE work_date LIKE '2026-10-%'").fetchone()
        self.assertIsNotNone(debt)
        self.assertIsNotNone(exc)

    def test_work_date_is_unique(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO entries (work_date) VALUES ('2026-10-01')")


if __name__ == "__main__":
    unittest.main()
