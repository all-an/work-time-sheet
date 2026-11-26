"""Clock favicon generator for the Work Time Sheet Tkinter windows (including Windows taskbar)."""
from __future__ import annotations

import ctypes
import math
import sys
import tkinter as tk
from typing import List, Tuple

BG_OUTER = "#1d4ed8"
BG_FACE = "#ffffff"
FG_HAND = "#0f172a"
FG_TICK = "#64748b"

APP_USER_MODEL_ID = "worktime.worktimesheet.app.1"


def set_windows_app_id() -> None:
    """Detach the process from python.exe's taskbar group on Windows so our custom clock icon appears on the taskbar."""
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except (AttributeError, OSError):
            pass


def _point_to_segment_dist_sq(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return (px - x1) ** 2 + (py - y1) ** 2
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return (px - proj_x) ** 2 + (py - proj_y) ** 2


def build_clock_grid(size: int = 32) -> List[Tuple[str, ...]]:
    """Build a `size x size` grid of hex colors (#rrggbb) depicting a clock face."""
    cx = (size - 1) / 2.0
    cy = (size - 1) / 2.0
    r_outer = size * 0.46
    r_face = size * 0.36
    r_center = max(1.3, size * 0.065)
    hand_width_sq = max(1.0, (size * 0.045) ** 2)

    # Hour hand pointing to ~10 o'clock (-150 deg), minute hand pointing to 2 o'clock (-30 deg)
    hx = cx + math.cos(math.radians(-145)) * (r_face * 0.55)
    hy = cy + math.sin(math.radians(-145)) * (r_face * 0.55)
    mx = cx + math.cos(math.radians(-35)) * (r_face * 0.78)
    my = cy + math.sin(math.radians(-35)) * (r_face * 0.78)

    # 12, 3, 6, 9 o'clock cardinal tick dots
    tick_centers = [
        (cx, cy - r_face * 0.82),
        (cx + r_face * 0.82, cy),
        (cx, cy + r_face * 0.82),
        (cx - r_face * 0.82, cy),
    ]
    tick_r_sq = max(0.9, (size * 0.04) ** 2)

    rows: List[Tuple[str, ...]] = []
    for y in range(size):
        row: List[str] = []
        for x in range(size):
            dist = math.hypot(x - cx, y - cy)
            if dist > r_outer:
                # Transparent outside the clock circle (white fallback for put)
                row.append("")
            elif dist > r_face:
                row.append(BG_OUTER)
            elif dist <= r_center:
                row.append(FG_HAND)
            elif (
                _point_to_segment_dist_sq(x, y, cx, cy, hx, hy) <= hand_width_sq
                or _point_to_segment_dist_sq(x, y, cx, cy, mx, my) <= hand_width_sq
            ):
                row.append(FG_HAND)
            elif any((x - tx) ** 2 + (y - ty) ** 2 <= tick_r_sq for tx, ty in tick_centers):
                row.append(FG_TICK)
            else:
                row.append(BG_FACE)
        rows.append(tuple(row))
    return rows


def create_clock_photo(master: tk.Misc, size: int = 32) -> tk.PhotoImage:
    """Create a `tk.PhotoImage` clock icon of `size x size` pixels."""
    img = tk.PhotoImage(master=master, width=size, height=size)
    grid = build_clock_grid(size)
    for y, row in enumerate(grid):
        for x, color in enumerate(row):
            if color:
                img.put(color, (x, y))
    return img


def apply_clock_icon(root: tk.Tk) -> Tuple[tk.PhotoImage, ...]:
    """Attach 48x48, 32x32, and 16x16 clock icons to `root` (and all child Toplevel windows)."""
    set_windows_app_id()
    icons = (
        create_clock_photo(root, 48),
        create_clock_photo(root, 32),
        create_clock_photo(root, 16),
    )
    root.iconphoto(True, *icons)
    return icons
