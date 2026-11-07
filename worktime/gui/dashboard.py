"""Dashboard tab: on-site and hours balance for a month, 6 months or year, with pie charts.

Pies are drawn on a plain Canvas (standard library only). Numbers come from
periods.summarize and gui.logic.
"""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk
from typing import Iterable, List

from worktime import db
from worktime.gui import logic, strings
from worktime.periods import MIN_ONSITE_PERCENT, summarize

ONSITE_COLOR = "#2f6fdb"
REMOTE_COLOR = "#e0a030"
DEBT_COLOR = "#c0392b"
EXCEEDING_COLOR = "#2e8b57"

_PERIOD_CHOICES = (
    (strings.DASH_MONTH_CHOICE, logic.PERIOD_MONTH),
    (strings.DASH_SEMESTER_CHOICE, logic.PERIOD_SEMESTER),
    (strings.DASH_YEAR_CHOICE, logic.PERIOD_YEAR),
)
_PIE_SIZE = 260


class Dashboard(ttk.Frame):
    def __init__(self, parent: tk.Misc, repo: db.EntryRepository, extra_years: Iterable[int] = ()) -> None:
        super().__init__(parent, padding=8)
        self._repo = repo
        self._extra_years = extra_years
        today = date.today()
        self._kind = logic.PERIOD_MONTH
        self._year = tk.IntVar(value=today.year)
        self._month = today.month
        self._title = tk.StringVar()
        self._background = ttk.Style().lookup("TFrame", "background") or "#f0f0f0"

        self._build_controls()
        self._build_body()
        self._build_breakdown()
        self._update_detail_choices()
        self.refresh()

    # -- layout -----------------------------------------------------------

    def _build_controls(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text=strings.DASH_PERIOD).pack(side="left", padx=(0, 4))
        self._period_box = ttk.Combobox(
            bar, width=10, state="readonly", values=[label for label, _ in _PERIOD_CHOICES]
        )
        self._period_box.current(0)
        self._period_box.pack(side="left")
        ttk.Label(bar, text=strings.LABEL_YEAR).pack(side="left", padx=(12, 4))
        self._year_box = ttk.Combobox(bar, textvariable=self._year, width=6, state="readonly")
        self._year_box.pack(side="left")
        self._detail_label = ttk.Label(bar)
        self._detail_label.pack(side="left", padx=(12, 4))
        self._detail_box = ttk.Combobox(bar, width=11, state="readonly")
        self._detail_box.pack(side="left")
        ttk.Button(bar, text=strings.BUTTON_EXPORT_CSV, command=self._export_csv).pack(side="right", padx=(10, 0))
        ttk.Label(bar, textvariable=self._title, font=("TkDefaultFont", 13, "bold")).pack(side="right")
        self._period_box.bind("<<ComboboxSelected>>", self._on_period_picked)
        self._year_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self._detail_box.bind("<<ComboboxSelected>>", self._on_detail_picked)

    def _build_body(self) -> None:
        body = ttk.Frame(self)
        body.pack(fill="x")
        self._onsite_card = self._make_card(body, strings.DASH_ONSITE_CARD, 0)
        self._hours_card = self._make_card(body, strings.DASH_HOURS_CARD, 1)
        self._onsite_canvas = self._make_canvas(body, 2)
        self._hours_canvas = self._make_canvas(body, 3)

    def _make_card(self, parent: ttk.Frame, title: str, column: int) -> ttk.Frame:
        card = ttk.LabelFrame(parent, text=title, padding=10)
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
        return card

    def _make_canvas(self, parent: ttk.Frame, column: int) -> tk.Canvas:
        canvas = tk.Canvas(
            parent, width=_PIE_SIZE, height=_PIE_SIZE + 70, highlightthickness=0, bg=self._background
        )
        canvas.grid(row=0, column=column, sticky="n", padx=(0, 8))
        return canvas

    def _build_breakdown(self) -> None:
        frame = ttk.LabelFrame(self, text=strings.DASH_BREAKDOWN, padding=6)
        frame.pack(fill="both", expand=True, pady=(8, 0))
        columns = strings.DASH_BREAKDOWN_COLUMNS
        self._table = ttk.Treeview(frame, columns=columns, show="headings", height=12, selectmode="none")
        for name in columns:
            self._table.heading(name, text=name)
            self._table.column(name, width=105, anchor="w" if name == columns[0] else "center")
        self._table.column(columns[0], width=145)
        self._table.pack(fill="both", expand=True)

    # -- choices ----------------------------------------------------------

    def _update_detail_choices(self) -> None:
        """The third picker is a month, a half year, or hidden for a whole year."""
        if self._kind == logic.PERIOD_MONTH:
            self._detail_label.configure(text=strings.LABEL_MONTH)
            self._detail_box["values"] = list(calendar.month_name)[1:]
            self._detail_box.current(self._month - 1)
        elif self._kind == logic.PERIOD_SEMESTER:
            self._detail_label.configure(text=strings.DASH_SEMESTER_CHOICE)
            self._detail_box["values"] = [strings.DASH_SEMESTER_1, strings.DASH_SEMESTER_2]
            self._detail_box.current(0 if self._month <= 6 else 1)
        if self._kind == logic.PERIOD_YEAR:
            self._detail_label.pack_forget()
            self._detail_box.pack_forget()
        elif not self._detail_box.winfo_ismapped():
            self._detail_label.pack(side="left", padx=(12, 4), after=self._year_box)
            self._detail_box.pack(side="left", after=self._detail_label)

    def _on_period_picked(self, _event) -> None:
        self._kind = _PERIOD_CHOICES[self._period_box.current()][1]
        self._update_detail_choices()
        self.refresh()

    def _on_detail_picked(self, _event) -> None:
        index = self._detail_box.current()
        if self._kind == logic.PERIOD_MONTH:
            self._month = index + 1
        else:
            self._month = logic.SEMESTER_FIRST_MONTHS[index]
        self.refresh()

    def _export_csv(self) -> None:
        anchor = date(self._year.get(), self._month, 1)
        start, end = logic.period_bounds(self._kind, anchor)
        path = filedialog.asksaveasfilename(
            parent=self,
            title=strings.EXPORT_TITLE,
            initialfile=logic.default_csv_name(self._kind, start),
            defaultextension=".csv",
            filetypes=[(strings.CSV_FILES, "*.csv"), (strings.EDITOR_ALL_FILES, "*.*")],
        )
        if not path:
            return
        count = logic.write_period_csv(path, self._repo.list_between(start, end), start, end)
        messagebox.showinfo(strings.EXPORT_TITLE, strings.EXPORT_DONE.format(count=count, path=path), parent=self)

    # -- drawing ----------------------------------------------------------

    def refresh(self) -> None:
        """Recompute everything for the chosen period from the database."""
        all_entries = self._repo.list_all()
        self._year_box["values"] = logic.year_choices(
            all_entries, date.today(), (*self._extra_years, self._year.get())
        )

        anchor = date(self._year.get(), self._month, 1)
        start, end = logic.period_bounds(self._kind, anchor)
        all_records = [db.to_day_record(e) for e in all_entries]
        summary = summarize(all_records, start, end)
        cum_balance = logic.cumulative_balance(all_records, end)
        self._title.set(logic.period_title(self._kind, start))

        stats = dict(logic.stats_lines(summary, MIN_ONSITE_PERCENT))
        stats[strings.STAT_CUMULATIVE] = logic.format_minutes(cum_balance)
        self._fill_card(self._onsite_card, [
            strings.STAT_DAYS, strings.STAT_ONSITE, strings.STAT_REMOTE,
            strings.STAT_PERCENT, strings.STAT_TARGET,
        ], stats)
        self._fill_card(self._hours_card, [
            strings.STAT_WORKED, strings.STAT_DEBT, strings.STAT_EXCEEDING,
            strings.STAT_BALANCE, strings.STAT_CUMULATIVE,
        ], stats, balances={strings.STAT_BALANCE: summary.balance, strings.STAT_CUMULATIVE: cum_balance})

        self._draw_pie(
            self._onsite_canvas, strings.PIE_ONSITE_TITLE,
            logic.pie_slices([(strings.PIE_ONSITE, summary.onsite_days), (strings.PIE_REMOTE, summary.remote_days)]),
            [ONSITE_COLOR, REMOTE_COLOR], "{value}",
        )
        self._draw_pie(
            self._hours_canvas, strings.PIE_HOURS_TITLE,
            logic.pie_slices([(strings.PIE_DEBT, summary.debt), (strings.PIE_EXCEEDING, summary.exceeding)]),
            [DEBT_COLOR, EXCEEDING_COLOR], "minutes",
        )

        self._table.delete(*self._table.get_children())
        for row in logic.running_balance_breakdown(all_records, start, end, MIN_ONSITE_PERCENT):
            self._table.insert("", "end", values=row)

    def _fill_card(self, card: ttk.Frame, keys: List[str], stats: dict, balances=None) -> None:
        for child in card.winfo_children():
            child.destroy()
        balances = balances or {}
        for row, key in enumerate(keys):
            ttk.Label(card, text=key + ":").grid(row=row, column=0, sticky="w", pady=2)
            value = ttk.Label(card, text=stats[key], wraplength=230, font=("TkDefaultFont", 10, "bold"))
            bal = balances.get(key)
            if bal:
                value.configure(foreground=EXCEEDING_COLOR if bal > 0 else DEBT_COLOR)
            value.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=2)

    def _draw_pie(self, canvas: tk.Canvas, title: str, slices, colors, value_kind: str) -> None:
        canvas.delete("all")
        canvas.create_text(_PIE_SIZE / 2, 12, text=title, font=("TkDefaultFont", 10, "bold"))
        box = (30, 30, _PIE_SIZE - 30, _PIE_SIZE - 30)
        if all(s.extent == 0 for s in slices):
            canvas.create_oval(*box, outline="#bbbbbb", dash=(3, 3))
            canvas.create_text(_PIE_SIZE / 2, _PIE_SIZE / 2, text=strings.PIE_EMPTY, fill="#777777")
        for piece, color in zip(slices, colors):
            if piece.extent == 0:
                continue
            if abs(piece.extent) >= 359.99:
                canvas.create_oval(*box, fill=color, outline="white", width=2)
            else:
                canvas.create_arc(
                    *box, start=piece.start, extent=piece.extent, fill=color, outline="white", width=2
                )
        for row, (piece, color) in enumerate(zip(slices, colors)):
            y = _PIE_SIZE - 14 + row * 22
            value = logic.format_minutes(piece.value) if value_kind == "minutes" else str(piece.value)
            canvas.create_rectangle(30, y, 44, y + 14, fill=color, outline=color)
            canvas.create_text(
                52, y + 7, anchor="w",
                text=strings.PIE_LEGEND.format(label=piece.label, value=value, percent=piece.percent),
            )
