import sqlite3
import unittest

from worktime import db, sql_runner
from worktime.sql_runner import SqlError


def memory_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    db.migrate(con)
    return con


class SplitTests(unittest.TestCase):
    def test_splits_on_semicolons(self):
        self.assertEqual(sql_runner.split_statements("SELECT 1; SELECT 2;"), ["SELECT 1;", "SELECT 2;"])

    def test_last_statement_without_semicolon_is_kept(self):
        self.assertEqual(sql_runner.split_statements("SELECT 1; SELECT 2"), ["SELECT 1;", "SELECT 2"])

    def test_semicolon_inside_string_does_not_split(self):
        self.assertEqual(
            sql_runner.split_statements("UPDATE entries SET note = 'a;b' WHERE id = 1;"),
            ["UPDATE entries SET note = 'a;b' WHERE id = 1;"],
        )

    def test_comments_and_blank_pieces_are_dropped(self):
        # a comment before a statement stays with it (harmless); a trailing comment-only piece is dropped
        script = "-- explains the query\nSELECT 1; -- trailing\n"
        self.assertEqual(sql_runner.split_statements(script), ["-- explains the query\nSELECT 1;"])
        self.assertEqual(sql_runner.split_statements("  \n -- nothing "), [])

    def test_trigger_body_stays_in_one_statement(self):
        script = (
            "CREATE TRIGGER t AFTER INSERT ON entries BEGIN "
            "UPDATE entries SET note = 'x' WHERE id = NEW.id; END; SELECT 1;"
        )
        self.assertEqual(len(sql_runner.split_statements(script)), 2)


class ClassifyTests(unittest.TestCase):
    def test_read_only(self):
        for sql in ("SELECT * FROM entries", "  select 1", "-- c\nSELECT 1", "EXPLAIN SELECT 1", "VALUES (1)"):
            with self.subTest(sql=sql):
                self.assertTrue(sql_runner.is_read_only(sql))

    def test_writes_need_confirmation(self):
        for sql in ("UPDATE entries SET note = 'x'", "DELETE FROM entries", "INSERT INTO entries (work_date) VALUES ('2027-01-01')",
                    "DROP TABLE entries", "PRAGMA user_version = 5", "WITH a AS (SELECT 1) DELETE FROM entries"):
            with self.subTest(sql=sql):
                self.assertFalse(sql_runner.is_read_only(sql))
                self.assertTrue(sql_runner.needs_confirmation(sql))

    def test_selects_do_not_need_confirmation(self):
        self.assertFalse(sql_runner.needs_confirmation("SELECT 1; SELECT 2;"))
        self.assertTrue(sql_runner.needs_confirmation("SELECT 1; DELETE FROM entries;"))
        self.assertFalse(sql_runner.needs_confirmation(""))


class RunScriptTests(unittest.TestCase):
    def setUp(self):
        self.con = memory_db()
        self.addCleanup(self.con.close)

    def test_select_returns_columns_and_rows(self):
        [result] = sql_runner.run_script(
            self.con, "SELECT work_date, worked_minutes FROM entries WHERE work_date = '2026-10-01'"
        )
        self.assertEqual(result.columns, ["work_date", "worked_minutes"])
        self.assertEqual(result.rows, [("2026-10-01", 399)])
        self.assertFalse(result.truncated)

    def test_update_is_saved_and_generated_columns_follow(self):
        # 1 Oct: 120 + (12:51 -> 18:30 = 339) = 459, debt 21
        [update, select] = sql_runner.run_script(
            self.con,
            "UPDATE entries SET departure = '18:30' WHERE work_date = '2026-10-01';"
            "SELECT worked_minutes, debt_minutes FROM entries WHERE work_date = '2026-10-01';",
        )
        self.assertEqual(update.rowcount, 1)
        self.assertEqual(select.rows, [(459, 21)])
        self.assertFalse(self.con.in_transaction)
        row = self.con.execute("SELECT departure FROM entries WHERE work_date = '2026-10-01'").fetchone()
        self.assertEqual(row[0], "18:30")

    def test_failure_rolls_back_the_whole_script(self):
        with self.assertRaises(SqlError) as caught:
            sql_runner.run_script(
                self.con,
                "UPDATE entries SET note = 'changed';"
                "UPDATE entries SET worked_minutes = 1;",  # generated column: not writable
            )
        self.assertIn("Statement 2 of 2 failed", str(caught.exception))
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM entries WHERE note = 'changed'").fetchone()[0], 0
        )
        self.assertFalse(self.con.in_transaction)

    def test_unique_date_is_enforced(self):
        with self.assertRaises(SqlError):
            sql_runner.run_script(self.con, "INSERT INTO entries (work_date) VALUES ('2026-10-01')")

    def test_syntax_error_is_reported(self):
        with self.assertRaises(SqlError) as caught:
            sql_runner.run_script(self.con, "SELEC 1")
        self.assertIn("Statement failed", str(caught.exception))

    def test_empty_script_is_an_error(self):
        for script in ("", "   ", "-- nothing here"):
            with self.subTest(script=script):
                with self.assertRaises(SqlError):
                    sql_runner.run_script(self.con, script)

    def test_rows_are_limited(self):
        [result] = sql_runner.run_script(
            self.con,
            "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 1500) SELECT i FROM n",
        )
        self.assertEqual(len(result.rows), sql_runner.MAX_ROWS)
        self.assertTrue(result.truncated)

    def test_insert_and_delete_counts(self):
        [insert] = sql_runner.run_script(
            self.con, "INSERT INTO entries (work_date, arrival) VALUES ('2027-01-04', '09:00')"
        )
        self.assertEqual(insert.rowcount, 1)
        [delete] = sql_runner.run_script(self.con, "DELETE FROM entries WHERE work_date = '2027-01-04'")
        self.assertEqual(delete.rowcount, 1)

    def test_summary_and_last_result_set(self):
        results = sql_runner.run_script(
            self.con,
            "UPDATE entries SET note = 'x' WHERE work_date LIKE '2026-09-%';"
            "SELECT COUNT(*) AS n FROM entries WHERE note = 'x';",
        )
        self.assertEqual(sql_runner.last_result_set(results).rows, [(18,)])
        self.assertEqual(
            sql_runner.summary(results), "2 statement(s) run, 18 row(s) changed, 1 row(s) shown"
        )

    def test_works_on_a_file_database_opened_by_path(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE t (x INTEGER)")
        sql_runner.run_script(con, "INSERT INTO t VALUES (1); INSERT INTO t VALUES (2);")
        [result] = sql_runner.run_script(con, "SELECT SUM(x) FROM t")
        self.assertEqual(result.rows, [(3,)])


if __name__ == "__main__":
    unittest.main()
