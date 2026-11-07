"""Main window: year -> month -> days navigation and the inline daily entries grid."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional, Union

from worktime import __version__, db
from worktime.gui import logic, strings
from worktime.gui.dashboard import Dashboard
from worktime.gui.day_grid import DayGrid
from worktime.gui.entry_form import EntryForm
from worktime.gui.projection import ProjectionTab
from worktime.gui.sqlite_editor import SqliteEditor
from worktime.periods import MIN_ONSITE_PERCENT, month_range, summarize


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
        self._new_year_var = tk.StringVar()
        self._extra_years: set = set()
        self._totals = tk.StringVar()
        self._target = tk.StringVar()

        root.title(f"{strings.APP_TITLE} v{__version__}")
        root.geometry("1080x760")
        root.minsize(960, 540)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        daily = ttk.Frame(notebook, padding=8)
        notebook.add(daily, text=strings.TAB_DAILY)
        self._build_navigation(daily)
        self._build_grid(daily)
        self._build_footer(daily)
        self._dashboard = Dashboard(notebook, self._repo, extra_years=self._extra_years)
        notebook.add(self._dashboard, text=strings.TAB_DASHBOARD)
        self._projection = ProjectionTab(notebook, self._repo, extra_years=self._extra_years)
        notebook.add(self._projection, text=strings.TAB_PROJECTION)

        root.bind("<Control-t>", lambda _e: self._go_today())
        root.bind("<Control-e>", lambda _e: self._edit_selected())
        self.refresh(select=today)

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
        self._new_year_entry = ttk.Entry(bar, textvariable=self._new_year_var, width=6, justify="center")
        self._new_year_entry.pack(side="left", padx=(6, 2))
        self._new_year_entry.bind("<Return>", lambda _e: self._add_year())
        ttk.Button(bar, text=strings.BUTTON_ADD_YEAR, command=self._add_year).pack(side="left", padx=(2, 0))
        ttk.Label(bar, text=strings.LABEL_MONTH).pack(side="left", padx=(10, 4))
        self._month_box = ttk.Combobox(
            bar, width=11, state="readonly", values=list(calendar.month_name)[1:]
        )
        self._month_box.pack(side="left")
        ttk.Button(bar, text=strings.BUTTON_NEXT, width=3, command=lambda: self._step(1)).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text=strings.BUTTON_TODAY, command=self._go_today).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text=strings.BUTTON_SQLITE_EDITOR, command=self._open_sqlite_editor).pack(side="right")
        ttk.Button(bar, text=strings.BUTTON_BACKUP, command=self._backup_database).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text=strings.BUTTON_EXPORT_CSV, command=self._export_month_csv).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text=strings.BUTTON_DELETE, command=self._delete_selected).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text=strings.BUTTON_EDIT, command=self._edit_selected).pack(side="right", padx=(0, 6))
        self._year_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self._month_box.bind("<<ComboboxSelected>>", self._on_month_picked)

    def _build_grid(self, parent: ttk.Frame) -> None:
        self._grid = DayGrid(
            parent,
            self._repo,
            on_changed=self.refresh_totals,
            on_edit_dialog=self._open_edit_dialog,
            on_import_week=self._import_week_csv,
        )
        self._grid.pack(fill="both", expand=True)

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent)
        footer.pack(fill="x", pady=(8, 0))
        ttk.Label(footer, text=strings.GRID_HINT, foreground="#64748b").pack(anchor="w", pady=(0, 4))
        ttk.Label(footer, textvariable=self._totals, wraplength=1020).pack(anchor="w")
        ttk.Label(footer, textvariable=self._target, font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(4, 0))

    # -- actions ----------------------------------------------------------

    def refresh(self, select: Optional[date] = None) -> None:
        """Reload the grid and totals for the chosen year and month."""
        year, month = self._year.get(), self._month.get()
        self._extra_years.add(year)
        self._month_box.current(month - 1)
        all_entries = self._repo.list_all()
        self._year_box["values"] = logic.year_choices(
            all_entries, date.today(), (*self._year_box["values"], *self._extra_years, year)
        )
        start, end = month_range(date(year, month, 1))
        entries = self._repo.list_between(start, end)
        default_req = logic.default_required_minutes(all_entries)
        self._grid.populate(year, month, entries, default_req, select=select)
        self.refresh_totals()

    def refresh_totals(self) -> None:
        """Recompute month footer totals and refresh the dashboard without rebuilding the grid."""
        year, month = self._year.get(), self._month.get()
        start, end = month_range(date(year, month, 1))
        entries = self._repo.list_between(start, end)
        records = [db.to_day_record(e) for e in entries]
        totals, target = logic.totals_text(summarize(records, start, end), MIN_ONSITE_PERCENT)
        self._totals.set(totals)
        self._target.set(target)
        self._dashboard.refresh()
        self._projection.refresh()

    def _step(self, delta: int) -> None:
        year, month = logic.shift_month(self._year.get(), self._month.get(), delta)
        self._set_month(year, month)

    def _go_today(self) -> None:
        today = date.today()
        self._set_month(today.year, today.month, select=today)

    def _set_month(self, year: int, month: int, select: Optional[date] = None) -> None:
        self._extra_years.add(year)
        self._year_box["values"] = logic.year_choices(
            self._repo.list_all(), date.today(), (*self._year_box["values"], *self._extra_years, year)
        )
        self._year.set(year)
        self._month.set(month)
        self.refresh(select=select)

    def _add_year(self) -> None:
        try:
            year = logic.parse_year(self._new_year_var.get(), self._year_box["values"])
        except ValueError as error:
            messagebox.showerror(strings.ERROR_TITLE, str(error), parent=self._root)
            return
        self._new_year_var.set("")
        self._set_month(year, self._month.get())

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
        self._year_box["values"] = logic.year_choices(
            self._repo.list_all(), date.today(), (self._year.get(),)
        )
        self.refresh()

    def _backup_database(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self._root,
            title=strings.BACKUP_TITLE,
            initialfile=logic.default_backup_name(date.today()),
            defaultextension=".sqlite3",
            filetypes=[(strings.EDITOR_DB_FILES, "*.sqlite3 *.sqlite *.db"), (strings.EDITOR_ALL_FILES, "*.*")],
        )
        if not path:
            return
        db.backup_database(self._con, path)
        messagebox.showinfo(strings.BACKUP_TITLE, strings.BACKUP_DONE.format(path=path), parent=self._root)

    def _export_month_csv(self) -> None:
        start, end = month_range(date(self._year.get(), self._month.get(), 1))
        path = filedialog.asksaveasfilename(
            parent=self._root,
            title=strings.EXPORT_TITLE,
            initialfile=logic.default_csv_name(logic.PERIOD_MONTH, start),
            defaultextension=".csv",
            filetypes=[(strings.CSV_FILES, "*.csv"), (strings.EDITOR_ALL_FILES, "*.*")],
        )
        if not path:
            return
        count = logic.write_period_csv(path, self._repo.list_between(start, end), start, end)
        messagebox.showinfo(strings.EXPORT_TITLE, strings.EXPORT_DONE.format(count=count, path=path), parent=self._root)

    def _import_week_csv(self, friday: date) -> None:
        path = filedialog.askopenfilename(
            parent=self._root,
            title=strings.IMPORT_WEEK_TITLE,
            filetypes=[(strings.CSV_FILES, "*.csv"), (strings.EDITOR_ALL_FILES, "*.*")],
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
            default_req = logic.default_required_minutes(self._repo.list_all())
            entries = logic.parse_week_csv(content, friday, default_required=default_req)
            for entry in entries:
                existing = self._repo.get(entry.work_date)
                if existing is not None:
                    self._repo.update(
                        entry.__class__(
                            work_date=entry.work_date,
                            arrival=entry.arrival,
                            lunch_out=entry.lunch_out,
                            lunch_in=entry.lunch_in,
                            departure=entry.departure,
                            required_minutes=entry.required_minutes,
                            on_site=entry.on_site,
                            exact_times=entry.exact_times,
                            note=entry.note,
                            id=existing.id,
                        )
                    )
                else:
                    self._repo.add(entry)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            messagebox.showerror(strings.ERROR_TITLE, str(error), parent=self._root)
            return
        monday = friday - timedelta(days=friday.weekday())
        self.refresh(select=friday)
        messagebox.showinfo(
            strings.IMPORT_WEEK_TITLE,
            strings.IMPORT_WEEK_DONE.format(
                count=len(entries),
                monday=logic.format_date(monday),
                friday=logic.format_date(friday),
            ),
            parent=self._root,
        )

    def _selected_date(self) -> Optional[date]:
        return self._grid.selected_date()

    def _open_edit_dialog(self, work_date: date) -> None:
        default_req = logic.default_required_minutes(self._repo.list_all())
        EntryForm(
            self._root,
            self._repo,
            work_date,
            self._repo.get(work_date),
            self._on_entry_saved,
            default_required=default_req,
        )

    def _on_entry_saved(self, saved_date: date) -> None:
        self._set_month(saved_date.year, saved_date.month, select=saved_date)

    def _edit_selected(self) -> None:
        work_date = self._selected_date()
        if work_date is None:
            messagebox.showinfo(strings.APP_TITLE, strings.NOTHING_SELECTED)
            return
        self._open_edit_dialog(work_date)

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
