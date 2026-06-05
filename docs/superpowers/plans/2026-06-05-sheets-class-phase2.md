# Sheets Class — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `Sheets` as a third user-facing class (alongside `drawing`/`document`) by folding the `Lists_MTOs_BOMs` bucket to `Sheets`, route SKETCH titles to Drawings, update every consumer, and regenerate `output/classified.csv`.

**Architecture:** The runtime classifier stays title-based. The class is produced by `normalize_doc_type` in `pipeline/_row.py`, which re-derives a type from the **title** via `pick_type_with_overrides`, maps it through `TYPE_TO_BUCKET` → `BUCKET_TO_CLASS`, and returns a lowercase class string. We change one fold entry, make the class string three-way in the two places that hard-code it, add a SKETCH→DWG guard, and update display/enum consumers. Phase-1 evidence grounded the membership: `{LST, MTO, BOM, IDX, REG, SCH}` (the `Lists_MTOs_BOMs` bucket).

**Tech Stack:** Python 3.10+, pandas, pytest; one HTML/JS viewer.

**Important pre-conditions:**
- The branch carries pre-existing **WIP** in `src/classifier/config/type_overrides.py` and `src/classifier/core/type_scoring.py` (PLN overrides, INSTRUMENT negatives, a DRAWING/SKETCH→DWG Phase-5 fallback). Per the user, we **build on this WIP and commit it** as part of Phase 2 so the regenerated CSV is reproducible from committed code.
- `output/classified.csv` IS git-tracked (gitignore exception). Regenerating it is a committable change.
- The class is derived from the **title**, not the stored `type` column. Verification audits `doc_type=="sheet"` rows by title.

---

## File Structure

- Modify: `src/classifier/config/buckets.py` — fold `Lists_MTOs_BOMs` → `Sheets`.
- Modify: `src/classifier/pipeline/_row.py` — three-way class return + `sheet` aliases.
- Modify: `src/classifier/tools/convert_classified.py` — three-way class return + `sheet` aliases.
- Modify: `src/classifier/core/type_scoring.py` — depluralize `SKETCHES`→`SKETCH` so the existing Phase-5 fallback routes sketches to `DWG` (Drawings).
- Modify: `src/classifier/cli/classify.py` — docstring enum `{drawing, document, sheet}`.
- Modify: `viewer.html` — `DOC_TYPES` add `'sheet'`.
- Create: `tests/config/__init__.py`, `tests/config/test_buckets_fold.py`.
- Create: `tests/pipeline/__init__.py`, `tests/pipeline/test_row_class.py`.
- Create: `tests/core/test_sketch_guard.py`.
- Regenerate: `output/classified.csv` (via `classify` console script).

---

## Task 1: Fold Lists_MTOs_BOMs to the new Sheets class

**Files:**
- Modify: `src/classifier/config/buckets.py:31-42` (`BUCKET_TO_CLASS`)
- Create: `tests/config/__init__.py`, `tests/config/test_buckets_fold.py`
bucket = {LST, MTO, BOM, IDX, REG, SCH}. 
- [ ] **Step 1: Create test package file**

Create `tests/config/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `tests/config/test_buckets_fold.py`:
```python
from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET


def test_lists_mtos_boms_folds_to_sheets():
    assert BUCKET_TO_CLASS["Lists_MTOs_BOMs"] == "Sheets"


def test_sheet_types_reach_sheets_class():
    for code in ("LST", "MTO", "BOM", "IDX", "REG", "SCH"):
        bucket = TYPE_TO_BUCKET[code]
        assert BUCKET_TO_CLASS[bucket] == "Sheets", code


def test_drawings_and_documents_unchanged():
    assert BUCKET_TO_CLASS["Drawings"] == "Drawings"
    assert BUCKET_TO_CLASS["Isometrics"] == "Drawings"
    assert BUCKET_TO_CLASS["Datasheets"] == "Documents"
    assert BUCKET_TO_CLASS["Specifications"] == "Documents"


def test_three_distinct_classes_exist():
    assert set(BUCKET_TO_CLASS.values()) == {"Drawings", "Documents", "Sheets"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/config/test_buckets_fold.py -v`
Expected: FAIL — current value is `"Documents"`, not `"Sheets"`.

- [ ] **Step 4: Make the change**

In `src/classifier/config/buckets.py`, in the `BUCKET_TO_CLASS` dict, change the `Lists_MTOs_BOMs` line from:
```python
    "Lists_MTOs_BOMs":  "Documents",
```
to:
```python
    "Lists_MTOs_BOMs":  "Sheets",
```
Leave every other entry unchanged. (Datasheets, Specifications, Calculations, Reports, Procedures_Plans, CRS, Documents all stay `"Documents"`; Drawings/Isometrics stay `"Drawings"`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/config/test_buckets_fold.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/classifier/config/buckets.py tests/config/__init__.py tests/config/test_buckets_fold.py
git commit -m "feat(buckets): fold Lists_MTOs_BOMs to new Sheets class"
```

---

## Task 2: Three-way class in normalize_doc_type

**Files:**
- Modify: `src/classifier/pipeline/_row.py:17-36`
- Create: `tests/pipeline/__init__.py`, `tests/pipeline/test_row_class.py`

`normalize_doc_type` currently returns only `"drawing"`/`"document"`. Make it return `"sheet"` when the bucket folds to `Sheets`, and recognize an existing `sheet` value.

- [ ] **Step 1: Create test package file**

Create `tests/pipeline/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `tests/pipeline/test_row_class.py`:
```python
from classifier.pipeline._row import normalize_doc_type


def test_list_title_classifies_as_sheet():
    cls, reason = normalize_doc_type("NULL", "VALVE LIST")
    assert cls == "sheet"


def test_mto_title_classifies_as_sheet():
    cls, _ = normalize_doc_type("Documents/Drawings", "MTO FOR PIPES AND FITTINGS")
    assert cls == "sheet"


def test_pid_title_still_drawing():
    cls, _ = normalize_doc_type("NULL", "PIPING AND INSTRUMENT DIAGRAM")
    assert cls == "drawing"


def test_spec_title_still_document():
    cls, _ = normalize_doc_type("NULL", "SPECIFICATION FOR PIPING MATERIAL")
    assert cls == "document"


def test_existing_sheet_value_preserved():
    cls, reason = normalize_doc_type("sheet", "ANYTHING AT ALL")
    assert cls == "sheet"
    assert reason == "existing"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/pipeline/test_row_class.py -v`
Expected: FAIL — list/mto titles currently return `"document"`; existing `"sheet"` not recognized.

- [ ] **Step 4: Make the change**

In `src/classifier/pipeline/_row.py`, add a `SHEET_ALIASES` constant next to the others (after line 18):
```python
SHEET_ALIASES = {"sheet", "sheets"}
```
Then in `normalize_doc_type`, add the sheet existing-value branch and make the fold three-way. Replace the body from the `if not is_empty(value):` block through the `return` so it reads:
```python
    if not is_empty(value):
        v = str(value).strip().lower()
        if v in DRAWING_ALIASES:
            return "drawing", "existing"
        if v in SHEET_ALIASES:
            return "sheet", "existing"
        if v in DOCUMENT_ALIASES:
            return "document", "existing"
    pick = pick_type_with_overrides(title)
    if pick["confidence"] == "high":
        bucket = TYPE_TO_BUCKET.get(pick["type"])
        if bucket is not None:
            folded = BUCKET_TO_CLASS[bucket]
            reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
            cls = {"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")
            return cls, reason_tag
    return "document", "defaulted"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/pipeline/test_row_class.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add src/classifier/pipeline/_row.py tests/pipeline/__init__.py tests/pipeline/test_row_class.py
git commit -m "feat(row): classify list/mto titles as the sheet class"
```

---

## Task 3: Three-way class in convert_classified

**Files:**
- Modify: `src/classifier/tools/convert_classified.py:57-58` and `:113-116`

`convert_classified` has its own copy of the fold and its own alias map. Keep them consistent with `_row.py`. The relevant function around line 113-116 currently ends with:
```python
    folded = BUCKET_TO_CLASS[bucket]
    return "drawing" if folded == "Drawings" else "document"
```

- [ ] **Step 1: Read the surrounding function**

Run: `.venv\Scripts\python -c "import inspect, classifier.tools.convert_classified as m; print(inspect.getsource(m))" ` and locate the alias dict (around line 57) and the fold return (around line 113-116). Confirm the exact local variable names before editing.

- [ ] **Step 2: Add sheet aliases**

In the alias dict near line 57-58 that maps existing doc-type strings, add a sheet row so it reads (preserve existing entries, add the new line):
```python
    "document": "document", "documents": "document",
    "drawing": "drawing", "drawings": "drawing",
    "sheet": "sheet", "sheets": "sheet",
```

- [ ] **Step 3: Make the fold three-way**

Replace:
```python
    folded = BUCKET_TO_CLASS[bucket]
    return "drawing" if folded == "Drawings" else "document"
```
with:
```python
    folded = BUCKET_TO_CLASS[bucket]
    return {"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")
```

- [ ] **Step 4: Verify import still works**

Run: `.venv\Scripts\python -c "import classifier.tools.convert_classified; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/tools/convert_classified.py
git commit -m "feat(convert): emit sheet class consistently with _row"
```

---

## Task 4: SKETCH titles route to Drawings

**Files:**
- Modify: `src/classifier/core/type_scoring.py` (`SINGULAR_FORMS`, around line 43-48)
- Create: `tests/core/test_sketch_guard.py`

The WIP Phase-5 fallback in `pick_type_with_overrides` already routes a title to `DWG` when `"SKETCH"` (or `"DRAWING"`) is among the tokens **and** nothing else scored. But the canonicalizer does not depluralize `SKETCHES`, so plural-sketch titles miss the fallback and fall through to a defaulted `document`. Adding `SKETCH` to `SINGULAR_FORMS` fixes this and makes both singular and plural sketch titles classify as Drawings.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_sketch_guard.py`:
```python
from classifier.core.type_scoring import canonicalize_title, pick_type_with_overrides
from classifier.pipeline._row import normalize_doc_type


def test_sketches_depluralizes_to_sketch():
    assert "SKETCH" in canonicalize_title("PIPING TIE-IN SKETCHES (25 SHEETS)")


def test_plural_sketch_title_is_drawing_type():
    pick = pick_type_with_overrides("PIPING TIE-IN SKETCHES (25 SHEETS)")
    assert pick["type"] == "DWG"


def test_sketch_title_class_is_drawing_not_sheet():
    cls, _ = normalize_doc_type("Documents/Drawings", "PIPING TIE-IN SKETCHES (25 SHEETS)")
    assert cls == "drawing"

    cls2, _ = normalize_doc_type("NULL", "TIE-IN SKETCHES")
    assert cls2 == "drawing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/core/test_sketch_guard.py -v`
Expected: FAIL — `SKETCHES` not depluralized; pick type is `""` (none); class defaults to `document`.

- [ ] **Step 3: Make the change**

In `src/classifier/core/type_scoring.py`, add `"SKETCH"` to the `SINGULAR_FORMS` frozenset (keep alphabetical-ish ordering; the exact position does not matter):
```python
SINGULAR_FORMS: frozenset[str] = frozenset({
    "CALCULATION", "DIAGRAM", "DRAWING", "INDEX",
    "LAYOUT", "LIST", "PROCEDURE", "PROCESS",
    "REPORT", "REQUISITION", "SCHEDULE", "SHEET",
    "SKETCH",
    "SPECIFICATION", "STANDARD",
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/core/test_sketch_guard.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Guard against regressions in the wider suite**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: all tests pass (table-detect, buckets, row, sketch).

- [ ] **Step 6: Commit**

```bash
git add src/classifier/core/type_scoring.py tests/core/test_sketch_guard.py
git commit -m "fix(type): depluralize SKETCHES so sketch titles classify as Drawings"
```

---

## Task 5: Update display + enum consumers

**Files:**
- Modify: `viewer.html:93`
- Modify: `src/classifier/cli/classify.py:8` (docstring)
- Inspect: `src/classifier/tools/build_type_enum.py` (likely no change)

- [ ] **Step 1: Update the viewer enum**

In `viewer.html`, change line 93 from:
```javascript
const DOC_TYPES = ['drawing', 'document'];
```
to:
```javascript
const DOC_TYPES = ['drawing', 'document', 'sheet'];
```

- [ ] **Step 2: Update the CLI docstring**

In `src/classifier/cli/classify.py`, the module docstring line that reads `` ``doc_type`` is normalized to the lowercase enum ``{drawing, document}``. `` — change the enum to `{drawing, document, sheet}`. This is documentation only; no logic changes.

- [ ] **Step 3: Confirm build_type_enum needs no change**

Run: `.venv\Scripts\python -c "import inspect, classifier.tools.build_type_enum as m; src=inspect.getsource(m); print('BUCKET_TO_CLASS' in src, 'Drawings' in src, 'Documents' in src)"`
If all three are `False`, this tool only deals with the 3-letter `type` enum (not the class) and needs no change — note that and move on. If it references the class fold, STOP and report as DONE_WITH_CONCERNS describing what you found (the plan did not anticipate a class dependency here).

- [ ] **Step 4: Commit**

```bash
git add viewer.html src/classifier/cli/classify.py
git commit -m "feat(viewer,cli): surface sheet as a third doc_type"
```

---

## Task 6: Regenerate classified.csv and verify the three-class split

**Files:**
- Regenerate: `output/classified.csv`
- Commit: the WIP type-rule files + regenerated CSV

- [ ] **Step 1: Regenerate**

Run: `.venv\Scripts\python -m classifier.cli.classify`
Expected: prints `Wrote output\classified.csv (825 rows)` and a `doc_type (before -> after)` table that now includes a `sheet` row with a non-zero `after` count.

- [ ] **Step 2: Audit the sheet rows by title (grounding check)**

Run:
```
.venv\Scripts\python -c "import csv; csv.field_size_limit(10**7); rows=list(csv.DictReader(open('output/classified.csv',encoding='utf-8'))); sheet=[r for r in rows if r['doc_type']=='sheet']; print('sheet rows:',len(sheet)); [print(' ',r['type'],'|',r['title'][:55]) for r in sheet]"
```
Confirm: every printed title is a list/MTO/BOM/index/register/schedule (e.g. VALVE LIST, MTO FOR…, INSTRUMENT CABLE SCHEDULE). There must be **no** SKETCH/DRAWING/SPEC/DATASHEET title in the sheet set.

- [ ] **Step 3: Confirm sketches are drawings, not sheets**

Run:
```
.venv\Scripts\python -c "import csv; csv.field_size_limit(10**7); rows=list(csv.DictReader(open('output/classified.csv',encoding='utf-8'))); [print(r['doc_type'],'|',r['title']) for r in rows if 'SKETCH' in (r['title'] or '').upper()]"
```
Expected: both sketch rows show `drawing`.

- [ ] **Step 4: Confirm the class distribution is sane**

Run:
```
.venv\Scripts\python -c "import csv; from collections import Counter; csv.field_size_limit(10**7); rows=list(csv.DictReader(open('output/classified.csv',encoding='utf-8'))); print(Counter(r['doc_type'] for r in rows))"
```
Expected: three keys `drawing`, `document`, `sheet`, all non-zero. (Phase-1 evidence implies ~40–55 sheet rows.)

- [ ] **Step 5: Commit the regenerated output and the WIP type rules**

Per the user's decision, commit the pre-existing WIP type-rule files together with the regenerated CSV so the output is reproducible from committed code:
```bash
git add output/classified.csv src/classifier/config/type_overrides.py src/classifier/core/type_scoring.py
git commit -m "data: regenerate classified.csv with Sheets class; commit type-rule WIP"
```
(Note: `type_scoring.py` was already partly committed in Task 4 — this picks up any remaining WIP hunks. Run `git status --short` first; if those two files show no remaining changes, commit only `output/classified.csv`.)

- [ ] **Step 6: Final full-suite check**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: all green.

---

## Self-Review

- **Spec coverage:** 3rd class (Task 1 ✓), class emitted by pipeline (Task 2 ✓) and converter (Task 3 ✓), SKETCH→Drawings guard (Task 4 ✓), display/enum consumers (Task 5 ✓), regenerate + grounded title audit (Task 6 ✓). Membership `{LST,MTO,BOM,IDX,REG,SCH}` matches the user's Phase-1 decision.
- **Placeholder scan:** none — every code step is concrete. Task 5 Step 3 is an explicit inspect-and-branch with a defined STOP condition.
- **Type/name consistency:** class strings are lowercase `"drawing"/"document"/"sheet"` everywhere (pipeline, converter, viewer, CSV); the internal fold values are capitalized `"Drawings"/"Sheets"/"Documents"` (buckets, mapping dicts). `SHEET_ALIASES` defined in Task 2 mirrors `DRAWING_ALIASES`/`DOCUMENT_ALIASES`. The fold-to-class mapping `{"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")` is identical in `_row.py` and `convert_classified.py`.
