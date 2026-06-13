# Learn Disciplines & Type Fallback from Dossiers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the ~50% null `discipline_id` rate by re-keying/expanding the discipline keyword buckets to the authoritative taxonomy from the EPC/FEED dossiers and adding a gated type→discipline fallback.

**Architecture:** Hand-author the mined dossier phrases into `config/discipline_keywords.py` (corrected canonical ids) and `config/type_to_discipline.py` (7 pure types). Add the fallback at the write gate `core/classify.py::fill_discipline`: when title keywords don't yield a high-confidence discipline but the row's type is one of the pure types, write that discipline with reason `via_type`. The throwaway miner (`scripts/mine_dossiers.py`, already written, untracked) produced the phrase candidates; it is not part of the package.

**Tech Stack:** Python 3.13/3.14, pytest, openpyxl (miner only). Source under `src/classifier`, tests under `tests/`. Run via `.venv/Scripts/python.exe` with `PYTHONPATH=src` (or the installed editable package).

**Spec:** [docs/superpowers/specs/2026-06-13-learn-dossier-disciplines-design.md](../specs/2026-06-13-learn-dossier-disciplines-design.md)

---

## File Structure

- `src/classifier/config/type_to_discipline.py` — **rewrite**: 7 pure types, canonical ids.
- `src/classifier/config/discipline_keywords.py` — **rewrite**: re-keyed + expanded buckets (ids 1, 3, 6, 7, 8, 11).
- `src/classifier/core/classify.py` — **modify** `fill_discipline` only (add fallback branch + import).
- `tests/io/test_type_to_discipline.py` — **create**: pure-type mappings + valid-id subset.
- `tests/core/test_discipline_keywords.py` — **create**: canonical-id resolution per discipline.
- `tests/core/test_discipline_type_fallback.py` — **create**: fallback behaviour.
- `tests/core/test_class_precedence.py`, `tests/pipeline/test_reason_baseline.py`, any scoring snapshot — **update** to corrected ids if they assert old ids.
- `scripts/mine_dossiers.py` — exists, **untracked**, never staged.

The confidence knobs that matter (in `core/scoring.py`): `MIN_SCORE=1.5`, `MIN_MARGIN=1.0`, `SINGLE_PHRASE_FLOOR=2.5`. A lone distinctive phrase must weigh ≥ 2.5 to classify at `"high"` on its own; the curated weights below respect that.

---

## Task 1: Rewrite `type_to_discipline.py` with the 7 pure types

**Files:**
- Modify: `src/classifier/config/type_to_discipline.py`
- Test: `tests/io/test_type_to_discipline.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/io/test_type_to_discipline.py`:

```python
from classifier.config.type_to_discipline import TYPE_TO_DISCIPLINE
from classifier.io.disciplines import load_valid_discipline_ids


def test_pure_type_mappings_canonical_ids():
    assert TYPE_TO_DISCIPLINE == {
        "PID": 11, "PFD": 11, "MSD": 11, "PSF": 11,
        "DSL": 3, "DSD": 3,
        "DGA": 8,
    }


def test_values_are_valid_discipline_ids():
    valid = load_valid_discipline_ids()
    assert set(TYPE_TO_DISCIPLINE.values()).issubset(valid)


def test_ambiguous_types_absent():
    for t in ("DAS", "REP", "SPC", "LST", "DAL", "CAL", "DWG", "REQ", "SCH"):
        assert t not in TYPE_TO_DISCIPLINE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/io/test_type_to_discipline.py -v`
Expected: FAIL — current table is `{'DBD': 4, 'DGA': 13, 'DSL': 4}`.

- [ ] **Step 3: Rewrite the config**

Replace the body of `src/classifier/config/type_to_discipline.py` (keep the module docstring style):

```python
"""Hand-maintained: type -> discipline_id fallback.

Only "pure" dossier types (100% concentrated in one discipline, support >= 3 in
learn/*.xlsx) are listed, so an ambiguous type never forces a discipline.
Used two ways: a +2 score bonus in discipline_scoring, and the gated
write-time fallback in core.classify.fill_discipline. Ids are canonical
(input/disciplines.csv). Comments record dossier support.
"""
from __future__ import annotations

TYPE_TO_DISCIPLINE: dict[str, int] = {
    "PID": 11,  # Process — 24/24 (P&ID filed under Process in both dossiers)
    "PFD": 11,  # Process — 6/6
    "MSD": 11,  # Process — 5/5
    "PSF": 11,  # Process — 3/3
    "DSL": 3,   # Electrical — 14/14 (single line diagram)
    "DSD": 3,   # Electrical — 3/3
    "DGA": 8,   # Piping — 12/12 (piping GA)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/io/test_type_to_discipline.py tests/io/test_disciplines.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/config/type_to_discipline.py tests/io/test_type_to_discipline.py
git commit -m "feat(classify): type->discipline fallback uses 7 pure dossier types"
```

---

## Task 2: Rewrite `discipline_keywords.py` with corrected canonical buckets

The old buckets are re-keyed (Electrical 4→3, instrumentation 7→6, tank/vessel 10→7, Piping 13→8; Civil 1 stays) and expanded with dossier phrases. Project/doc-no noise (`SAHIL`, `CDS`, bare numbers, `&`) and cross-discipline type words (`SHEET`, `DATA`, bare `DIAGRAM`/`DRAWING`/`DETAILS`) are excluded.

**Files:**
- Modify: `src/classifier/config/discipline_keywords.py`
- Test: `tests/core/test_discipline_keywords.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_discipline_keywords.py`:

```python
import pytest
from classifier.core.discipline_scoring import (
    score_disciplines, pick_discipline,
)


def _id(title):
    return pick_discipline(score_disciplines(title))["discipline_id"]


@pytest.mark.parametrize("title, expected", [
    ("SINGLE LINE DIAGRAM SUBSTATION", 3),     # Electrical
    ("ELECTRICAL LIGHTING LAYOUT", 3),
    ("PIPING LAYOUT DRAWING AREA 01", 8),       # Piping
    ("PIPING ISOMETRIC", 8),
    ("PIPING & INSTRUMENT DIAGRAM WATER", 11),  # Process (P&ID)
    ("PROCESS FLOW DIAGRAM", 11),
    ("FOUNDATION DETAILS STEEL STRUCTURE", 1),  # Civil
    ("CIVIL GENERAL ARRANGEMENT", 1),
    ("WATER DISPOSAL TANK", 7),                 # Mechanical
    ("ACTING REGULATORS DATA SHEET", 6),        # I&C
])
def test_titles_resolve_to_canonical_discipline(title, expected):
    assert _id(title) == expected


def test_keys_are_all_valid_discipline_ids():
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
    from classifier.io.disciplines import load_valid_discipline_ids
    assert set(DISCIPLINE_KEYWORDS).issubset(load_valid_discipline_ids())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/core/test_discipline_keywords.py -v`
Expected: FAIL — e.g. "SINGLE LINE DIAGRAM SUBSTATION" currently resolves to 4, not 3.

- [ ] **Step 3: Rewrite the config**

Replace `src/classifier/config/discipline_keywords.py` in full:

```python
"""Hand-maintained per-discipline title scoring.

Keys are canonical discipline ids (input/disciplines.csv). Authored from the
learn/*.xlsx dossiers (see docs/superpowers/specs/2026-06-13-learn-dossier-
disciplines-design.md). Project/doc-no noise and cross-discipline type words
are deliberately excluded. Weights follow core.scoring thresholds: a lone
distinctive phrase weighs >= 2.5 so it classifies at "high" alone.
"""
from __future__ import annotations

UNTRAINED_DISCIPLINES: frozenset[int] = frozenset()

DISCIPLINE_KEYWORDS: dict[int, tuple[tuple[str, float], ...]] = {
    1: (  # Civil
        ('FOUNDATION', 3.2),
        ('FOUNDATION DETAILS', 2.6),
        ('STEEL STRUCTURE', 3.0),
        ('STEEL', 2.5),
        ('STRUCTURE', 2.5),
        ('CIVIL GENERAL ARRANGEMENT', 2.8),
        ('GENERAL ARRANGEMENT LAYOUT', 2.6),
        ('CIVIL', 2.4),
        ('TOPOGRAPHICAL', 2.3),
        ('PIPE RACK', 2.0),
    ),
    3: (  # Electrical
        ('SINGLE LINE DIAGRAM', 3.5),
        ('SINGLE LINE', 3.2),
        ('LINE DIAGRAM', 2.8),
        ('SUBSTATION', 3.0),
        ('SUBSTATION NO', 2.6),
        ('ELECTRICAL', 2.8),
        ('LIGHTING', 2.4),
        ('EARTHING', 2.4),
    ),
    6: (  # I&C
        ('TRANSMITTERS', 2.8),
        ('ELECTRONIC TRANSMITTERS', 2.8),
        ('ACTING REGULATORS', 2.6),
        ('PRESSURE GAUGES', 2.5),
        ('ROTAMETER', 2.5),
        ('MULTIPHASE FLOW METER', 2.6),
        ('AREA FLOWMETER', 2.4),
        ('ICSS', 2.4),
    ),
    7: (  # Mechanical (incl. tanks/vessels, ex-id-10)
        ('WATER DISPOSAL TANK', 3.2),
        ('DISPOSAL TANK', 2.8),
        ('WATER PUMPS', 2.6),
        ('MECHANICAL DATA SHEET', 2.6),
        ('MECHANICAL', 2.5),
        ('EOT CRANE', 2.4),
        ('NOZZLES DETAILS', 2.2),
        ('SHELL', 2.0),
    ),
    8: (  # Piping
        ('PIPING LAYOUT DRAWING', 3.4),
        ('PIPING LAYOUT', 3.0),
        ('PIPING ISOMETRIC', 3.0),
        ('ISOMETRIC', 2.6),
        ('PIPING GA', 2.8),
        ('PIPING GA CONSTRUCTION', 2.8),
        ('VALVES', 2.4),
        ('FITTINGS', 2.4),
    ),
    11: (  # Process
        ('PIPING & INSTRUMENT', 3.5),
        ('INSTRUMENT DIAGRAM', 3.2),
        ('PROCESS FLOW DIAGRAM', 3.2),
        ('FLOW DIAGRAM', 2.6),
        ('PROCESS', 2.4),
        ('MATERIAL SELECTION DIAGRAM', 2.8),
        ('SAFEGUARDING', 2.4),
    ),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/core/test_discipline_keywords.py -v`
Expected: PASS (11 cases). If a title lands on the wrong id, check for a colliding phrase across buckets (e.g. don't add bare `PIPING`/`INSTRUMENT`/`DIAGRAM` to any bucket) and adjust weights so the intended bucket clears `MIN_MARGIN`.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/config/discipline_keywords.py tests/core/test_discipline_keywords.py
git commit -m "feat(classify): re-key + expand discipline buckets from dossiers"
```

---

## Task 3: Add the gated type→discipline fallback in `fill_discipline`

**Files:**
- Modify: `src/classifier/core/classify.py` (`fill_discipline`, ~lines 72-83, + import)
- Test: `tests/core/test_discipline_type_fallback.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_discipline_type_fallback.py`:

```python
from classifier.core.classify import fill_discipline


def test_pure_type_rescues_blank_title():
    # title scores no discipline; PID is a pure type -> Process (11)
    assert fill_discipline("", "ZZZ NONSENSE", type_hint="PID") == ("11", "via_type")


def test_pure_type_rescues_when_keyword_low():
    # garbage title, DSL pure type -> Electrical (3)
    assert fill_discipline("", "QWERTY", type_hint="DSL") == ("3", "via_type")


def test_ambiguous_type_does_not_rescue():
    assert fill_discipline("", "ZZZ NONSENSE", type_hint="DAS") == ("", "miss")


def test_no_type_still_misses():
    assert fill_discipline("", "ZZZ NONSENSE")[1] == "miss"


def test_keyword_high_beats_type_fallback():
    # title clearly Electrical via keywords; even with a Process type hint,
    # the high-confidence keyword discipline (3) wins and reason is via_keyword.
    val, reason = fill_discipline("", "SINGLE LINE DIAGRAM SUBSTATION", type_hint="PID")
    assert val == "3" and reason == "via_keyword"


def test_existing_discipline_preserved():
    assert fill_discipline("8", "anything", type_hint="PID") == ("8", "preserved")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/core/test_discipline_type_fallback.py -v`
Expected: FAIL — `test_pure_type_rescues_blank_title` returns `("", "miss")` today.

- [ ] **Step 3: Modify `fill_discipline`**

In `src/classifier/core/classify.py`, add the import near the other config imports (after line 12, `from classifier.config.buckets import TYPE_TO_BUCKET`):

```python
from classifier.config.type_to_discipline import TYPE_TO_DISCIPLINE
```

Replace the body of `fill_discipline` (lines 72-83) with:

```python
def fill_discipline(row_disc: str, title: str,
                    type_hint: str = "") -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / via_type / miss.

    ``value`` is the discipline_id as a decimal string when found, else "".
    Falls back to a pure type->discipline mapping when title keywords do not
    yield a high-confidence discipline (the value that would otherwise be a miss).
    """
    if not is_empty(row_disc):
        return str(row_disc).strip(), "preserved"
    pick = pick_discipline_with_overrides(title, type_hint=type_hint or None)
    if pick["confidence"] == "high" and pick["discipline_id"] is not None:
        return str(pick["discipline_id"]), "via_keyword"
    fb = TYPE_TO_DISCIPLINE.get(type_hint.strip().upper()) if type_hint else None
    if fb is not None:
        return str(fb), "via_type"
    return "", "miss"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/core/test_discipline_type_fallback.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/core/classify.py tests/core/test_discipline_type_fallback.py
git commit -m "feat(classify): gated type->discipline fallback at write boundary"
```

---

## Task 4: Reconcile existing tests + measure null reduction

**Files:**
- Modify (only if failing): `tests/core/test_class_precedence.py`, `tests/core/test_classify_record.py`, `tests/pipeline/test_reason_baseline.py`, any scoring snapshot test.

- [ ] **Step 1: Run the full suite to find fallout**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`
Expected: the three new test files pass; any failures are pre-existing tests asserting the **old** discipline ids (4/7/10/13) or `via_keyword`-only discipline reasons.

- [ ] **Step 2: Fix each failing assertion to the corrected id / reason**

For every failure, update the expected value to the canonical id (Electrical 3, I&C 6, Mechanical 7, Piping 8, Process 11) or accept `via_type` where a pure type now fills a previously-null discipline. Do **not** weaken a test to `pass`; change it to assert the correct new behaviour. Re-read the spec's "Decisions" if unsure which id is correct. Example (illustrative — match the real assertion in the file):

```python
# before:  assert res.discipline_id.value == "4"   # legacy Electrical id
# after:   assert res.discipline_id.value == "3"    # canonical Electrical (disciplines.csv)
```

- [ ] **Step 3: Re-run the full suite**

Run: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`
Expected: PASS, no failures.

- [ ] **Step 4: Measure the null-discipline reduction on the snapshot**

Run (counts blank/null discipline before vs after across the input snapshot):

```bash
PYTHONPATH=src .venv/Scripts/python.exe -c "
import csv
from classifier.core.classify import fill_discipline, fill_type
null_before = filled = 0
with open('input/_document__202606051455.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if (row.get('discipline_id') or '').strip():
            continue
        null_before += 1
        ty, _ = fill_type(row.get('type','') or '', row.get('title','') or '')
        val, reason = fill_discipline('', row.get('title','') or '', type_hint=ty)
        if val:
            filled += 1
print(f'rows null in source: {null_before}')
print(f'now filled by classifier: {filled}')
print(f'still null: {null_before - filled}')
"
```

Expected: `now filled` is a large fraction of `rows null in source` (the spec's goal — report the actual numbers; do not assert a hard threshold). Record the figures in the commit body.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test(classify): reconcile discipline ids to canonical taxonomy

Null-discipline reduction on input snapshot: <filled>/<null_before> rows
recovered (was 0)."
```

---

## Task 5: Confirm the miner stays untracked

- [ ] **Step 1: Verify the throwaway miner is not staged**

Run: `git status --porcelain scripts/`
Expected: `scripts/` shows as untracked (`??`) and is **not** part of any commit above. Leave it on disk for re-runs; do not `git add` it. If the repo policy is to ignore it, add `scripts/` to `.gitignore` in a separate housekeeping commit (optional, out of scope here).

---

## Self-Review notes (author)

- **Spec coverage:** Task 1 ↔ spec §3 (type_to_discipline); Task 2 ↔ §2 (discipline_keywords re-key/expand); Task 3 ↔ §4 (fill_discipline fallback); Task 4 ↔ spec "Testing" + "Success criteria"; Task 5 ↔ §"scripts/mine_dossiers.py (throwaway)".
- **Uncovered disciplines** (QA/QC-13 etc.) intentionally get no rules — matches spec "Out of scope".
- **Type consistency:** `fill_discipline(row_disc, title, type_hint="")` signature unchanged; `pick_discipline_with_overrides` reused as-is; `TYPE_TO_DISCIPLINE` values are ints (matches `pick`/SQL int contract and `test_values_are_valid_discipline_ids`).
- **Known judgement call to verify at impl time:** ex-id-10 tank/vessel keywords are placed under Mechanical-7; if the DB treats vessels/tanks as Mechanical Static-36, re-key bucket 7→36 in Task 2 and its test.
