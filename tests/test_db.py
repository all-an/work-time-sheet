import shutil
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from worktime import db
from worktime.calc import calculate_day
from worktime.models import Entry
from worktime.periods import summarize


def memory_repo():
    con = sqlite3.connect(":memory:")
    db.migrate(con)
    return con, db.EntryRepository(con)


class MigrateTests(unittest.TestCase):
    def test_empty_db_gets_all_migrations(self):
        con = sqlite3.connect(":memory:")
        self.assertEqual(db.migrate(con), 3)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 3)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 32)

    def test_running_twice_does_not_duplicate_seed(self):
        con = sqlite3.connect(":memory:")
        db.migrate(con)
        db.migrate(con)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 32)

    def test_only_newer_migrations_are_applied(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
        con = sqlite3.connect(":memory:")
        self.assertEqual(db.migrate(con, tmp), 1)
        (tmp / "0002_b.sql").write_text("CREATE TABLE b (x INTEGER);")
        self.assertEqual(db.migrate(con, tmp), 2)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"a", "b"})

    def test_failing_migration_rolls_back_and_keeps_version(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
        (tmp / "0002_bad.sql").write_text("CREATE TABLE b (x INTEGER); INSERT INTO missing VALUES (1);")
        con = sqlite3.connect(":memory:")
        with self.assertRaises(sqlite3.Error):
            db.migrate(con, tmp)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 1)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"a"})  # table b was rolled back

    def test_duplicate_numbers_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "0001_a.sql").write_text("SELECT 1;")
        (tmp / "0001_b.sql").write_text("SELECT 1;")
        with self.assertRaises(ValueError):
            db.list_migrations(tmp)

    def test_file_without_number_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "init.sql").write_text("SELECT 1;")
        with self.assertRaises(ValueError):
            db.list_migrations(tmp)

    def test_connect_creates_file_and_persists(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        path = tmp / "test.sqlite3"
        con = db.connect(path)
        db.EntryRepository(con).add(Entry(date(2026, 11, 2), "09:00", "12:00", "13:00", "18:00"))
        con.close()
        con = db.connect(path)
        self.addCleanup(con.close)
        self.assertEqual(len(db.EntryRepository(con).list_all()), 33)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.con, self.repo = memory_repo()
        self.addCleanup(self.con.close)

    def test_add_returns_calculated_columns(self):
        # 1 Oct style day on a free date: 2h00 + 4h39 = 6h39 = 399, debt 81
        saved = self.repo.add(Entry(date(2026, 11, 2), "09:47", "11:47", "12:51", "17:30"))
        self.assertIsNotNone(saved.id)
        self.assertEqual(
            (saved.worked_minutes, saved.debt_minutes, saved.exceeding_minutes), (399, 81, 0)
        )

    def test_get_seeded_day(self):
        entry = self.repo.get(date(2026, 10, 1))
        self.assertEqual((entry.arrival, entry.departure, entry.on_site), ("09:47", "17:30", False))
        self.assertEqual(entry.worked_minutes, 399)
        self.assertIsNone(self.repo.get(date(2030, 1, 1)))

    def test_incomplete_day_has_no_calculated_values(self):
        saved = self.repo.add(Entry(date(2026, 11, 2), arrival="09:00"))
        self.assertIsNone(saved.worked_minutes)
        self.assertIsNone(saved.debt_minutes)
        self.assertIsNone(saved.exceeding_minutes)

    def test_empty_strings_are_stored_as_null(self):
        saved = self.repo.add(Entry(date(2026, 11, 2), arrival="09:00", lunch_out="", note=""))
        self.assertIsNone(saved.lunch_out)
        self.assertIsNone(saved.note)

    def test_update_recalculates(self):
        saved = self.repo.add(Entry(date(2026, 11, 2), arrival="09:00"))
        done = self.repo.update(
            Entry(date(2026, 11, 2), "09:00", "12:00", "13:00", "19:00", id=saved.id, on_site=True)
        )
        self.assertEqual(done.worked_minutes, 540)  # 3h + 6h = 9h, so 1h exceeding
        self.assertEqual(done.exceeding_minutes, 60)
        self.assertTrue(done.on_site)

    def test_update_unknown_id_fails(self):
        with self.assertRaises(ValueError):
            self.repo.update(Entry(date(2026, 11, 2), id=9999))
        with self.assertRaises(ValueError):
            self.repo.update(Entry(date(2026, 11, 2)))

    def test_delete(self):
        saved = self.repo.add(Entry(date(2026, 11, 2)))
        self.assertTrue(self.repo.delete(saved.id))
        self.assertFalse(self.repo.delete(saved.id))
        self.assertIsNone(self.repo.get(date(2026, 11, 2)))

    def test_duplicate_date_rejected_on_add_and_update(self):
        with self.assertRaises(ValueError):
            self.repo.add(Entry(date(2026, 10, 1)))
        saved = self.repo.add(Entry(date(2026, 11, 2)))
        with self.assertRaises(ValueError):
            self.repo.update(Entry(date(2026, 10, 1), id=saved.id))

    def test_invalid_times_rejected_and_nothing_saved(self):
        before = len(self.repo.list_all())
        with self.assertRaises(ValueError):
            self.repo.add(Entry(date(2026, 11, 2), "17:00", "12:00", "13:00", "18:00"))
        with self.assertRaises(ValueError):
            self.repo.add(Entry(date(2026, 11, 2), "9:00"))
        with self.assertRaises(ValueError):
            self.repo.add(Entry(date(2026, 11, 2), required_minutes=-1))
        self.assertEqual(len(self.repo.list_all()), before)

    def test_list_between_is_inclusive_and_ordered(self):
        got = self.repo.list_between(date(2026, 10, 1), date(2026, 10, 2))
        self.assertEqual([e.work_date for e in got], [date(2026, 10, 1), date(2026, 10, 2)])
        self.assertEqual(len(self.repo.list_between(date(2026, 9, 1), date(2026, 9, 30))), 18)
        self.assertEqual(len(self.repo.list_between(date(2026, 10, 1), date(2026, 10, 31))), 14)

    def test_list_all_counts_seed(self):
        self.assertEqual(len(self.repo.list_all()), 32)

    def test_day_records_feed_period_summary(self):
        repo_con, repo = memory_repo()
        self.addCleanup(repo_con.close)
        repo_con.execute("DELETE FROM entries")
        repo.add(Entry(date(2026, 11, 2), "09:00", "12:00", "13:00", "18:00", on_site=True))   # 480
        repo.add(Entry(date(2026, 11, 3), "09:00", "12:00", "13:00", "17:00"))                 # 420, debt 60
        repo.add(Entry(date(2026, 11, 4), "09:00"))                                            # open
        records = repo.day_records(date(2026, 11, 1), date(2026, 11, 30))
        s = summarize(records, date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual((s.days_worked, s.onsite_days, s.worked, s.debt), (2, 1, 900, 60))

    def test_python_and_sql_calculations_agree(self):
        cases = [
            ("09:47", "11:47", "12:51", "17:30", 480),   # debt
            ("09:00", "12:00", "13:00", "18:00", 480),   # exact
            ("08:00", "12:00", "13:00", "19:00", 480),   # exceeding
            ("09:00", "12:00", "13:00", "13:00", 240),   # custom required
            ("09:00", None, "13:00", "18:00", 480),      # missing lunch
            ("09:00", None, None, None, 480),            # incomplete
        ]
        for i, (a, lo, li, d, req) in enumerate(cases, start=1):
            with self.subTest(case=cases[i - 1]):
                saved = self.repo.add(Entry(date(2027, 1, i), a, lo, li, d, required_minutes=req))
                py = calculate_day(a, lo, li, d, req)
                self.assertEqual(saved.worked_minutes, py.worked)
                self.assertEqual(saved.debt_minutes, py.debt)
                self.assertEqual(saved.exceeding_minutes, py.exceeding)

    def test_backup_database_copies_entries_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "sub" / "backup.sqlite3"
            result = db.backup_database(self.con, dest)
            self.assertEqual(result, dest)
            self.assertTrue(dest.exists())
            backup_con = sqlite3.connect(str(dest))
            try:
                copied = db.EntryRepository(backup_con).list_all()
                self.assertEqual(len(copied), 32)
            finally:
                backup_con.close()


if __name__ == "__main__":
    unittest.main()


class VacationTests(unittest.TestCase):
    def test_vacation_excluded_from_summary_projection_and_balance(self):
        from worktime.gui import logic
        con, repo = memory_repo()
        repo.add(Entry(date(2027, 3, 1), "09:00", "12:00", "13:00", "19:00", on_site=True))
        repo.add(Entry(date(2027, 3, 2), "09:00", "12:00", "13:00", "19:00", on_site=True, vacation=True))
        repo.add(Entry(date(2027, 3, 3), vacation=True))
        self.assertTrue(repo.get(date(2027, 3, 2)).vacation)
        records = repo.day_records(date(2027, 3, 1), date(2027, 3, 31))
        s = summarize(records, date(2027, 3, 1), date(2027, 3, 31))
        self.assertEqual((s.days_worked, s.onsite_days, s.exceeding), (1, 1, 60))
        self.assertEqual(logic.cumulative_balance(records, date(2027, 3, 31)), 60)
        proj = logic.build_semester_projection(records, date(2027, 1, 1), date(2027, 3, 1))
        with_vac = proj.remaining_workdays
        proj2 = logic.build_semester_projection(records[:1], date(2027, 1, 1), date(2027, 3, 1))
        self.assertEqual(with_vac, proj2.remaining_workdays - 2)  # Mar 2 and 3 are vacation
