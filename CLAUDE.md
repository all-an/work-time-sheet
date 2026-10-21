# work-time-sheet

A local desktop app to record daily work times and track **on-site (presencial) attendance**, **debt hours** (hours owed) and **exceeding hours** (hours over the required amount). It replaces the Excel sheets kept by hand today.

- Python project, isolated in a **venv** (`.venv/`, already in `.gitignore`).
- GUI: **Tkinter** (standard library, `ttk` widgets). Runs locally, no server, no network.
- Storage: **SQLite** through the standard `sqlite3` module. Default file: `db.sqlite3` in the project root (already in `.gitignore`, because it holds personal data).
- Tests: **unit tests are mandatory** for every change (see "Testing").
- Prefer the standard library. A new third-party dependency needs a good reason; list it in `requirements.txt` (runtime) or `requirements-dev.txt` (dev only).

## Setup and commands

Windows (the user's machine, project at `C:\Users\Public\code\work-time-sheet`):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m worktime            # run the app
python -m unittest discover -s tests -v   # run all tests
```

Always work inside the venv. Never install packages globally.

The Excel sheets are gone and **not used by the app**. Their data was copied once into a SQLite migration (see "Seed data"). Do not add `openpyxl` or any xlsx import code.

## Domain: what the sheets contain

The two original sheets (`Control-Hours-and-OnSite-2026.xlsx`, `010-OCT.xlsx`, in Portuguese) were the reference for the data model. They have been **deleted** from the project; their data lives in the seed migration.

### `Control-Hours-and-OnSite-2026.xlsx`
One sheet per month (`SET-2026`, `OCT-2026`). Columns:

| Column | Header | Meaning |
|---|---|---|
| A | Data | Work date |
| B | Hora Entrada | Arrival time |
| C | Hora Almoço Saída | Leaves for lunch |
| D | Hora Almoço Volta | Back from lunch |
| E | Hora Saída | Departure time |
| F | Presencial | `Sim` = worked on-site, `Não` = remote |
| G | Obs.: | `Hora real` (exact times) or `Hora aproximada` (estimated times) |
| H | (no header) | Worked = `(C-B)+(E-D)` |
| I | Hora faltante | Debt = `J-H` |
| J | Hora devida | Required hours for the day (always 08:00 so far) |
| K | Horas sobras | Excess = `H-J` |
| K27 | | Month total `SUM(K)` |

### `010-OCT.xlsx`
Newer layout for October 2026. Columns: Data, Hora chegada, Entrar almoço, Sair almoço, Hora saída, Hora necessaria (required, 08:00), Presencial (`Sim` or empty), Obs 2 (empty), Horas Trabalhadas, Horas devidas, Horas excedentes.

- Worked = `(lunch_out - arrival) + (departure - lunch_in)`.
- Debt = `required - worked` when worked < required, else 0.
- Exceeding = `worked - required` when worked > required, else 0.
- Empty required hours default to 08:00.

### Rules to implement (taken from the formulas above)
- Worked time = morning block + afternoon block. The lunch break is never counted.
- Debt and exceeding are **two non-negative values per day**; a day has at most one of them. Both are stored in the table (see Database).
- Required hours per day default to 08:00 but can be overridden per day (e.g. half days, holidays).
- Net balance of a period = total exceeding - total debt.
- Times are stored with minute precision. Durations are stored as **integer minutes**, never as floats or strings.

### Seed data (replaces any import feature)
The sheet data lives in `worktime/migrations/0002_seed_2026_sheet_data.sql` (32 days: 18 in Sep 2026, 14 in Oct 2026). It was generated once from the sheets; there is no importer. Decisions taken while copying:
1. **Swapped dates in `010-OCT.xlsx`** were fixed (e.g. `2026-01-10` is 1 Oct, `2026-12-10` is 12 Oct).
2. **1 Oct 2026 conflict:** the two files disagree (lunch 11:45/12:59 in the control file vs 11:47/12:51 in `010-OCT.xlsx`). The `010-OCT.xlsx` values were used, with `on_site = 0`. Tell Claude if the other file was right.
3. **Incomplete day:** 21 Oct 2026 has only an arrival time and stays open; it is excluded from totals until completed.
4. **Empty formula-only rows** were skipped.
5. **Real vs approximate:** `Hora real` -> `exact_times = 1`, `Hora aproximada` -> `0`. `010-OCT.xlsx` has no such flag, so its rows are `1`.
6. **On-site:** `Sim` -> 1, `Não` or empty -> 0.
7. Values are copied as-is, including possible typos (e.g. 22 Sep: arrival 11:38, lunch out 12:17). The user fixes them in the app.

## Reporting requirements

On-site time and debt/exceeding hours are reported for three period types:

- **Month** (calendar month).
- **Semester**: each block of 6 months (Jan-Jun, Jul-Dec).
- **Year** (calendar year).

For each period show: days worked, on-site days, remote days, on-site percentage, total worked, total debt hours, total exceeding hours and net balance.

**On-site target: at least 50% on-site** in each period (month, semester, year). The app compares each period's on-site percentage with this target and shows whether it is met, plus how many more on-site days are needed to reach it (or how many remote days remain before it drops below). Keep the 50% as a single named constant (`MIN_ONSITE_PERCENT = 50`) so it is easy to change.

Percentage = on-site days / completed days worked in the period (incomplete days are excluded). Confirm with the user if it should instead be measured in hours.

## Architecture

Keep logic separate from the GUI so everything except the widgets is testable without a display.

```
work-time-sheet/
  CLAUDE.md
  requirements.txt
  requirements-dev.txt
  worktime/
    __init__.py
    __main__.py        # entry point: python -m worktime
    models.py          # dataclasses: Entry, DaySummary, PeriodSummary
    demo.py            # python -m worktime.demo 09:47 11:47 12:51 17:30
    calc.py            # pure functions: worked/debt/exceeding minutes, period sums
    periods.py         # month / semester / year ranges for a date
    db.py              # sqlite3 access (repository) and migration runner. No Tkinter here
    migrations/
      0001_create_entries.sql
      0002_seed_2026_sheet_data.sql   # data from the old sheets
    gui/
      app.py           # main window, tabs
      entry_form.py    # add/edit a day
      reports.py       # month / 6 months / year views
  tests/
    test_calc.py
    test_periods.py
    test_db.py
    test_migrations.py
    test_gui_logic.py
```

### Database
- One table `entries`: `id`, `work_date` (ISO `YYYY-MM-DD`, UNIQUE), `arrival`, `lunch_out`, `lunch_in`, `departure` (`HH:MM` text, nullable), `required_minutes` (int, default 480), `on_site` (0/1), `exact_times` (0/1; 1 = `Hora real`), `note` (text).
- Calculated columns, stored in the table as SQLite **generated (STORED) columns**: `worked_minutes`, `debt_minutes`, `exceeding_minutes`. The database computes them from the times and `required_minutes`, so they are always consistent and cannot be written directly. They are `NULL` while a day is incomplete, so `SUM()` over a period ignores open days.
- The same rules also exist in `calc.py` (needed to validate and preview a day before saving). A test must check that `calc.py` and the SQL columns give identical results.
- Use parameterized queries only. Never build SQL with string formatting.
- Schema and seed data change only through numbered `.sql` files in `worktime/migrations/`, applied in order and tracked with `PRAGMA user_version`. Never edit an applied migration; add a new one. Never edit the table by hand.
- Dates in the database are always ISO. Display format in the UI is `dd/mm/yyyy`.

### GUI
- Tkinter + `ttk`. Tabs: Daily entries, Month, 6 months, Year.
- GUI code only collects input, calls `calc`/`db`, and displays results. No business rules in widgets.
- Validation (departure after arrival, lunch times in order, `HH:MM` format) lives in non-GUI functions so it can be unit tested.

## Conventions

- Code, identifiers, comments and commit messages in **English**. Domain terms from the sheets may appear in docstrings (`presencial`, `horas devidas`, `horas excedentes`).
- Type hints on all public functions. Follow PEP 8.
- Use `datetime.time`, `datetime.date` and integer minutes. Do not use `float` for time.
- UI labels are in **English** (decided by the user). Keep all user-visible strings in one place (e.g. `gui/strings.py`) so they are easy to find.
- Do not commit `db.sqlite3` or `.venv/`. Do not write code that reads xlsx files.

## Testing (mandatory)

Every feature and bug fix ships with unit tests in the same change. No exceptions.

- Framework: `unittest` from the standard library (add `pytest` only if the user asks).
- Tests must not touch the real `db.sqlite3`: use `sqlite3.connect(":memory:")` or a temp file.
- Tests must not open a window. Keep Tkinter out of the tested logic.
- Required cases for `calc.py`: exact 8:00 day, short day (debt), long day (exceeding), custom required hours, missing lunch times, incomplete day, and overnight/invalid ranges rejected.
- Required cases for `periods.py`: month edges, Jun 30 / Jul 1 semester boundary, year edges, leap year.
- Required cases for the on-site target: exactly 50% (met), just below 50% (not met), no completed days, days needed to reach the target.
- Required cases for migrations: calculated columns (exact day, debt day, exceeding day, incomplete day = NULL, recalculated after UPDATE, not writable), all migrations apply to an empty in-memory DB, row counts (18 Sep, 14 Oct), fixed dates, 1 Oct values, on-site/exact flags, incomplete day, unique date.
- Use the real sheet values as fixtures, and verify expected numbers by hand, not by copying the code's output. Example from `010-OCT.xlsx`, 1 Oct 2026: 09:47 / 11:47 / 12:51 / 17:30 -> worked 6h39 (2h00 + 4h39), debt 1h21, exceeding 0.
- Run `python -m unittest discover -s tests -v` before saying a task is done.

## Working agreements for Claude

- Read this file and the sheets before changing the data model.
- Ask before deciding anything marked "open" in this file.
- Keep changes small and tested. Report what was run and its result.
