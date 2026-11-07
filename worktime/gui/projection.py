"""Projection tab: 6-month on-site days/week and daily working hours suggestions.

All calculations live in gui.logic (build_semester_projection, projection_stats,
projection_table_rows).
"""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Iterable, List, Tuple

from worktime import db
from worktime.gui import logic, strings
from worktime.periods import MIN_ONSITE_PERCENT

ONSITE_COLOR = "#1d4ed8"
DEBT_COLOR = "#c0392b"
EXCEEDING_COLOR = "#2e8b57"


class ProjectionTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, repo: db.EntryRepository, extra_years: Iterable[int] = ()) -> None:
        super().__init__(parent, padding=8)
        self._repo = repo
        self._extra_years = extra_years
        today = date.today()
        self._year = tk.IntVar(value=today.year)
        self._semester_idx = 0 if today.month <= 6 else 1
        self._title = tk.StringVar()

        self._build_controls()
        self._build_cards()
        self._build_table()
        self.refresh()

    def _build_controls(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text=strings.LABEL_YEAR).pack(side="left", padx=(0, 4))
        self._year_box = ttk.Combobox(bar, textvariable=self._year, width=6, state="readonly")
        self._year_box.pack(side="left")
        ttk.Label(bar, text=strings.DASH_SEMESTER_CHOICE).pack(side="left", padx=(12, 4))
        self._sem_box = ttk.Combobox(
            bar, width=11, state="readonly", values=[strings.DASH_SEMESTER_1, strings.DASH_SEMESTER_2]
        )
        self._sem_box.current(self._semester_idx)
        self._sem_box.pack(side="left")
        ttk.Label(bar, textvariable=self._title, font=("TkDefaultFont", 13, "bold")).pack(side="right")

        self._year_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self._sem_box.bind("<<ComboboxSelected>>", self._on_semester_picked)

    def _build_cards(self) -> None:
        body = ttk.Frame(self)
        body.pack(fill="x")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self._onsite_card = ttk.LabelFrame(body, text=strings.PROJ_ONSITE_CARD, padding=12)
        self._onsite_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._hours_card = ttk.LabelFrame(body, text=strings.PROJ_HOURS_CARD, padding=12)
        self._hours_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

    def _build_table(self) -> None:
        frame = ttk.LabelFrame(self, text=strings.PROJ_WEEKLY_TABLE, padding=6)
        frame.pack(fill="both", expand=True, pady=(10, 0))
        columns = strings.PROJ_COLUMNS
        self._table = ttk.Treeview(frame, columns=columns, show="headings", height=12, selectmode="browse")
        widths = (175, 80, 175, 210, 100, 130, 120)
        for name, width in zip(columns, widths):
            self._table.heading(name, text=name)
            anchor = "w" if name == columns[0] else "center"
            self._table.column(name, width=width, anchor=anchor)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self._table.yview)
        self._table.configure(yscrollcommand=scroll.set)
        self._table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _on_semester_picked(self, _event) -> None:
        self._semester_idx = self._sem_box.current()
        self.refresh()

    def refresh(self) -> None:
        all_entries = self._repo.list_all()
        today = date.today()
        self._year_box["values"] = logic.year_choices(all_entries, today, (*self._extra_years, self._year.get()))

        first_month = logic.SEMESTER_FIRST_MONTHS[self._semester_idx]
        anchor = date(self._year.get(), first_month, 1)
        records = [db.to_day_record(e) for e in all_entries]
        default_req = logic.default_required_minutes(all_entries)
        proj = logic.build_semester_projection(
            records, anchor, today, MIN_ONSITE_PERCENT, required_per_day=default_req
        )
        self._title.set(logic.period_title(logic.PERIOD_SEMESTER, proj.start))

        onsite_lines, hours_lines = logic.projection_stats(proj, MIN_ONSITE_PERCENT)
        self._fill_card(
            self._onsite_card,
            onsite_lines,
            highlights={
                strings.PROJ_ONSITE_PACE: EXCEEDING_COLOR if proj.achievable_onsite else DEBT_COLOR,
                strings.PROJ_ONSITE_NEEDED: ONSITE_COLOR,
            },
        )
        bal_color = (
            EXCEEDING_COLOR if proj.current_balance > 0
            else (DEBT_COLOR if proj.current_balance < 0 else None)
        )
        self._fill_card(
            self._hours_card,
            hours_lines,
            highlights={
                strings.PROJ_CURRENT_BALANCE: bal_color,
                strings.PROJ_DAILY_TARGET: ONSITE_COLOR,
                strings.PROJ_SCHEDULE: EXCEEDING_COLOR,
            },
        )

        self._table.delete(*self._table.get_children())
        for row in logic.projection_table_rows(proj):
            self._table.insert("", "end", values=row)

    def _fill_card(
        self,
        card: ttk.Frame,
        lines: List[Tuple[str, str]],
        highlights: dict,
    ) -> None:
        for child in card.winfo_children():
            child.destroy()
        for row_idx, (label, val) in enumerate(lines):
            ttk.Label(card, text=label + ":").grid(row=row_idx, column=0, sticky="w", pady=3)
            val_lbl = ttk.Label(card, text=val, wraplength=310, font=("TkDefaultFont", 10, "bold"))
            color = highlights.get(label)
            if color:
                val_lbl.configure(foreground=color)
            val_lbl.grid(row=row_idx, column=1, sticky="w", padx=(12, 0), pady=3)
