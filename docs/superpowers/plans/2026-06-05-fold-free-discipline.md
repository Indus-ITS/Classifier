# Fold-free Discipline Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the client→DEST discipline fold; train discipline rules directly on the labelled `discipline_id` (already `disciplines.csv` ids), validated against `disciplines.csv`. Type classification unchanged.

**Architecture:** Two existing learner tools are made fold-free; `input/discipline_fold.csv` is deleted; the two generated config dicts + golden + scoring baseline are regenerated. The runtime (`core/discipline_scoring.py`) is untouched.

**Tech Stack:** Python 3.10+, pandas, pytest.

**Spec:** `docs/superpowers/specs/2026-06-05-curated-discipline-classification-design.md`

**Conventions for every task:**
- Run tests with `python -m pytest` from the repo root.
- Run the learner tools with `PYTHONPATH=src python -m classifier.tools.<module>` (works without an editable install).
- Windows: PowerShell cmdlets via the Bash tool are BLOCKED — use Read/Write/Edit tools and POSIX commands (`python`, `git`, `cp`).
- Do NOT stage/commit `docs/superpowers/plans/2026-06-05-sheets-class-phase2.md`. `git add` only the files each task lists.
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Baseline at start: 93 tests pass.

---

## File Structure

| File | Change |
|---|---|
| `src/classifier/tools/learn_discipline_keywords.py` | remove fold; train on raw validated ids |
| `src/classifier/tools/learn_type_discipline.py` | remove fold; raw validated ids |
| `tests/tools/__init__.py` | new (empty) |
| `tests/tools/test_learn_discipline_keywords.py` | new — no-fold + orphan behavior |
| `tests/tools/test_learn_type_discipline.py` | new — raw-id majority behavior |
| `input/discipline_fold.csv` | deleted |
| `src/classifier/config/discipline_keywords.py` | regenerated (data) |
| `src/classifier/config/type_to_discipline.py` | regenerated (data) |
| `tests/golden/classified.csv` | regenerated (discipline_id column only) |
| `tests/core/scoring_baseline.json` | regenerated (disc fields only) |
| `INTEGRATION.md`, `README.md` | docs: drop fold narrative |

---

### Task 1: Make `learn_discipline_keywords` fold-free (+ tests)

**Files:**
- Modify: `src/classifier/tools/learn_discipline_keywords.py`
- Create: `tests/tools/__init__.py` (empty)
- Create: `tests/tools/test_learn_discipline_keywords.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/__init__.py` (empty) and `tests/tools/test_learn_discipline_keywords.py`:

```python
import csv
import classifier.tools.learn_discipline_keywords as L


def _write(path, rows):
    cols = ["discipline_id", "title"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def test_no_fold_symbols():
    # The fold is gone entirely.
    assert not hasattr(L, "_load_fold")
    assert not hasattr(L, "DISCIPLINE_FOLD_CSV")


def test_collect_rows_uses_raw_id_no_remap(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [{"discipline_id": "8", "title": "VALVE LIST"},
                         {"discipline_id": "8", "title": "MTO FOR PIPES"}])
    monkeypatch.setattr(L, "CSV_ROOT", d)
    rows, orphans = L._collect_rows(frozenset({1, 8}))
    assert sorted(rows_d := [dd for dd, _, _ in rows]) == [8, 8]
    assert orphans == {}


def test_collect_rows_drops_id_not_in_disciplines(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [{"discipline_id": "999", "title": "X"},
                         {"discipline_id": "8", "title": "VALVE"}])
    monkeypatch.setattr(L, "CSV_ROOT", d)
    rows, orphans = L._collect_rows(frozenset({8}))
    assert [dd for dd, _, _ in rows] == [8]
    assert orphans[999] == 1


def test_valid_discipline_ids_loaded_from_disciplines_csv():
    ids = L._load_valid_discipline_ids()
    # disciplines.csv contains these (sanity)
    assert {1, 3, 6, 7, 8, 11}.issubset(ids)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/tools/test_learn_discipline_keywords.py -v`
Expected: FAIL — `_collect_rows` currently takes `fold` and `_load_valid_discipline_ids` doesn't exist yet (`_load_fold`/`DISCIPLINE_FOLD_CSV` still present).

- [ ] **Step 3: Edit `learn_discipline_keywords.py`**

Read the file first. Make these surgical changes:

(a) **Module docstring** (lines 1–26): replace the fold narrative with:
```python
"""Generate ``classifier.config.discipline_keywords`` from labelled CSVs.

Each labelled row's ``discipline_id`` is already a ``disciplines.csv`` id.
Train keyword rules directly under that id; no remapping. Rows whose
``discipline_id`` is not present in ``input/disciplines.csv`` are dropped as
orphans (keeps ``documents.discipline_id`` FK-safe). Disciplines with fewer
than ``MIN_CLASS_DOCS`` labelled rows emit no rules and never fire.

Scoring, eligibility, and auto-stopword rules mirror ``learn_type_keywords``.

Run from project root::

    learn-discipline-keywords
"""
```

(b) **Remove** the `DISCIPLINE_FOLD_CSV = Path("input/discipline_fold.csv")` line.

(c) **Rename** `_load_valid_dest_ids` → `_load_valid_discipline_ids` (signature and body unchanged except the docstring). Update its docstring to:
```python
    """Load the valid discipline id set from disciplines.csv. A labelled
    discipline_id must be in this set to be trained; others are dropped."""
```

(d) **Delete** the entire `_load_fold(...)` function.

(e) **Replace** `_collect_rows` with the fold-free version:
```python
def _collect_rows(valid_ids: frozenset[int]
                  ) -> tuple[list[tuple[int, str, Path]], Counter[int]]:
    """Yield ``(discipline_id, title, source_path)`` for every eligible row,
    using the labelled discipline_id as-is.

    Returns ``(rows, orphan_counts)`` where ``orphan_counts`` is a Counter of
    discipline_ids seen in the training CSVs that are NOT in
    ``input/disciplines.csv`` (and are therefore dropped).
    """
    rows: list[tuple[int, str, Path]] = []
    orphans: Counter[int] = Counter()
    csv_paths = sorted(CSV_ROOT.rglob("*.csv"), key=lambda p: str(p).lower())
    for p in csv_paths:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[])
        if not {"discipline_id", "title"}.issubset(df.columns):
            print(f"  [skip] {p}: missing 'discipline_id' or 'title' column")
            continue
        for _, row in df.iterrows():
            if is_empty(row["title"]):
                continue
            disc = _parse_discipline(row["discipline_id"])
            if disc is None:
                continue
            if disc not in valid_ids:
                orphans[disc] += 1
                continue
            rows.append((disc, str(row["title"]), p))
    return rows, orphans
```

(f) **Replace `main()`** with the fold-free version:
```python
def main() -> None:
    if not CSV_ROOT.exists():
        raise SystemExit(f"csv dir not found: {CSV_ROOT}")
    valid_ids = _load_valid_discipline_ids()
    rows, orphans = _collect_rows(valid_ids)
    if not rows:
        raise SystemExit(f"no eligible (discipline_id, title) rows found under {CSV_ROOT}")
    rules, class_counts, untrained = learn(rows)
    text = render(rules, class_counts, untrained, len(rows), CSV_ROOT)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT_PATH}")
    print(f"  training rows kept:       {len(rows)}")
    print(f"  disciplines trained:      {sorted(rules)}")
    print(f"  disciplines untrained (< {MIN_CLASS_DOCS} rows): {sorted(untrained)}")
    if orphans:
        orphan_summary = ", ".join(f"{d} ({n})" for d, n in orphans.most_common())
        print(f"  ids dropped (not in disciplines.csv):")
        print(f"    {orphan_summary}")
    for d in sorted(rules)[:3]:
        sample = ", ".join(f"{p!r}" for p, _ in rules[d][:3])
        print(f"    discipline_id={d}: {sample}")
```

Leave `_parse_discipline`, `learn`, `render`, `_auto_stopwords`,
`_phrase_is_publishable`, and all constants unchanged. (Keep `render` emitting
`UNTRAINED_DISCIPLINES` — shape unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/tools/test_learn_discipline_keywords.py -v`
Expected: PASS (4 passed). Then `python -m pytest -q` — expect 97 passed (93 + 4); the OLD generated configs are still in place so golden/baseline stay green.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/tools/learn_discipline_keywords.py tests/tools/__init__.py tests/tools/test_learn_discipline_keywords.py
git commit -m "$(cat <<'EOF'
refactor(tools): learn-discipline-keywords trains on raw ids, no fold

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Make `learn_type_discipline` fold-free (+ test)

**Files:**
- Modify: `src/classifier/tools/learn_type_discipline.py`
- Create: `tests/tools/test_learn_type_discipline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/tools/test_learn_type_discipline.py`:

```python
import csv
import classifier.tools.learn_type_discipline as T
from classifier.config.type_enum import KNOWN_TYPES

_T = "ISO" if "ISO" in KNOWN_TYPES else sorted(KNOWN_TYPES)[0]


def _write(path, rows):
    cols = ["type", "discipline_id"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for t, d in rows:
            w.writerow([t, d])


def test_no_fold_import():
    assert not hasattr(T, "_load_fold")


def test_collect_pairs_uses_raw_id(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [(_T, "8")] * 5)
    monkeypatch.setattr(T, "CSV_ROOT", d)
    per_type, orphans = T._collect_pairs(frozenset({8}))
    assert per_type[_T][8] == 5
    assert orphans == {}


def test_collect_pairs_drops_id_not_in_disciplines(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [(_T, "999")] * 3)
    monkeypatch.setattr(T, "CSV_ROOT", d)
    per_type, orphans = T._collect_pairs(frozenset({8}))
    assert per_type == {} or per_type.get(_T, {}) == {}
    assert orphans[999] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_learn_type_discipline.py -v`
Expected: FAIL — `_collect_pairs` currently takes `fold`; `_load_fold` still imported.

- [ ] **Step 3: Edit `learn_type_discipline.py`**

Read the file first. Changes:

(a) **Imports** (lines 27–30): replace
```python
from classifier.tools.learn_discipline_keywords import (
    DISCIPLINE_FOLD_CSV, DISCIPLINES_TABLE_CSV,
    _load_fold, _load_valid_dest_ids, _parse_discipline,
)
```
with
```python
from classifier.tools.learn_discipline_keywords import (
    DISCIPLINES_TABLE_CSV,
    _load_valid_discipline_ids, _parse_discipline,
)
```

(b) **Module docstring** (lines 1–16): drop the fold sentence; describe that it
counts labelled `discipline_id` (validated against `disciplines.csv`) per type
and emits a majority hint.

(c) **Replace `_collect_pairs`** with:
```python
def _collect_pairs(valid_ids: frozenset[int]
                   ) -> tuple[dict[str, Counter[int]], Counter[int]]:
    """Return ``(per_type_counts, orphans)`` where ``per_type_counts[type]``
    is a Counter of discipline ids (validated against disciplines.csv)."""
    per_type: dict[str, Counter[int]] = defaultdict(Counter)
    orphans: Counter[int] = Counter()
    for p in sorted(CSV_ROOT.rglob("*.csv"), key=lambda x: str(x).lower()):
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[])
        if not {"type", "discipline_id"}.issubset(df.columns):
            print(f"  [skip] {p}: missing 'type' or 'discipline_id' column")
            continue
        for _, row in df.iterrows():
            t = str(row["type"]).strip().upper()
            if not t or t not in KNOWN_TYPES:
                continue
            disc = _parse_discipline(row["discipline_id"])
            if disc is None:
                continue
            if disc not in valid_ids:
                orphans[disc] += 1
                continue
            per_type[t][disc] += 1
    return per_type, orphans
```

(d) **Replace `main()`** body's fold lines:
```python
    valid_dest_ids = _load_valid_dest_ids()
    fold = _load_fold(valid_dest_ids)
    per_type, orphans = _collect_pairs(fold)
```
with:
```python
    valid_ids = _load_valid_discipline_ids()
    per_type, orphans = _collect_pairs(valid_ids)
```
And update the print line that referenced `DISCIPLINE_FOLD_CSV` (drop the
`fold table:` line; keep types observed/emitted/ambiguous and the orphan
summary, relabelled `ids dropped (not in disciplines.csv)`).

The `_decide_mappings` and `render` functions are unchanged.

- [ ] **Step 4: Run test + full suite**

Run: `python -m pytest tests/tools/test_learn_type_discipline.py -v` → expect 3 passed.
Then `python -m pytest -q` → expect 100 passed (97 + 3). Old configs still in place → golden/baseline green.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/tools/learn_type_discipline.py tests/tools/test_learn_type_discipline.py
git commit -m "$(cat <<'EOF'
refactor(tools): learn-type-discipline uses raw ids, no fold

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Delete the fold table

**Files:**
- Delete: `input/discipline_fold.csv`

- [ ] **Step 1: Confirm no remaining references**

Run: `grep -rn "discipline_fold\|_load_fold\|_load_valid_dest_ids" src tests`
Expected: zero matches (Tasks 1–2 removed them). If any remain, fix before deleting.

- [ ] **Step 2: Delete and verify suite**

```bash
git rm input/discipline_fold.csv
python -m pytest -q
```
Expected: 100 passed (nothing imports the fold at test time).

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
chore: remove discipline_fold.csv (fold retired)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Regenerate configs + golden + baseline (scoped behavior change)

This task intentionally changes discipline output. Do all regeneration, run the
scope checks, confirm the suite is green, then commit once so history stays
bisectable-green.

**Files:**
- Modify: `src/classifier/config/discipline_keywords.py` (regenerated)
- Modify: `src/classifier/config/type_to_discipline.py` (regenerated)
- Modify: `tests/golden/classified.csv` (regenerated)
- Modify: `tests/core/scoring_baseline.json` (regenerated)

- [ ] **Step 1: Snapshot the current artifacts for scope-checking**

```bash
cp tests/golden/classified.csv /tmp/old_golden.csv
cp tests/core/scoring_baseline.json /tmp/old_baseline.json
```

- [ ] **Step 2: Regenerate the two configs (fold-free)**

```bash
PYTHONPATH=src python -m classifier.tools.learn_discipline_keywords
PYTHONPATH=src python -m classifier.tools.learn_type_discipline
```
Read the console output: confirm "disciplines trained" is a subset of
`disciplines.csv` ids and there are no orphans (today all labelled ids exist in
`disciplines.csv`). If there ARE orphans, STOP and report (a labelled id is not
in `disciplines.csv`).

- [ ] **Step 3: FK-safety check on the regenerated config**

```bash
PYTHONPATH=src python -c "
import pandas as pd
from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
from classifier.config.type_to_discipline import TYPE_TO_DISCIPLINE
ids = {int(float(x)) for x in pd.read_csv('input/disciplines.csv', dtype=str)['id']}
bad_k = [d for d in DISCIPLINE_KEYWORDS if d not in ids]
bad_t = [(t,d) for t,d in TYPE_TO_DISCIPLINE.items() if d not in ids]
assert not bad_k, bad_k
assert not bad_t, bad_t
print('FK ok: discipline ids', sorted(DISCIPLINE_KEYWORDS))
print('type->discipline:', TYPE_TO_DISCIPLINE)
"
```
Expected: no assertion error; ids are real `disciplines.csv` ids.

- [ ] **Step 4: Regenerate the golden + scope check (only discipline_id changed)**

```bash
PYTHONPATH=src python -m classifier.cli.classify
PYTHONPATH=src python -c "
import pandas as pd
old = pd.read_csv('/tmp/old_golden.csv', dtype=str, keep_default_na=False)
new = pd.read_csv('output/classified.csv', dtype=str, keep_default_na=False)
assert list(old.columns) == list(new.columns), 'column set changed'
assert len(old) == len(new), 'row count changed'
changed = [c for c in old.columns if not old[c].equals(new[c])]
print('changed columns:', changed)
assert changed == ['discipline_id'], f'unexpected column changes: {changed}'
print('OK: only discipline_id changed')
"
cp output/classified.csv tests/golden/classified.csv
```
If the scope check fails (any column other than `discipline_id` changed), STOP
and report — the change is not scoped as intended.

- [ ] **Step 5: Regenerate the scoring baseline + scope check (type fields identical)**

```bash
rm tests/core/scoring_baseline.json
python -m pytest tests/core/test_scoring_snapshot.py -q   # rewrites the baseline
PYTHONPATH=src python -c "
import json
old = json.load(open('/tmp/old_baseline.json'))
new = json.load(open('tests/core/scoring_baseline.json'))
assert len(old) == len(new), 'baseline length changed'
for o, n in zip(old, new):
    assert o['title'] == n['title'], 'title order changed'
    for k in ('type', 'type_conf', 'cr_type', 'cr_doc_type'):
        assert o[k] == n[k], f'TYPE field changed for {o[\"title\"]!r}: {k} {o[k]}->{n[k]}'
chg = sum(1 for o,n in zip(old,new) if o['disc'] != n['disc'] or o['cr_disc'] != n['cr_disc'])
print(f'OK: type fields identical; discipline changed on {chg} titles')
"
```
If a TYPE field changed, STOP and report — discipline work must not affect type.

- [ ] **Step 6: Full suite green**

Run: `python -m pytest -q`
Expected: 100 passed (golden + baseline now match the regenerated artifacts).

- [ ] **Step 7: Commit (one commit)**

```bash
git add src/classifier/config/discipline_keywords.py src/classifier/config/type_to_discipline.py tests/golden/classified.csv tests/core/scoring_baseline.json
git commit -m "$(cat <<'EOF'
data: regenerate discipline configs/golden/baseline (fold-free, real ids)

Discipline output now uses disciplines.csv ids directly. Verified scope:
only the discipline_id column of the golden changed, and only the disc
fields of the scoring baseline changed (type behavior byte-identical).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Docs — drop the fold narrative

**Files:**
- Modify: `INTEGRATION.md`
- Modify: `README.md`

- [ ] **Step 1: Update INTEGRATION.md**

Remove the "How the discipline pipeline folds client → DEST" section and the
`discipline_fold.csv` references / "three files to keep in sync" fold bullet.
Replace with: discipline rules are learned directly from the labelled
`discipline_id` (which are `disciplines.csv` ids), validated against
`disciplines.csv`; ids not in the table are dropped; disciplines with
`< MIN_CLASS_DOCS` examples stay NULL. To improve coverage, add labelled rows
(or a new discipline to `disciplines.csv`) and re-run `learn-discipline-keywords`
and `learn-type-discipline`. Remove `input/discipline_fold.csv` from the
"What to copy" / vendoring lists.

- [ ] **Step 2: Update README.md**

Remove any `discipline_fold.csv` mention; ensure the discipline description
matches the fold-free flow.

- [ ] **Step 3: Verify no stale references remain**

Run: `grep -rni "discipline_fold\|client -> dest\|client→dest\|fold table" README.md INTEGRATION.md`
Expected: no matches.

- [ ] **Step 4: Full suite**

Run: `python -m pytest -q` → expect 100 passed (docs-only).

- [ ] **Step 5: Commit**

```bash
git add INTEGRATION.md README.md
git commit -m "$(cat <<'EOF'
docs: describe fold-free discipline learning

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] `python -m pytest -q` — all green (100).
- [ ] `grep -rn "discipline_fold\|_load_fold\|_load_valid_dest_ids" src tests` — zero matches.
- [ ] `config/discipline_keywords.py` keys ⊆ `disciplines.csv` ids; `type_to_discipline` values ⊆ `disciplines.csv` ids (Task 4 Step 3 proved this).
- [ ] Golden differs from the pre-change version only in `discipline_id`; scoring baseline differs only in the discipline fields (Task 4 scope checks).
- [ ] `core/` and the scoring engine are untouched: `git diff --name-only <plan-base>..HEAD -- src/classifier/core` is empty.
