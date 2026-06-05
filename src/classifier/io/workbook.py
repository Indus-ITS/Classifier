"""Workbook readers: turn .xls/.xlsx files into grids, and locate the first
sheet that holds a real table. The pure table-shape logic lives in
core.table_detect; this module owns the file I/O.
"""
from __future__ import annotations

from typing import Iterator

from classifier.core.table_detect import TableHit, find_table


def iter_grids(path: str) -> Iterator[tuple[str, list]]:
    """Yield (sheet_name, grid) per worksheet. openpyxl for .xlsx/.xlsm,
    xlrd for legacy .xls. Unreadable workbooks yield nothing."""
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
    except ImportError:
        raise
    except Exception:
        return


def file_has_table(path: str) -> tuple[str, TableHit] | None:
    """Return (sheet_name, TableHit) for the first worksheet holding a real
    table, or None. Scans every worksheet."""
    for sheet_name, grid in iter_grids(path):
        hit = find_table(grid)
        if hit is not None:
            return sheet_name, hit
    return None
