# Core / Execution / Output Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate the invariant classifier core from the variant execution backends (CSV / RDS / in-memory) and output producers behind `RecordReader` / `ResultWriter` protocols, with a single `classify_record` core entry, a `plan_writes` rule, and a collapsed scoring engine — all behavior-preserving.

**Architecture:** A pure core (`classify_record`, `plan_writes`, one scoring engine) depends on nothing above it. A single `run(reader, writer)` loop orchestrates read → classify → persist. Each input source implements `RecordReader`; each output sink implements `ResultWriter`. Backends map a superset `Stats` object back to their existing public dict shapes at the edge so external contracts never change.

**Tech Stack:** Python 3.10+, pandas, openpyxl/xlrd, psycopg2, pytest.

**Spec:** `docs/superpowers/specs/2026-06-05-core-execution-output-separation-design.md`

**Conventions for every task:**
- Run tests with `pytest` from the repository root (paths are cwd-relative).
- Every commit message ends with this trailer (shown in each commit step):
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on the current branch unless told otherwise.

---

## File Structure

| File | Responsibility | Phase |
|---|---|---|
| `tests/golden/classified.csv` | Frozen byte-for-byte golden of `classify` output | 0 |
| `tests/golden/test_csv_golden.py` | Asserts `classify` reproduces the golden | 0 |
| `tests/pipeline/test_classify_titles.py` | Locks the `classify_titles` public contract (incl. `int\|None`) | 0 |
| `tests/io/test_rds.py` | Fake-conn test: SQL params, write/skip, commit cadence, stats shape | 0 |
| `src/classifier/core/record.py` | `Record`, `FieldResult`, `ClassificationResult` dataclasses | 1 |
| `src/classifier/core/classify.py` | Relocated field helpers + `classify_record` (+ `plan_writes` in Phase 2) | 1/2 |
| `src/classifier/pipeline/_row.py` | Thin re-export shim of the relocated helpers | 1 |
| `src/classifier/pipeline/run.py` | The single orchestration loop `run()` | 2 |
| `src/classifier/pipeline/stats.py` | `Stats` superset + `observe()` | 2 |
| `src/classifier/pipeline/staleness.py` | Shared stale-config detection | 2 |
| `src/classifier/io/csv_io.py` | `CsvReader`, `CsvWriter` | 2 |
| `src/classifier/io/memory.py` | `InMemoryReader`, `InMemoryWriter` | 2 |
| `src/classifier/io/rds.py` | + `RdsReader`, `RdsWriter` (existing fns kept) | 2 |
| `src/classifier/core/scoring.py` | Generic phrase-scoring engine `score()` / `pick()` + primitives | 3 |
| `src/classifier/io/workbook.py` | `iter_grids`, `file_has_table` (moved out of core) | 4 |
| `src/classifier/core/folding.py` | `doc_type_for_bucket()` single fold function | 4 |

---

# Phase 0 — Safety net (no production code change)

Behavior-preserving guard rails. No `src/` code changes in this phase.

### Task 1: Freeze the CSV golden output

**Files:**
- Create: `tests/golden/classified.csv` (copy of current output)
- Create: `tests/golden/__init__.py` (empty)
- Create: `tests/golden/test_csv_golden.py`

- [ ] **Step 1: Create the golden directory package marker**

Create `tests/golden/__init__.py` as an empty file.

- [ ] **Step 2: Copy current output to the golden location**

The current committed `output/classified.csv` is the reference. Copy it:

```bash
cp output/classified.csv tests/golden/classified.csv
```

(On Windows PowerShell: `Copy-Item output/classified.csv tests/golden/classified.csv`.)

- [ ] **Step 3: Write the golden test**

Create `tests/golden/test_csv_golden.py`:

```python
"""Golden test: `classify` must reproduce tests/golden/classified.csv byte-for-byte.

Runs the real classifier against the real input but redirects OUTPUT_PATH to a
temp file so the tracked output/ file is never touched by the test.
"""
from pathlib import Path

from classifier.cli import classify


def test_classify_reproduces_golden(tmp_path, monkeypatch):
    out = tmp_path / "classified.csv"
    monkeypatch.setattr(classify, "OUTPUT_PATH", out)

    classify.main()

    golden = Path("tests/golden/classified.csv").read_bytes()
    produced = out.read_bytes()
    assert produced == golden, "classify output drifted from golden"
```

- [ ] **Step 4: Run the test to verify it passes against current code**

Run: `pytest tests/golden/test_csv_golden.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/golden/
git commit -m "$(cat <<'EOF'
test: freeze classify CSV golden output

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 2: Lock the `classify_titles` public contract

**Files:**
- Create: `tests/pipeline/test_classify_titles.py`

- [ ] **Step 1: Write the contract test**

Create `tests/pipeline/test_classify_titles.py`:

```python
"""Locks the classify_titles public contract before refactoring.

Critical invariants: discipline_id is int|None (NOT a string), doc_type is
always set, existing populated fields are preserved, and include_reasons
attaches (value, reason) tuples.
"""
from classifier.pipeline.classify_titles import classify_titles


def test_doc_type_always_set_and_defaults_to_document():
    out = classify_titles([{"title": "ZZZ NONSENSE TOKEN"}])
    assert out[0]["doc_type"] == "document"


def test_drawing_title_classifies_as_drawing():
    out = classify_titles([{"title": "PIPING AND INSTRUMENT DIAGRAM"}])
    assert out[0]["doc_type"] == "drawing"


def test_discipline_id_is_int_or_none_never_string():
    out = classify_titles([{"title": "EQUIPMENT REQUISITION"}])
    val = out[0]["discipline_id"]
    assert val is None or isinstance(val, int)


def test_existing_fields_preserved():
    out = classify_titles([
        {"title": "", "doc_type": "drawing", "type": "DWG", "discipline_id": 7},
    ])
    assert out[0]["doc_type"] == "drawing"
    assert out[0]["type"] == "DWG"
    assert out[0]["discipline_id"] == 7


def test_include_reasons_returns_tuples():
    out = classify_titles([{"title": "P&ID AREA 01"}], include_reasons=True)
    value, reason = out[0]["doc_type"]
    assert isinstance(reason, str)
    assert value in ("drawing", "document", "sheet")
```

- [ ] **Step 2: Run the test to verify it passes against current code**

Run: `pytest tests/pipeline/test_classify_titles.py -v`
Expected: PASS (5 passed). If any title-specific assertion fails, adjust the *expected value* to match current behavior — these tests must lock CURRENT behavior, not desired behavior.

- [ ] **Step 3: Commit**

```bash
git add tests/pipeline/test_classify_titles.py
git commit -m "$(cat <<'EOF'
test: lock classify_titles public contract

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 3: Lock the RDS read/write SQL and stats shape (fake conn)

**Files:**
- Create: `tests/io/__init__.py` (empty)
- Create: `tests/io/test_rds.py`

- [ ] **Step 1: Create the test package marker**

Create `tests/io/__init__.py` as an empty file.

- [ ] **Step 2: Write the fake-conn RDS test**

Create `tests/io/test_rds.py`:

```python
"""Fake-conn tests for the RDS pipeline: locks write/skip decisions, the
per-row UPDATE parameters, commit cadence, and the stats dict shape — none
of which the CSV golden covers.
"""
from classifier.pipeline.classify_rds import classify_from_rds


class FakeServerCursor:
    """Stands in for the named server-side cursor used by iter_unclassified."""
    def __init__(self, rows):
        self._rows = rows
        self.itersize = None
    def execute(self, *a, **k):
        pass
    def __iter__(self):
        return iter(self._rows)
    def close(self):
        pass


class FakeWriteCursor:
    def __init__(self, log):
        self._log = log
    def execute(self, stmt, params=None):
        self._log.append(params)
    def close(self):
        pass


class FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.updates = []        # list of params lists from UPDATE
        self.commits = 0
    def cursor(self, name=None):
        if name is not None:
            return FakeServerCursor(self._rows)
        return FakeWriteCursor(self.updates)
    def commit(self):
        self.commits += 1


def test_fills_empty_fields_and_skips_complete_rows():
    rows = [
        # (pk, doc_type, type, discipline_id, title)
        (1, None, None, None, "PIPING AND INSTRUMENT DIAGRAM"),  # should update
        (2, "drawing", "PID", 7, ""),                            # already full -> but selected? simulate skip
    ]
    conn = FakeConn(rows)
    stats = classify_from_rds(conn, commit_every=10)
    assert stats["rows_scanned"] == 2
    # Row 1 has all-empty targets and a recognizable title -> at least one write.
    assert stats["rows_updated"] >= 1
    # Stats dict shape (superset preserved):
    for key in ("rows_scanned", "rows_updated", "rows_skipped",
                "doc_type", "type", "discipline_id", "callback_error"):
        assert key in stats
    assert isinstance(stats["doc_type"], dict)


def test_final_commit_happens():
    conn = FakeConn([(1, None, None, None, "VALVE LIST")])
    classify_from_rds(conn, commit_every=500)
    assert conn.commits >= 1   # final commit at end


def test_on_done_callback_receives_stats():
    seen = {}
    conn = FakeConn([(1, None, None, None, "VALVE LIST")])
    classify_from_rds(conn, on_done=lambda s: seen.update(s))
    assert seen["rows_scanned"] == 1
```

- [ ] **Step 3: Run the test against current code**

Run: `pytest tests/io/test_rds.py -v`
Expected: PASS (3 passed). If row 2 in `test_fills_empty_fields_and_skips_complete_rows` causes an unexpected write, relax that assertion to match current behavior (the goal is to lock CURRENT behavior).

- [ ] **Step 4: Commit**

```bash
git add tests/io/
git commit -m "$(cat <<'EOF'
test: lock RDS write/skip, commit, and stats shape via fake conn

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 4: Capture the reason-counter baselines

**Files:**
- Create: `tests/pipeline/test_reason_baseline.py`

Reasons drive `Stats` but are absent from the golden CSV output, so they need their own lock.

- [ ] **Step 1: Write the reason-baseline test**

Create `tests/pipeline/test_reason_baseline.py`:

```python
"""Locks the reason vocabulary emitted by the core field helpers. These feed
Stats in Phase 2; the CSV golden does not contain reasons.
"""
from classifier.pipeline._row import (
    normalize_doc_type, fill_type, fill_discipline,
)


def test_doc_type_reasons():
    assert normalize_doc_type("drawing", "X")[1] == "existing"
    assert normalize_doc_type("", "ZZZ NONSENSE")[1] == "defaulted"
    assert normalize_doc_type("", "PIPING AND INSTRUMENT DIAGRAM")[1] in (
        "via_keyword", "via_override",
    )


def test_fill_type_reasons():
    assert fill_type("DWG", "X")[1] == "preserved"
    assert fill_type("", "ZZZ NONSENSE")[1] == "miss"


def test_fill_discipline_reasons():
    assert fill_discipline("7", "X")[1] == "preserved"
    assert fill_discipline("", "ZZZ NONSENSE")[1] == "miss"
```

- [ ] **Step 2: Run the test against current code**

Run: `pytest tests/pipeline/test_reason_baseline.py -v`
Expected: PASS (3 passed). Adjust expected reason strings if any differ from current output.

- [ ] **Step 3: Run the full suite as a Phase 0 baseline**

Run: `pytest -q`
Expected: all tests pass. Record the count; later phases must keep it green.

- [ ] **Step 4: Commit**

```bash
git add tests/pipeline/test_reason_baseline.py
git commit -m "$(cat <<'EOF'
test: lock core reason vocabulary baseline

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 1 — Extract the core row entry

Introduce `classify_record`. Relocate the three pure field helpers from `pipeline/_row.py` into `core/classify.py` (resolving the core→pipeline import direction) and leave `_row.py` as a re-export shim so every existing import and test keeps working. Behavior identical.

### Task 5: Add the core data types

**Files:**
- Create: `src/classifier/core/record.py`
- Create: `tests/core/test_record.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_record.py`:

```python
from classifier.core.record import Record, FieldResult, ClassificationResult


def test_record_defaults():
    r = Record(title="X")
    assert r.doc_type == "" and r.type == "" and r.discipline_id == ""
    assert r.handle is None


def test_classification_result_holds_field_results():
    cr = ClassificationResult(
        doc_type=FieldResult("drawing", "via_keyword"),
        type=FieldResult("DWG", "via_keyword"),
        discipline_id=FieldResult("7", "via_keyword"),
    )
    assert cr.doc_type.value == "drawing"
    assert cr.type.reason == "via_keyword"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_record.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'classifier.core.record'`.

- [ ] **Step 3: Write the implementation**

Create `src/classifier/core/record.py`:

```python
"""Pure data types shared across the classifier core and all backends.

No I/O, no behavior — just the record-in / result-out shapes that the core
entry point (``classify_record``) consumes and produces.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    """One row to classify. Raw existing values are strings; "" means empty.

    ``handle`` is an opaque value a writer may need to persist the result
    (a PK, a full source row, a list index). The core never inspects it.
    """
    title: str
    doc_type: str = ""
    type: str = ""
    discipline_id: str = ""
    handle: object = None


@dataclass(frozen=True)
class FieldResult:
    value: object
    reason: str


@dataclass(frozen=True)
class ClassificationResult:
    doc_type: FieldResult
    type: FieldResult
    discipline_id: FieldResult
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_record.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/core/record.py tests/core/test_record.py
git commit -m "$(cat <<'EOF'
feat(core): add Record/FieldResult/ClassificationResult types

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 6: Relocate field helpers into `core/classify.py` and add `classify_record`

**Files:**
- Create: `src/classifier/core/classify.py`
- Modify: `src/classifier/pipeline/_row.py` (becomes a re-export shim)
- Create: `tests/core/test_classify_record.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_classify_record.py`:

```python
from classifier.core.record import Record
from classifier.core.classify import classify_record


def test_classify_record_drawing():
    res = classify_record(Record(title="PIPING AND INSTRUMENT DIAGRAM"))
    assert res.doc_type.value == "drawing"


def test_classify_record_preserves_existing():
    res = classify_record(Record(title="", doc_type="drawing", type="DWG",
                                 discipline_id="7"))
    assert res.doc_type.value == "drawing"
    assert res.type.value == "DWG"
    assert res.type.reason == "preserved"
    assert res.discipline_id.value == "7"


def test_classify_record_uses_type_as_discipline_hint():
    # An ISO type should bias discipline scoring; assert it does not crash and
    # returns a FieldResult triple with reasons.
    res = classify_record(Record(title="ISOMETRIC DRAWING"))
    assert res.doc_type.reason in ("via_keyword", "via_override", "defaulted",
                                   "existing")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_classify_record.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'classifier.core.classify'`.

- [ ] **Step 3: Create `core/classify.py` with the relocated helpers + entry point**

Create `src/classifier/core/classify.py` (the three function bodies are copied verbatim from the current `pipeline/_row.py` — unchanged behavior):

```python
"""Core per-row classification: the single invariant entry point.

The three field helpers (``normalize_doc_type`` / ``fill_type`` /
``fill_discipline``) live here (relocated from ``pipeline/_row.py``, which now
re-exports them). ``classify_record`` composes them once so every execution
backend shares identical row logic.

Each helper takes ``(existing_value, title)`` and returns ``(value, reason)``.
"""
from __future__ import annotations

from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.core.discipline_scoring import pick_discipline_with_overrides
from classifier.core.type_scoring import pick_type_with_overrides
from classifier.core.record import Record, FieldResult, ClassificationResult
from classifier.io.normalize import is_empty

DRAWING_ALIASES = {"drawing", "drawings", "dwg"}
DOCUMENT_ALIASES = {"document", "documents", "doc", "docs"}
SHEET_ALIASES = {"sheet", "sheets"}


def normalize_doc_type(value: str, title: str) -> tuple[str, str]:
    """Return ``(normalized, reason)``. reason: existing / via_keyword / via_override / defaulted."""
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


def fill_type(row_type: str, title: str) -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / via_override / miss."""
    if not is_empty(row_type):
        return str(row_type).strip(), "preserved"
    pick = pick_type_with_overrides(title)
    if pick["confidence"] == "high":
        reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
        return pick["type"], reason_tag
    return "", "miss"


def fill_discipline(row_disc: str, title: str,
                    type_hint: str = "") -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / miss.

    ``value`` is the discipline_id as a decimal string when found, else "".
    """
    if not is_empty(row_disc):
        return str(row_disc).strip(), "preserved"
    pick = pick_discipline_with_overrides(title, type_hint=type_hint or None)
    if pick["confidence"] == "high" and pick["discipline_id"] is not None:
        return str(pick["discipline_id"]), "via_keyword"
    return "", "miss"


def classify_record(rec: Record) -> ClassificationResult:
    """The single per-row entry. Pure; no I/O. Composes the three helpers,
    feeding the just-inferred ``type`` as the discipline scorer's hint.
    """
    dt = normalize_doc_type(rec.doc_type, rec.title)
    ty = fill_type(rec.type, rec.title)
    di = fill_discipline(rec.discipline_id, rec.title, type_hint=ty[0])
    return ClassificationResult(
        FieldResult(*dt), FieldResult(*ty), FieldResult(*di),
    )
```

- [ ] **Step 4: Replace `pipeline/_row.py` with a re-export shim**

Overwrite `src/classifier/pipeline/_row.py` with:

```python
"""Backward-compatible shim. The per-row helpers moved to
``classifier.core.classify``; this module re-exports them so existing imports
(and tests) keep working.
"""
from __future__ import annotations

from classifier.core.classify import (  # noqa: F401
    DRAWING_ALIASES, DOCUMENT_ALIASES, SHEET_ALIASES,
    normalize_doc_type, fill_type, fill_discipline,
)
```

- [ ] **Step 5: Run the new test plus the Phase 0 guards**

Run: `pytest tests/core/test_classify_record.py tests/pipeline/test_row_class.py tests/pipeline/test_reason_baseline.py tests/golden/ -v`
Expected: all PASS. The golden and `_row` import path must remain green (proving the relocation is behavior-preserving).

- [ ] **Step 6: Commit**

```bash
git add src/classifier/core/classify.py src/classifier/pipeline/_row.py tests/core/test_classify_record.py
git commit -m "$(cat <<'EOF'
refactor(core): relocate row helpers, add classify_record entry

_row.py is now a re-export shim; behavior unchanged (golden green).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 7: Repoint the three call sites to `classify_record`

> Note: these edits are partly throwaway — Phase 2 rewrites the same sites to use `run()`. They are kept because Phase 1 must be independently shippable and they de-risk Phase 2 by proving `classify_record` is a faithful drop-in.

**Files:**
- Modify: `src/classifier/pipeline/classify_titles.py:57-87`
- Modify: `src/classifier/pipeline/classify_rds.py:99-104`
- Modify: `src/classifier/cli/classify.py:75-86`

- [ ] **Step 1: Repoint `classify_titles`**

In `src/classifier/pipeline/classify_titles.py`, replace the per-field calls (the block currently at lines 69-71) with a single `classify_record` call. Update imports at the top from:

```python
from classifier.pipeline._row import (
    fill_discipline, fill_type, normalize_doc_type,
)
```
to:
```python
from classifier.core.record import Record
from classifier.core.classify import classify_record
```

Then replace the body of the `for row in rows:` loop (lines 58-86) with:

```python
        title = "" if row.get("title") is None else str(row["title"])
        cur_doc_type = row.get("doc_type")
        cur_type     = row.get("type")
        cur_disc     = row.get("discipline_id")

        rec = Record(
            title=title,
            doc_type="" if cur_doc_type is None else str(cur_doc_type),
            type="" if cur_type is None else str(cur_type),
            discipline_id="" if cur_disc is None or is_empty(cur_disc) else str(cur_disc),
        )
        res = classify_record(rec)

        disc_value = int(res.discipline_id.value) if res.discipline_id.value else None

        if include_reasons:
            out.append({
                "doc_type":      (res.doc_type.value, res.doc_type.reason),
                "type":          (res.type.value, res.type.reason),
                "discipline_id": (disc_value, res.discipline_id.reason),
            })
        else:
            out.append({
                "doc_type":      res.doc_type.value,
                "type":          res.type.value,
                "discipline_id": disc_value,
            })
```

(Keep the existing `from classifier.io.normalize import is_empty` import.)

- [ ] **Step 2: Repoint `classify_rds`**

In `src/classifier/pipeline/classify_rds.py`, change the import at lines 15-17 from:

```python
from classifier.pipeline._row import (
    fill_discipline, fill_type, normalize_doc_type,
)
```
to:
```python
from classifier.core.record import Record
from classifier.core.classify import classify_record
```

Then replace the classification block (lines 99-104) with:

```python
            rec = Record(title=title_s, doc_type=cur_doc_type_s,
                         type=cur_type_s, discipline_id=cur_disc_s, handle=pk_value)
            res = classify_record(rec)
            new_doc_type, dt_reason = res.doc_type.value, res.doc_type.reason
            new_type,     t_reason  = res.type.value, res.type.reason
            new_disc,     d_reason  = res.discipline_id.value, res.discipline_id.reason
```

The downstream `writes` / stats code (lines 106-128) is unchanged because the
`new_*` / `*_reason` names are preserved.

- [ ] **Step 3: Repoint `cli/classify`**

In `src/classifier/cli/classify.py`, change the import at line 35 from:

```python
from classifier.pipeline._row import fill_discipline, fill_type, normalize_doc_type
```
to:
```python
from classifier.core.record import Record
from classifier.core.classify import classify_record
```

Then replace lines 75-86 (the three helper calls) with:

```python
            rec = Record(title=out["title"], doc_type=out["doc_type"],
                         type=out["type"], discipline_id=out["discipline_id"])
            res = classify_record(rec)

            new_doc_type, dt_reason = res.doc_type.value, res.doc_type.reason
            out["doc_type"] = new_doc_type
            doc_type_after[new_doc_type] += 1
            doc_type_reason[dt_reason] += 1

            new_type, t_reason = res.type.value, res.type.reason
            out["type"] = new_type
            type_reason[t_reason] += 1

            new_disc, d_reason = res.discipline_id.value, res.discipline_id.reason
            out["discipline_id"] = new_disc
            disc_reason[d_reason] += 1
```

- [ ] **Step 4: Run the full guard suite**

Run: `pytest -q`
Expected: all PASS, same count as the Phase 0 baseline. The CSV golden, `classify_titles` contract, and RDS fake-conn tests all prove the three sites still behave identically.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/pipeline/classify_titles.py src/classifier/pipeline/classify_rds.py src/classifier/cli/classify.py
git commit -m "$(cat <<'EOF'
refactor: route all three backends through classify_record

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 2 — Protocols + generic loop

Add `plan_writes`, the `Stats` superset, the `run()` loop, and reader/writer concretes. Rewrite the three backends to construct a reader + writer and call `run()`. Each backend maps `Stats` back to its existing public dict at the edge.

### Task 8: Add `plan_writes` to the core

**Files:**
- Modify: `src/classifier/core/classify.py` (append `plan_writes`)
- Create: `tests/core/test_plan_writes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_plan_writes.py`:

```python
from classifier.core.record import Record, FieldResult, ClassificationResult
from classifier.core.classify import plan_writes


def _result(dt, ty, di):
    return ClassificationResult(FieldResult(dt, "x"), FieldResult(ty, "x"),
                                FieldResult(di, "x"))


def test_writes_doc_type_when_changed():
    rec = Record(title="X", doc_type="", type="DWG", discipline_id="7")
    w = plan_writes(rec, _result("document", "DWG", "7"))
    assert w == {"doc_type": "document"}


def test_no_doc_type_write_when_same():
    rec = Record(title="X", doc_type="drawing", type="DWG", discipline_id="7")
    w = plan_writes(rec, _result("drawing", "DWG", "7"))
    assert "doc_type" not in w


def test_type_written_only_when_was_empty():
    rec = Record(title="X", doc_type="document", type="", discipline_id="7")
    assert plan_writes(rec, _result("document", "DWG", "7")) == {"type": "DWG"}
    rec2 = Record(title="X", doc_type="document", type="DDT", discipline_id="7")
    assert "type" not in plan_writes(rec2, _result("document", "DDT", "7"))


def test_discipline_written_only_when_was_empty_and_hit():
    rec = Record(title="X", doc_type="document", type="DWG", discipline_id="")
    assert plan_writes(rec, _result("document", "DWG", "7")) == {"discipline_id": "7"}
    rec_miss = Record(title="X", doc_type="document", type="DWG", discipline_id="")
    assert "discipline_id" not in plan_writes(rec_miss, _result("document", "DWG", ""))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_plan_writes.py -v`
Expected: FAIL with `ImportError: cannot import name 'plan_writes'`.

- [ ] **Step 3: Append `plan_writes` to `core/classify.py`**

Add to the end of `src/classifier/core/classify.py`:

```python
def plan_writes(rec: Record, result: ClassificationResult) -> dict[str, object]:
    """Fields a sink should persist, applying only-fill-empty + doc_type diff.

    Returns {} when nothing should change (a "skipped" row). Faithful to the
    historical RDS write conditions: doc_type writes on a normalized diff;
    type/discipline write only when the existing value was empty AND inference
    produced a value. Values are returned in their core string form; a sink
    that needs another type (e.g. discipline_id as int for SQL) casts at write.
    """
    writes: dict[str, object] = {}
    if result.doc_type.value != rec.doc_type.strip().lower():
        writes["doc_type"] = result.doc_type.value
    if rec.type == "" and result.type.value != "":
        writes["type"] = result.type.value
    if rec.discipline_id == "" and result.discipline_id.value not in ("", None):
        writes["discipline_id"] = result.discipline_id.value
    return writes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_plan_writes.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/core/classify.py tests/core/test_plan_writes.py
git commit -m "$(cat <<'EOF'
feat(core): add plan_writes (only-fill-empty/diff rule)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 9: Add the `Stats` superset

**Files:**
- Create: `src/classifier/pipeline/stats.py`
- Create: `tests/pipeline/test_stats.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_stats.py`:

```python
from classifier.core.record import Record, FieldResult, ClassificationResult
from classifier.pipeline.stats import Stats


def _res(dt_r, ty_r, di_r):
    return ClassificationResult(FieldResult("document", dt_r),
                                FieldResult("", ty_r),
                                FieldResult("", di_r))


def test_observe_counts_scanned_updated_skipped():
    s = Stats()
    s.observe(Record(title="X", doc_type=""), _res("defaulted", "miss", "miss"),
              {"doc_type": "document"})
    s.observe(Record(title="Y", doc_type="document"), _res("existing", "miss", "miss"),
              {})
    assert s.rows_scanned == 2
    assert s.rows_updated == 1
    assert s.rows_skipped == 1


def test_reason_counters_and_before_after():
    s = Stats()
    s.observe(Record(title="X", doc_type=""), _res("defaulted", "miss", "miss"),
              {"doc_type": "document"})
    assert s.reasons["doc_type"]["defaulted"] == 1
    assert s.reasons["type"]["miss"] == 1
    assert s.doc_type_before["(empty)"] == 1
    assert s.doc_type_after["document"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'classifier.pipeline.stats'`.

- [ ] **Step 3: Write the implementation**

Create `src/classifier/pipeline/stats.py`:

```python
"""Aggregate run statistics — a strict superset of every backend's legacy
stat vocabulary, so each edge can reconstruct its historical dict shape.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from classifier.core.record import Record, ClassificationResult
from classifier.io.normalize import is_empty


@dataclass
class Stats:
    rows_scanned: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    reasons: dict = field(default_factory=lambda: {
        "doc_type": Counter(), "type": Counter(), "discipline_id": Counter(),
    })
    doc_type_before: Counter = field(default_factory=Counter)
    doc_type_after: Counter = field(default_factory=Counter)
    callback_error: object = None

    def observe(self, rec: Record, result: ClassificationResult,
                writes: dict) -> None:
        self.rows_scanned += 1
        if writes:
            self.rows_updated += 1
        else:
            self.rows_skipped += 1
        self.reasons["doc_type"][result.doc_type.reason] += 1
        self.reasons["type"][result.type.reason] += 1
        self.reasons["discipline_id"][result.discipline_id.reason] += 1
        before = "" if is_empty(rec.doc_type) else rec.doc_type.strip().lower()
        self.doc_type_before[before or "(empty)"] += 1
        self.doc_type_after[result.doc_type.value] += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_stats.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/pipeline/stats.py tests/pipeline/test_stats.py
git commit -m "$(cat <<'EOF'
feat(pipeline): add Stats superset with observe()

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 10: Add the `run()` loop

**Files:**
- Create: `src/classifier/pipeline/run.py`
- Create: `tests/pipeline/test_run.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_run.py`:

```python
from classifier.core.record import Record
from classifier.pipeline.run import run


class ListReader:
    def __init__(self, records): self._records = records; self.closed = False
    def __iter__(self): return iter(self._records)
    def close(self): self.closed = True


class RecordingWriter:
    def __init__(self): self.writes = []; self.closed = False
    def write(self, rec, result, writes): self.writes.append((rec, result, writes))
    def close(self): self.closed = True


def test_run_classifies_and_persists_each_record():
    reader = ListReader([Record(title="PIPING AND INSTRUMENT DIAGRAM"),
                         Record(title="ZZZ NONSENSE")])
    writer = RecordingWriter()
    stats = run(reader, writer)
    assert stats.rows_scanned == 2
    assert len(writer.writes) == 2
    assert reader.closed and writer.closed


def test_run_closes_both_on_exception():
    class Boom(ListReader):
        def __iter__(self):
            raise RuntimeError("boom")
    reader = Boom([])
    writer = RecordingWriter()
    try:
        run(reader, writer)
    except RuntimeError:
        pass
    assert reader.closed and writer.closed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'classifier.pipeline.run'`.

- [ ] **Step 3: Write the implementation**

Create `src/classifier/pipeline/run.py`:

```python
"""The single orchestration loop: read -> classify -> persist.

Generic over any RecordReader (input source) and ResultWriter (output sink).
Core decides what to write (plan_writes); the writer only persists. run()
owns the lifecycle of both reader and writer and closes them even on error.
Per-record errors propagate (fail-fast), matching historical behavior.
"""
from __future__ import annotations

from typing import Callable, Optional

from classifier.core.classify import classify_record, plan_writes
from classifier.pipeline.stats import Stats


def run(reader, writer, *,
        on_progress: Optional[Callable[[Stats], None]] = None) -> Stats:
    stats = Stats()
    try:
        for rec in reader:
            result = classify_record(rec)
            writes = plan_writes(rec, result)
            writer.write(rec, result, writes)
            stats.observe(rec, result, writes)
            if on_progress is not None:
                on_progress(stats)
    finally:
        reader.close()
        writer.close()
    return stats
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_run.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/pipeline/run.py tests/pipeline/test_run.py
git commit -m "$(cat <<'EOF'
feat(pipeline): add generic run() loop

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 11: In-memory reader/writer + rewrite `classify_titles`

**Files:**
- Create: `src/classifier/io/memory.py`
- Modify: `src/classifier/pipeline/classify_titles.py` (rewrite to use `run`)

- [ ] **Step 1: Write the in-memory concretes**

Create `src/classifier/io/memory.py`:

```python
"""In-memory RecordReader/ResultWriter for callers holding rows already.

The writer collects ClassificationResults in input order; classify_titles
renders the public dict shape from them.
"""
from __future__ import annotations

from typing import Iterable, Iterator, Mapping

from classifier.core.record import Record, ClassificationResult
from classifier.io.normalize import is_empty


class InMemoryReader:
    def __init__(self, rows: Iterable[Mapping]):
        self._rows = rows

    def __iter__(self) -> Iterator[Record]:
        for row in self._rows:
            title = "" if row.get("title") is None else str(row["title"])
            dt = row.get("doc_type")
            ty = row.get("type")
            di = row.get("discipline_id")
            yield Record(
                title=title,
                doc_type="" if dt is None else str(dt),
                type="" if ty is None else str(ty),
                discipline_id="" if di is None or is_empty(di) else str(di),
            )

    def close(self) -> None:
        pass


class InMemoryWriter:
    def __init__(self):
        self.results: list[ClassificationResult] = []

    def write(self, rec: Record, result: ClassificationResult, writes) -> None:
        self.results.append(result)

    def close(self) -> None:
        pass
```

- [ ] **Step 2: Rewrite `classify_titles` to use `run`**

Overwrite the body of `src/classifier/pipeline/classify_titles.py` (keep the module docstring) so the function reads:

```python
from __future__ import annotations

from typing import Iterable, Mapping

from classifier.io.memory import InMemoryReader, InMemoryWriter
from classifier.pipeline.run import run


def classify_titles(rows: Iterable[Mapping],
                    *,
                    include_reasons: bool = False) -> list[dict]:
    reader = InMemoryReader(rows)
    writer = InMemoryWriter()
    run(reader, writer)

    out: list[dict] = []
    for res in writer.results:
        disc_value = int(res.discipline_id.value) if res.discipline_id.value else None
        if include_reasons:
            out.append({
                "doc_type":      (res.doc_type.value, res.doc_type.reason),
                "type":          (res.type.value, res.type.reason),
                "discipline_id": (disc_value, res.discipline_id.reason),
            })
        else:
            out.append({
                "doc_type":      res.doc_type.value,
                "type":          res.type.value,
                "discipline_id": disc_value,
            })
    return out
```

- [ ] **Step 3: Run the contract test (must still pass)**

Run: `pytest tests/pipeline/test_classify_titles.py -v`
Expected: PASS (5 passed) — the public contract is unchanged.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/io/memory.py src/classifier/pipeline/classify_titles.py
git commit -m "$(cat <<'EOF'
refactor(pipeline): classify_titles via in-memory reader/writer + run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 12: Shared stale-config detection

**Files:**
- Create: `src/classifier/pipeline/staleness.py`
- Create: `tests/pipeline/test_staleness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_staleness.py`:

```python
from pathlib import Path
from classifier.pipeline.staleness import stale_configs


def test_flags_config_older_than_training(tmp_path):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    cfg = tmp_path / "rules.py"
    cfg.write_text("x = 1")
    # make a training CSV newer than the config
    newer = csv_dir / "a.csv"
    newer.write_text("h\n")
    import os, time
    old = cfg.stat().st_mtime - 100
    os.utime(cfg, (old, old))

    stale = stale_configs([(cfg, "learn-x")], csv_dir)
    assert stale == [(cfg, "learn-x")]


def test_empty_when_no_training_dir(tmp_path):
    cfg = tmp_path / "rules.py"; cfg.write_text("x=1")
    assert stale_configs([(cfg, "learn-x")], tmp_path / "missing") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_staleness.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `src/classifier/pipeline/staleness.py`:

```python
"""Shared detection of generated configs older than the labelled training CSVs.

Returns the stale (path, learner-command) pairs; callers format/emit in their
own style (the CSV CLI prints, the RDS pipeline logs).
"""
from __future__ import annotations

from pathlib import Path


def stale_configs(configs: list[tuple[Path, str]], csv_dir: Path
                  ) -> list[tuple[Path, str]]:
    if not csv_dir.exists():
        return []
    mtimes = [p.stat().st_mtime for p in csv_dir.rglob("*.csv")]
    if not mtimes:
        return []
    newest = max(mtimes)
    return [(p, tool) for p, tool in configs
            if p.exists() and newest > p.stat().st_mtime]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_staleness.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/pipeline/staleness.py tests/pipeline/test_staleness.py
git commit -m "$(cat <<'EOF'
feat(pipeline): shared stale-config detection

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 13: CSV reader/writer + rewrite `cli/classify`

**Files:**
- Create: `src/classifier/io/csv_io.py`
- Modify: `src/classifier/cli/classify.py` (rewrite to use `run`)

- [ ] **Step 1: Write the CSV concretes**

Create `src/classifier/io/csv_io.py`:

```python
"""CSV RecordReader/ResultWriter for the standalone `classify` CLI.

CsvReader streams the 28-column input, validating the schema, and carries each
full original row as the Record.handle so non-target columns pass through
untouched. CsvWriter rewrites every row (full-row sink) applying the three
classified fields from the result; it ignores `writes` because the CSV output
always re-emits all columns.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

import pandas as pd

from classifier.core.record import Record, ClassificationResult
from classifier.io.schema import TARGET_COLUMNS, validate_schema


class CsvReader:
    def __init__(self, path: Path):
        self.path = path

    def __iter__(self) -> Iterator[Record]:
        df = pd.read_csv(self.path, dtype=str, keep_default_na=False, na_values=[])
        validate_schema(df.columns)
        for _, row in df.iterrows():
            original = {c: str(row[c]) for c in TARGET_COLUMNS}
            yield Record(
                title=original["title"],
                doc_type=original["doc_type"],
                type=original["type"],
                discipline_id=original["discipline_id"],
                handle=original,
            )

    def close(self) -> None:
        pass


class CsvWriter:
    def __init__(self, path: Path):
        self.path = path
        self._f = None
        self._w = None

    def _ensure_open(self):
        if self._w is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._f = self.path.open("w", newline="", encoding="utf-8")
            self._w = csv.writer(self._f, quoting=csv.QUOTE_MINIMAL,
                                 lineterminator="\n")
            self._w.writerow(TARGET_COLUMNS)

    def write(self, rec: Record, result: ClassificationResult, writes) -> None:
        self._ensure_open()
        out = dict(rec.handle)   # full original row
        out["doc_type"] = result.doc_type.value
        out["type"] = result.type.value
        out["discipline_id"] = result.discipline_id.value
        self._w.writerow([out[c] for c in TARGET_COLUMNS])

    def close(self) -> None:
        if self._f is not None:
            self._f.close()
```

- [ ] **Step 2: Rewrite `cli/classify.main()` to use `run`**

Overwrite `src/classifier/cli/classify.py` (keep the module docstring at the top), with this body:

```python
from __future__ import annotations

from pathlib import Path

from classifier.io.csv_io import CsvReader, CsvWriter
from classifier.pipeline.run import run
from classifier.pipeline.staleness import stale_configs

INPUT_PATH = Path("input/To be classified/document.csv")
OUTPUT_PATH = Path("output/classified.csv")
CLASSIFIED_CSV_DIR = Path("input/classified_csv")
TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")


def main() -> None:
    if not INPUT_PATH.exists():
        raise SystemExit(f"input not found: {INPUT_PATH}")

    for path, tool in stale_configs(
        [(TYPE_KEYWORDS_PATH, "learn-type-keywords")], CLASSIFIED_CSV_DIR
    ):
        print(f"!! WARNING: {path.name} is older than training data. "
              f"Run: {tool}")

    reader = CsvReader(INPUT_PATH)
    writer = CsvWriter(OUTPUT_PATH)
    stats = run(reader, writer)

    total = sum(stats.doc_type_after.values())
    print(f"\nWrote {OUTPUT_PATH}  ({total} rows)")
    print()
    print("doc_type (before -> after):")
    for k in sorted(set(stats.doc_type_before) | set(stats.doc_type_after)):
        print(f"  {k:20s} before={stats.doc_type_before.get(k, 0):>6}  "
              f"after={stats.doc_type_after.get(k, 0):>6}")
    print(f"  reasons: {dict(stats.reasons['doc_type'])}")
    print()
    print("type fill outcomes:")
    for k in ("preserved", "via_override", "via_keyword", "miss"):
        print(f"  {k:14s} {stats.reasons['type'].get(k, 0):>6}")
    print()
    print("discipline_id fill outcomes:")
    for k in ("preserved", "via_keyword", "miss"):
        print(f"  {k:14s} {stats.reasons['discipline_id'].get(k, 0):>6}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the golden test (must still pass)**

Run: `pytest tests/golden/test_csv_golden.py -v`
Expected: PASS — `classify` reproduces the golden byte-for-byte through the new reader/writer/run path.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/io/csv_io.py src/classifier/cli/classify.py
git commit -m "$(cat <<'EOF'
refactor(cli): classify via CSV reader/writer + run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 14: RDS reader/writer + rewrite `classify_from_rds`

**Files:**
- Modify: `src/classifier/io/rds.py` (append `RdsReader`, `RdsWriter`)
- Modify: `src/classifier/pipeline/classify_rds.py` (rewrite to use `run`)

- [ ] **Step 1: Append the RDS concretes**

Add to the end of `src/classifier/io/rds.py`:

```python
from classifier.core.record import Record, ClassificationResult  # noqa: E402


class RdsReader:
    """Streams unclassified rows as Records. Does NOT own the connection
    (caller's lifecycle); the server-side cursor is closed inside
    iter_unclassified.
    """
    def __init__(self, conn, *, table: str = "documents",
                 pk: str = "document_id", fetch_size: int = 1000):
        self.conn = conn
        self.table = table
        self.pk = pk
        self.fetch_size = fetch_size

    def __iter__(self):
        for pk_value, dt, ty, disc, title in iter_unclassified(
            self.conn, table=self.table, pk=self.pk, fetch_size=self.fetch_size
        ):
            yield Record(
                title="" if title is None else str(title),
                doc_type="" if dt is None else str(dt),
                type="" if ty is None else str(ty),
                discipline_id="" if disc is None else str(disc),
                handle=pk_value,
            )

    def close(self) -> None:
        pass


class RdsWriter:
    """Per-row UPDATE sink. Owns commit cadence (every commit_every processed
    rows + a final commit on close) and its own non-server-side cursor. Does
    NOT own the connection.
    """
    def __init__(self, conn, *, table: str = "documents",
                 pk: str = "document_id", commit_every: int = 500):
        self.conn = conn
        self.table = table
        self.pk = pk
        self.commit_every = commit_every
        self.cur = conn.cursor()
        self.processed = 0

    def write(self, rec: Record, result: ClassificationResult, writes) -> None:
        w = dict(writes)
        if "discipline_id" in w:
            w["discipline_id"] = int(w["discipline_id"])   # SQL needs int FK
        update_row(self.cur, table=self.table, pk=self.pk,
                   pk_value=rec.handle, writes=w)
        self.processed += 1
        if self.processed % self.commit_every == 0:
            self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.cur.close()
```

- [ ] **Step 2: Rewrite `classify_from_rds` to use `run`**

Overwrite `src/classifier/pipeline/classify_rds.py` (keep the module docstring),
preserving the stale-warning, logging, stats-dict shape, and `on_done`
behavior:

```python
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from classifier.io.rds import RdsReader, RdsWriter
from classifier.pipeline.run import run
from classifier.pipeline.staleness import stale_configs

log = logging.getLogger("classifier.rds")

TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")
DISCIPLINE_KEYWORDS_PATH = Path("src/classifier/config/discipline_keywords.py")
TYPE_TO_DISCIPLINE_PATH = Path("src/classifier/config/type_to_discipline.py")
CLASSIFIED_CSV_DIR = Path("input/classified_csv")

_GENERATED_CONFIGS = (
    (TYPE_KEYWORDS_PATH,       "learn-type-keywords"),
    (DISCIPLINE_KEYWORDS_PATH, "learn-discipline-keywords"),
    (TYPE_TO_DISCIPLINE_PATH,  "learn-type-discipline"),
)


def _stats_to_dict(stats) -> dict:
    return {
        "rows_scanned": stats.rows_scanned,
        "rows_updated": stats.rows_updated,
        "rows_skipped": stats.rows_skipped,
        "doc_type": dict(stats.reasons["doc_type"]),
        "type": dict(stats.reasons["type"]),
        "discipline_id": dict(stats.reasons["discipline_id"]),
        "callback_error": stats.callback_error,
    }


def classify_from_rds(
    conn,
    *,
    table: str = "documents",
    pk: str = "document_id",
    commit_every: int = 500,
    fetch_size: int = 1000,
    on_done: Callable[[dict], None] | None = None,
) -> dict:
    for path, tool in stale_configs(list(_GENERATED_CONFIGS), CLASSIFIED_CSV_DIR):
        log.warning("%s is older than training data; run %s", path.name, tool)

    log.info("classify_from_rds start: table=%s pk=%s", table, pk)
    start = time.monotonic()

    reader = RdsReader(conn, table=table, pk=pk, fetch_size=fetch_size)
    writer = RdsWriter(conn, table=table, pk=pk, commit_every=commit_every)

    def _progress(stats) -> None:
        if stats.rows_scanned % commit_every == 0:
            elapsed = time.monotonic() - start
            rate = stats.rows_scanned / elapsed if elapsed > 0 else 0.0
            log.info("progress: scanned=%d updated=%d elapsed=%.1fs rate=%.1f rows/s",
                     stats.rows_scanned, stats.rows_updated, elapsed, rate)

    stats = run(reader, writer, on_progress=_progress)

    elapsed = time.monotonic() - start
    log.info("done: scanned=%d updated=%d skipped=%d elapsed=%.1fs",
             stats.rows_scanned, stats.rows_updated, stats.rows_skipped, elapsed)

    result = _stats_to_dict(stats)
    if on_done is not None:
        try:
            on_done(result)
        except Exception as e:  # callback isolation -- never propagate
            log.warning("on_done callback raised: %r", e)
            result["callback_error"] = repr(e)
    return result
```

- [ ] **Step 3: Run the RDS fake-conn tests (must still pass)**

Run: `pytest tests/io/test_rds.py -v`
Expected: PASS (3 passed) — stats shape, write/skip, final commit, and `on_done` all preserved.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all PASS (Phase 0 baseline count + the new Phase 1/2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/io/rds.py src/classifier/pipeline/classify_rds.py
git commit -m "$(cat <<'EOF'
refactor(rds): classify_from_rds via RdsReader/RdsWriter + run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 3 — Collapse the scoring engine

Extract one generic phrase-scoring engine. `type_scoring` and `discipline_scoring` become thin callers differing only by rule table and key type. Behavior-preserving: the same thresholds, the same span-consumption algorithm, the same gates.

### Task 15: Snapshot the current pick_* behavior over the full corpus

**Files:**
- Create: `tests/core/test_scoring_snapshot.py`

This guard asserts the refactor produces identical `pick_type` / `pick_discipline` outputs across every training title.

- [ ] **Step 1: Write the snapshot guard**

Create `tests/core/test_scoring_snapshot.py`:

```python
"""Behavior-lock for the scoring collapse: pick_type / pick_discipline must
return identical results before and after the engine extraction, across every
title in the labelled training CSVs.
"""
from pathlib import Path
import csv

from classifier.core.type_scoring import score_types, pick_type
from classifier.core.discipline_scoring import score_disciplines, pick_discipline

CSV_DIR = Path("input/classified_csv")


def _titles():
    titles = []
    for p in sorted(CSV_DIR.rglob("*.csv")):   # sorted -> deterministic across machines
        with p.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = (row.get("title") or "").strip()
                if t:
                    titles.append(t)
    return titles[:2000]   # cap for runtime; sorted-path order is stable


def test_pick_type_is_deterministic_and_runs():
    # Smoke + determinism: same title twice -> same verdict.
    for t in _titles():
        a = pick_type(score_types(t))
        b = pick_type(score_types(t))
        assert a == b


def test_pick_discipline_is_deterministic_and_runs():
    for t in _titles():
        a = pick_discipline(score_disciplines(t))
        b = pick_discipline(score_disciplines(t))
        assert a == b
```

- [ ] **Step 2: Generate a frozen baseline of verdicts**

Add this one-off snapshot test that writes a baseline file the first run and
compares on subsequent runs. Append to `tests/core/test_scoring_snapshot.py`:

```python
import json

BASELINE = Path("tests/core/scoring_baseline.json")


def _verdicts():
    out = []
    for t in _titles():
        pt = pick_type(score_types(t))
        pd_ = pick_discipline(score_disciplines(t))
        out.append({"title": t,
                    "type": pt.get("type"), "type_conf": pt.get("confidence"),
                    "disc": pd_.get("discipline_id"), "disc_conf": pd_.get("confidence")})
    return out


def test_verdicts_match_frozen_baseline():
    current = _verdicts()
    if not BASELINE.exists():
        BASELINE.write_text(json.dumps(current, indent=0))
        return  # first run records the baseline
    saved = json.loads(BASELINE.read_text())
    assert current == saved, "scoring verdicts drifted from frozen baseline"
```

- [ ] **Step 3: Run to record the baseline against CURRENT code**

Run: `pytest tests/core/test_scoring_snapshot.py -v`
Expected: PASS (3 passed). The first run writes `tests/core/scoring_baseline.json`.

- [ ] **Step 4: Commit the baseline**

```bash
git add tests/core/test_scoring_snapshot.py tests/core/scoring_baseline.json
git commit -m "$(cat <<'EOF'
test: freeze scoring verdicts baseline before engine collapse

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 16: Extract the generic engine into `core/scoring.py`

**Files:**
- Create: `src/classifier/core/scoring.py`
- Create: `tests/core/test_scoring_engine.py`

- [ ] **Step 1: Write the engine test**

Create `tests/core/test_scoring_engine.py`:

```python
from classifier.core.scoring import score, pick


def test_score_matches_phrases_with_span_consumption():
    rules = {"AAA": [("VALVE LIST", 5), ("VALVE", 2)]}
    scores = score("VALVE LIST", rules)
    # "VALVE LIST" consumes the span; the lower-weight "VALVE" cannot re-score it
    assert scores["AAA"] == (5.0, 1)


def test_pick_high_confidence_gate():
    out = pick({"AAA": (5.0, 2), "BBB": (1.0, 1)})
    assert out["key"] == "AAA"
    assert out["confidence"] == "high"


def test_pick_none_when_below_min_score():
    out = pick({"AAA": (1.0, 1)})
    assert out["confidence"] == "none"
    assert out["key"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_scoring_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'classifier.core.scoring'`.

- [ ] **Step 3: Create `core/scoring.py` with the moved primitives + generic engine**

Create `src/classifier/core/scoring.py`. Move the primitives currently in
`type_scoring.py` (constants, `STOP_TOKENS`, `SINGULAR_FORMS`, `_depluralize`,
the regex constants, `canonicalize_title`, `_ngrams`, `candidate_phrases`,
`_index_phrases_in`, `_phrase_matches`) into it verbatim, then add the generic
`score`/`pick`:

```python
"""Generic phrase-scoring engine shared by type and discipline classification.

Holds the canonicalizer, n-gram/phrase primitives, the confidence knobs, and
the generic score()/pick(). type_scoring and discipline_scoring are thin
callers that supply a rule table and adapt the result shape.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Sequence

MIN_SCORE: float = 1.5
MIN_MARGIN: float = 1.0
SINGLE_PHRASE_FLOOR: float = 2.5

STOP_TOKENS: frozenset[str] = frozenset({
    "FOR", "AND", "OR", "OF", "THE", "TO", "WITH",
    "ON", "IN", "AT", "FROM", "INTO", "A", "AN",
})

SINGULAR_FORMS: frozenset[str] = frozenset({
    "CALCULATION", "DIAGRAM", "DRAWING", "INDEX",
    "LAYOUT", "LIST", "PROCEDURE", "PROCESS",
    "REPORT", "REQUISITION", "SCHEDULE", "SHEET",
    "SKETCH", "SPECIFICATION", "STANDARD",
})


def _depluralize(tok: str) -> str:
    if len(tok) >= 5 and tok.endswith("S"):
        if tok[:-1] in SINGULAR_FORMS:
            return tok[:-1]
        if tok.endswith("ES") and tok[:-2] in SINGULAR_FORMS:
            return tok[:-2]
    return tok


_DASHES = str.maketrans({
    "‐": " ", "‑": " ", "‒": " ",
    "–": " ", "—": " ", "―": " ",
    "−": " ", " ": " ",
})
_PARENS_RE = re.compile(r"\([^)]*\)")
_REV_NOISE_RE = re.compile(
    r"\b(\d+\s*SHEETS?|REV\s*\d+|SHEET\s+\d+\s+OF\s+\d+)\b"
)
_PUNCT_KEEP_AMP_SLASH_RE = re.compile(r"[^A-Z0-9&/ ]+")
_WS_RE = re.compile(r"\s+")


def canonicalize_title(raw: str) -> list[str]:
    if not raw:
        return []
    s = unicodedata.normalize("NFKC", str(raw))
    s = s.translate(_DASHES)
    s = s.upper()
    s = _PARENS_RE.sub(" ", s)
    s = _REV_NOISE_RE.sub(" ", s)
    s = _PUNCT_KEEP_AMP_SLASH_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return []
    return [_depluralize(t) for t in s.split(" ")]


def _ngrams(tokens: Sequence[str], n: int) -> list[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def candidate_phrases(tokens: Sequence[str],
                      extra_stop: frozenset[str] = frozenset()) -> list[tuple[str, ...]]:
    stop = STOP_TOKENS | extra_stop
    out: list[tuple[str, ...]] = []
    for n in (1, 2, 3):
        for ng in _ngrams(tokens, n):
            if any(tok in stop for tok in ng):
                continue
            out.append(ng)
    return out


def _index_phrases_in(tokens: Sequence[str], phrase_tokens: Sequence[str]) -> int:
    n, m = len(tokens), len(phrase_tokens)
    if m == 0 or m > n:
        return -1
    for i in range(n - m + 1):
        if all(tokens[i + j] == phrase_tokens[j] for j in range(m)):
            return i
    return -1


def _phrase_matches(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    return _index_phrases_in(tokens, phrase) >= 0


def score(title: str, rules: dict) -> dict:
    """Cumulative ``(score, n_phrases)`` per key from matching the rules.

    Generic over the key type (str type-code or int discipline-id). Span
    consumption is per-key: a higher-weight phrase consumes its span so an
    overlapping lower-weight phrase for the same key cannot re-score it.
    """
    tokens = canonicalize_title(title)
    if not tokens:
        return {}
    scores: dict = {}
    for key, krules in rules.items():
        consumed: list[tuple[int, int]] = []
        total = 0.0
        n_phrases = 0
        for phrase_text, weight in krules:
            phrase = phrase_text.split(" ")
            start = _index_phrases_in(tokens, phrase)
            if start < 0:
                continue
            end = start + len(phrase)
            if any(not (end <= cs or start >= ce) for cs, ce in consumed):
                continue
            consumed.append((start, end))
            total += weight
            n_phrases += 1
        if total > 0:
            scores[key] = (total, n_phrases)
    return scores


def pick(scores: dict) -> dict:
    """Generic confidence-gated choice. Returns
    ``{key, score, runner_up, runner_up_score, n_phrases, confidence}``.
    Ties broken by natural key order.
    """
    if not scores:
        return {"key": None, "score": 0.0, "runner_up": None,
                "runner_up_score": 0.0, "n_phrases": 0, "confidence": "none"}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    top_key, (top_score, top_n) = ranked[0]
    if len(ranked) > 1:
        rup_key, (rup_score, _) = ranked[1]
    else:
        rup_key, rup_score = None, 0.0
    if top_score < MIN_SCORE:
        confidence = "none"
    elif (top_score - rup_score) < MIN_MARGIN:
        confidence = "low"
    elif top_n < 2 and top_score < SINGLE_PHRASE_FLOOR:
        confidence = "low"
    else:
        confidence = "high"
    return {
        "key": top_key if confidence != "none" else None,
        "score": top_score,
        "runner_up": rup_key,
        "runner_up_score": rup_score,
        "n_phrases": top_n,
        "confidence": confidence,
    }
```

- [ ] **Step 4: Run the engine test**

Run: `pytest tests/core/test_scoring_engine.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/core/scoring.py tests/core/test_scoring_engine.py
git commit -m "$(cat <<'EOF'
feat(core): generic phrase-scoring engine (score/pick)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 17: Re-point `type_scoring` onto the engine

**Files:**
- Modify: `src/classifier/core/type_scoring.py`

- [ ] **Step 1: List every external importer of `type_scoring` names**

Run: `grep -rn "from classifier.core.type_scoring import\|classifier.core.type_scoring" src tests`
Record every imported name (the learners in `tools/` import `canonicalize_title`
and may import `candidate_phrases`, `STOP_TOKENS`, `_index_phrases_in`,
`_depluralize`, `SINGULAR_FORMS`). The re-export block in Step 2 MUST include
every name found here, or those importers break. If you find a name not in the
Step 2 re-export list, add it to the re-export.

- [ ] **Step 2: Replace the moved primitives with imports and adapt the public functions**

Overwrite `src/classifier/core/type_scoring.py` so it imports the primitives
from `scoring` (re-exporting `canonicalize_title` etc. for the learners), and
reimplements `score_types` / `pick_type` as thin adapters. Keep
`pick_type_with_overrides` (override / negative / fallback logic) intact but
sourcing primitives from `scoring`:

```python
"""Type-level scoring: thin adapter over the generic engine in core.scoring.

Re-exports the canonicalizer and primitives so existing importers (learners,
discipline_scoring) keep working.
"""
from __future__ import annotations

from typing import Sequence

from classifier.core.scoring import (  # noqa: F401  (re-exported)
    MIN_SCORE, MIN_MARGIN, SINGLE_PHRASE_FLOOR,
    STOP_TOKENS, SINGULAR_FORMS, _depluralize,
    canonicalize_title, candidate_phrases,
    _ngrams, _index_phrases_in, _phrase_matches,
    score as _score, pick as _pick,
)


def score_types(title: str) -> dict[str, tuple[float, int]]:
    from classifier.config.type_keywords import TYPE_KEYWORD_RULES
    return _score(title, TYPE_KEYWORD_RULES)


def pick_type(scores: dict[str, tuple[float, int]]) -> dict:
    p = _pick(scores)
    return {
        "type": p["key"] if p["key"] is not None else "",
        "score": p["score"],
        "runner_up": p["runner_up"] if p["runner_up"] is not None else "",
        "runner_up_score": p["runner_up_score"],
        "n_phrases": p["n_phrases"],
        "confidence": p["confidence"],
    }


def pick_type_with_overrides(title: str) -> dict:
    from classifier.config.type_overrides import HARD_OVERRIDES, NEGATIVE_KEYWORDS

    tokens = canonicalize_title(title)
    if not tokens:
        result = pick_type({})
        result["reason"] = "none"
        return result

    # Phase 1: hard overrides (longest phrase wins; alpha tie-break).
    override_hits: list[tuple[int, str]] = []
    for type_code, phrases in HARD_OVERRIDES.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            if _phrase_matches(tokens, phrase):
                override_hits.append((len(phrase), type_code))
                break
    if override_hits:
        override_hits.sort(key=lambda t: (-t[0], t[1]))
        return {
            "type": override_hits[0][1], "score": float("inf"),
            "runner_up": "", "runner_up_score": 0.0,
            "n_phrases": 1, "confidence": "high", "reason": "override",
        }

    # Phase 2: learned scoring.
    scores = score_types(title)

    # Phase 3: negative-keyword suppression.
    NEGATIVE_MULTIPLIER: float = 0.0
    for type_code, neg_phrases in NEGATIVE_KEYWORDS.items():
        if type_code not in scores:
            continue
        for phrase in neg_phrases:
            if _phrase_matches(tokens, phrase):
                cur_score, cur_n = scores[type_code]
                scores[type_code] = (cur_score * NEGATIVE_MULTIPLIER, cur_n)
                break
    scores = {t: v for t, v in scores.items() if v[0] > 0}

    # Phase 4: pick.
    result = pick_type(scores)
    result["reason"] = "scored" if result["confidence"] != "none" else "none"

    # Phase 5: DRAWING / SKETCH fallback.
    if result["confidence"] == "none":
        if "DRAWING" in tokens or "SKETCH" in tokens:
            return {
                "type": "DWG", "score": float("inf"),
                "runner_up": "", "runner_up_score": 0.0,
                "n_phrases": 1, "confidence": "high", "reason": "fallback",
            }
    return result
```

- [ ] **Step 3: Run the type tests + scoring snapshot**

Run: `pytest tests/core/test_scoring_snapshot.py tests/core/test_classify_record.py tests/pipeline/test_row_class.py -v`
Expected: PASS — verdicts match the frozen baseline.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/core/type_scoring.py
git commit -m "$(cat <<'EOF'
refactor(core): type_scoring as thin adapter over scoring engine

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 18: Re-point `discipline_scoring` onto the engine

**Files:**
- Modify: `src/classifier/core/discipline_scoring.py`

- [ ] **Step 1: Rewrite using the engine**

Overwrite `src/classifier/core/discipline_scoring.py`:

```python
"""Discipline-level scoring: thin adapter over the generic engine, plus the
type-hint bonus. See module history for the calibration rationale.
"""
from __future__ import annotations

from classifier.core.scoring import score as _score, pick as _pick

TYPE_HINT_BONUS: float = 2.0


def score_disciplines(title: str, type_hint: str | None = None
                      ) -> dict[int, tuple[float, int]]:
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
    scores = _score(title, DISCIPLINE_KEYWORDS)

    if type_hint:
        try:
            from classifier.config.type_to_discipline import TYPE_TO_DISCIPLINE
        except ImportError:
            TYPE_TO_DISCIPLINE = {}
        hint_disc = TYPE_TO_DISCIPLINE.get(type_hint.strip().upper())
        if hint_disc is not None:
            cur_score, cur_n = scores.get(hint_disc, (0.0, 0))
            scores[hint_disc] = (cur_score + TYPE_HINT_BONUS, cur_n)
    return scores


def pick_discipline(scores: dict[int, tuple[float, int]]) -> dict:
    p = _pick(scores)
    return {"discipline_id": p["key"], "confidence": p["confidence"]}


def pick_discipline_with_overrides(title: str, type_hint: str | None = None
                                   ) -> dict:
    pick = pick_discipline(score_disciplines(title, type_hint=type_hint))
    pick["reason"] = "keyword" if pick["confidence"] != "none" else "miss"
    return pick
```

Note: `_score` returns `{}` for an empty title, then the type-hint bonus is
applied unconditionally — identical to the previous `if tokens:`-guarded
keyword scoring followed by an unconditional bonus.

- [ ] **Step 2: Run the discipline + snapshot + full suite**

Run: `pytest -q`
Expected: all PASS — scoring verdicts still match the frozen baseline; nothing else regressed.

- [ ] **Step 3: Commit**

```bash
git add src/classifier/core/discipline_scoring.py
git commit -m "$(cat <<'EOF'
refactor(core): discipline_scoring as thin adapter over scoring engine

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 4 — Tidy SoC leftovers (low risk)

### Task 19: Single fold-to-class function

**Files:**
- Create: `src/classifier/core/folding.py`
- Modify: `src/classifier/core/classify.py` (use it in `normalize_doc_type`)
- Modify: `src/classifier/tools/convert_classified.py` (use it in `_doc_type_for`)
- Create: `tests/core/test_folding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_folding.py`:

```python
from classifier.core.folding import doc_type_for_bucket


def test_drawings_bucket_folds_to_drawing():
    assert doc_type_for_bucket("Drawings") == "drawing"
    assert doc_type_for_bucket("Isometrics") == "drawing"


def test_lists_bucket_folds_to_sheet():
    assert doc_type_for_bucket("Lists_MTOs_BOMs") == "sheet"


def test_other_buckets_fold_to_document():
    assert doc_type_for_bucket("Specifications") == "document"
    assert doc_type_for_bucket("Reports") == "document"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_folding.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the fold function**

Create `src/classifier/core/folding.py`:

```python
"""Single source of truth for bucket -> user-facing doc_type folding."""
from __future__ import annotations

from classifier.config.buckets import BUCKET_TO_CLASS


def doc_type_for_bucket(bucket: str) -> str:
    """Return the lowercase doc_type ("drawing"/"sheet"/"document") for a bucket."""
    folded = BUCKET_TO_CLASS[bucket]
    return {"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")
```

- [ ] **Step 4: Use it in `core/classify.py`**

In `src/classifier/core/classify.py`, add the import:

```python
from classifier.core.folding import doc_type_for_bucket
```
and in `normalize_doc_type`, replace these two lines:
```python
            folded = BUCKET_TO_CLASS[bucket]
            reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
            cls = {"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")
```
with:
```python
            reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
            cls = doc_type_for_bucket(bucket)
```
Remove the now-unused `BUCKET_TO_CLASS` from the import if nothing else uses it
(`TYPE_TO_BUCKET` is still used — keep it).

- [ ] **Step 5: Use it in `convert_classified.py`**

In `src/classifier/tools/convert_classified.py`, change the import line 21 from:
```python
from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
```
to:
```python
from classifier.config.buckets import TYPE_TO_BUCKET
from classifier.core.folding import doc_type_for_bucket
```
and in `_doc_type_for` (lines 116-117), replace:
```python
    folded = BUCKET_TO_CLASS[bucket]
    return {"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")
```
with:
```python
    return doc_type_for_bucket(bucket)
```

- [ ] **Step 6: Run folding test, golden, and full suite**

Run: `pytest tests/core/test_folding.py tests/golden/ -q && pytest -q`
Expected: all PASS — the golden proves `normalize_doc_type` is unchanged.

- [ ] **Step 7: Commit**

```bash
git add src/classifier/core/folding.py src/classifier/core/classify.py src/classifier/tools/convert_classified.py tests/core/test_folding.py
git commit -m "$(cat <<'EOF'
refactor: single doc_type_for_bucket fold function

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 20: Split workbook I/O out of `core/table_detect.py`

**Files:**
- Create: `src/classifier/io/workbook.py`
- Modify: `src/classifier/core/table_detect.py` (remove `iter_grids`/`file_has_table`, dedupe `_is_empty`)
- Modify: `tests/core/test_table_detect.py` (move `file_has_table` import)
- Create: `tests/io/test_workbook.py`

- [ ] **Step 1: Create `io/workbook.py` with the moved I/O functions**

Create `src/classifier/io/workbook.py`:

```python
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
```

- [ ] **Step 2: Trim `core/table_detect.py`**

In `src/classifier/core/table_detect.py`, delete `iter_grids` (lines 89-115)
and `file_has_table` (lines 118-126). Replace the private `_is_empty`
(lines 29-31) usage with the shared `is_empty`: add at the top
```python
from classifier.io.normalize import is_empty as _is_empty
```
and delete the local `def _is_empty(cell)...` definition. (Keep `_is_text`,
`_header_cols`, `TableHit`, `_row_fills_cols`, `find_table`.)

Verify `is_empty` from `io.normalize` is behavior-compatible here: it returns
True for None and whitespace-only strings (the cells are values from a grid).
It additionally treats the literal strings "NULL"/"nan" as empty — acceptable
for table detection (a cell literally containing "NULL" is not real data).

- [ ] **Step 3: Update callers of the moved functions**

Search for importers: `grep -rn "from classifier.core.table_detect import" src tests`.
Any import of `iter_grids` or `file_has_table` from `core.table_detect` must
change to `from classifier.io.workbook import ...`. Update
`tests/core/test_table_detect.py` line 2-8 to import `file_has_table` from
`classifier.io.workbook` (keep `find_table`, `_header_cols`, the constants from
`core.table_detect`). Check `tools/learn_sheet_patterns.py` and any other tool
for these imports and repoint them.

- [ ] **Step 4: Move the file-based table tests**

Create `tests/io/test_workbook.py` and move the two file-based tests
(`test_file_has_table_finds_table_behind_cover_sheet` and
`test_file_has_table_returns_none_for_form`) out of
`tests/core/test_table_detect.py` into it:

```python
import openpyxl
from classifier.io.workbook import file_has_table


def test_file_has_table_finds_table_behind_cover_sheet(tmp_path):
    wb = openpyxl.Workbook()
    cover = wb.active
    cover.title = "Cover"
    cover["B2"] = "PROJECT TITLE"
    idx = wb.create_sheet("Index")
    idx.append(["Sr No", "Area", "Line Number", "ISO Dwg"])
    for i in range(1, 9):
        idx.append([i, f"01{i:03d}P", f'3"-D-{i}', f"16-01-15-{i}"])
    p = tmp_path / "iso_index.xlsx"
    wb.save(p)

    hit = file_has_table(str(p))
    assert hit is not None
    assert hit[0] == "Index"
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

Then delete those two test functions (and the now-unused `file_has_table`
import) from `tests/core/test_table_detect.py`.

- [ ] **Step 5: Run the table + workbook tests + full suite**

Run: `pytest tests/core/test_table_detect.py tests/io/test_workbook.py -q && pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/classifier/io/workbook.py src/classifier/core/table_detect.py tests/core/test_table_detect.py tests/io/test_workbook.py
git commit -m "$(cat <<'EOF'
refactor: move workbook I/O out of core.table_detect into io.workbook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 21: Update docs to match the new structure

**Files:**
- Modify: `README.md`
- Modify: `INTEGRATION.md`

- [ ] **Step 1: Fix the README architecture/tunables sections**

In `README.md`, update the stale references so they point at real locations:
- The fold function: replace `core/scoring.py` `fold_to_class()` reference with
  `doc_type_for_bucket()` in `src/classifier/core/folding.py`.
- `config/keywords.py` → `src/classifier/config/type_keywords.py` and
  `src/classifier/config/discipline_keywords.py` (generated).
- `config/patterns.py` → remove (no such file); patterns live in
  `src/classifier/config/type_overrides.py`.
- Add a short "Execution backends & output producers" note: the core entry is
  `classifier.core.classify.classify_record`; backends implement
  `RecordReader`/`ResultWriter` and run through `classifier.pipeline.run.run`.
- Update the layering diagram to show `core/scoring.py` as the engine and
  `core/classify.py` as the per-row entry.

- [ ] **Step 2: Fix INTEGRATION.md cross-references**

In `INTEGRATION.md`, verify the import examples still resolve
(`classifier.pipeline.classify_rds.classify_from_rds`,
`classifier.pipeline.classify_titles.classify_titles`,
`classifier.io.rds.iter_unclassified`/`update_row`) — all preserved by this
refactor. Add a one-line note that new output producers implement
`ResultWriter` and run via `classifier.pipeline.run.run` with no core changes.

- [ ] **Step 3: Sanity-check the doc references resolve**

Run: `grep -rn "core/scoring.py\|config/keywords.py\|config/patterns.py\|fold_to_class" README.md INTEGRATION.md`
Expected: no stale matches remain (only the corrected references).

- [ ] **Step 4: Run the full suite one final time**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md INTEGRATION.md
git commit -m "$(cat <<'EOF'
docs: align README/INTEGRATION with separated architecture

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] Run the complete suite: `pytest -q` — all green.
- [ ] Confirm the golden is byte-identical: `pytest tests/golden/ -v`.
- [ ] Confirm scoring verdicts unchanged: `pytest tests/core/test_scoring_snapshot.py -v`.
- [ ] Spot-check the CLIs still run: `classify` against the sample input produces the same `output/classified.csv` (diff against the committed file).
- [ ] Verify a new producer needs zero core edits: writing a `JsonlWriter` (per the spec's worked example) and running `run(RdsReader(conn), JsonlWriter(path))` touches no file under `core/` or `pipeline/run.py`.
