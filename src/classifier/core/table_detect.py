"""Pure table detection: decide whether a 2-D grid of cell values
contains a real data table (repeating records), as opposed to a
label-value form (e.g. a Comment Response Sheet).

No file I/O lives here. The learning tool feeds grids in; this module
only reasons about their shape. Thresholds are module constants so we
can tune them against the Phase-1 evidence report.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Iterator

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


@dataclass
class TableHit:
    header_row: int
    col_start: int
    col_width: int
    n_data_rows: int


def _row_fills_span(row, start: int, width: int) -> bool:
    """True iff a majority of the header's columns are populated in row."""
    filled = 0
    for c in range(start, start + width):
        cell = row[c] if c < len(row) else None
        if cell is not None and str(cell).strip() != "":
            filled += 1
    return filled >= (width + 1) // 2  # strict majority (ceil of half)


def find_table(grid) -> TableHit | None:
    """Return the first qualifying table in the grid, or None.

    A qualifying table is a header row (>= MIN_HEADER_COLS adjacent text
    cells) followed by >= MIN_DATA_ROWS rows that each keep a majority of
    those header columns populated. Data rows may be interrupted by blank
    rows without resetting the count, but blanks do not count as data.
    """
    for r, row in enumerate(grid):
        span = _header_span(row)
        if span is None:
            continue
        start, width = span
        n_data = 0
        for below in grid[r + 1:]:
            if all((below[c] if c < len(below) else None) in (None, "")
                   for c in range(start, start + width)):
                continue  # blank row inside/after the table — skip, don't reset
            if _row_fills_span(below, start, width):
                n_data += 1
            else:
                break  # structure broke; stop counting this header's table
        if n_data >= MIN_DATA_ROWS:
            return TableHit(r, start, width, n_data)
    return None


def iter_grids(path: str):
    """Yield (sheet_name, grid) for each worksheet in the workbook.

    Uses openpyxl for .xlsx/.xlsm and xlrd for legacy .xls. Unreadable
    workbooks yield nothing (the caller treats that as 'no table').
    """
    lower = path.lower()
    try:
        if lower.endswith((".xlsx", ".xlsm")):
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                for ws in wb.worksheets:
                    grid = [list(row) for row in ws.iter_rows(values_only=True)]
                    yield ws.title, grid
            finally:
                wb.close()
        elif lower.endswith(".xls"):
            import xlrd
            book = xlrd.open_workbook(path)
            for sh in book.sheets():
                grid = [sh.row_values(r) for r in range(sh.nrows)]
                yield sh.name, grid
    except Exception:
        return  # unreadable / corrupt — no grids


def file_has_table(path: str):
    """Return (sheet_name, TableHit) for the first worksheet that holds a
    real table, or None. Scans every worksheet — real tables frequently
    sit behind a Cover/Notes/Index tab."""
    for sheet_name, grid in iter_grids(path):
        hit = find_table(grid)
        if hit is not None:
            return sheet_name, hit
    return None
