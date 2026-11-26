"""Modern inline day grid for typing times directly in the month view (Step 5b).

GUI code only: collects input, delegates validation/calculation to gui.logic,
and persists changes through db.EntryRepository.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from worktime.db import EntryRepository
from worktime.gui import logic, strings
from worktime.models import Entry

BG_GRID = "#f8fafc"
BG_HEADER = "#e2e8f0"
BG_ROW = "#ffffff"
BG_ROW_WEEKEND = "#f1f5f9"
BG_ROW_OPEN = "#fffbeb"
BG_ROW_SELECTED = "#eff6ff"
BG_INVALID = "#fee2e2"

FG_DEFAULT = "#0f172a"
FG_WEEKEND = "#64748b"
FG_DEBT = "#b3261e"
FG_EXCEEDING = "#1b7f3b"
FG_OPEN = "#b45309"
FG_INVALID = "#b3261e"

BADGE_ONSITE_BG = "#dbeafe"
BADGE_ONSITE_FG = "#1d4ed8"
BADGE_REMOTE_BG = "#f1f5f9"
BADGE_REMOTE_FG = "#64748b"

FONT_HEADER = ("Segoe UI", 9, "bold")
FONT_CELL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_BADGE = ("Segoe UI", 9, "bold")

BADGE_VACATION_BG = "#fef3c7"
BADGE_VACATION_FG = "#b45309"
BADGE_HOLIDAY_BG = "#f3e8ff"
BADGE_HOLIDAY_FG = "#6b21a8"
BG_ROW_VACATION = "#fffbeb"
BG_ROW_HOLIDAY = "#faf5ff"

# Shared by the header and every row so all columns line up: (min pixel width, weight).
COL_DATE, COL_DAY, COL_ARRIVAL, COL_LUNCH_OUT, COL_LUNCH_IN, COL_DEPARTURE = range(6)
COL_SITE, COL_WORKED, COL_DEBT, COL_EXCEEDING, COL_EXTRA, COL_NOTE, COL_ACTION = range(6, 13)
GRID_COLUMNS = (
    (90, 0), (50, 0), (72, 0), (72, 0), (72, 0), (72, 0),
    (84, 0), (76, 0), (76, 0), (86, 0), (90, 0), (160, 1), (130, 0),
)
CELL_PADX = 3


def configure_columns(frame: tk.Misc) -> None:
    for idx, (minsize, weight) in enumerate(GRID_COLUMNS):
        frame.grid_columnconfigure(idx, minsize=minsize, weight=weight, uniform="")


class ExtraModal(tk.Toplevel):
    """Modal opened from the Extra button on a day row to mark Vacation or Holiday."""

    def __init__(
        self,
        parent: tk.Misc,
        work_date: date,
        vacation: bool,
        holiday: bool,
        on_apply: Callable[[bool, bool], None],
    ) -> None:
        super().__init__(parent)
        self._on_apply = on_apply
        self.title(strings.EXTRA_MODAL_TITLE.format(date=logic.format_date(work_date)))
        self.resizable(False, False)
        self.transient(parent)

        self._vacation_var = tk.BooleanVar(value=vacation)
        self._holiday_var = tk.BooleanVar(value=holiday)

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        ttk.Label(body, text=strings.EXTRA_MODAL_HINT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        vac_cb = ttk.Checkbutton(
            body,
            text=strings.COLUMN_VACATION,
            variable=self._vacation_var,
            command=self._on_vacation_toggled,
        )
        vac_cb.grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        hol_cb = ttk.Checkbutton(
            body,
            text=strings.COLUMN_HOLIDAY,
            variable=self._holiday_var,
            command=self._on_holiday_toggled,
        )
        hol_cb.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=strings.BUTTON_CANCEL, command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text=strings.BUTTON_SAVE, command=self._save).grid(row=0, column=1)

        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        vac_cb.focus_set()

    def _on_vacation_toggled(self) -> None:
        if self._vacation_var.get():
            self._holiday_var.set(False)

    def _on_holiday_toggled(self) -> None:
        if self._holiday_var.get():
            self._vacation_var.set(False)

    def _save(self) -> None:
        vac = bool(self._vacation_var.get())
        hol = bool(self._holiday_var.get())
        self.destroy()
        self._on_apply(vac, hol)


class _RowWidgets:
    """Holds the Tkinter variables and widgets for a single calendar day row."""

    def __init__(
        self,
        parent: tk.Widget,
        day_row: logic.DayRow,
        default_required: int,
        on_select: Callable[[date], None],
        on_edit_dialog: Callable[[date], None],
        on_commit: Callable[[date], None],
        on_navigate: Callable[[date, int, int], None],
        on_import_week: Callable[[date], None],
    ) -> None:
        self.work_date = day_row.work_date
        self.is_weekend = day_row.is_weekend
        self.existing: Optional[Entry] = day_row.entry
        self.default_required = default_required
        self._on_select = on_select
        self._on_commit = on_commit
        self._on_navigate = on_navigate
        self._selected = False
        self._building = True

        entry = day_row.entry
        self.time_vars: Dict[str, tk.StringVar] = {
            "arrival": tk.StringVar(value=entry.arrival or "" if entry else ""),
            "lunch_out": tk.StringVar(value=entry.lunch_out or "" if entry else ""),
            "lunch_in": tk.StringVar(value=entry.lunch_in or "" if entry else ""),
            "departure": tk.StringVar(value=entry.departure or "" if entry else ""),
        }
        self.note_var = tk.StringVar(value=entry.note or "" if entry else "")
        self.on_site = bool(entry.on_site) if entry else False
        self.vacation = bool(entry.vacation) if entry else False
        self.holiday = bool(entry.holiday) if entry else False

        self.worked_var = tk.StringVar()
        self.debt_var = tk.StringVar()
        self.exceeding_var = tk.StringVar()

        base_bg = self._base_bg(day_row.state)
        fg_date = FG_WEEKEND if day_row.is_weekend else FG_DEFAULT

        self.frame = tk.Frame(parent, bg=base_bg, pady=3, padx=4, highlightthickness=1, highlightbackground="#e2e8f0")
        self.frame.pack(fill="x", padx=2, pady=1)
        configure_columns(self.frame)

        self.date_lbl = tk.Label(
            self.frame, text=logic.format_date(self.work_date), width=1, anchor="w",
            bg=base_bg, fg=fg_date, font=FONT_CELL, cursor="hand2",
        )
        self.date_lbl.grid(row=0, column=COL_DATE, sticky="ew", padx=CELL_PADX)
        self.day_lbl = tk.Label(
            self.frame, text=day_row.weekday, width=1, anchor="w",
            bg=base_bg, fg=fg_date, font=FONT_CELL, cursor="hand2",
        )
        self.day_lbl.grid(row=0, column=COL_DAY, sticky="ew", padx=CELL_PADX)

        for lbl in (self.frame, self.date_lbl, self.day_lbl):
            lbl.bind("<Button-1>", lambda _e: self._select())
            lbl.bind("<Double-1>", lambda _e: on_edit_dialog(self.work_date))

        self.entries: Dict[str, tk.Entry] = {}
        self.focus_order: List[tk.Widget] = []

        for col_idx, field in enumerate(logic.TIME_FIELDS):
            var = self.time_vars[field]
            ent = tk.Entry(
                self.frame, textvariable=var, width=1, justify="center",
                font=FONT_CELL, relief="solid", bd=1,
                bg="#ffffff", fg=FG_DEFAULT,
            )
            ent.grid(row=0, column=COL_ARRIVAL + col_idx, sticky="ew", padx=CELL_PADX)
            var.trace_add("write", lambda *_a: self._on_typed())
            ent.bind("<FocusIn>", lambda _e: self._select())
            ent.bind("<FocusOut>", lambda _e: self._commit())
            ent.bind("<Return>", lambda _e, c=col_idx: self._return_key(c))
            ent.bind("<Up>", lambda _e, c=col_idx: self._arrow_key(-1, c))
            ent.bind("<Down>", lambda _e, c=col_idx: self._arrow_key(1, c))
            self.entries[field] = ent
            self.focus_order.append(ent)

        self.badge = tk.Label(
            self.frame, width=1, anchor="center", font=FONT_BADGE,
            cursor="hand2", padx=4, pady=1, takefocus=1,
        )
        self.badge.grid(row=0, column=COL_SITE, sticky="ew", padx=CELL_PADX)
        self.badge.bind("<Button-1>", lambda _e: self._toggle_site())
        self.badge.bind("<space>", lambda _e: self._toggle_site())
        self.badge.bind("<Return>", lambda _e: self._toggle_site())
        self.badge.bind("<FocusIn>", lambda _e: self._select())
        self.focus_order.append(self.badge)

        self.worked_lbl = tk.Label(
            self.frame, textvariable=self.worked_var, width=1, anchor="center",
            bg=base_bg, fg=FG_DEFAULT, font=FONT_BOLD,
        )
        self.worked_lbl.grid(row=0, column=COL_WORKED, sticky="ew", padx=CELL_PADX)
        self.debt_lbl = tk.Label(
            self.frame, textvariable=self.debt_var, width=1, anchor="center",
            bg=base_bg, fg=FG_DEBT, font=FONT_BOLD,
        )
        self.debt_lbl.grid(row=0, column=COL_DEBT, sticky="ew", padx=CELL_PADX)
        self.exceeding_lbl = tk.Label(
            self.frame, textvariable=self.exceeding_var, width=1, anchor="center",
            bg=base_bg, fg=FG_EXCEEDING, font=FONT_BOLD,
        )
        self.exceeding_lbl.grid(row=0, column=COL_EXCEEDING, sticky="ew", padx=CELL_PADX)

        self.extra_btn = tk.Label(
            self.frame, text=strings.COLUMN_EXTRA, width=1, anchor="center", font=FONT_BADGE,
            cursor="hand2", padx=4, pady=1, takefocus=1,
        )
        self.extra_btn.grid(row=0, column=COL_EXTRA, sticky="ew", padx=CELL_PADX)
        self.extra_btn.bind("<Button-1>", lambda _e: self._open_extra_modal())
        self.extra_btn.bind("<space>", lambda _e: self._open_extra_modal())
        self.extra_btn.bind("<Return>", lambda _e: self._open_extra_modal())
        self.extra_btn.bind("<FocusIn>", lambda _e: self._select())
        self.focus_order.append(self.extra_btn)

        self.note_entry = tk.Entry(
            self.frame, textvariable=self.note_var, font=FONT_CELL,
            relief="solid", bd=1, bg="#ffffff", fg=FG_DEFAULT,
        )
        self.note_entry.grid(row=0, column=COL_NOTE, sticky="ew", padx=CELL_PADX)
        self.note_var.trace_add("write", lambda *_a: self._on_typed())
        self.note_entry.bind("<FocusIn>", lambda _e: self._select())
        self.note_entry.bind("<FocusOut>", lambda _e: self._commit())
        self.note_entry.bind("<Return>", lambda _e: self._return_key(4))
        self.note_entry.bind("<Up>", lambda _e: self._arrow_key(-1, 4))
        self.note_entry.bind("<Down>", lambda _e: self._arrow_key(1, 4))
        self.focus_order.append(self.note_entry)

        if logic.is_friday(self.work_date):
            self.import_btn = ttk.Button(
                self.frame,
                text=strings.BUTTON_IMPORT_WEEK_CSV,
                command=lambda: on_import_week(self.work_date),
            )
            self.import_btn.grid(row=0, column=COL_ACTION, sticky="e", padx=CELL_PADX)

        self._update_badge()
        self._update_extra_btn()
        self._building = False
        self.evaluate()

    def _base_bg(self, state: str) -> str:
        if self._selected:
            return BG_ROW_SELECTED
        if state == "vacation":
            return BG_ROW_VACATION
        if state == "holiday":
            return BG_ROW_HOLIDAY
        if state == "open":
            return BG_ROW_OPEN
        if self.is_weekend:
            return BG_ROW_WEEKEND
        return BG_ROW

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_row_bg(self.evaluate().state)

    def _apply_row_bg(self, state: str) -> None:
        bg = self._base_bg(state)
        border = "#3b82f6" if self._selected else "#e2e8f0"
        self.frame.configure(bg=bg, highlightbackground=border)
        for w in (self.date_lbl, self.day_lbl, self.worked_lbl, self.debt_lbl, self.exceeding_lbl):
            w.configure(bg=bg)

    def _update_badge(self) -> None:
        if self.on_site:
            self.badge.configure(text=strings.SITE_BADGE_ONSITE, bg=BADGE_ONSITE_BG, fg=BADGE_ONSITE_FG)
        else:
            self.badge.configure(text=strings.SITE_BADGE_REMOTE, bg=BADGE_REMOTE_BG, fg=BADGE_REMOTE_FG)

    def _update_extra_btn(self) -> None:
        if self.vacation:
            self.extra_btn.configure(
                text=strings.COLUMN_VACATION, bg=BADGE_VACATION_BG, fg=BADGE_VACATION_FG, relief="solid", bd=1
            )
        elif self.holiday:
            self.extra_btn.configure(
                text=strings.COLUMN_HOLIDAY, bg=BADGE_HOLIDAY_BG, fg=BADGE_HOLIDAY_FG, relief="solid", bd=1
            )
        else:
            self.extra_btn.configure(
                text=strings.COLUMN_EXTRA, bg=BADGE_REMOTE_BG, fg=BADGE_REMOTE_FG, relief="flat", bd=1
            )

    def _open_extra_modal(self) -> None:
        self._select()
        ExtraModal(
            self.frame.winfo_toplevel(),
            self.work_date,
            self.vacation,
            self.holiday,
            self._apply_extra,
        )

    def _apply_extra(self, vacation: bool, holiday: bool) -> None:
        self.vacation = vacation
        self.holiday = holiday
        self._update_extra_btn()
        self.evaluate()
        self._commit()

    def _select(self) -> None:
        self._on_select(self.work_date)

    def _toggle_site(self) -> None:
        self._select()
        self.on_site = not self.on_site
        self._update_badge()
        self.evaluate()
        self._commit()

    def _on_typed(self) -> None:
        if not self._building:
            self.evaluate()

    def evaluate(self) -> logic.InlineDayState:
        state = logic.validate_inline_day(
            self.work_date,
            self.time_vars["arrival"].get(),
            self.time_vars["lunch_out"].get(),
            self.time_vars["lunch_in"].get(),
            self.time_vars["departure"].get(),
            self.on_site,
            existing=self.existing,
            default_required=self.default_required,
            note=self.note_var.get(),
            vacation=self.vacation,
            holiday=self.holiday,
        )
        for name, ent in self.entries.items():
            if name in state.invalid_fields:
                ent.configure(bg=BG_INVALID, fg=FG_INVALID)
            else:
                ent.configure(bg="#ffffff", fg=FG_DEFAULT)
        worked_display = state.worked_text
        if state.warnings and worked_display:
            worked_display = f"{worked_display} Ã¢Å¡Â "
        self.worked_var.set(worked_display)
        self.debt_var.set(state.debt_text)
        self.exceeding_var.set(state.exceeding_text)
        self.worked_lbl.configure(fg=FG_OPEN if state.state == "open" else FG_DEFAULT)
        self._apply_row_bg(state.state)
        return state

    def _commit(self) -> None:
        if not self._building:
            self._on_commit(self.work_date)

    def _return_key(self, col_idx: int) -> str:
        self._commit()
        if col_idx < 3:
            self.entries[logic.TIME_FIELDS[col_idx + 1]].focus_set()
        else:
            self._on_navigate(self.work_date, 1, 0)
        return "break"

    def _arrow_key(self, row_delta: int, col_idx: int) -> str:
        self._commit()
        self._on_navigate(self.work_date, row_delta, col_idx)
        return "break"

    def focus_column(self, col_idx: int) -> None:
        if col_idx == 4:
            self.note_entry.focus_set()
            self.note_entry.icursor("end")
        else:
            ent = self.entries[logic.TIME_FIELDS[min(max(col_idx, 0), 3)]]
            ent.focus_set()
            ent.icursor("end")


class DayGrid(ttk.Frame):
    """Scrollable month grid with inline time fields, on-site badge, and live totals."""

    def __init__(
        self,
        parent: tk.Misc,
        repo: EntryRepository,
        on_changed: Callable[[], None],
        on_edit_dialog: Callable[[date], None],
        on_import_week: Callable[[date], None],
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._on_changed = on_changed
        self._on_edit_dialog = on_edit_dialog
        self._on_import_week = on_import_week
        self._rows: Dict[date, _RowWidgets] = {}
        self._ordered_dates: List[date] = []
        self._selected: Optional[date] = None

        self._build_header()
        self._build_canvas()

    def _build_header(self) -> None:
        # Same left inset as a row: row pack padx (2) + border (1) + row padx (4).
        self._hdr = tk.Frame(self, bg=BG_HEADER, pady=6, padx=7)
        self._hdr.pack(fill="x")
        configure_columns(self._hdr)
        specs = (
            (COL_DATE, strings.COLUMN_DATE, "w"),
            (COL_DAY, strings.COLUMN_DAY, "w"),
            (COL_ARRIVAL, strings.COLUMN_ARRIVAL, "center"),
            (COL_LUNCH_OUT, strings.COLUMN_LUNCH_OUT, "center"),
            (COL_LUNCH_IN, strings.COLUMN_LUNCH_IN, "center"),
            (COL_DEPARTURE, strings.COLUMN_DEPARTURE, "center"),
            (COL_SITE, strings.COLUMN_SITE, "center"),
            (COL_WORKED, strings.COLUMN_WORKED, "center"),
            (COL_DEBT, strings.COLUMN_DEBT, "center"),
            (COL_EXCEEDING, strings.COLUMN_EXCEEDING, "center"),
            (COL_EXTRA, strings.COLUMN_EXTRA, "center"),
            (COL_NOTE, strings.COLUMN_NOTE, "w"),
        )
        for col, text, anchor in specs:
            tk.Label(
                self._hdr, text=text, width=1, anchor=anchor,
                bg=BG_HEADER, fg=FG_DEFAULT, font=FONT_HEADER,
            ).grid(row=0, column=col, sticky="ew", padx=CELL_PADX)

    def _build_canvas(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(container, bg=BG_GRID, highlightthickness=0)
        scroll = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=BG_GRID)

        self._inner.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._window_id, width=e.width),
        )
        self._canvas.configure(yscrollcommand=scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        # Rows end where the scrollbar starts; give the header the same right inset.
        self.update_idletasks()
        self._hdr.grid_columnconfigure(len(GRID_COLUMNS), minsize=scroll.winfo_reqwidth())
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_mousewheel(self, event) -> None:
        if self.winfo_ismapped():
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def populate(
        self,
        year: int,
        month: int,
        entries: Iterable[Entry],
        default_required: int,
        select: Optional[date] = None,
    ) -> None:
        for child in self._inner.winfo_children():
            child.destroy()
        self._rows.clear()
        self._ordered_dates.clear()

        for day_row in logic.build_month_rows(year, month, entries):
            rw = _RowWidgets(
                self._inner,
                day_row,
                default_required=default_required,
                on_select=self.select_date,
                on_edit_dialog=self._on_edit_dialog,
                on_commit=self._commit_row,
                on_navigate=self._navigate_from,
                on_import_week=self._on_import_week,
            )
            self._rows[day_row.work_date] = rw
            self._ordered_dates.append(day_row.work_date)

        target = select or self._selected
        if target in self._rows:
            self.select_date(target)
        elif self._ordered_dates:
            self.select_date(self._ordered_dates[0])

    def selected_date(self) -> Optional[date]:
        return self._selected

    def select_date(self, work_date: date) -> None:
        if self._selected and self._selected in self._rows:
            self._rows[self._selected].set_selected(False)
        self._selected = work_date
        if work_date in self._rows:
            self._rows[work_date].set_selected(True)

    def _navigate_from(self, work_date: date, row_delta: int, col_idx: int) -> None:
        if work_date not in self._ordered_dates:
            return
        idx = self._ordered_dates.index(work_date)
        next_idx = max(0, min(len(self._ordered_dates) - 1, idx + row_delta))
        next_date = self._ordered_dates[next_idx]
        self.select_date(next_date)
        self._rows[next_date].focus_column(col_idx)
        if len(self._ordered_dates) > 1:
            fraction = max(0.0, (next_idx - 3) / len(self._ordered_dates))
            self._canvas.yview_moveto(min(fraction, 1.0))

    def _commit_row(self, work_date: date) -> None:
        rw = self._rows.get(work_date)
        if rw is None:
            return
        state = rw.evaluate()
        if not state.valid:
            return
        if state.empty:
            if rw.existing is not None and rw.existing.id is not None:
                self._repo.delete(rw.existing.id)
                rw.existing = None
                self._on_changed()
            return
        entry = state.entry_to_save
        if entry is None:
            return
        if rw.existing is not None:
            if (
                rw.existing.arrival == entry.arrival
                and rw.existing.lunch_out == entry.lunch_out
                and rw.existing.lunch_in == entry.lunch_in
                and rw.existing.departure == entry.departure
                and rw.existing.on_site == entry.on_site
                and rw.existing.note == entry.note
                and rw.existing.vacation == entry.vacation
                and rw.existing.holiday == entry.holiday
            ):
                return
            saved = self._repo.update(entry)
        else:
            saved = self._repo.add(entry)
        rw.existing = saved
        for field in logic.TIME_FIELDS:
            val = getattr(saved, field) or ""
            if rw.time_vars[field].get() != val:
                rw.time_vars[field].set(val)
        rw.evaluate()
        self._on_changed()
