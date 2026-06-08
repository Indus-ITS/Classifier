# Class-Precedence Guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ordered class-level guards to `normalize_doc_type` so DRAWING-titled docs classify as drawing, INDEX titles as sheet, and borderline (low-confidence) sheet-type titles prefer sheet over document.

**Architecture:** Title-only, no scorer retuning. Guards run in `classifier.core.classify.normalize_doc_type` in priority order: prose→document (existing), DRAWING→drawing, INDEX→sheet, high-confidence type fold (existing), then low-confidence sheet-bucket→sheet. Marker phrases live in a small config module mirroring `prose_guard.py`.

**Tech Stack:** Python 3.10+, pytest.

**Current `normalize_doc_type` (for reference):** at `src/classifier/core/classify.py:31-50`. It already imports `canonicalize_title`, `_phrase_matches`, `TYPE_TO_BUCKET`, `doc_type_for_bucket`, and has `_is_prose_document`. The existing-value alias block and the prose guard stay first.

---

## File Structure

- Create: `src/classifier/config/drawing_markers.py` — `DRAWING_TITLE_MARKERS`, `INDEX_MARKERS`.
- Modify: `src/classifier/core/classify.py` — add `_title_has`; insert drawing + index guards; add prefer-sheet branch.
- Test: `tests/core/test_class_precedence.py`.

---

## Task 1: Drawing-title and index guards

**Files:**
- Create: `src/classifier/config/drawing_markers.py`
- Modify: `src/classifier/core/classify.py`
- Test: `tests/core/test_class_precedence.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_class_precedence.py`:
```python
from classifier.core.classify import normalize_doc_type


def _cls(title):
    return normalize_doc_type("NULL", title)[0]


def test_standard_drawing_titles_are_drawing():
    assert _cls("STANDARD DRAWING REBAR ARRANGEMENT") == "drawing"
    assert _cls("STANDARD DRAWING ANCHOR BOLT DETAILS") == "drawing"


def test_drawing_wins_over_index_and_list():
    assert _cls("3D MODEL DESIGN AREA/MODEL INDEX DRAWING AREA-2") == "drawing"
    assert _cls("STANDARD DRAWING MEMBER LIST") == "drawing"


def test_sketch_title_is_drawing():
    assert _cls("PIPING TIE-IN SKETCHES (25 SHEETS)") == "drawing"


def test_index_titles_are_sheet():
    assert _cls("INSTRUMENT INDEX") == "sheet"
    assert _cls("INSTRUMENT INDEX - SAHIL CDS") == "sheet"
    assert _cls("ISO INDEX") == "sheet"
    assert _cls("ISOMETRIC INDEX") == "sheet"


def test_prose_guard_still_wins_over_new_rules():
    assert _cls("HAZARDOUS AREA CLASSIFICATION SCHEDULE") == "document"
    assert _cls("RELAY SETTING SCHEDULE SUBSTATION 4-SAHIL CDS") == "document"


def test_plain_isometrics_stay_drawing():
    assert _cls("PIPING ISOMETRICS FOR SAHIL CDS") == "drawing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/core/test_class_precedence.py -v`
Expected: FAIL — `STANDARD DRAWING …` returns `document`, `INSTRUMENT INDEX`/`ISO INDEX` return `document`.

- [ ] **Step 3: Create the markers module**

Create `src/classifier/config/drawing_markers.py`:
```python
"""Title markers for class-level precedence guards.

Matched as contiguous token subsequences against the canonicalized title
(same canonicalizer the scorer uses). Data only — the ordering/precedence
logic lives in classify.normalize_doc_type.
"""
from __future__ import annotations

# A title naming a DRAWING (or SKETCH) is a drawing, even when it also
# carries a LIST/INDEX/REGISTER word. Canonicalization depluralizes
# DRAWINGS->DRAWING and SKETCHES->SKETCH, so the singular forms suffice.
DRAWING_TITLE_MARKERS: tuple[tuple[str, ...], ...] = (
    ("DRAWING",),
    ("SKETCH",),
)

# An INDEX title is a tabular sheet (INSTRUMENT INDEX, ISO INDEX, ...).
INDEX_MARKERS: tuple[tuple[str, ...], ...] = (
    ("INDEX",),
)
```

- [ ] **Step 4: Add `_title_has` and wire the two guards**

In `src/classifier/core/classify.py`:

(a) Add the import after the `prose_guard` import (line 13):
```python
from classifier.config.drawing_markers import DRAWING_TITLE_MARKERS, INDEX_MARKERS
```

(b) Add a helper next to `_is_prose_document`:
```python
def _title_has(title: str, markers) -> bool:
    """True iff the canonicalized title contains any marker phrase."""
    tokens = canonicalize_title(title)
    return any(_phrase_matches(tokens, list(m)) for m in markers)
```

(c) In `normalize_doc_type`, insert the two guards immediately AFTER the
prose-guard line (`return "document", "prose_guard"`) and BEFORE
`pick = pick_type_with_overrides(title)`:
```python
    if _title_has(title, DRAWING_TITLE_MARKERS):
        return "drawing", "drawing_title"
    if _title_has(title, INDEX_MARKERS):
        return "sheet", "index"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/core/test_class_precedence.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Run full suite (guard against regressions)**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: all pass. (The existing `test_sketch_guard.py` asserts
`PIPING TIE-IN SKETCHES … -> drawing`, still satisfied by the new
drawing-title guard.)

- [ ] **Step 7: Commit**

```bash
git add src/classifier/config/drawing_markers.py src/classifier/core/classify.py tests/core/test_class_precedence.py
git commit -m "feat(classify): drawing-title and index class guards"
```

---

## Task 2: Prefer-sheet on borderline (low-confidence sheet types)

**Files:**
- Modify: `src/classifier/core/classify.py`
- Test: `tests/core/test_class_precedence.py`

When no high-confidence type is picked, but the top low-confidence type
folds to the `Sheets` bucket, return `sheet` instead of defaulting to
`document`.

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_class_precedence.py`:
```python
def test_line_list_prefers_sheet():
    # LST (3.50) vs DSL (2.79): margin < 1.0 => low confidence,
    # currently defaults to document; should prefer sheet.
    assert _cls("LINE LIST") == "sheet"


def test_low_confidence_sheet_type_prefers_sheet():
    # INSTRUMENT INDEX also reaches sheet via the index guard, but a bare
    # low-confidence LST/SCH/IDX title must lean sheet too.
    assert normalize_doc_type("NULL", "LINE LIST")[1] == "prefer_sheet"


def test_low_confidence_nonsheet_stays_document():
    # A title with no sheet-bucket score stays document.
    assert _cls("MISCELLANEOUS NOTE") == "document"


def test_genuine_documents_unchanged():
    assert _cls("CABLE SIZING CALCULATION") == "document"
    assert _cls("MATERIAL REQUISITION FOR CS & LTCS") == "document"
    assert _cls("SPECIFICATION FOR LV POWER, CONTROL") == "document"


def test_genuine_sheets_unchanged():
    assert _cls("VALVE LIST") == "sheet"
    assert _cls("MTO FOR PIPES AND FITTINGS") == "sheet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/core/test_class_precedence.py -v`
Expected: FAIL — `LINE LIST` currently returns `document` / `defaulted`.

- [ ] **Step 3: Make the change**

In `src/classifier/core/classify.py`, replace the tail of
`normalize_doc_type` (the `pick = ...` block through the final `return`)
with:
```python
    pick = pick_type_with_overrides(title)
    bucket = TYPE_TO_BUCKET.get(pick["type"])
    if pick["confidence"] == "high" and bucket is not None:
        reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
        return doc_type_for_bucket(bucket), reason_tag
    if bucket is not None and doc_type_for_bucket(bucket) == "sheet":
        return "sheet", "prefer_sheet"
    return "document", "defaulted"
```
(`pick["type"]` is `""` when nothing scored above `MIN_SCORE`, so
`TYPE_TO_BUCKET.get("")` is `None` and such titles fall through to the
`document` default. A low-confidence type that folds to `Sheets` is the
only case the new branch promotes.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/core/test_class_precedence.py -v`
Expected: PASS (all, incl. the Task-1 tests).

- [ ] **Step 5: Run full suite**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/classifier/core/classify.py tests/core/test_class_precedence.py
git commit -m "feat(classify): prefer sheet for low-confidence sheet-type titles"
```

---

## Task 3: End-to-end spot check via classify_record

**Files:**
- Test: `tests/core/test_class_precedence.py`

Confirm the fixes hold through the real entry point the sorter uses
(`classify_record(Record(title=...)).doc_type.value`), not just the
helper.

- [ ] **Step 1: Write the test**

Append to `tests/core/test_class_precedence.py`:
```python
from classifier.core.classify import classify_record
from classifier.core.record import Record


def _rec_cls(title):
    return classify_record(Record(title=title)).doc_type.value


def test_classify_record_end_to_end():
    assert _rec_cls("STANDARD DRAWING REBAR ARRANGEMENT") == "drawing"
    assert _rec_cls("INSTRUMENT INDEX") == "sheet"
    assert _rec_cls("LINE LIST") == "sheet"
    assert _rec_cls("PIPING & INSTRUMENT DIAGRAM") == "drawing"
    assert _rec_cls("CABLE SIZING CALCULATION") == "document"
    assert _rec_cls("VALVE LIST") == "sheet"
    assert _rec_cls("HAZARDOUS AREA CLASSIFICATION SCHEDULE") == "document"
```

- [ ] **Step 2: Run the test**

Run: `.venv\Scripts\python -m pytest tests/core/test_class_precedence.py::test_classify_record_end_to_end -v`
Expected: PASS. If `PIPING & INSTRUMENT DIAGRAM` is not `drawing`, STOP and
report — that would mean the high-confidence drawing fold regressed (it
should still classify via the type scorer, unaffected by the new guards).

- [ ] **Step 3: Full suite + commit**

Run: `.venv\Scripts\python -m pytest tests/ -q` (all green).
```bash
git add tests/core/test_class_precedence.py
git commit -m "test(classify): end-to-end class-precedence checks via classify_record"
```

---

## Self-Review

- **Spec coverage:** drawing-title rule (Task 1 ✓), index rule (Task 1 ✓),
  prose-guard precedence retained (Task 1 test ✓), high-confidence fold
  retained (Task 2 code ✓), prefer-sheet borderline (Task 2 ✓), edge cases
  STANDARD DRAWING MEMBER LIST / MODEL INDEX DRAWING / PIPING ISOMETRICS
  (Task 1 ✓), end-to-end via classify_record (Task 3 ✓).
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type/name consistency:** `_title_has`, `DRAWING_TITLE_MARKERS`,
  `INDEX_MARKERS` defined in Task 1 and used as written; reason tags
  `drawing_title` / `index` / `prefer_sheet` are new and only asserted in
  these tests; `doc_type_for_bucket`/`TYPE_TO_BUCKET` already imported in
  classify.py. Ordering (prose → drawing → index → high-fold → prefer-sheet)
  matches the spec.
