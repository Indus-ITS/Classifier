# Sheets — Cleanup + Phase 1 Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the repo of throwaway scripts, then build a learning tool that opens the real `TO CLIENT` spreadsheets, detects which ones are genuine tables, joins them to their CSV titles/types, and emits an evidence report — so we can later decide which title patterns become the `Sheets` class.

**Architecture:** A pure, unit-tested table detector (`core/table_detect.py`) that decides "is this grid a real table?" with zero file I/O, plus a thin CLI tool (`tools/learn_sheet_patterns.py`) that walks the directory, opens workbooks, joins to `output/classified.csv` on `customer_ref`, and writes `output/sheet_learning.csv` + a printed aggregation. The runtime classifier is untouched — this is evidence-gathering only.

**Tech Stack:** Python 3.10+, openpyxl (xlsx/xlsm), xlrd (legacy xls), stdlib csv, pytest.

**Scope note:** Phase 2 (adding the `Sheets` class to the bucket→class fold) is deliberately NOT in this plan. Its exact membership depends on the numbers this learning pass produces. A second plan gets written after we review the evidence together.

---

## File Structure

- Create: `src/classifier/core/table_detect.py` — pure detection logic. Public: `find_table(grid)` returns `TableHit | None`; `MIN_HEADER_COLS`, `MIN_DATA_ROWS` constants.
- Create: `src/classifier/tools/learn_sheet_patterns.py` — CLI: walk dir, open files, join CSV, detect, emit report.
- Create: `tests/__init__.py`, `tests/core/__init__.py`, `tests/core/test_table_detect.py` — unit tests for the pure detector.
- Modify: `pyproject.toml` — add `learn-sheet-patterns` console-script entry.
- Delete: 13 untracked throwaway root scripts (Task 1).

---

## Task 1: Repo cleanup — delete throwaway scripts

**Files:**
- Delete: `analyze2.py`, `audit_missing.py`, `audit_wholetree.py`, `build_chunking_input.py`, `check_example.py`, `copy_docs.py`, `copy_notincsv.py`, `fuzzy_find.py`, `move_to_dsahil.py`, `probe.py`, `reconcile.py`, `reconcile_full.py`, `scripts/_gen_validation_report.py`

- [ ] **Step 1: Confirm none are imported by tracked source**

Run: `git grep -nE "import (analyze2|audit_missing|audit_wholetree|build_chunking_input|check_example|copy_docs|copy_notincsv|fuzzy_find|move_to_dsahil|probe|reconcile|reconcile_full)" -- src scripts`
Expected: no output (nothing imports them).

- [ ] **Step 2: Delete the files**

Run (PowerShell):
```powershell
Remove-Item analyze2.py,audit_missing.py,audit_wholetree.py,build_chunking_input.py,check_example.py,copy_docs.py,copy_notincsv.py,fuzzy_find.py,move_to_dsahil.py,probe.py,reconcile.py,reconcile_full.py,scripts\_gen_validation_report.py
```

- [ ] **Step 3: Verify working tree is clean of them**

Run: `git status --short`
Expected: none of the 13 files appear as `??` anymore. Only `src/classifier/config/type_overrides.py` and `src/classifier/core/type_scoring.py` remain as ` M` (pre-existing, untouched by us).

- [ ] **Step 4: Commit**

These files are untracked, so there is nothing to commit for the deletion itself. Skip the commit; the cleanup is complete once `git status` is clean of the 13 files.

---

## Task 2: Pure table detector — header detection

**Files:**
- Create: `src/classifier/core/table_detect.py`
- Test: `tests/core/test_table_detect.py`

The detector works on a `grid`: a `list[list]` of cell values (None for empty). A "header row" is a row with `>= MIN_HEADER_COLS` adjacent non-empty *text* cells. We test header-row finding first.

- [ ] **Step 1: Create test package files**

Create `tests/__init__.py` (empty), `tests/core/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `tests/core/test_table_detect.py`:
```python
from classifier.core.table_detect import _header_span, MIN_HEADER_COLS


def test_header_span_finds_three_adjacent_text_cells():
    row = [None, "Sr No", "Area", "Line Number", None]
    start, width = _header_span(row)
    assert (start, width) == (1, 3)


def test_header_span_rejects_too_few_columns():
    row = [None, "Title", None, None]
    assert _header_span(row) is None


def test_header_span_ignores_pure_numbers_as_header():
    # a row of numbers is data, not a header
    row = [1, 2, 3, 4]
    assert _header_span(row) is None


def test_min_header_cols_is_three():
    assert MIN_HEADER_COLS == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/core/test_table_detect.py -v`
Expected: FAIL — `ModuleNotFoundError` / `cannot import name '_header_span'`.

- [ ] **Step 4: Write minimal implementation**

Create `src/classifier/core/table_detect.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/core/test_table_detect.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/classifier/core/table_detect.py tests/__init__.py tests/core/__init__.py tests/core/test_table_detect.py
git commit -m "feat(table-detect): header-row span detection"
```

---

## Task 3: Pure table detector — full find_table

**Files:**
- Modify: `src/classifier/core/table_detect.py`
- Test: `tests/core/test_table_detect.py`

`find_table(grid)` scans for a header row, then counts data rows beneath it where the majority of the header columns stay populated. Returns a `TableHit` (header row index, span, data-row count) or `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/test_table_detect.py`:
```python
from classifier.core.table_detect import find_table, MIN_DATA_ROWS


def _mto_grid():
    header = [None, "Sr No", "Tag", "Description", "Qty"]
    rows = [[None, i, f"T-{i}", "VALVE", i * 2] for i in range(1, 9)]
    return [[None] * 5, header, *rows]


def test_find_table_accepts_real_table():
    hit = find_table(_mto_grid())
    assert hit is not None
    assert hit.n_data_rows >= MIN_DATA_ROWS
    assert hit.header_row == 1


def test_find_table_rejects_label_value_form():
    # CRS-style: each "data" row only fills 1-2 scattered cells
    grid = [
        ["DESCON TRANSMITTAL", "ADCO PDR", "DATE", "REVIEW CODE"],
        ["CTA-ED-SA-1576", None, None, None],
        ["REVIEWED BY", None, None, None],
        ["NAME", "Ahmed", None, None],
        ["POSITION", "CE", None, None],
    ]
    assert find_table(grid) is None


def test_find_table_rejects_short_table():
    header = ["A", "B", "C"]
    grid = [header, [1, 2, 3], [4, 5, 6]]  # only 2 data rows < MIN_DATA_ROWS
    assert find_table(grid) is None


def test_find_table_scans_past_leading_blank_rows():
    grid = [[None, None, None, None]] * 4 + _mto_grid()
    assert find_table(grid) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/core/test_table_detect.py -v`
Expected: FAIL — `cannot import name 'find_table'`.

- [ ] **Step 3: Write the implementation**

Append to `src/classifier/core/table_detect.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/core/test_table_detect.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/core/table_detect.py tests/core/test_table_detect.py
git commit -m "feat(table-detect): find_table with data-row consistency check"
```

---

## Task 4: Workbook reader — grids from a spreadsheet file

**Files:**
- Modify: `src/classifier/core/table_detect.py`
- Test: `tests/core/test_table_detect.py`

`iter_grids(path)` yields `(sheet_name, grid)` for each worksheet, using openpyxl for `.xlsx/.xlsm` and xlrd for `.xls`. `file_has_table(path)` runs `find_table` over every sheet and returns the first `TableHit` with its sheet name, or `None`. We test against a workbook written to a temp file.

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_table_detect.py`:
```python
import openpyxl
from classifier.core.table_detect import file_has_table


def test_file_has_table_finds_table_behind_cover_sheet(tmp_path):
    wb = openpyxl.Workbook()
    cover = wb.active
    cover.title = "Cover"
    cover["B2"] = "PROJECT TITLE"           # non-tabular cover
    idx = wb.create_sheet("Index")
    idx.append(["Sr No", "Area", "Line Number", "ISO Dwg"])
    for i in range(1, 9):
        idx.append([i, f"01{i:03d}P", f'3"-D-{i}', f"16-01-15-{i}"])
    p = tmp_path / "iso_index.xlsx"
    wb.save(p)

    hit = file_has_table(str(p))
    assert hit is not None
    assert hit[0] == "Index"          # sheet name
    assert hit[1].n_data_rows >= 5


def test_file_has_table_returns_none_for_form(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CRS"
    ws["B1"] = "ADCO PROJECT"
    ws["B2"] = "RESPONSE SHEET"
    ws["A4"] = "NAME"; ws["B4"] = "Ahmed"
    ws["A5"] = "POSITION"; ws["B5"] = "CE"
    p = tmp_path / "crs.xlsx"
    wb.save(p)

    assert file_has_table(str(p)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/core/test_table_detect.py -v`
Expected: FAIL — `cannot import name 'file_has_table'`.

- [ ] **Step 3: Write the implementation**

Append to `src/classifier/core/table_detect.py` (add `import warnings` and `from typing import Iterator` to the top imports):
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/core/test_table_detect.py -v`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/core/table_detect.py tests/core/test_table_detect.py
git commit -m "feat(table-detect): read workbook grids, scan all worksheets"
```

---

## Task 5: Learning tool — walk dir, join CSV, label files

**Files:**
- Create: `src/classifier/tools/learn_sheet_patterns.py`
- Modify: `pyproject.toml`

This is the Phase-1 driver. It has no unit test (it's an I/O script over an external directory); we verify it by running it and eyeballing the report. It must accept the directory and CSV as arguments with sensible defaults.

- [ ] **Step 1: Write the tool**

Create `src/classifier/tools/learn_sheet_patterns.py`:
```python
"""Phase-1 learning tool for the Sheets class.

Walks a deliverables directory, finds spreadsheets, joins each to its
title/type in classified.csv via the 16-01-xx-xxxx doc-number embedded
in the filename, opens the file to detect a real table, and writes an
evidence report. Produces NO change to classification behavior.

Usage:
    learn-sheet-patterns --dir "<TO CLIENT path>" \
        --csv output/classified.csv --out output/sheet_learning.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter, defaultdict

from classifier.core.table_detect import file_has_table

csv.field_size_limit(10 ** 7)

DOCNUM_RE = re.compile(r"(\d{2}-\d{2}-\d{2}-\d{4})")
SPREADSHEET_EXTS = (".xlsx", ".xlsm", ".xls")

DEFAULT_DIR = (
    r"D:\Indus\DEST Pilot DATA\KR\HISTORIC Projects\SAHIL (Clean)"
    r"\5. Deliverables + Correspondence - Execution\Transmittals\TO CLIENT"
)


def load_titles(csv_path: str) -> dict[str, dict]:
    """Map customer_ref -> {title, type, discipline_id} from the CSV."""
    out: dict[str, dict] = {}
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ref = (row.get("customer_ref") or "").strip()
            if ref and ref != "NULL":
                out[ref] = {
                    "title": row.get("title", ""),
                    "type": row.get("type", ""),
                    "discipline_id": row.get("discipline_id", ""),
                }
    return out


def find_spreadsheets(root: str):
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(SPREADSHEET_EXTS):
                yield os.path.join(dirpath, f)


def run(directory: str, csv_path: str, out_path: str) -> None:
    titles = load_titles(csv_path)
    rows = []
    for path in find_spreadsheets(directory):
        fname = os.path.basename(path)
        m = DOCNUM_RE.search(fname)
        docnum = m.group(1) if m else ""
        meta = titles.get(docnum, {})
        hit = file_has_table(path)
        rows.append({
            "docnum": docnum,
            "file": fname,
            "title": meta.get("title", ""),
            "type": meta.get("type", ""),
            "discipline_id": meta.get("discipline_id", ""),
            "has_table": "1" if hit else "0",
            "table_sheet": hit[0] if hit else "",
            "n_data_rows": hit[1].n_data_rows if hit else 0,
        })

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    _print_report(rows)


def _print_report(rows: list[dict]) -> None:
    total = len(rows)
    joined = [r for r in rows if r["type"]]
    tables = [r for r in rows if r["has_table"] == "1"]
    print(f"\nspreadsheets scanned : {total}")
    print(f"joined to a CSV title: {len(joined)}")
    print(f"detected as tables   : {len(tables)}")

    by_type_total: Counter = Counter(r["type"] for r in joined)
    by_type_table: Counter = Counter(r["type"] for r in joined if r["has_table"] == "1")
    print("\nper-type table fraction (joined files only):")
    print(f"  {'type':6} {'tables':>7} {'total':>7} {'frac':>6}")
    for t, n in by_type_total.most_common():
        tab = by_type_table.get(t, 0)
        print(f"  {t or '(blank)':6} {tab:7d} {n:7d} {tab / n:6.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Learn which titles are table-sheets.")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--csv", default="output/classified.csv")
    ap.add_argument("--out", default="output/sheet_learning.csv")
    args = ap.parse_args()
    run(args.dir, args.csv, args.out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Register the console script**

In `pyproject.toml`, under `[project.scripts]`, add this line after `learn-type-discipline`:
```toml
learn-sheet-patterns      = "classifier.tools.learn_sheet_patterns:main"
```

- [ ] **Step 3: Reinstall the console script entry**

Run: `.venv\Scripts\python -m pip install -e . --quiet`
Expected: completes with no error (registers the new entry point).

- [ ] **Step 4: Smoke-test import**

Run: `.venv\Scripts\python -c "from classifier.tools.learn_sheet_patterns import run, load_titles; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/tools/learn_sheet_patterns.py pyproject.toml
git commit -m "feat(tools): Phase-1 learn-sheet-patterns evidence tool"
```

---

## Task 6: Run the learning pass and capture evidence

**Files:**
- Produces: `output/sheet_learning.csv` (generated; do not hand-edit)

- [ ] **Step 1: Run the tool against the real directory**

Run:
```
.venv\Scripts\python -m classifier.tools.learn_sheet_patterns --out output/sheet_learning.csv
```
Expected: prints the scan/joined/tables counts and the per-type table-fraction table. `output/sheet_learning.csv` is written.

- [ ] **Step 2: Sanity-check known cases**

Run: `.venv\Scripts\python -m pytest tests/ -q` (all detector tests still pass), then open `output/sheet_learning.csv` and confirm:
  - rows whose `file` contains `MTO`, `ISO INDEX`, or `LINE LIST` mostly have `has_table=1`;
  - rows whose `file` contains `CRS` or `Comment Response Sheet` have `has_table=0`.

If known MTOs read as `0` or CRS forms read as `1`, adjust `MIN_DATA_ROWS` / `MIN_HEADER_COLS` in `core/table_detect.py`, re-run the detector tests, and re-run this pass. Record the final thresholds.

- [ ] **Step 3: Commit the evidence**

```bash
git add output/sheet_learning.csv
git commit -m "data: Phase-1 sheet-learning evidence report"
```

- [ ] **Step 4: STOP — decision gate**

Do not start Phase 2. Bring the per-type fractions to the user and decide together:
  1. promotion rule (whole-bucket re-route vs. per-type ≥90% threshold);
  2. final table-strictness thresholds.
Then a separate plan implements the `Sheets` class.

---

## Self-Review

- **Spec coverage:** Cleanup (Task 1 ✓), Phase-1 tool with dir→CSV join (Task 5 ✓), table detector scanning all worksheets (Tasks 2–4 ✓), evidence report + aggregation (Task 5 `_print_report`, Task 6 ✓), decision gate (Task 6 Step 4 ✓). Phase 2 intentionally deferred per spec's gate.
- **Placeholder scan:** none — every code step shows full code.
- **Type consistency:** `find_table`→`TableHit`; `file_has_table` returns `(sheet_name, TableHit)`; tests and tool both index `hit[1].n_data_rows`. `MIN_HEADER_COLS`/`MIN_DATA_ROWS` named identically across detector, tests, and tuning step. Docnum regex `\d{2}-\d{2}-\d{2}-\d{4}` matches the `16-01-xx-xxxx` format confirmed in the data.
