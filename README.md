# work-time-sheet

Local desktop app (Tkinter + SQLite) to record daily work times and track on-site attendance, debt hours and exceeding hours by month, semester and year.

## Run

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m worktime
```

## Test

```
python -m unittest discover -s tests -v
```

## Week CSV Import (Friday Button)

In the **Daily entries** tab, every **Friday** row has an **Import week CSV** button on the right side of the `Note` field. Clicking it imports a weekly `.csv` exported from the external time-tracking page and adds or updates the entries for that week (Monday–Friday).

### Supported Week CSV Formats

1. **With explicit dates** (`dd/mm/yyyy` or ISO `YYYY-MM-DD`):
   ```csv
   Date,Arrival,Lunch out,Lunch in,Departure,Required,On-site,Exact times,Note
   02/11/2026,09:00,12:00,13:00,18:00,08:00,yes,yes,
   03/11/2026,09:15,12:15,13:15,18:15,08:00,no,yes,Remote
   ```
2. **With weekday names (`Day` column) or ordered Monday–Friday rows** (automatically mapped to the Monday–Friday of the Friday row clicked):
   ```csv
   Day,Arrival,Lunch out,Lunch in,Departure,On-site,Note
   Mon,09:00,12:00,13:00,18:00,yes,
   Tue,09:00,12:00,13:00,18:00,no,
   Wed,09:00,12:00,13:00,18:00,yes,
   Thu,09:00,12:00,13:00,18:00,no,
   Fri,09:00,12:00,13:00,18:00,yes,
   ```
