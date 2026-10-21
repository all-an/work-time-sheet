import unittest
from datetime import date

from worktime.calc import calculate_day
from worktime.models import DayRecord
from worktime.periods import (
    MIN_ONSITE_PERCENT,
    month_range,
    onsite_days_needed,
    remote_days_spare,
    semester_range,
    summarize,
    year_range,
)


def record(day: date, on_site: bool, *times: str) -> DayRecord:
    return DayRecord(day, on_site, calculate_day(*times))


FULL_DAY = ("09:00", "12:00", "13:00", "18:00")  # 3h + 5h = 8h00, no debt, no excess


class RangeTests(unittest.TestCase):
    def test_month_edges(self):
        self.assertEqual(month_range(date(2026, 10, 15)), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(month_range(date(2026, 10, 1)), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(month_range(date(2026, 10, 31)), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(month_range(date(2026, 9, 30)), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(month_range(date(2026, 12, 25)), (date(2026, 12, 1), date(2026, 12, 31)))

    def test_february_and_leap_years(self):
        self.assertEqual(month_range(date(2026, 2, 10))[1], date(2026, 2, 28))
        self.assertEqual(month_range(date(2028, 2, 10))[1], date(2028, 2, 29))
        self.assertEqual(month_range(date(2100, 2, 10))[1], date(2100, 2, 28))  # not leap
        self.assertEqual(month_range(date(2000, 2, 10))[1], date(2000, 2, 29))  # leap

    def test_semester_boundary_jun_30_jul_1(self):
        first = (date(2026, 1, 1), date(2026, 6, 30))
        second = (date(2026, 7, 1), date(2026, 12, 31))
        self.assertEqual(semester_range(date(2026, 1, 1)), first)
        self.assertEqual(semester_range(date(2026, 6, 30)), first)
        self.assertEqual(semester_range(date(2026, 7, 1)), second)
        self.assertEqual(semester_range(date(2026, 12, 31)), second)

    def test_year_edges(self):
        expected = (date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(year_range(date(2026, 1, 1)), expected)
        self.assertEqual(year_range(date(2026, 12, 31)), expected)
        self.assertEqual(year_range(date(2028, 2, 29)), (date(2028, 1, 1), date(2028, 12, 31)))


class OnsiteTargetTests(unittest.TestCase):
    def test_default_target_is_50(self):
        self.assertEqual(MIN_ONSITE_PERCENT, 50)

    def test_exactly_50_percent_is_met(self):
        records = [
            record(date(2026, 10, 1), True, *FULL_DAY),
            record(date(2026, 10, 2), False, *FULL_DAY),
        ]
        s = summarize(records, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(s.onsite_percent, 50.0)
        self.assertTrue(s.target_met)
        self.assertEqual(s.onsite_days_needed, 0)
        self.assertEqual(s.remote_days_spare, 0)

    def test_just_below_50_percent_is_not_met(self):
        # 49 on-site of 100 days = 49%
        records = [
            record(date(2026, 1, 1), i < 49, *FULL_DAY) for i in range(100)
        ]
        s = summarize(records, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(s.days_worked, 100)
        self.assertEqual(s.onsite_days, 49)
        self.assertFalse(s.target_met)

    def test_no_completed_days(self):
        s = summarize([], date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(s.days_worked, 0)
        self.assertIsNone(s.onsite_percent)
        self.assertFalse(s.target_met)
        self.assertEqual(s.onsite_days_needed, 0)
        self.assertEqual(s.remote_days_spare, 0)
        self.assertEqual(s.balance, 0)

    def test_days_needed_to_reach_target(self):
        # 1 of 4 on-site: +2 on-site days gives 3 of 6 = 50%; +1 gives 2 of 5 = 40%
        self.assertEqual(onsite_days_needed(1, 4), 2)
        # 0 of 3: +3 gives 3 of 6
        self.assertEqual(onsite_days_needed(0, 3), 3)
        # 49 of 100: +2 gives 51 of 102 = 50%; +1 gives 50 of 101 < 50%
        self.assertEqual(onsite_days_needed(49, 100), 2)
        # already met
        self.assertEqual(onsite_days_needed(3, 4), 0)

    def test_remote_days_spare(self):
        # 3 of 4: +2 remote gives 3 of 6 = 50%; +3 gives 3 of 7 < 50%
        self.assertEqual(remote_days_spare(3, 4), 2)
        # 2 of 3: +1 remote gives 2 of 4 = 50%
        self.assertEqual(remote_days_spare(2, 3), 1)
        # not met
        self.assertEqual(remote_days_spare(1, 4), 0)

    def test_custom_target(self):
        # 1 of 2 = 50%, but a 60% target needs +1 on-site (2 of 3 = 66%)
        self.assertEqual(onsite_days_needed(1, 2, 60), 1)


class SummarizeTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            # 1 Oct 2026 from 010-OCT.xlsx: 2h00 + 4h39 = 6h39 -> 399 min, debt 81
            record(date(2026, 10, 1), False, "09:47", "11:47", "12:51", "17:30"),
            record(date(2026, 10, 2), True, *FULL_DAY),  # 480, nothing
            # 3h + 4h = 7h00 -> 420, debt 60
            record(date(2026, 10, 5), True, "09:00", "12:00", "13:00", "17:00"),
            # 4h + 5h = 9h00 -> 540, exceeding 60
            record(date(2026, 10, 6), False, "08:00", "12:00", "13:00", "18:00"),
            # incomplete: arrival only, ignored even though marked on-site
            record(date(2026, 10, 7), True, "09:00", None, None, None),
            # outside the month
            record(date(2026, 9, 30), True, *FULL_DAY),
        ]

    def test_month_totals_by_hand(self):
        s = summarize(self.records, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(s.days_worked, 4)
        self.assertEqual(s.onsite_days, 2)
        self.assertEqual(s.remote_days, 2)
        self.assertEqual(s.onsite_percent, 50.0)
        self.assertEqual(s.worked, 399 + 480 + 420 + 540)  # 1839
        self.assertEqual(s.debt, 81 + 60)  # 141
        self.assertEqual(s.exceeding, 60)
        self.assertEqual(s.balance, 60 - 141)  # -81
        self.assertTrue(s.target_met)

    def test_incomplete_day_is_excluded(self):
        s = summarize(self.records, date(2026, 10, 7), date(2026, 10, 7))
        self.assertEqual(s.days_worked, 0)
        self.assertIsNone(s.onsite_percent)

    def test_range_is_inclusive_on_both_ends(self):
        s = summarize(self.records, date(2026, 10, 2), date(2026, 10, 5))
        self.assertEqual(s.days_worked, 2)

    def test_semester_and_year_include_other_months(self):
        s = summarize(self.records, *semester_range(date(2026, 10, 1)))
        self.assertEqual(s.days_worked, 5)  # the 30 Sep day is in the same semester
        y = summarize(self.records, *year_range(date(2026, 10, 1)))
        self.assertEqual(y.days_worked, 5)


if __name__ == "__main__":
    unittest.main()
