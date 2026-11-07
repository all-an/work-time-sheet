import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from worktime import db
from worktime.gui import logic
from worktime.models import Entry
from worktime.periods import month_range, summarize


def seeded_entries():
    con = sqlite3.connect(":memory:")
    db.migrate(con)
    entries = db.EntryRepository(con).list_all()
    con.close()
    return entries


class DateAndTimeTests(unittest.TestCase):
    def test_format_and_parse_date(self):
        self.assertEqual(logic.format_date(date(2026, 10, 1)), "01/10/2026")
        self.assertEqual(logic.parse_date("01/10/2026"), date(2026, 10, 1))
        self.assertEqual(logic.parse_date(" 29/02/2028 "), date(2028, 2, 29))

    def test_parse_date_rejects_bad_input(self):
        for bad in ("2026-10-01", "31/02/2026", "1/13/2026", "", "abc"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    logic.parse_date(bad)

    def test_normalize_time(self):
        self.assertIsNone(logic.normalize_time(""))
        self.assertIsNone(logic.normalize_time("   "))
        self.assertIsNone(logic.normalize_time(None))
        self.assertEqual(logic.normalize_time(" 9:05 "), "09:05")
        self.assertEqual(logic.normalize_time("17:30"), "17:30")
        self.assertEqual(logic.normalize_time("25:00"), "25:00")  # left for validation

    def test_parse_required(self):
        self.assertEqual(logic.parse_required(""), 480)
        self.assertEqual(logic.parse_required(None), 480)
        self.assertEqual(logic.parse_required("4:00"), 240)
        self.assertEqual(logic.parse_required("08:00"), 480)
        with self.assertRaises(ValueError):
            logic.parse_required("abc")

    def test_required_text_round_trips(self):
        self.assertEqual(logic.required_text(480), "08:00")
        self.assertEqual(logic.required_text(270), "04:30")
        self.assertEqual(logic.parse_required(logic.required_text(270)), 270)

    def test_shift_month(self):
        self.assertEqual(logic.shift_month(2026, 12, 1), (2027, 1))
        self.assertEqual(logic.shift_month(2026, 1, -1), (2025, 12))
        self.assertEqual(logic.shift_month(2026, 10, 0), (2026, 10))
        self.assertEqual(logic.shift_month(2026, 10, 14), (2027, 12))
        self.assertEqual(logic.shift_month(2026, 3, -15), (2024, 12))

    def test_year_choices(self):
        entries = [Entry(date(2023, 5, 1)), Entry(date(2026, 10, 1))]
        self.assertEqual(logic.year_choices(entries, date(2026, 10, 21)), [2023, 2025, 2026, 2027])
        self.assertEqual(logic.year_choices([], date(2026, 10, 21)), [2025, 2026, 2027])
        self.assertEqual(
            logic.year_choices([], date(2026, 10, 21), ("2025", "2026", "2027", 2026, 2024)),
            [2024, 2025, 2026, 2027],
        )

    def test_parse_year(self):
        self.assertEqual(logic.parse_year("2028"), 2028)
        self.assertEqual(logic.parse_year(" 2030 "), 2030)
        self.assertEqual(logic.parse_year("", ("2025", "2026", "2027")), 2028)
        for bad in ("", "abc", "1999", "2101", "-2028"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    logic.parse_year(bad)


class MonthRowsTests(unittest.TestCase):
    def setUp(self):
        self.rows = logic.build_month_rows(2026, 10, seeded_entries())

    def test_one_row_per_calendar_day(self):
        self.assertEqual(len(self.rows), 31)
        self.assertEqual(self.rows[0].work_date, date(2026, 10, 1))
        self.assertEqual(self.rows[-1].work_date, date(2026, 10, 31))
        self.assertEqual(len(logic.build_month_rows(2028, 2, [])), 29)
        self.assertEqual(len(logic.build_month_rows(2026, 2, [])), 28)

    def test_oct_1_row(self):
        row = self.rows[0]  # Thursday
        self.assertEqual(row.weekday, "Thu")
        self.assertFalse(row.is_weekend)
        self.assertEqual(row.state, "debt")
        self.assertEqual(
            row.cells,
            ("01/10/2026", "Thu", "09:47", "11:47", "12:51", "17:30", "no", "6h39", "1h21", "0h00", ""),
        )

    def test_weekend_and_empty_days(self):
        saturday = self.rows[2]
        self.assertEqual((saturday.weekday, saturday.is_weekend), ("Sat", True))
        self.assertEqual(saturday.state, "empty")
        self.assertIsNone(saturday.entry)
        self.assertEqual(saturday.cells[2:], ("",) * 9)
        self.assertTrue(self.rows[3].is_weekend)  # Sunday 4 Oct

    def test_open_day(self):
        row = self.rows[20]  # 21 Oct, arrival only
        self.assertEqual(row.state, "open")
        self.assertEqual(row.cells[2], "08:30")
        self.assertEqual(row.cells[7], "open")

    def test_exceeding_and_exact_day_states(self):
        self.assertEqual(self.rows[1].state, "exceeding")  # 2 Oct: 8h07
        entries = [Entry(date(2026, 10, 5), "09:00", "12:00", "13:00", "18:00",
                         worked_minutes=480, debt_minutes=0, exceeding_minutes=0)]
        self.assertEqual(logic.build_month_rows(2026, 10, entries)[4].state, "ok")


class TotalsTextTests(unittest.TestCase):
    def test_october_totals_and_target(self):
        entries = seeded_entries()
        records = [db.to_day_record(e) for e in entries]
        summary = summarize(records, *month_range(date(2026, 10, 1)))
        totals, target = logic.totals_text(summary, 50)
        self.assertIn("October 2026", totals)
        self.assertIn("13 days worked (5 on-site, 8 remote)", totals)
        self.assertIn("On-site 38.5%", totals)
        self.assertIn("Worked 103h05", totals)
        self.assertIn("Debt 6h11", totals)
        self.assertIn("Exceeding 5h16", totals)
        self.assertIn("Balance -0h55", totals)
        self.assertEqual(target, "Target 50% not met (need 3 more on-site day(s))")

    def test_met_and_no_days(self):
        records = [db.to_day_record(Entry(
            date(2026, 11, 2), "09:00", "12:00", "13:00", "18:00", on_site=True,
            worked_minutes=480, debt_minutes=0, exceeding_minutes=0))]
        met = summarize(records, *month_range(date(2026, 11, 1)))
        self.assertEqual(logic.totals_text(met, 50)[1], "Target 50% met (can still add 1 remote day(s))")
        empty = summarize([], *month_range(date(2026, 12, 1)))
        totals, target = logic.totals_text(empty, 50)
        self.assertIn("On-site n/a", totals)
        self.assertEqual(target, "Target 50%: no completed days yet")


class PreviewTests(unittest.TestCase):
    def test_complete_day(self):
        text = logic.preview_text("09:47", "11:47", "12:51", "17:30", "")
        self.assertEqual(text, "Worked 6h39   Debt 1h21   Exceeding 0h00")

    def test_loose_times_and_custom_required(self):
        text = logic.preview_text("9:00", "12:00", "13:00", "17:00", "7:00")
        self.assertEqual(text, "Worked 7h00   Debt 0h00   Exceeding 0h00")

    def test_incomplete_and_invalid(self):
        self.assertIn("Incomplete", logic.preview_text("09:00", "", "", "", ""))
        self.assertIn("earlier", logic.preview_text("17:00", "12:00", "13:00", "18:00", ""))
        self.assertIn("Invalid time", logic.preview_text("9h", "", "", "", ""))


class BuildEntryTests(unittest.TestCase):
    def test_valid_entry(self):
        entry = logic.build_entry(
            "01/10/2026", "9:47", "11:47", "12:51", "17:30", "", False, True, "  hello  ", entry_id=7
        )
        self.assertEqual(entry.work_date, date(2026, 10, 1))
        self.assertEqual((entry.arrival, entry.departure), ("09:47", "17:30"))
        self.assertEqual(entry.required_minutes, 480)
        self.assertEqual(entry.note, "hello")
        self.assertEqual(entry.id, 7)

    def test_empty_times_and_note_become_none(self):
        entry = logic.build_entry("01/10/2026", "09:00", "", "", "", "04:00", True, False, "")
        self.assertIsNone(entry.lunch_out)
        self.assertIsNone(entry.note)
        self.assertEqual(entry.required_minutes, 240)
        self.assertTrue(entry.on_site)
        self.assertFalse(entry.exact_times)

    def test_invalid_input_is_rejected(self):
        cases = [
            ("bad date", ("2026-10-01", "09:00", "", "", "", "", False, True, "")),
            ("bad time", ("01/10/2026", "25:00", "", "", "", "", False, True, "")),
            ("bad format", ("01/10/2026", "9h", "", "", "", "", False, True, "")),
            ("out of order", ("01/10/2026", "17:00", "12:00", "13:00", "18:00", "", False, True, "")),
            ("bad required", ("01/10/2026", "09:00", "", "", "", "abc", False, True, "")),
        ]
        for name, args in cases:
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    logic.build_entry(*args)


if __name__ == "__main__":
    unittest.main()


class DashboardLogicTests(unittest.TestCase):
    def setUp(self):
        self.entries = seeded_entries()
        self.records = [db.to_day_record(e) for e in self.entries]

    def test_period_bounds(self):
        day = date(2026, 10, 21)
        self.assertEqual(logic.period_bounds(logic.PERIOD_MONTH, day), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(logic.period_bounds(logic.PERIOD_SEMESTER, day), (date(2026, 7, 1), date(2026, 12, 31)))
        self.assertEqual(logic.period_bounds(logic.PERIOD_SEMESTER, date(2026, 6, 30)),
                         (date(2026, 1, 1), date(2026, 6, 30)))
        self.assertEqual(logic.period_bounds(logic.PERIOD_YEAR, day), (date(2026, 1, 1), date(2026, 12, 31)))
        with self.assertRaises(ValueError):
            logic.period_bounds("decade", day)

    def test_period_title(self):
        self.assertEqual(logic.period_title(logic.PERIOD_MONTH, date(2026, 10, 1)), "October 2026")
        self.assertEqual(logic.period_title(logic.PERIOD_SEMESTER, date(2026, 7, 1)), "Jul-Dec 2026")
        self.assertEqual(logic.period_title(logic.PERIOD_SEMESTER, date(2026, 1, 1)), "Jan-Jun 2026")
        self.assertEqual(logic.period_title(logic.PERIOD_YEAR, date(2026, 1, 1)), "2026")

    def test_pie_slices_half_and_half(self):
        a, b = logic.pie_slices([("on-site", 5), ("remote", 5)])
        self.assertEqual((a.percent, b.percent), (50.0, 50.0))
        self.assertEqual((a.start, a.extent), (90.0, -180.0))
        self.assertEqual((b.start, b.extent), (-90.0, -180.0))

    def test_pie_slices_cover_the_whole_circle(self):
        slices = logic.pie_slices([("a", 7), ("b", 11), ("c", 5)])
        self.assertAlmostEqual(sum(s.extent for s in slices), -360.0)
        self.assertAlmostEqual(sum(s.percent for s in slices), 100.0)
        self.assertAlmostEqual(slices[0].extent, -360.0 * 7 / 23)

    def test_pie_slices_with_one_value_or_none(self):
        only, empty = logic.pie_slices([("a", 4), ("b", 0)])
        self.assertEqual((only.percent, only.extent, empty.extent), (100.0, -360.0, 0.0))
        for s in logic.pie_slices([("a", 0), ("b", 0)]):
            self.assertEqual((s.percent, s.extent), (0.0, 0.0))

    def test_stats_for_october_by_hand(self):
        s = summarize(self.records, date(2026, 10, 1), date(2026, 10, 31))
        stats = dict(logic.stats_lines(s, 50))
        self.assertEqual(stats["Days worked"], "13")
        self.assertEqual(stats["On-site days"], "5")
        self.assertEqual(stats["Remote days"], "8")
        self.assertEqual(stats["On-site percentage"], "38.5%")
        self.assertEqual(stats["Worked"], "103h05")
        self.assertEqual(stats["Debt"], "6h11")
        self.assertEqual(stats["Exceeding"], "5h16")
        self.assertEqual(stats["Net balance"], "-0h55")
        self.assertIn("not met", stats["On-site target"])

    def test_semester_totals_by_hand(self):
        # Sep + Oct: 31 days, 12 on-site (38.7%), 14851 min = 247h31, debt 723 = 12h03,
        # exceeding 694 = 11h34, balance -29
        start, end = logic.period_bounds(logic.PERIOD_SEMESTER, date(2026, 10, 1))
        stats = dict(logic.stats_lines(summarize(self.records, start, end), 50))
        self.assertEqual(stats["Days worked"], "31")
        self.assertEqual(stats["On-site days"], "12")
        self.assertEqual(stats["On-site percentage"], "38.7%")
        self.assertEqual(stats["Worked"], "247h31")
        self.assertEqual(stats["Debt"], "12h03")
        self.assertEqual(stats["Exceeding"], "11h34")
        self.assertEqual(stats["Net balance"], "-0h29")

    def test_breakdown_has_one_row_per_month(self):
        rows = logic.month_breakdown(self.records, date(2026, 7, 1), date(2026, 12, 31), 50)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0], ("July 2026", "0", "0 / 0", "n/a", "0h00", "0h00", "0h00", "0h00"))
        self.assertEqual(rows[2], ("September 2026", "18", "7 / 11", "38.9%", "144h26", "5h52", "6h18", "0h26"))
        self.assertEqual(rows[3], ("October 2026", "13", "5 / 8", "38.5%", "103h05", "6h11", "5h16", "-0h55"))
        year_rows = logic.month_breakdown(self.records, date(2026, 1, 1), date(2026, 12, 31), 50)
        self.assertEqual(len(year_rows), 12)
        self.assertEqual(len(logic.month_breakdown(self.records, date(2026, 10, 1), date(2026, 10, 31), 50)), 1)

    def test_cumulative_and_running_balance_breakdown(self):
        # Sep net balance = +26 min (0h26); Oct net balance = -55 min (-0h55); cumulative Oct = -29 min (-0h29)
        self.assertEqual(logic.cumulative_balance(self.records, date(2026, 8, 31)), 0)
        self.assertEqual(logic.cumulative_balance(self.records, date(2026, 9, 30)), 26)
        self.assertEqual(logic.cumulative_balance(self.records, date(2026, 10, 31)), -29)
        rows = logic.running_balance_breakdown(self.records, date(2026, 7, 1), date(2026, 12, 31), 50)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0][-1], "0h00")   # July cumulative
        self.assertEqual(rows[2][-1], "0h26")   # September cumulative
        self.assertEqual(rows[3][-1], "-0h29")  # October cumulative (carry-over from Sep + Oct)
        self.assertEqual(rows[5][-1], "-0h29")  # December cumulative carries forward


class InlineGridAndPolishTests(unittest.TestCase):
    def test_validate_inline_day_complete_and_incomplete(self):
        complete = logic.validate_inline_day(
            date(2026, 10, 1), "9:47", "11:47", "12:51", "17:30", False
        )
        self.assertTrue(complete.valid)
        self.assertFalse(complete.empty)
        self.assertEqual(complete.state, "debt")
        self.assertEqual((complete.worked_text, complete.debt_text, complete.exceeding_text), ("6h39", "1h21", "0h00"))
        self.assertEqual(complete.entry_to_save.arrival, "09:47")

        open_day = logic.validate_inline_day(
            date(2026, 10, 21), "08:30", "", "", "", True
        )
        self.assertTrue(open_day.valid)
        self.assertEqual(open_day.state, "open")
        self.assertEqual(open_day.worked_text, "open")
        self.assertTrue(open_day.entry_to_save.on_site)

        empty_day = logic.validate_inline_day(
            date(2026, 10, 3), "", "", "", "", False
        )
        self.assertTrue(empty_day.valid)
        self.assertTrue(empty_day.empty)
        self.assertEqual(empty_day.state, "empty")
        self.assertIsNone(empty_day.entry_to_save)

    def test_validate_inline_day_highlights_invalid_fields(self):
        bad_format = logic.validate_inline_day(
            date(2026, 10, 1), "09:00", "bad", "13:00", "17:00", False
        )
        self.assertFalse(bad_format.valid)
        self.assertEqual(bad_format.invalid_fields, ("lunch_out",))
        self.assertEqual(bad_format.state, "invalid")

        out_of_order = logic.validate_inline_day(
            date(2026, 10, 1), "09:00", "12:00", "11:30", "17:00", False
        )
        self.assertFalse(out_of_order.valid)
        self.assertEqual(out_of_order.invalid_fields, ("lunch_in",))

    def test_validate_inline_day_preserves_existing_metadata(self):
        existing = Entry(
            date(2026, 10, 1), "09:00", "12:00", "13:00", "17:00",
            required_minutes=240, on_site=True, exact_times=False, note="half day", id=42,
        )
        updated = logic.validate_inline_day(
            date(2026, 10, 1), "09:00", "12:00", "13:00", "14:30", True, existing=existing
        )
        self.assertTrue(updated.valid)
        self.assertEqual(updated.state, "exceeding")
        self.assertEqual(updated.exceeding_text, "0h30")
        self.assertEqual(updated.entry_to_save.id, 42)
        self.assertEqual(updated.entry_to_save.required_minutes, 240)
        self.assertFalse(updated.entry_to_save.exact_times)
        self.assertEqual(updated.entry_to_save.note, "half day")

    def test_entry_warnings_and_default_required(self):
        self.assertEqual(logic.entry_warnings("09:00", "12:00", "13:00", "18:00"), [])
        late = logic.entry_warnings("11:38", "12:17", "13:20", "17:42")
        self.assertIn("late arrival 11:38", late)
        self.assertIn("Warning:", logic.preview_text("11:38", "12:17", "13:20", "17:42", ""))

        self.assertEqual(logic.default_required_minutes([]), 480)
        entries = [
            Entry(date(2026, 10, 1), required_minutes=480),
            Entry(date(2026, 10, 5), required_minutes=360),
        ]
        self.assertEqual(logic.default_required_minutes(entries), 360)

    def test_export_and_write_period_csv(self):
        entries = seeded_entries()
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "october.csv"
            count = logic.write_period_csv(csv_path, entries, date(2026, 10, 1), date(2026, 10, 31))
            self.assertEqual(count, 14)  # 13 complete + 1 open day in October 2026
            content = csv_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(content), 15)  # header + 14 rows
            self.assertIn("01/10/2026,09:47,11:47,12:51,17:30,08:00,no,yes,6h39,1h21,0h00,", content[1])
            self.assertIn("21/10/2026,08:30,,,,08:00,no,yes,open,,,", content[-1])

    def test_default_filenames(self):
        self.assertEqual(logic.default_backup_name(date(2026, 11, 7)), "worktime-backup-2026-11-07.sqlite3")
        self.assertEqual(logic.default_csv_name(logic.PERIOD_MONTH, date(2026, 10, 1)), "worktime-2026-10.csv")
        self.assertEqual(logic.default_csv_name(logic.PERIOD_SEMESTER, date(2026, 7, 1)), "worktime-2026-H2.csv")
        self.assertEqual(logic.default_csv_name(logic.PERIOD_YEAR, date(2026, 1, 1)), "worktime-2026.csv")


class SemesterProjectionTests(unittest.TestCase):
    def setUp(self):
        self.entries = seeded_entries()
        self.records = [db.to_day_record(e) for e in self.entries]

    def test_seeded_semester_projection_by_hand(self):
        # As of Saturday 2026-11-07:
        # 31 completed days (12 on-site, 19 remote), balance = -29 min.
        # Remaining weekdays in Nov (16) + Dec (23) = 39 workdays across 8 weeks.
        # Total projected days = 31 + 39 = 70 -> 50% target = 35 on-site -> need 23 more on-site days.
        proj = logic.build_semester_projection(self.records, date(2026, 10, 1), date(2026, 11, 7))
        self.assertEqual((proj.start, proj.end), (date(2026, 7, 1), date(2026, 12, 31)))
        self.assertEqual((proj.days_worked, proj.onsite_days, proj.remote_days), (31, 12, 19))
        self.assertEqual(proj.current_balance, -29)
        self.assertEqual(proj.remaining_workdays, 39)
        self.assertEqual(proj.remaining_weeks, 8)
        self.assertEqual(proj.projected_total_days, 70)
        self.assertEqual(proj.projected_onsite_target, 35)
        self.assertEqual(proj.onsite_still_needed, 23)
        self.assertEqual(proj.recommended_onsite_per_week, 3)
        self.assertTrue(proj.achievable_onsite)
        self.assertEqual(proj.extra_minutes_per_day, 1)
        self.assertEqual(proj.daily_minutes_needed, 481)
        self.assertEqual(proj.weekly_minutes_needed, 2405)
        self.assertEqual(proj.schedule_suggestion, "09:00-12:00, 13:00-18:01")

        self.assertEqual(len(proj.weekly_plan), 8)
        self.assertEqual(sum(w.workdays for w in proj.weekly_plan), 39)
        self.assertEqual(sum(w.onsite_days for w in proj.weekly_plan), 23)
        self.assertAlmostEqual(proj.weekly_plan[-1].projected_onsite_percent, 50.0)
        self.assertGreaterEqual(proj.weekly_plan[-1].projected_balance, 0)

        onsite_stats, hours_stats = logic.projection_stats(proj)
        self.assertIn("3 day(s)/week on-site", dict(onsite_stats)["Suggested on-site pace"])
        self.assertEqual(dict(hours_stats)["Suggested daily work time"], "8h01 / day")
        self.assertEqual(len(logic.projection_table_rows(proj)), 8)

    def test_projection_when_target_already_met_and_in_credit(self):
        records = [
            db.to_day_record(
                Entry(
                    date(2026, 12, d), "09:00", "12:00", "13:00", "18:30",
                    on_site=True, worked_minutes=510, debt_minutes=0, exceeding_minutes=30,
                )
            )
            for d in (1, 2, 3, 4, 7)
        ]
        # As of 2026-12-28 (4 remaining weekdays: Dec 28, 29, 30, 31):
        # 5 worked (5 on-site) + 4 remaining = 9 total days -> target = 5 on-site -> 0 more needed!
        proj = logic.build_semester_projection(records, date(2026, 12, 1), date(2026, 12, 28))
        self.assertEqual(proj.remaining_workdays, 4)
        self.assertEqual(proj.onsite_still_needed, 0)
        self.assertEqual(proj.recommended_onsite_per_week, 0)
        self.assertEqual(proj.extra_minutes_per_day, 0)
        self.assertEqual(proj.daily_minutes_needed, 480)
        self.assertEqual(proj.schedule_suggestion, "09:00-12:00, 13:00-18:00")

    def test_projection_past_semester_has_no_remaining_days(self):
        proj = logic.build_semester_projection(self.records, date(2026, 1, 1), date(2026, 11, 7))
        self.assertEqual(proj.remaining_workdays, 0)
        self.assertEqual(proj.weekly_plan, ())


class WeekCsvImportTests(unittest.TestCase):
    def test_is_friday(self):
        self.assertTrue(logic.is_friday(date(2026, 11, 6)))   # Friday
        self.assertFalse(logic.is_friday(date(2026, 11, 5)))  # Thursday
        self.assertFalse(logic.is_friday(date(2026, 11, 7)))  # Saturday

    def test_parse_week_csv_with_explicit_dates(self):
        csv_text = (
            "Date,Arrival,Lunch out,Lunch in,Departure,Required,On-site,Exact times,Note\n"
            "02/11/2026,9:00,12:00,13:00,18:00,08:00,yes,yes,Monday office\n"
            "2026-11-03,09:15,12:15,13:15,18:00,08:00,no,no,Remote\n"
        )
        entries = logic.parse_week_csv(csv_text, date(2026, 11, 6))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].work_date, date(2026, 11, 2))
        self.assertEqual(entries[0].arrival, "09:00")
        self.assertTrue(entries[0].on_site)
        self.assertTrue(entries[0].exact_times)
        self.assertEqual(entries[0].note, "Monday office")
        self.assertEqual(entries[1].work_date, date(2026, 11, 3))
        self.assertFalse(entries[1].on_site)
        self.assertFalse(entries[1].exact_times)

    def test_parse_week_csv_with_weekday_or_positional_rows(self):
        csv_text = (
            "Day,Arrival,Lunch out,Lunch in,Departure,On-site\n"
            "Mon,09:00,12:00,13:00,18:00,yes\n"
            "Wed,09:00,12:00,13:00,18:00,no\n"
            "Fri,09:00,12:00,13:00,18:00,Sim\n"
        )
        entries = logic.parse_week_csv(csv_text, date(2026, 11, 6))
        self.assertEqual([e.work_date for e in entries], [
            date(2026, 11, 2),
            date(2026, 11, 4),
            date(2026, 11, 6),
        ])
        self.assertEqual([e.on_site for e in entries], [True, False, True])

    def test_parse_week_csv_rejects_empty_or_invalid(self):
        for bad in ("", "Date,Arrival\n", "Date,Arrival,Lunch out\n02/11/2026,14:00,12:00\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    logic.parse_week_csv(bad, date(2026, 11, 6))
