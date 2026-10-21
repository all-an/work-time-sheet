# ROADMAP

Small steps. Each step ends with something you can **run and see**, plus its unit tests. We do one step at a time; you try it, then we move on. Rules and domain details are in `CLAUDE.md`.

Run commands from the project root with the venv active:

```
.venv\Scripts\activate
python -m unittest discover -s tests -v
```

Status legend: `[ ]` todo, `[x]` done.

---

## Step 0 - Project skeleton  `[x]`
Create the venv-based project structure.
- `requirements.txt`, `requirements-dev.txt`, package `worktime/`, `tests/`, `python -m worktime` entry point.
- A first test that passes, to prove the test setup works.

**You run:** `python -m unittest discover -s tests -v` (1 test OK) and `python -m worktime` (prints a hello/version line).

## Step 1 - Time calculations  `[x]`
Pure logic, no GUI and no database (`calc.py`, `models.py`).
- Worked minutes = morning block + afternoon block.
- Debt and exceeding minutes against the required hours (default 08:00).
- Incomplete days are detected and left out of totals.
- Input validation (times in order, `HH:MM` format).

**You run:** the tests, and a tiny demo: `python -m worktime.demo 09:47 11:47 12:51 17:30` -> worked 6h39, debt 1h21.

## Step 2 - Periods and summaries  `[x]`
`periods.py`: month, semester (Jan-Jun, Jul-Dec) and year ranges; sums of worked, debt, exceeding, net balance, on-site days and percentage.
- 50% on-site target check (`MIN_ONSITE_PERCENT = 50`) and days needed to reach it.

**You run:** tests, plus a demo that prints a summary for a hard-coded list of days.

## Step 3 - SQLite storage and migrations  `[x]`
`db.py` plus `worktime/migrations/` (the schema, including stored worked/debt/exceeding columns, and the data from your old sheets are already written and tested; the xlsx files have been deleted).
- Migration runner using `PRAGMA user_version`: applies `0001_create_entries.sql` and `0002_seed_2026_sheet_data.sql` to a new `db.sqlite3`.
- Add/edit/delete/list entries, query by date range.

**You run:** tests (in-memory DB), then `python -m worktime.list_days`, which creates `db.sqlite3` and lists the 32 seeded days (Sep-Oct 2026).

## Step 4 - Check the seeded data  `[x]`
No Excel import: the sheet data is already a migration. This step is a review.
- Print the seeded days with worked, debt and exceeding per day, and the Sep and Oct totals.
- You compare with your sheets and tell me what to correct (1 Oct 2026 conflict, 22 Sep arrival 11:38, 21 Oct still open). Corrections go in a new migration.

**You run:** `python -m worktime.report_seed` and compare the totals.

## Step 5 - First window: year / month / days navigation  `[x]`
Tkinter main window where you navigate **year -> month -> days** to enter data.
- Year and month selectors at the top (previous/next arrows plus pickers); the days of the chosen month are listed below, one row per calendar day (weekends visually muted).
- Clicking a day opens the add/edit form (date, 4 times, required hours, on-site, real/approximate, note).
- Shows worked, debt and exceeding per day, and the month total at the bottom.
- Validation messages in English.

**You run:** `python -m worktime`, pick Oct 2026 and enter or edit a day.

## Step 5a - Sqlite Editor button  `[x]`
"Sqlite Editor" button in the main window: run SELECT/UPDATE/other SQL on the program database or on another `.sqlite` file, and load a `.sql` file into the editor. Writes ask for confirmation, a script runs in one transaction (all or nothing), and the day table reloads after a change.

## Step 5b - Modern day grid for typing times  `[ ]`
Type times directly in the month view, without opening the form each time. Not an Excel clone: a clean, modern look.
- One row per day with inline time fields (arrival, lunch out, lunch in, departure) and an on-site toggle.
- Worked, debt and exceeding update as you type; invalid times are highlighted, and the day is saved when you leave the field or press Enter.
- Tab/Enter moves to the next field; arrow keys move between days.
- Modern look using `ttk` styling only: custom theme colors, larger spacing and font, row hover/selection, debt in red and exceeding in green, on-site badge. Light theme first.
- Validation stays in non-GUI functions (`calc.py`), the grid only collects input and shows results.

**You run:** the app, fill a few days of the month by keyboard only, and check the totals.

## Step 6 - Month report  `[ ]`
A "Month" tab: pick month and year, see totals (worked, debt, exceeding, net balance), on-site days and percentage, and whether the 50% target is met.

**You run:** the app, compare October 2026 with your sheet.

## Step 7 - 6-month and year reports  `[ ]`
"6 months" and "Year" tabs with the same figures, plus a per-month breakdown inside the period.

**You run:** the app, check the semester and year numbers.

## Step 8 - Running balance of debt and exceeding hours  `[ ]`
Carry-over view: cumulative balance across months so you can see the total hours you owe or have in credit at any date.

**You run:** the app, check the cumulative balance against your own count.

## Step 9 - Polish  `[ ]`
- Keyboard shortcuts, sensible defaults (today's date, last used required hours).
- Warn on odd entries (e.g. arrival after lunch out).
- Export a period to CSV.
- Backup of `db.sqlite3`.

## Step 10 - Packaging (optional)  `[ ]`
Build a Windows `.exe` with PyInstaller so it can run without opening a terminal.

---

## Open decisions
- On-site percentage is measured in **days** (confirmed target: 50%). Switch to hours only if you ask.
- 1 Oct 2026: the `010-OCT.xlsx` values were used; confirm in Step 4.
- Whether Step 10 is wanted.
- Step 5b look: `ttk` styling only (no new dependency) by default. A third-party theme such as `ttkbootstrap` would look more modern but adds a dependency; decide before Step 5b.

## Working rule
After each step: tests green, you run it, you tell me what to change, then we tick the box and move on.
