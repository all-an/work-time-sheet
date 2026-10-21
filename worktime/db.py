"""SQLite access: migration runner and entries repository. No Tkinter here.

Schema and seed data change only through numbered .sql files in
worktime/migrations/, applied in order and tracked with PRAGMA user_version.
All values are passed as query parameters, never formatted into SQL.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import List, Optional, Union

from worktime.calc import validate_times
from worktime.models import DayRecord, DaySummary, Entry

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "db.sqlite3"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_MIGRATION_NAME = re.compile(r"^(\d+)_.+\.sql$")


def list_migrations(directory: Path = MIGRATIONS_DIR) -> List[tuple]:
    """Return [(version, path)] sorted by version. Versions must be unique."""
    found = []
    for path in directory.glob("*.sql"):
        match = _MIGRATION_NAME.match(path.name)
        if not match:
            raise ValueError(f"Migration file name must start with a number: {path.name}")
        found.append((int(match.group(1)), path))
    found.sort()
    versions = [version for version, _ in found]
    if len(versions) != len(set(versions)):
        raise ValueError("Two migration files share the same number")
    return found


def migrate(con: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> int:
    """Apply every migration newer than PRAGMA user_version. Returns the new version.

    Each file runs in its own transaction together with the version bump, so a
    failing migration leaves the database at the previous version.
    """
    current = con.execute("PRAGMA user_version").fetchone()[0]
    for version, path in list_migrations(directory):
        if version <= current:
            continue
        script = path.read_text(encoding="utf-8")
        try:
            # version is an int taken from the file name, so formatting it is safe
            con.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {int(version)};\nCOMMIT;")
        except sqlite3.Error:
            if con.in_transaction:
                con.rollback()
            raise
        current = version
    return current


def connect(path: Union[str, Path] = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open (creating it if needed) the database and bring it up to date."""
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    migrate(con)
    return con


_COLUMNS = (
    "id, work_date, arrival, lunch_out, lunch_in, departure, required_minutes, "
    "on_site, exact_times, note, worked_minutes, debt_minutes, exceeding_minutes"
)


def _to_entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        work_date=date.fromisoformat(row["work_date"]),
        arrival=row["arrival"],
        lunch_out=row["lunch_out"],
        lunch_in=row["lunch_in"],
        departure=row["departure"],
        required_minutes=row["required_minutes"],
        on_site=bool(row["on_site"]),
        exact_times=bool(row["exact_times"]),
        note=row["note"],
        worked_minutes=row["worked_minutes"],
        debt_minutes=row["debt_minutes"],
        exceeding_minutes=row["exceeding_minutes"],
    )


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    return value if value else None


def _checked(entry: Entry) -> tuple:
    """Validate an entry and return its writable values in column order."""
    validate_times(entry.arrival, entry.lunch_out, entry.lunch_in, entry.departure)
    if entry.required_minutes < 0:
        raise ValueError("required minutes cannot be negative")
    return (
        entry.work_date.isoformat(),
        _blank_to_none(entry.arrival),
        _blank_to_none(entry.lunch_out),
        _blank_to_none(entry.lunch_in),
        _blank_to_none(entry.departure),
        entry.required_minutes,
        int(entry.on_site),
        int(entry.exact_times),
        _blank_to_none(entry.note),
    )


class EntryRepository:
    """Add, edit, delete and query days. Takes an already migrated connection."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    def add(self, entry: Entry) -> Entry:
        values = _checked(entry)
        try:
            with self._con:
                cursor = self._con.execute(
                    "INSERT INTO entries (work_date, arrival, lunch_out, lunch_in, departure, "
                    "required_minutes, on_site, exact_times, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"A day already exists for {entry.work_date.isoformat()}") from error
        return self._get_by_id(cursor.lastrowid)

    def update(self, entry: Entry) -> Entry:
        if entry.id is None:
            raise ValueError("Cannot update an entry without an id")
        values = _checked(entry)
        try:
            with self._con:
                cursor = self._con.execute(
                    "UPDATE entries SET work_date = ?, arrival = ?, lunch_out = ?, lunch_in = ?, "
                    "departure = ?, required_minutes = ?, on_site = ?, exact_times = ?, note = ? "
                    "WHERE id = ?",
                    values + (entry.id,),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"A day already exists for {entry.work_date.isoformat()}") from error
        if cursor.rowcount == 0:
            raise ValueError(f"No entry with id {entry.id}")
        return self._get_by_id(entry.id)

    def delete(self, entry_id: int) -> bool:
        """Delete by id. Returns True if a row was removed."""
        with self._con:
            cursor = self._con.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def get(self, work_date: date) -> Optional[Entry]:
        row = self._con.execute(
            f"SELECT {_COLUMNS} FROM entries WHERE work_date = ?", (work_date.isoformat(),)
        ).fetchone()
        return _to_entry(row) if row else None

    def list_between(self, start: date, end: date) -> List[Entry]:
        """Entries with start <= work_date <= end, oldest first."""
        rows = self._con.execute(
            f"SELECT {_COLUMNS} FROM entries WHERE work_date BETWEEN ? AND ? ORDER BY work_date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [_to_entry(row) for row in rows]

    def list_all(self) -> List[Entry]:
        rows = self._con.execute(f"SELECT {_COLUMNS} FROM entries ORDER BY work_date").fetchall()
        return [_to_entry(row) for row in rows]

    def day_records(self, start: date, end: date) -> List[DayRecord]:
        """Entries in the range as DayRecord, ready for periods.summarize()."""
        return [to_day_record(entry) for entry in self.list_between(start, end)]

    def _get_by_id(self, entry_id: int) -> Entry:
        row = self._con.execute(
            f"SELECT {_COLUMNS} FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return _to_entry(row)


def to_day_record(entry: Entry) -> DayRecord:
    """Build a DayRecord from the database-calculated columns of an entry."""
    complete = entry.worked_minutes is not None
    return DayRecord(
        work_date=entry.work_date,
        on_site=entry.on_site,
        summary=DaySummary(
            complete=complete,
            required=entry.required_minutes,
            worked=entry.worked_minutes,
            debt=entry.debt_minutes,
            exceeding=entry.exceeding_minutes,
        ),
    )
