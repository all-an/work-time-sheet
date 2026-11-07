"""Sqlite Editor window: run SQL on the program database, or on another database file.

Collects input and shows results. Splitting, running and rolling back live in
worktime.sql_runner.
"""
from __future__ import annotations

import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, Optional

from worktime import sql_runner
from worktime.gui import strings
from worktime.sql_runner import SqlError


class SqliteEditor(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        program_con: sqlite3.Connection,
        program_path: str,
        on_changed: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._program_con = program_con
        self._program_path = str(program_path)
        self._on_changed = on_changed
        self._con = program_con
        self._path = self._program_path
        self._other_con: Optional[sqlite3.Connection] = None
        self._item_to_table: Dict[str, str] = {}

        self.title(strings.EDITOR_TITLE)
        self.geometry("1040x660")
        self.minsize(740, 420)

        self._db_label = tk.StringVar()
        self._status = tk.StringVar()
        self._build()
        self._update_db_label()
        self._refresh_tables()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # -- layout -----------------------------------------------------------

    def _build(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Button(top, text=strings.EDITOR_BUTTON_OPEN_SQL, command=self._open_sql_file).pack(side="left")
        ttk.Button(top, text=strings.EDITOR_BUTTON_OPEN_DB, command=self._open_database).pack(side="left", padx=6)
        self._program_button = ttk.Button(
            top, text=strings.EDITOR_BUTTON_PROGRAM_DB, command=self._use_program_database
        )
        self._program_button.pack(side="left")
        ttk.Button(top, text=strings.EDITOR_BUTTON_RUN, command=self._run).pack(side="right")
        ttk.Button(top, text=strings.EDITOR_BUTTON_CLEAR, command=self._clear).pack(side="right", padx=6)

        ttk.Label(self, textvariable=self._db_label, padding=(8, 0)).pack(fill="x")

        workspace = ttk.PanedWindow(self, orient="horizontal")
        workspace.pack(fill="both", expand=True, padx=8, pady=6)

        # Left sidebar: VS Code Explorer-style tables tree
        sidebar = ttk.Frame(workspace)
        ttk.Label(
            sidebar,
            text=strings.EDITOR_TABLES_HEADER,
            font=("Segoe UI", 9, "bold"),
            foreground="#475569",
            padding=(6, 4),
        ).pack(fill="x")
        tree_wrap = ttk.Frame(sidebar)
        tree_wrap.pack(fill="both", expand=True)
        self._tables_tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse")
        self._tables_tree.column("#0", width=210, minwidth=140, stretch=True)
        sidebar_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self._tables_tree.yview)
        self._tables_tree.configure(yscrollcommand=sidebar_scroll.set)
        self._tables_tree.pack(side="left", fill="both", expand=True)
        sidebar_scroll.pack(side="right", fill="y")
        self._tables_tree.bind("<<TreeviewSelect>>", self._on_table_selected)
        self._tables_tree.bind("<Double-1>", self._on_table_selected)
        self._tables_tree.bind("<Return>", self._on_table_selected)
        workspace.add(sidebar, weight=1)

        # Right pane: SQL editor on top, query results on bottom
        panes = ttk.PanedWindow(workspace, orient="vertical")
        workspace.add(panes, weight=4)

        editor_frame = ttk.Frame(panes)
        self._text = tk.Text(editor_frame, height=10, wrap="none", undo=True, font=("Consolas", 11))
        editor_scroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=editor_scroll.set)
        self._text.pack(side="left", fill="both", expand=True)
        editor_scroll.pack(side="right", fill="y")
        self._text.insert("1.0", strings.EDITOR_DEFAULT_SQL)
        self._text.bind("<Control-Return>", self._on_ctrl_enter)
        panes.add(editor_frame, weight=1)

        result_frame = ttk.Frame(panes)
        self._tree = ttk.Treeview(result_frame, show="headings", selectmode="browse")
        v_scroll = ttk.Scrollbar(result_frame, orient="vertical", command=self._tree.yview)
        h_scroll = ttk.Scrollbar(result_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        self._tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        panes.add(result_frame, weight=3)

        self._status_label = ttk.Label(self, textvariable=self._status, padding=(8, 0, 8, 2))
        self._status_label.pack(fill="x")
        ttk.Label(self, text=strings.EDITOR_HINT, foreground="#777777", padding=(8, 0, 8, 8)).pack(fill="x")
        self._text.focus_set()

    # -- sidebar explorer -------------------------------------------------

    def _refresh_tables(self) -> None:
        """Populate the left sidebar with all tables and columns of the active database."""
        self._tables_tree.delete(*self._tables_tree.get_children())
        self._item_to_table.clear()
        try:
            tables = sql_runner.list_tables(self._con)
        except sqlite3.Error:
            tables = []
        if not tables:
            self._tables_tree.insert("", "end", text=strings.EDITOR_NO_TABLES)
            return
        for table in tables:
            table_node = self._tables_tree.insert("", "end", text=f"⊞ {table.name}", open=True)
            self._item_to_table[table_node] = table.name
            for col_name, col_type in table.columns:
                col_node = self._tables_tree.insert(
                    table_node, "end", text=f"{col_name} ({col_type})"
                )
                self._item_to_table[col_node] = table.name

    def _on_table_selected(self, _event) -> None:
        selection = self._tables_tree.selection()
        if not selection:
            return
        table_name = self._item_to_table.get(selection[0])
        if not table_name:
            return
        sql = sql_runner.select_table_sql(table_name)
        self._text.delete("1.0", "end")
        self._text.insert("1.0", sql)
        self._run()

    # -- database and file choice ----------------------------------------

    def _update_db_label(self) -> None:
        suffix = strings.EDITOR_PROGRAM_DB if self._con is self._program_con else ""
        self._db_label.set(strings.EDITOR_DATABASE.format(path=self._path) + suffix)
        self._program_button.state(["disabled"] if self._con is self._program_con else ["!disabled"])

    def _open_sql_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[(strings.EDITOR_SQL_FILES, "*.sql"), (strings.EDITOR_ALL_FILES, "*.*")],
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            messagebox.showerror(strings.EDITOR_FILE_ERROR, str(error), parent=self)
            return
        self._text.delete("1.0", "end")
        self._text.insert("1.0", content)

    def _open_database(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[
                (strings.EDITOR_DB_FILES, "*.sqlite *.sqlite3 *.db"),
                (strings.EDITOR_ALL_FILES, "*.*"),
            ],
        )
        if not path:
            return
        try:
            con = sqlite3.connect(path)  # no migrations: another database is left as it is
            con.execute("SELECT name FROM sqlite_master LIMIT 1")
        except sqlite3.Error as error:
            messagebox.showerror(strings.EDITOR_FILE_ERROR, str(error), parent=self)
            return
        self._close_other()
        self._other_con = con
        self._con, self._path = con, path
        self._update_db_label()
        self._refresh_tables()

    def _use_program_database(self) -> None:
        self._close_other()
        self._con, self._path = self._program_con, self._program_path
        self._update_db_label()
        self._refresh_tables()

    def _close_other(self) -> None:
        if self._other_con is not None:
            self._other_con.close()
            self._other_con = None

    # -- running ----------------------------------------------------------

    def _on_ctrl_enter(self, _event) -> str:
        self._run()
        return "break"

    def _clear(self) -> None:
        self._text.delete("1.0", "end")

    def _sql_to_run(self) -> str:
        if self._text.tag_ranges("sel"):
            return self._text.get("sel.first", "sel.last")
        return self._text.get("1.0", "end")

    def _run(self) -> None:
        script = self._sql_to_run()
        writes = sql_runner.needs_confirmation(script)
        if writes and not messagebox.askyesno(
            strings.EDITOR_CONFIRM_TITLE, strings.EDITOR_CONFIRM.format(path=self._path), parent=self
        ):
            return
        try:
            results = sql_runner.run_script(self._con, script)
        except SqlError as error:
            self._show_status(str(error), error=True)
            return
        self._show_result(sql_runner.last_result_set(results))
        self._show_status(sql_runner.summary(results), error=False)
        if writes:
            self._refresh_tables()
            if self._con is self._program_con:
                self._on_changed()

    def _show_status(self, text: str, error: bool) -> None:
        self._status.set(text)
        self._status_label.configure(foreground="#b3261e" if error else "#1b7f3b")

    def _show_result(self, result: Optional[sql_runner.StatementResult]) -> None:
        self._tree.delete(*self._tree.get_children())
        columns = result.columns if result else []
        self._tree.configure(columns=columns)
        for name in columns:
            self._tree.heading(name, text=name)
            self._tree.column(name, width=120, minwidth=60, stretch=False)
        if result is None:
            return
        for row in result.rows:
            self._tree.insert("", "end", values=[strings.EDITOR_NULL if v is None else v for v in row])

    def _close(self) -> None:
        self._close_other()
        self.destroy()
