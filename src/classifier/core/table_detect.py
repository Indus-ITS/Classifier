"""Pure table detection: decide whether a 2-D grid of cell values
contains a real data table (repeating records), as opposed to a
label-value form (e.g. a Comment Response Sheet).

No file I/O lives here. The learning tool feeds grids in; this module
only reasons about their shape. Thresholds are module constants so we
can tune them against the Phase-1 evidence report.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_HEADER_COLS: int = 3   # adjacent non-empty text cells to call a row a header
MIN_DATA_ROWS: int = 5     # consistent data rows required under the header


def _is_text(cell) -> bool:
    """True iff the cell is a non-empty, non-numeric label."""
    if cell is None:
        return False
    if isinstance(cell, bool):
        return False
    if isinstance(cell, (int, float)):
        return False
    return str(cell).strip() != ""


def _header_span(row) -> tuple[int, int] | None:
    """Longest run of adjacent text cells; return (start, width) if the
    run is at least MIN_HEADER_COLS wide, else None."""
    best_start = best_len = 0
    cur_start = cur_len = 0
    for i, cell in enumerate(row):
        if _is_text(cell):
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len, best_start = cur_len, cur_start
        else:
            cur_len = 0
    if best_len >= MIN_HEADER_COLS:
        return best_start, best_len
    return None
