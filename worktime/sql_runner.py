"""Run ad-hoc SQL for the Sqlite Editor window. No Tkinter here.

A script is split into statements and run in one transaction: if any
statement fails, everything is rolled back and nothing is saved.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MAX_ROWS = 1000  # rows kept per result, so a huge SELECT cannot freeze the window

_READ_ONLY_KEYWORDS = ("SELECT", "EXPLAIN", "VALUES")
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


class SqlError(Exception):
    """A statement failed. The whole script was rolled back."""


@dataclass
class StatementResult:
    sql: str
    columns: List[str] = field(default_factory=list)
    rows: List[Tuple] = field(default_factory=list)
    truncated: bool = False
    rowcount: int = 0  # rows changed by INSERT/UPDATE/DELETE


def _has_code(text: str) -> bool:
    return bool(_COMMENTS.sub("", text).strip())


def split_statements(script: str) -> List[str]:
    """Split a script on semicolons that end a complete statement.

    Semicolons inside quotes, comments and triggers do not split. A last
    statement without a semicolon is kept. Comment-only pieces are dropped.
    """
    statements = []
    buffer = ""
    for char in script:
        buffer += char
        if char == ";" and sqlite3.complete_statement(buffer):
            if _has_code(buffer):
                statements.append(buffer.strip())
            buffer = ""
    if _has_code(buffer):
        statements.append(buffer.strip())
    return statements


def is_read_only(statement: str) -> bool:
    """True for SELECT / EXPLAIN / VALUES. Everything else may change the database."""
    words = _COMMENTS.sub("", statement).split(None, 1)
    return bool(words) and words[0].upper() in _READ_ONLY_KEYWORDS


def needs_confirmation(script: str) -> bool:
    """True when any statement of the script could change the database."""
    return any(not is_read_only(s) for s in split_statements(script))


def run_script(con: sqlite3.Connection, script: str) -> List[StatementResult]:
    """Run every statement in one transaction; commit only if all succeed."""
    statements = split_statements(script)
    if not statements:
        raise SqlError("Nothing to run: the SQL is empty")
    results = []
    if not con.in_transaction:
        con.execute("BEGIN")
    try:
        for number, sql in enumerate(statements, start=1):
            cursor = con.execute(sql)
            result = StatementResult(sql)
            if cursor.description:
                result.columns = [column[0] for column in cursor.description]
                fetched = cursor.fetchmany(MAX_ROWS + 1)
                result.truncated = len(fetched) > MAX_ROWS
                result.rows = [tuple(row) for row in fetched[:MAX_ROWS]]
            else:
                result.rowcount = max(cursor.rowcount, 0)
            results.append(result)
    except sqlite3.Error as error:
        con.rollback()
        which = f"Statement {number} of {len(statements)}" if len(statements) > 1 else "Statement"
        raise SqlError(f"{which} failed, nothing was saved: {error}") from error
    con.commit()
    return results


def summary(results: List[StatementResult]) -> str:
    """One status line for the editor window."""
    changed = sum(r.rowcount for r in results)
    last = next((r for r in reversed(results) if r.columns), None)
    parts = [f"{len(results)} statement(s) run"]
    if changed:
        parts.append(f"{changed} row(s) changed")
    if last is not None:
        shown = f"{len(last.rows)} row(s) shown"
        parts.append(shown + (f" (limited to the first {MAX_ROWS})" if last.truncated else ""))
    return ", ".join(parts)


def last_result_set(results: List[StatementResult]) -> Optional[StatementResult]:
    """The last statement that returned columns (a SELECT), if any."""
    return next((r for r in reversed(results) if r.columns), None)


_SIMPLE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class TableInfo:
    """One table of a SQLite database and its (column_name, column_type) pairs."""

    name: str
    columns: Tuple[Tuple[str, str], ...] = ()


def quote_identifier(name: str) -> str:
    """Return `name` as-is if it is a simple identifier, otherwise double-quoted."""
    if _SIMPLE_IDENTIFIER.match(name):
        return name
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def select_table_sql(table_name: str) -> str:
    """Build a SELECT * query for `table_name`."""
    return f"SELECT * FROM {quote_identifier(table_name)};"


def list_tables(con: sqlite3.Connection) -> List[TableInfo]:
    """List user tables in `con` in alphabetical order, including their columns."""
    rows = con.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    tables: List[TableInfo] = []
    for row in rows:
        name = row[0]
        escaped = name.replace('"', '""')
        col_rows = con.execute(f'PRAGMA table_xinfo("{escaped}")').fetchall()
        cols = tuple(( str(c[1]), str(c[2] or "ANY") ) for c in col_rows)
        tables.append(TableInfo(name=name, columns=cols))
    return tables
