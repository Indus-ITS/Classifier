"""Pure table detection: decide whether a 2-D grid of cell values
contains a real data table (repeating records), as opposed to a
label-value form (e.g. a Comment Response Sheet).

No file I/O lives here. The learning tool feeds grids in; this module
only reasons about their shape. Thresholds are module constants so we
can tune them against the Phase-1 evidence report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from classifier.io.normalize import is_empty as _is_empty

MIN_HEADER_COLS: int = 3   # text cells required to call a row a header
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


def _header_cols(row) -> list[int] | None:
    """Column indices of the text cells in a candidate header row.

    Gaps are allowed: merged header cells leave Nones between labels
    (e.g. ITEM | DESCRIPTION | <merged gap> | UNIT | QTY), so we collect
    the specific text columns rather than requiring an adjacent run.
    Returns the column indices if there are at least MIN_HEADER_COLS of
    them, else None.
    """
    cols = [i for i, c in enumerate(row) if _is_text(c)]
    if len(cols) >= MIN_HEADER_COLS:
        return cols
    return None


@dataclass
class TableHit:
    header_row: int
    col_start: int
    col_width: int
    n_data_rows: int


def _row_fills_cols(row, cols) -> bool:
    """True iff a strict majority of the header's columns are populated."""
    filled = sum(1 for c in cols if c < len(row) and not _is_empty(row[c]))
    return filled > len(cols) // 2  # strict majority: more than half


def find_table(grid: Sequence) -> TableHit | None:
    """Return the first qualifying table in the grid, or None.

    A qualifying table is a header row (>= MIN_HEADER_COLS text cells,
    gaps allowed) followed by >= MIN_DATA_ROWS rows that each keep a
    strict majority of those header columns populated. Blank rows are
    skipped without resetting the count; a row that breaks the structure
    stops the count.
    """
    for r, row in enumerate(grid):
        cols = _header_cols(row)
        if cols is None:
            continue
        n_data = 0
        for below in grid[r + 1:]:
            if all(_is_empty(below[c] if c < len(below) else None) for c in cols):
                continue  # blank row inside/after the table — skip, don't reset
            if _row_fills_cols(below, cols):
                n_data += 1
            else:
                break  # structure broke; stop counting this header's table
        if n_data >= MIN_DATA_ROWS:
            return TableHit(r, cols[0], len(cols), n_data)
    return None


