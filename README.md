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
