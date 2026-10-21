"""Dialog to add or edit one day. Collects input, then calls logic and the repository."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from typing import Callable, Optional

from worktime.db import EntryRepository
from worktime.gui import logic, strings
from worktime.models import Entry


class EntryForm(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        repo: EntryRepository,
        work_date: date,
        entry: Optional[Entry],
        on_saved: Callable[[date], None],
    ) -> None:
        super().__init__(parent)
        self._repo = repo
        self._entry = entry
        self._on_saved = on_saved
        self.title(strings.FORM_TITLE_EDIT if entry else strings.FORM_TITLE_NEW)
        self.resizable(False, False)
        self.transient(parent)

        entry = entry or Entry(work_date)
        self._vars = {
            "date": tk.StringVar(value=logic.format_date(entry.work_date)),
            "arrival": tk.StringVar(value=entry.arrival or ""),
            "lunch_out": tk.StringVar(value=entry.lunch_out or ""),
            "lunch_in": tk.StringVar(value=entry.lunch_in or ""),
            "departure": tk.StringVar(value=entry.departure or ""),
            "required": tk.StringVar(value=logic.required_text(entry.required_minutes)),
            "note": tk.StringVar(value=entry.note or ""),
        }
        self._on_site = tk.BooleanVar(value=entry.on_site)
        self._exact = tk.BooleanVar(value=entry.exact_times)
        self._preview = tk.StringVar()

        body = ttk.Frame(self, padding=16)
        body.grid(sticky="nsew")
        fields = (
            (strings.FIELD_DATE, "date"),
            (strings.FIELD_ARRIVAL, "arrival"),
            (strings.FIELD_LUNCH_OUT, "lunch_out"),
            (strings.FIELD_LUNCH_IN, "lunch_in"),
            (strings.FIELD_DEPARTURE, "departure"),
            (strings.FIELD_REQUIRED, "required"),
        )
        first_entry = None
        for row, (label, key) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            widget = ttk.Entry(body, textvariable=self._vars[key], width=14)
            widget.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=3)
            self._vars[key].trace_add("write", lambda *_: self._update_preview())
            first_entry = first_entry or widget
        next_row = len(fields)
        ttk.Checkbutton(body, text=strings.FIELD_ON_SITE, variable=self._on_site).grid(
            row=next_row, column=0, columnspan=2, sticky="w", pady=3
        )
        ttk.Checkbutton(body, text=strings.FIELD_EXACT, variable=self._exact).grid(
            row=next_row + 1, column=0, columnspan=2, sticky="w", pady=3
        )
        ttk.Label(body, text=strings.FIELD_NOTE).grid(row=next_row + 2, column=0, sticky="w", pady=3)
        ttk.Entry(body, textvariable=self._vars["note"], width=32).grid(
            row=next_row + 2, column=1, sticky="w", padx=(12, 0), pady=3
        )
        ttk.Label(body, textvariable=self._preview, wraplength=340).grid(
            row=next_row + 3, column=0, columnspan=2, sticky="w", pady=(10, 4)
        )
        buttons = ttk.Frame(body)
        buttons.grid(row=next_row + 4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=strings.BUTTON_CANCEL, command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text=strings.BUTTON_SAVE, command=self._save).grid(row=0, column=1)

        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self._update_preview()
        self.grab_set()
        first_entry.focus_set()

    def _update_preview(self) -> None:
        v = self._vars
        self._preview.set(
            logic.preview_text(
                v["arrival"].get(), v["lunch_out"].get(), v["lunch_in"].get(),
                v["departure"].get(), v["required"].get(),
            )
        )

    def _save(self) -> None:
        v = self._vars
        try:
            entry = logic.build_entry(
                v["date"].get(), v["arrival"].get(), v["lunch_out"].get(), v["lunch_in"].get(),
                v["departure"].get(), v["required"].get(), self._on_site.get(), self._exact.get(),
                v["note"].get(), entry_id=self._entry.id if self._entry else None,
            )
            saved = self._repo.update(entry) if self._entry else self._repo.add(entry)
        except ValueError as error:
            messagebox.showerror(strings.ERROR_TITLE, str(error), parent=self)
            return
        self.destroy()
        self._on_saved(saved.work_date)
