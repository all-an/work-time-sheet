"""Main window: year -> month -> days navigation and the daily entries table."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional, Union

from worktime import __version__, db
from worktime.gui import logic, strings
from worktime.gui.dashboard import Dashboard
from worktime.gui.entry_form import EntryForm
from worktime.gui.sqlite_editor import SqliteEditor
from worktime.periods import MIN_ONSITE_PERCENT, month_range, summarize

_COLUMNS = (
    (strings.COLUMN_DATE, 100, "w"),
    (strings.COLUMN_DAY, 50, "w"),
    (strings.COLUMN_ARRIVAL, 70, "center"),
    (strings.COLUMN_LUNCH_OUT, 80, "center"),
    (strings.COLUMN_LUNCH_IN, 80, "center"),
    (strings.COLUMN_DEPARTURE, 80, "center"),
    (strings.COLUMN_SITE, 70, "center"),
    (strings.COLUMN_WORKED, 75, "center"),
    (strings.COLUMN_DEBT, 75, "center"),
    (strings.COLUMN_EXCEEDING, 80, "center"),
    (strings.COLUMN_NOTE, 220, "w"),
)

_ROW_COLORS = {
    "weekend": {"foreground": "#9a9a9a"},
    "open": {"background": "#fff4cc"},
    "debt": {"foreground": "#b3261e"},
    "exceeding": {"foreground": "#1b7f3b"},
}


class MainWindow:
    def __init__(self, root: tk.Tk, con, db_path: Union[str, Path] = db.DEFAULT_DB_PATH) -> None:
        self._root = root
        self._con = con
        self._db_path = str(db_path)
        self._editor: Optional[SqliteEditor] = None
        self._repo = db.EntryRepository(con)
        today = date.today()
        self._year = tk.IntVar(value=today.year)
        self._month = tk.IntVar(value=today.month)
        self._totals = tk.StringVar()
        self._target = tk.StringVar()

        root.title(f"{strings.APP_TITLE} v{__version__}")
        root.geometry("1000x720")
        root.minsize(900, 500)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        daily = ttk.Frame(notebook, padding=8)
        notebook.add(daily, text=strings.TAB_DAILY)
        self._build_navigation(daily)
        self._build_table(daily)
        self._build_footer(daily)
        self._dashboard = Dashboard(notebook, self._repo)
        notebook.add(self._dashboard, text=strings.TAB_DASHBOARD)
        self.refresh()

    # -- layout -----------------------------------------------------------

    def _build_navigation(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text=strings.BUTTON_PREVIOUS, width=3, command=lambda: self._step(-1)).pack(side="left")
        ttk.Label(bar, text=strings.LABEL_YEAR).pack(side="left", padx=(10, 4))
        self._year_box = ttk.Combobox(
            bar, textvariable=self._year, width=6, state="readonly",
            values=logic.year_choices(self._repo.list_all(), date.today()),
        )
        self._year_box.pack(side="left")
        ttk.Label(bar, text=strings.LABEL_MONTH).pack(side="left", padx=(10, 4))
        self._month_box = ttk.Combobox(
            bar, width=11, state="readonly", values=list(calendar.month_name)[1:]
        )
        self._month_box.pack(side="left")
        ttk.Button(bar, text=strings.BUTTON_NEXT, width=3, command=lambda: self._step(1)).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text=strings.BUTTON_TODAY, command=self._go_today).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text=strings.BUTTON_SQLITE_EDITOR, command=self._open_sqlite_editor).pack(side="right")
        ttk.Button(bar, text=strings.BUTTON_DELETE, command=self._delete_selected).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text=strings.BUTTON_EDIT, command=self._edit_selected).pack(side="right", padx=(0, 6))
        self._year_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self._month_box.bind("<<ComboboxSelected>>", self._on_month_picked)

    def _build_table(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        style = ttk.Style()
        style.configure("Treeview", rowheight=26)
        self._tree = ttk.Treeview(
            frame, columns=[c[0] for c in _COLUMNS], show="headings", selectmode="browse"
        )
        for name, width, anchor in _COLUMNS:
            self._tree.heading(name, text=name)
            self._tree.column(name, width=width, anchor=anchor, stretch=(name == strings.COLUMN_NOTE))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for tag, options in _ROW_COLORS.items():
            self._tree.tag_configure(tag, **options)
        self._tree.bind("<Double-1>", lambda _e: self._edit_selected())
        self._tree.bind("<Return>", lambda _e: self._edit_selected())
        self._tree.bind("<Delete>", lambda _e: self._delete_selected())

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent)
        footer.pack(fill="x", pady=(8, 0))
        ttk.Label(footer, textvariable=self._totals, wraplength=960).pack(anchor="w")
        ttk.Label(footer, textvariable=self._target, font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(4, 0))

    # -- actions ----------------------------------------------------------

    def refresh(self, select: Optional[date] = None) -> None:
        """Reload the table and totals for the chosen year and month."""
        year, month = self._year.get(), self._month.get()
        self._month_box.current(month - 1)
        start, end = month_range(date(year, month, 1))
        entries = self._repo.list_between(start, end)
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in logic.build_month_rows(year, month, entries):
            tags = (row.state,) + (("weekend",) if row.is_weekend else ())
            self._tree.insert("", "end", iid=row.work_date.isoformat(), values=row.cells, tags=tags)
        records = [db.to_day_record(e) for e in entries]
        totals, target = logic.totals_text(summarize(records, start, end), MIN_ONSITE_PERCENT)
        self._totals.set(totals)
        self._target.set(target)
        self._dashboard.refresh()
        if select is not None and self._tree.exists(select.isoformat()):
            self._tree.selection_set(select.isoformat())
            self._tree.see(select.isoformat())

    def _step(self, delta: int) -> None:
        year, month = logic.shift_month(self._year.get(), self._month.get(), delta)
        self._set_month(year, month)

    def _go_today(self) -> None:
        today = date.today()
        self._set_month(today.year, today.month)

    def _set_month(self, year: int, month: int) -> None:
        years = set(self._year_box["values"]) | {year}
        self._year_box["values"] = sorted(int(y) for y in years)
        self._year.set(year)
        self._month.set(month)
        self.refresh()

    def _on_month_picked(self, _event) -> None:
        self._month.set(self._month_box.current() + 1)
        self.refresh()

    def _open_sqlite_editor(self) -> None:
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.lift()
            self._editor.focus_set()
            return
        self._editor = SqliteEditor(self._root, self._con, self._db_path, self._after_sql_change)

    def _after_sql_change(self) -> None:
        """Data may have changed through the editor: reload the table, and the year list."""
        self._year_box["values"] = logic.year_choices(self._repo.list_all(), date.today())
        self.refresh()

    def _selected_date(self) -> Optional[date]:
        selection = self._tree.selection()
        return date.fromisoformat(selection[0]) if selection else None

    def _edit_selected(self) -> None:
        work_date = self._selected_date()
        if work_date is None:
            messagebox.showinfo(strings.APP_TITLE, strings.NOTHING_SELECTED)
            return
        EntryForm(self._root, self._repo, work_date, self._repo.get(work_date), self.refresh)

    def _delete_selected(self) -> None:
        work_date = self._selected_date()
        if work_date is None:
            messagebox.showinfo(strings.APP_TITLE, strings.NOTHING_SELECTED)
            return
        entry = self._repo.get(work_date)
        if entry is None:
            return
        message = strings.CONFIRM_DELETE.format(date=logic.format_date(work_date))
        if messagebox.askyesno(strings.CONFIRM_DELETE_TITLE, message):
            self._repo.delete(entry.id)
            self.refresh(select=work_date)


def run(db_path: Union[str, Path] = db.DEFAULT_DB_PATH) -> None:
    con = db.connect(db_path)
    root = tk.Tk()
    MainWindow(root, con, db_path)
    root.mainloop()
    con.close()
