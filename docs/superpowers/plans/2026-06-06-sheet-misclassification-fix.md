# Sheet Mis-classification Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop prose documents (titled LIST/SCHEDULE/REGISTER) from being sorted as sheets and stop CRS/CTA artifacts from being bucketed — keeping runtime classification title-only, and adding an offline content-based verifier to prove the title rules are right.

**Architecture:** A pure, unit-tested text-ratio metric (`core/text_ratio.py`) decides "prose vs grid" from extracted text. An offline tool (`tools/verify_sheets.py`) reads real files, computes the ratio, and reports where the title-derived class disagrees with content — calibration only, no runtime effect. The runtime fix is title-rule edits (move `REG` out of Sheets, add prose-pattern negatives) plus dropping `CRS` from the taxonomy and skipping `CRS`/`CTA` files in the sorter.

**Tech Stack:** Python 3.10+, pdfplumber (PDF text), openpyxl/xlrd (spreadsheets), pytest.

**Pre-conditions:**
- Live data is `output/documents_updated.csv` (has `title`, `doc_type`, `customer_ref`, `document_no`, `file_name`). The sorted file tree is under `D:/Sahil_input/`.
- `pdfplumber` is installed in the venv; add it to `pyproject.toml` dependencies.
- Runtime classification path: `classifier.core.classify.classify_record(Record(title=...)).doc_type.value` → uses `pick_type_with_overrides` (type_scoring.py) → `TYPE_TO_BUCKET` → `doc_type_for_bucket` (folding.py) → `BUCKET_TO_CLASS` (buckets.py).

---

## File Structure

- Create: `src/classifier/core/text_ratio.py` — pure prose-vs-grid metric. Public: `is_prose_line(line)`, `text_ratio(lines)`, constant `MIN_PROSE_WORDS`.
- Create: `src/classifier/tools/verify_sheets.py` — offline IO tool: read files, compute ratio, match CSV, emit mismatch report. Public: `file_text_ratio(path)`, `run(...)`, `main()`, constant `THRESHOLD`.
- Modify: `src/classifier/config/buckets.py` — drop `CRS`; move `REG` to a Documents bucket.
- Modify: `src/classifier/config/type_overrides.py` — negative keywords for prose patterns.
- Modify: `src/classifier/routing/source_plan.py` — skip `CRS`/`CTA` files in `build_plan`.
- Modify: `pyproject.toml` — add `pdfplumber` dep + `verify-sheets` console script.
- Tests under `tests/core/`, `tests/tools/`, `tests/routing/`, `tests/config/`.

---

## Task 1: Pure text-ratio metric

**Files:**
- Create: `src/classifier/core/text_ratio.py`
- Test: `tests/core/test_text_ratio.py`

A `line` is "prose" when it reads like a sentence rather than a table row. `text_ratio(lines)` = fraction of non-whitespace characters that live in prose lines. Spreadsheets (short cell tokens) score ~0; paragraphs score ~1.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_text_ratio.py`:
```python
from classifier.core.text_ratio import is_prose_line, text_ratio, MIN_PROSE_WORDS


def test_min_prose_words_default():
    assert MIN_PROSE_WORDS == 6


def test_sentence_is_prose():
    assert is_prose_line(
        "South East Group of Fields of Abu Dhabi Company consists of Sahil and Asab")


def test_table_row_is_not_prose():
    assert not is_prose_line("1 01001P 3\"-D-2501 16-01-15 01 / 03")


def test_short_label_is_not_prose():
    assert not is_prose_line("VALVE LIST")


def test_numeric_row_is_not_prose():
    assert not is_prose_line("1 2 3 4 5 6 7 8")


def test_text_ratio_high_for_paragraphs():
    lines = [
        "This document describes the hazardous area classification for the plant.",
        "The introduction sets out the scope and purpose of the study in detail.",
        "Each area is assessed against the relevant standards and guidelines here.",
    ]
    assert text_ratio(lines) > 0.8


def test_text_ratio_low_for_grid():
    lines = ["ITEM DESC QTY", "1 PUMP 4", "2 VALVE 8", "3 PIPE 12", "4 FLANGE 6"]
    assert text_ratio(lines) < 0.2


def test_text_ratio_empty_is_zero():
    assert text_ratio([]) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/core/test_text_ratio.py -v`
Expected: FAIL — module/function not found.

- [ ] **Step 3: Write the implementation**

Create `src/classifier/core/text_ratio.py`:
```python
"""Pure prose-vs-grid text metric.

A genuine sheet is a grid of short cell tokens; a document carries
narrative paragraphs. text_ratio(lines) returns the fraction of
non-whitespace characters that live in "prose" lines — high for
documents, near zero for spreadsheets. No file I/O lives here.
"""
from __future__ import annotations

import re
from typing import Sequence

MIN_PROSE_WORDS: int = 6   # tunable: words needed before a line counts as prose

_WORD = re.compile(r"\S+")
_ALPHA = re.compile(r"[A-Za-z]")


def _is_wordy(token: str) -> bool:
    """A token that looks like a real word: >= 2 letters, not a pure code/number."""
    letters = len(_ALPHA.findall(token))
    return letters >= 2 and letters >= len(token) / 2


def is_prose_line(line: str) -> bool:
    """True iff the line reads like a sentence: enough wordy tokens, mostly words."""
    tokens = _WORD.findall(line)
    if len(tokens) < MIN_PROSE_WORDS:
        return False
    wordy = sum(1 for t in tokens if _is_wordy(t))
    return wordy >= len(tokens) / 2


def _nonws_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def text_ratio(lines: Sequence[str]) -> float:
    """Fraction of non-whitespace characters that belong to prose lines.

    Returns 0.0 when there is no non-whitespace content.
    """
    total = prose = 0
    for ln in lines:
        n = _nonws_len(ln)
        total += n
        if is_prose_line(ln):
            prose += n
    return (prose / total) if total else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/core/test_text_ratio.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/core/text_ratio.py tests/core/test_text_ratio.py
git commit -m "feat(text-ratio): pure prose-vs-grid text metric"
```

---

## Task 2: Verifier tool — read files, report title-vs-content mismatches

**Files:**
- Create: `src/classifier/tools/verify_sheets.py`
- Modify: `pyproject.toml`
- Test: `tests/tools/test_verify_sheets.py`

The tool reads each file's text into lines, computes `text_ratio`, derives `content_class`, compares to the title-derived `title_class`, and writes a mismatch report. `file_text_ratio(path)` is the testable IO seam (synthetic xlsx in a temp dir).

- [ ] **Step 1: Create test package file**

Create `tests/tools/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `tests/tools/test_verify_sheets.py`:
```python
import openpyxl
from classifier.tools.verify_sheets import file_text_ratio, content_class


def test_xlsx_grid_has_low_ratio(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ITEM", "DESC", "QTY"])
    for i in range(1, 8):
        ws.append([i, "VALVE", i * 2])
    p = tmp_path / "grid.xlsx"
    wb.save(p)
    assert file_text_ratio(str(p)) < 0.2


def test_content_class_threshold():
    # threshold is a parameter; document when ratio >= threshold
    assert content_class(0.9, 0.4) == "document"
    assert content_class(0.05, 0.4) == "sheet"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/tools/test_verify_sheets.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Write the tool**

Create `src/classifier/tools/verify_sheets.py`:
```python
"""Offline verifier: does the title-derived class agree with file content?

For each documents-CSV row, locate its file(s), compute the prose
text-ratio, derive a content class, and report rows where the
title-derived class says "sheet" but the content says "document" (and
the inverse). VERIFICATION ONLY — changes no classification and moves no
files. The threshold is a tunable parameter, calibrated against known
files; it is not a hardcoded business rule.

Usage:
    verify-sheets --csv output/documents_updated.csv \
        --root "D:/Sahil_input" --threshold 0.4 --out output/sheet_verify.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter

from classifier.core.record import Record
from classifier.core.classify import classify_record
from classifier.core.text_ratio import text_ratio

csv.field_size_limit(10 ** 7)

DOCNUM_RE = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")
DEFAULT_THRESHOLD: float = 0.4


def _pdf_lines(path: str) -> list[str]:
    import pdfplumber
    out: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            out.extend(txt.splitlines())
    return out


def _xlsx_lines(path: str) -> list[str]:
    lower = path.lower()
    out: list[str] = []
    if lower.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                out.append(" ".join("" if c is None else str(c) for c in row))
        wb.close()
    elif lower.endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(path)
        for sh in book.sheets():
            for r in range(sh.nrows):
                out.append(" ".join(str(c) for c in sh.row_values(r)))
    return out


def file_text_ratio(path: str) -> float | None:
    """Prose text-ratio of a file, or None if it can't be read."""
    lower = path.lower()
    try:
        if lower.endswith(".pdf"):
            lines = _pdf_lines(path)
        elif lower.endswith((".xlsx", ".xlsm", ".xls")):
            lines = _xlsx_lines(path)
        else:
            return None
    except Exception:
        return None
    return text_ratio(lines)


def content_class(ratio: float, threshold: float) -> str:
    return "document" if ratio >= threshold else "sheet"


def _index_files(root: str) -> dict[str, list[str]]:
    """Map each embedded doc-number -> list of file paths under root."""
    idx: dict[str, list[str]] = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            m = DOCNUM_RE.search(f)
            if m:
                idx.setdefault(m.group(0), []).append(os.path.join(dirpath, f))
    return idx


def run(csv_path: str, root: str, threshold: float, out_path: str) -> None:
    file_idx = _index_files(root)
    rows_out = []
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ref = (row.get("customer_ref") or "").strip()
            title = row.get("title", "")
            title_class = classify_record(Record(title=title)).doc_type.value
            for path in file_idx.get(ref, []):
                fname = os.path.basename(path)
                if re.match(r"\s*(crs|cta)", fname, re.I):
                    continue  # CRS/CTA never count
                ratio = file_text_ratio(path)
                if ratio is None:
                    cclass = "unknown"
                else:
                    cclass = content_class(ratio, threshold)
                rows_out.append({
                    "docnum": ref, "title": title, "file": fname,
                    "title_class": title_class,
                    "text_ratio": "" if ratio is None else f"{ratio:.3f}",
                    "content_class": cclass,
                    "mismatch": "1" if (title_class == "sheet"
                                        and cclass == "document") else "",
                })

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    _report(rows_out, threshold)


def _report(rows: list[dict], threshold: float) -> None:
    mism = [r for r in rows if r["mismatch"]]
    inv = [r for r in rows if r["title_class"] == "document"
           and r["content_class"] == "sheet"]
    print(f"\nthreshold              : {threshold}")
    print(f"files checked          : {len(rows)}")
    print(f"sheet->document misses : {len(mism)}")
    print(f"document->sheet misses : {len(inv)}")
    print("\nsheet->document mismatches (title says sheet, content says document):")
    for r in mism:
        print(f"  ratio={r['text_ratio']:>6}  {r['title'][:45]:45}  {r['file'][:30]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify sheet class vs file content.")
    ap.add_argument("--csv", default="output/documents_updated.csv")
    ap.add_argument("--root", default=r"D:/Sahil_input")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--out", default="output/sheet_verify.csv")
    args = ap.parse_args()
    run(args.csv, args.root, args.threshold, args.out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Register dependency + console script**

In `pyproject.toml`, add `"pdfplumber>=0.11"` to the `dependencies` list, and under `[project.scripts]` add:
```toml
verify-sheets       = "classifier.tools.verify_sheets:main"
```

- [ ] **Step 6: Install + run tests**

Run: `.venv\Scripts\python -m pip install -e . --quiet`
Then: `.venv\Scripts\python -m pytest tests/tools/test_verify_sheets.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add src/classifier/tools/verify_sheets.py tests/tools/__init__.py tests/tools/test_verify_sheets.py pyproject.toml
git commit -m "feat(tools): offline verify-sheets content-vs-title checker"
```

---

## Task 3: Calibrate the threshold (coordination, no code)

**Files:** produces `output/sheet_verify.csv` (generated)

- [ ] **Step 1: Run the verifier at a low threshold to see ratios**

Run:
```
.venv\Scripts\python -m classifier.tools.verify_sheets --threshold 0.0 --out output/sheet_verify.csv
```
This labels everything (threshold 0 ⇒ all "document"); the value we want is the per-file `text_ratio` column.

- [ ] **Step 2: Inspect the anchor set**

Open `output/sheet_verify.csv`. Confirm the known prose documents score HIGH and the known sheets score LOW:
```
.venv\Scripts\python -c "import csv; rows=list(csv.DictReader(open('output/sheet_verify.csv',encoding='utf-8'))); anchors_doc=['HAZARD & EFFECT REGISTER','SPECIALITY ITEMS LIST','RELAY SETTING SCHEDULE','LIST OF ENGINEERING DELIVERABLES','HAZARDOUS AREA CLASSIFICATION SCHEDULE']; anchors_sheet=['VALVE LIST','MTO FOR PIPES AND FITTINGS','INSTRUMENT CABLE SCHEDULE','TIE-IN LIST']; print('DOCS:'); [print(' ',r['text_ratio'],r['title'][:40]) for r in rows if any(a in r['title'] for a in anchors_doc)]; print('SHEETS:'); [print(' ',r['text_ratio'],r['title'][:40]) for r in rows if any(a in r['title'] for a in anchors_sheet)]"
```
Pick `THRESHOLD` in the gap between the highest sheet ratio and the lowest document ratio. Record the chosen value in the commit message of Task 6. If the groups overlap (no clean gap), STOP and report — the metric needs adjusting (e.g. raise `MIN_PROSE_WORDS`) before proceeding.

- [ ] **Step 3: Re-run at the chosen threshold to capture the mismatch baseline**

Run (substitute the calibrated value, e.g. 0.25):
```
.venv\Scripts\python -m classifier.tools.verify_sheets --threshold 0.25 --out output/sheet_verify.csv
```
Note the printed `sheet->document mismatches` list — this is the work-list for Task 6.

---

## Task 4: Skip CRS/CTA files in the sorter

**Files:**
- Modify: `src/classifier/routing/source_plan.py`
- Test: `tests/routing/test_source_plan_crs.py`

`build_plan` must never let a `CRS`/`CTA`-named file enter a bucket. Filter at the start, before indexing candidates, and record skipped files on the `Plan`.

- [ ] **Step 1: Write the failing test**

Create `tests/routing/test_source_plan_crs.py`:
```python
from pathlib import Path
from classifier.routing.source_plan import build_plan, DocRow


def test_crs_file_is_skipped(tmp_path):
    # A row whose only on-disk file is a CRS artifact yields no copy action.
    f = tmp_path / "CRS_16-01-55-2601 REV-B.xlsx"
    f.write_text("x")
    rows = [DocRow(customer_ref="16-01-55-2601", document_no="",
                   doc_source="deliverable", title="ELECTRICAL LOAD LIST")]
    plan = build_plan(rows, [f])
    assert plan.actions == ()
    assert "CRS_16-01-55-2601 REV-B.xlsx" in plan.skipped_crs


def test_cta_file_is_skipped(tmp_path):
    f = tmp_path / "CTA-ED-SA-15760 16-01-19-2602.pdf"
    f.write_text("x")
    rows = [DocRow(customer_ref="16-01-19-2602", document_no="",
                   doc_source="deliverable", title="VALVE LIST")]
    plan = build_plan(rows, [f])
    assert plan.actions == ()
    assert any(p.startswith("CTA") for p in plan.skipped_crs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/routing/test_source_plan_crs.py -v`
Expected: FAIL — `Plan` has no `skipped_crs`; CRS file currently becomes an action.

- [ ] **Step 3: Make the change**

In `src/classifier/routing/source_plan.py`:

(a) Add a module-level matcher after the existing `_CUST_REF` line:
```python
_CRS_CTA = re.compile(r"\s*(crs|cta)", re.I)
```

(b) Add `skipped_crs` to the `Plan` dataclass (after `skipped_no_preferred`):
```python
@dataclass(frozen=True)
class Plan:
    actions: tuple[CopyAction, ...]
    rows_without_file: tuple[str, ...]
    skipped_no_preferred: tuple[str, ...]
    skipped_crs: tuple[str, ...]
```

(c) At the very top of `build_plan`, partition out CRS/CTA files before anything else:
```python
def build_plan(rows: list[DocRow], files: list[Path]) -> Plan:
    skipped_crs = [Path(p).name for p in files if _CRS_CTA.match(Path(p).name)]
    files = [p for p in files if not _CRS_CTA.match(Path(p).name)]
    entries = [parse_entry(Path(p)) for p in files]
    ...
```

(d) At the two `return Plan(...)` sites (the early one if present and the final one), add the new field. The final return becomes:
```python
    return Plan(tuple(actions), tuple(rows_without_file),
                tuple(skipped), tuple(skipped_crs))
```
Search the file for every `Plan(` construction and add `tuple(skipped_crs)` (or `()` if that construction path has no CRS context) so all constructions match the new 4-field shape.

- [ ] **Step 4: Run the new test + the existing routing suite**

Run: `.venv\Scripts\python -m pytest tests/routing/ -v`
Expected: the two new tests PASS; pre-existing `test_source_plan.py` still passes (update any direct `Plan(...)` constructions in those tests to the 4-field shape if they fail — add `skipped_crs=()`).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/routing/source_plan.py tests/routing/test_source_plan_crs.py
git commit -m "feat(routing): skip CRS/CTA files; record them on the plan"
```

---

## Task 5: Drop CRS from taxonomy; move REG to Documents

**Files:**
- Modify: `src/classifier/config/buckets.py`
- Test: `tests/config/test_taxonomy_changes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/config/test_taxonomy_changes.py`:
```python
from classifier.config.buckets import (
    BUCKETS, BUCKET_TO_CLASS, TYPE_TO_BUCKET, BUCKET_PRIMARY_CODE,
)


def test_crs_removed_from_taxonomy():
    assert "CRS" not in BUCKETS
    assert "CRS" not in BUCKET_TO_CLASS
    assert "CRS" not in BUCKET_PRIMARY_CODE


def test_reg_folds_to_document():
    bucket = TYPE_TO_BUCKET["REG"]
    assert BUCKET_TO_CLASS[bucket] == "Documents"


def test_genuine_sheet_types_still_sheets():
    for code in ("LST", "MTO", "BOM", "IDX", "SCH"):
        assert BUCKET_TO_CLASS[TYPE_TO_BUCKET[code]] == "Sheets"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/config/test_taxonomy_changes.py -v`
Expected: FAIL — CRS still present; REG folds to Sheets.

- [ ] **Step 3: Make the change**

In `src/classifier/config/buckets.py`:
- Remove the `"CRS",` entry from the `BUCKETS` tuple.
- Remove the `"CRS":              "Documents",` line from `BUCKET_TO_CLASS`.
- Remove the `"CRS": "CRS",` line from `BUCKET_PRIMARY_CODE`.
- In `TYPE_TO_BUCKET`, change the `REG` mapping from `"REG": "Lists_MTOs_BOMs"` to `"REG": "Documents"` (leave `LST`/`MTO`/`BOM`/`IDX`/`SCH` on `Lists_MTOs_BOMs`).

- [ ] **Step 4: Run tests (new + any taxonomy-dependent suites)**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: new tests pass. If a pre-existing test asserts a fixed bucket count or lists CRS, update it to reflect CRS removal (CRS is intentionally gone).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/config/buckets.py tests/config/test_taxonomy_changes.py
git commit -m "feat(taxonomy): drop CRS bucket; fold REG to Documents"
```

---

## Task 6: Prose-document guard at the class-derivation layer

**Files:**
- Create: `src/classifier/config/prose_guard.py`
- Modify: `src/classifier/core/classify.py`
- Test: `tests/core/test_prose_doc_titles.py`

**Why a guard, not negative keywords:** `("SCHEDULE",)` is a HARD_OVERRIDE for
`SCH`, and overrides return *before* the negative-keyword prune runs. So
`RELAY SETTING SCHEDULE` / `HAZARDOUS AREA CLASSIFICATION SCHEDULE`
(`reason=override`) cannot be fixed by negatives. A guard at the
class-derivation layer (`normalize_doc_type`) short-circuits to `document`
for proven prose phrases regardless of type scoring or overrides. The LST
prose titles (`reason=scored`) are fixed by the same guard, uniformly.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_prose_doc_titles.py`:
```python
from classifier.core.classify import normalize_doc_type


def _cls(title):
    return normalize_doc_type("NULL", title)[0]


def test_known_prose_docs_classify_as_document():
    for title in [
        "HAZARD & EFFECT REGISTER",
        "HSE ACTION TRACKING REGISTER",
        "HAZARDOUS AREA CLASSIFICATION SCHEDULE",
        "LIST OF PIPING SPECIALTY ITEMS",
        "SPECIALITY ITEMS LIST",
        "RELAY SETTING SCHEDULE SUBSTATION 4-SAHIL CDS",
        "LIST OF ENGINEERING DELIVERABLES",
    ]:
        assert _cls(title) == "document", title


def test_genuine_sheets_stay_sheet():
    for title in [
        "VALVE LIST",
        "MTO FOR PIPES AND FITTINGS",
        "INSTRUMENT CABLE SCHEDULE",
        "TIE-IN LIST",
        "ELECTRICAL LOAD LIST - SAHIL CDS",
        "DCS I/O LIST",
    ]:
        assert _cls(title) == "sheet", title
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/core/test_prose_doc_titles.py -v`
Expected: FAIL — `HAZARDOUS AREA … SCHEDULE` / `RELAY SETTING SCHEDULE` still
classify as `sheet` (via the SCH override), and the LST prose titles too.

- [ ] **Step 3: Create the prose-guard module**

Create `src/classifier/config/prose_guard.py`:
```python
"""Titles that name a prose engineering document despite carrying a
sheet-ish keyword (LIST / SCHEDULE / REGISTER). Verified by reading the
actual files: each has a Table of Contents + Introduction narrative.

Matched as contiguous token subsequences against the canonicalized title
(same canonicalizer the scorer uses). Kept here as data so the list can
grow from verifier evidence without touching logic.
"""
from __future__ import annotations

PROSE_DOC_PHRASES: tuple[tuple[str, ...], ...] = (
    ("HAZARDOUS", "AREA"),                       # HAZARDOUS AREA CLASSIFICATION SCHEDULE
    ("RELAY", "SETTING"),                        # RELAY SETTING SCHEDULE
    ("SPECIALITY", "ITEMS"),                     # SPECIALITY ITEMS LIST
    ("SPECIALTY", "ITEMS"),                      # LIST OF PIPING SPECIALTY ITEMS
    ("LIST", "OF", "ENGINEERING", "DELIVERABLES"),
    ("HAZARD", "&", "EFFECT"),                   # HAZARD & EFFECT REGISTER ('&' is kept as a token)
    ("HSE",),                                    # HSE ACTION TRACKING REGISTER / HSE plans
)
```

- [ ] **Step 4: Wire the guard into class derivation**

In `src/classifier/core/classify.py`:

(a) Add imports near the top (alongside the existing imports):
```python
from classifier.config.prose_guard import PROSE_DOC_PHRASES
from classifier.core.type_scoring import canonicalize_title, _phrase_matches
```

(b) Add a helper above `normalize_doc_type`:
```python
def _is_prose_document(title: str) -> bool:
    """True iff the title matches a known prose-document phrase."""
    tokens = canonicalize_title(title)
    return any(_phrase_matches(tokens, list(p)) for p in PROSE_DOC_PHRASES)
```

(c) In `normalize_doc_type`, insert the guard immediately AFTER the
existing-value block and BEFORE `pick = pick_type_with_overrides(title)`:
```python
    if _is_prose_document(title):
        return "document", "prose_guard"
    pick = pick_type_with_overrides(title)
```

- [ ] **Step 5: Run the new test + full suite**

Run: `.venv\Scripts\python -m pytest tests/core/test_prose_doc_titles.py tests/ -q`
Expected: new tests PASS; nothing else regresses. (`HAZARD AND EFFECT` /
`HSE` are also covered here even though Task 5 moved REG → Documents — the
guard is a belt-and-suspenders for the class and is harmless.)

- [ ] **Step 6: Commit** (record the calibrated threshold from Task 3 here)

```bash
git add src/classifier/config/prose_guard.py src/classifier/core/classify.py tests/core/test_prose_doc_titles.py
git commit -m "fix(classify): prose-document guard routes HSE/HAZARDOUS/RELAY/LIST-OF titles to Documents

Runs before type overrides, so it catches SCHEDULE-override titles that
negative keywords cannot. Calibrated verifier threshold: <value from Task 3>."
```

---

## Task 7: Re-verify and confirm convergence

**Files:** regenerates `output/sheet_verify.csv`

- [ ] **Step 1: Re-run the verifier at the calibrated threshold**

Run (use the Task-3 value):
```
.venv\Scripts\python -m classifier.tools.verify_sheets --threshold 0.25 --out output/sheet_verify.csv
```

- [ ] **Step 2: Confirm the known mismatches are gone**

Confirm the printed `sheet->document mismatches` no longer lists the 7 known documents. Any remaining mismatch is either (a) a new prose pattern — add it to Task 6's negatives and re-run, or (b) a genuine borderline — note it in the report. Do not silently ignore remaining mismatches; print the final list.

- [ ] **Step 3: Full suite green**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: all pass.

---

## Self-Review

- **Spec coverage:** verifier metric (Task 1 ✓), verifier IO+report (Task 2 ✓), tunable+calibrated threshold (Task 3 ✓, no hardcode), CRS/CTA file skip (Task 4 ✓), CRS taxonomy drop + REG→Documents (Task 5 ✓), title-rule negatives data-driven (Task 6 ✓), re-verify convergence (Task 7 ✓). Runtime stays title-only (no file reads in classify path). Tests per spec's Testing section are present in Tasks 1, 4, 5, 6.
- **Placeholder scan:** the only deferred value is the calibrated threshold (intentionally chosen in Task 3 and recorded in Task 6) — every code block is complete.
- **Type/name consistency:** `text_ratio`/`is_prose_line`/`MIN_PROSE_WORDS` (Task 1) used verbatim in Task 2; `file_text_ratio`/`content_class`/`run`/`THRESHOLD`→`DEFAULT_THRESHOLD` defined and used consistently; `Plan.skipped_crs` (Task 4) matches its test; `normalize_doc_type` is the real symbol in `core/classify.py` (re-exported from `pipeline/_row.py`).
