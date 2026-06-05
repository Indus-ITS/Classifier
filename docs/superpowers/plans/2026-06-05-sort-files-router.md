# sort-files Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone `sort-files` CLI that consumes the classified CSV and copies one preferred file per logical document into `dest/<Drawings|Documents|Sheets|Unmatched>/`, with a CSV sidecar report.

**Architecture:** A loosely-coupled `routing/` package (pure logic) + `io/classified_index.py` (CSV→class map) + `cli/sort.py` (entry). It does NOT route through the classify `run()` loop — classification is already in the CSV. Reuses only pure helpers `io/normalize` and `io/schema`.

**Tech Stack:** Python 3.10+, pandas (CSV read), pytest, stdlib `shutil`/`csv`/`re`.

**Spec:** `docs/superpowers/specs/2026-06-05-sort-files-router-design.md`

**Conventions for every task:**
- Run tests with `python -m pytest` from the repository root.
- Windows: PowerShell cmdlets via the Bash tool are BLOCKED — use Read/Write/Edit tools and POSIX commands (`python -m pytest`, `git`).
- Do NOT stage/commit the unrelated `docs/superpowers/plans/2026-06-05-sheets-class-phase2.md`. `git add` only the files each task lists.
- Every commit message ends with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Baseline at start: 65 tests pass.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/classifier/routing/__init__.py` | package marker (empty) |
| `src/classifier/routing/cust_ref.py` | extract cust_ref + parse group/revision from a filename stem (pure) |
| `src/classifier/routing/dedup.py` | `FileEntry`/`Group`, grouping, class-aware `pick_winner` (pure) |
| `src/classifier/io/classified_index.py` | load classified CSV → `{norm cust_ref: Classification}` |
| `src/classifier/routing/plan.py` | `CopyAction`/`Plan`, `build_plan` (pure) |
| `src/classifier/routing/execute.py` | perform copies (I/O) |
| `src/classifier/routing/report.py` | sidecar rows (pure) + write CSV + console summary |
| `src/classifier/cli/sort.py` | `sort-files` argparse entry, wiring |
| `pyproject.toml` | add `sort-files` console script |
| `tests/routing/…`, `tests/io/test_classified_index.py` | tests mirroring the above |

---

### Task 1: cust_ref + revision parsing

**Files:**
- Create: `src/classifier/routing/__init__.py` (empty)
- Create: `src/classifier/routing/cust_ref.py`
- Create: `tests/routing/__init__.py` (empty)
- Create: `tests/routing/test_cust_ref.py`

- [ ] **Step 1: Write the failing test**

Create `tests/routing/__init__.py` (empty) and `tests/routing/test_cust_ref.py`:

```python
from classifier.routing.cust_ref import extract_cust_ref, parse_group_and_revision


def test_extract_present_and_absent():
    assert extract_cust_ref("16-01-39-2602-B") == "16-01-39-2602"
    assert extract_cust_ref("CRS 16-99-90-2601-B") == "16-99-90-2601"
    assert extract_cust_ref("random_file_name") is None


def test_group_and_revision_with_cust_ref():
    assert parse_group_and_revision("16-01-39-2602-B") == ("16-01-39-2602", "B")
    assert parse_group_and_revision("16-01-27-2604_Rev.A") == ("16-01-27-2604", "A")
    assert parse_group_and_revision("16-99-90-2601-1") == ("16-99-90-2601", "1")
    # cust_ref with no revision tail keeps the whole (lowercased) stem as key
    assert parse_group_and_revision("16-01-19-2602") == ("16-01-19-2602", None)
    # prefix is preserved in the group key, lowercased
    gk, rev = parse_group_and_revision("CRS 16-99-90-2601-B")
    assert gk == "crs 16-99-90-2601" and rev == "B"
    # extra descriptive tail after the revision is dropped
    gk, rev = parse_group_and_revision("16-01-52-2609_B-MR for MPFM")
    assert gk == "16-01-52-2609" and rev == "B"


def test_group_and_revision_without_cust_ref():
    assert parse_group_and_revision("design note rev B") == ("design note", "B")
    assert parse_group_and_revision("plainfile") == ("plainfile", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/routing/test_cust_ref.py -v`
Expected: FAIL (`ModuleNotFoundError: classifier.routing.cust_ref`).

- [ ] **Step 3: Implement**

Create `src/classifier/routing/__init__.py` empty. Create `src/classifier/routing/cust_ref.py`:

```python
"""Extract the project cust_ref from a filename stem and parse a logical
group key + revision. Pure string logic; no I/O.
"""
from __future__ import annotations

import re

CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")
# Revision tail: a single letter OR single digit, optionally "Rev"-prefixed,
# optionally followed by more descriptive text. Single-char value so a
# 4-digit cust_ref tail is never misread as a revision.
_REV_TAIL = re.compile(
    r"^[\s_-]+(?:REV\.?)?([A-Z]|\d)(?:[\s_.\-].*)?$", re.IGNORECASE
)
_REV_WHOLE = re.compile(
    r"[\s_-]+(?:REV\.?)?([A-Z]|\d)(?:[\s_.\-].*)?$", re.IGNORECASE
)


def extract_cust_ref(stem: str) -> str | None:
    m = CUST_REF.search(stem)
    return m.group(0) if m else None


def parse_group_and_revision(stem: str) -> tuple[str, str | None]:
    """Return (group_key, revision).

    With a cust_ref: anchor on it, strip a revision only from the tail that
    follows it; group_key = the rest (lowercased, stripped). Without a
    cust_ref: strip a trailing revision from the whole stem.
    """
    m = CUST_REF.search(stem)
    if m:
        prefix, suffix = stem[: m.end()], stem[m.end():]
        rev = _REV_TAIL.match(suffix)
        if rev:
            return prefix.strip().lower(), rev.group(1).upper()
        return (prefix + suffix).strip().lower(), None
    rev = _REV_WHOLE.search(stem)
    if rev:
        return stem[: rev.start()].strip().lower(), rev.group(1).upper()
    return stem.strip().lower(), None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/routing/test_cust_ref.py -v`
Expected: PASS (3 passed). If a case differs, fix the implementation (not the test) until the documented examples hold.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/routing/__init__.py src/classifier/routing/cust_ref.py tests/routing/__init__.py tests/routing/test_cust_ref.py
git commit -m "$(cat <<'EOF'
feat(routing): cust_ref + revision parsing

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: dedup — FileEntry, grouping, class-aware winner

**Files:**
- Create: `src/classifier/routing/dedup.py`
- Create: `tests/routing/test_dedup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/routing/test_dedup.py`:

```python
from pathlib import Path
from classifier.routing.dedup import (
    parse_entry, group_files, pick_winner, format_priority, CANDIDATE_EXTS,
)


def test_parse_entry_fields():
    e = parse_entry(Path("a/16-01-39-2602-B.pdf"))
    assert e.cust_ref == "16-01-39-2602"
    assert e.group_key == "16-01-39-2602"
    assert e.revision == "B"
    assert e.ext == "pdf"
    assert e.rev_rank == (0, "B")


def test_rev_rank_ordering():
    digit2 = parse_entry(Path("16-01-39-2602-2.pdf")).rev_rank
    digit1 = parse_entry(Path("16-01-39-2602-1.pdf")).rev_rank
    letterB = parse_entry(Path("16-01-39-2602-B.pdf")).rev_rank
    letterA = parse_entry(Path("16-01-39-2602-A.pdf")).rev_rank
    none = parse_entry(Path("16-01-39-2602.pdf")).rev_rank
    assert digit2 > digit1 > letterB > letterA > none


def test_format_priority_class_aware():
    # drawing/document: pdf preferred
    assert format_priority("pdf", "document") < format_priority("xlsx", "document")
    assert format_priority("pdf", "drawing") < format_priority("xls", "drawing")
    # sheet: xlsx preferred over pdf
    assert format_priority("xlsx", "sheet") < format_priority("pdf", "sheet")
    assert format_priority("xls", "sheet") < format_priority("pdf", "sheet")
    # unknown class behaves like doc (pdf-first)
    assert format_priority("pdf", None) < format_priority("xlsx", None)


def test_pick_winner_prefers_latest_rev_then_format():
    entries = [
        parse_entry(Path("16-01-39-2602-A.pdf")),
        parse_entry(Path("16-01-39-2602-B.pdf")),
        parse_entry(Path("16-01-39-2602-B.docx")),
    ]
    g = pick_winner(entries, "document")
    assert g.winner == Path("16-01-39-2602-B.pdf")
    assert Path("16-01-39-2602-B.docx") in g.related
    assert Path("16-01-39-2602-A.pdf") in g.related


def test_pick_winner_sheet_prefers_xlsx():
    entries = [
        parse_entry(Path("16-01-39-2602-B.pdf")),
        parse_entry(Path("16-01-39-2602-B.xlsx")),
    ]
    g = pick_winner(entries, "sheet")
    assert g.winner == Path("16-01-39-2602-B.xlsx")


def test_non_candidate_never_wins_but_is_related():
    entries = [
        parse_entry(Path("16-01-39-2602-B.dwg")),
        parse_entry(Path("16-01-39-2602-B.pdf")),
    ]
    g = pick_winner(entries, "drawing")
    assert g.winner == Path("16-01-39-2602-B.pdf")
    assert Path("16-01-39-2602-B.dwg") in g.related


def test_group_with_only_non_candidates_has_no_winner():
    entries = [parse_entry(Path("16-01-39-2602-B.dwg"))]
    g = pick_winner(entries, "drawing")
    assert g.winner is None
    assert Path("16-01-39-2602-B.dwg") in g.related


def test_group_files_groups_by_group_key():
    paths = [Path("16-01-39-2602-A.pdf"), Path("16-01-39-2602-B.pdf"),
             Path("16-01-39-2700-A.pdf")]
    groups = group_files(paths)
    assert set(groups) == {"16-01-39-2602", "16-01-39-2700"}
    assert len(groups["16-01-39-2602"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/routing/test_dedup.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

Create `src/classifier/routing/dedup.py`:

```python
"""Logical-document grouping and class-aware winner selection. Pure logic;
only Path operations, no filesystem reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from classifier.io.normalize import normalize_lookup_key
from classifier.routing.cust_ref import extract_cust_ref, parse_group_and_revision

CANDIDATE_EXTS = ("pdf", "doc", "docx", "xls", "xlsx")

FORMAT_PRIORITY_DOC = {"pdf": 0, "doc": 1, "docx": 1, "xls": 2, "xlsx": 2}
FORMAT_PRIORITY_SHEET = {"xlsx": 0, "xls": 1, "pdf": 2, "doc": 3, "docx": 3}


def format_priority(ext: str, doc_type: str | None) -> int:
    """Lower = preferred. 'sheet' prefers spreadsheets; everything else
    (incl. unknown/None) prefers pdf. Non-candidate exts return a large
    sentinel so they never win."""
    table = FORMAT_PRIORITY_SHEET if doc_type == "sheet" else FORMAT_PRIORITY_DOC
    return table.get(ext, 99)


def _rev_rank(revision: str | None) -> tuple[int, object]:
    if revision is None:
        return (-1, "")
    if revision.isdigit():
        return (1, int(revision))
    return (0, revision)


@dataclass(frozen=True)
class FileEntry:
    path: Path
    group_key: str
    cust_ref: str | None      # normalized; None when no cust_ref in name
    revision: str | None
    rev_rank: tuple[int, object]
    ext: str                  # lowercase, no leading dot


@dataclass(frozen=True)
class Group:
    group_key: str
    winner: Path | None
    related: tuple[Path, ...]


def parse_entry(path: Path) -> FileEntry:
    stem = path.stem
    group_key, revision = parse_group_and_revision(stem)
    raw_ref = extract_cust_ref(stem)
    cust_ref = normalize_lookup_key(raw_ref) if raw_ref else None
    ext = path.suffix.lower().lstrip(".")
    return FileEntry(
        path=path, group_key=group_key, cust_ref=cust_ref,
        revision=revision, rev_rank=_rev_rank(revision), ext=ext,
    )


def group_files(paths: Iterable[Path]) -> dict[str, list[FileEntry]]:
    groups: dict[str, list[FileEntry]] = {}
    for p in paths:
        e = parse_entry(p)
        groups.setdefault(e.group_key, []).append(e)
    return groups


def pick_winner(entries: list[FileEntry], doc_type: str | None) -> Group:
    """Winner = max rev_rank, then min class-aware format_priority, then
    lexically smallest filename. Only candidate extensions can win; if none,
    winner is None. All non-winning files become `related`."""
    group_key = entries[0].group_key if entries else ""
    candidates = [e for e in entries if e.ext in CANDIDATE_EXTS]
    if not candidates:
        return Group(group_key, None, tuple(e.path for e in entries))
    # Two-step selection (clear and total-order-safe across rev_rank types):
    best_rank = max(e.rev_rank for e in candidates)
    top = [e for e in candidates if e.rev_rank == best_rank]
    top.sort(key=lambda e: (format_priority(e.ext, doc_type), e.path.name))
    winner = top[0]
    related = tuple(e.path for e in entries if e.path != winner.path)
    return Group(group_key, winner.path, related)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/routing/test_dedup.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Self-check** — confirm no dead placeholder line remains in `dedup.py` (grep for `if False`). Then commit.

```bash
git add src/classifier/routing/dedup.py tests/routing/test_dedup.py
git commit -m "$(cat <<'EOF'
feat(routing): grouping + class-aware winner selection

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: classified index loader

**Files:**
- Create: `src/classifier/io/classified_index.py`
- Create: `tests/io/test_classified_index.py`

- [ ] **Step 1: Write the failing test**

Create `tests/io/test_classified_index.py`:

```python
import csv
from pathlib import Path
from classifier.io.classified_index import load_classified_index
from classifier.io.schema import TARGET_COLUMNS


def _write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(TARGET_COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in TARGET_COLUMNS])


def test_maps_cust_ref_to_classification(tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, [
        {"customer_ref": "16-01-19-2602", "doc_type": "sheet", "title": "VALVE LIST"},
        {"customer_ref": "16-01-19-2605", "doc_type": "drawing", "title": "P&ID"},
    ])
    idx = load_classified_index(p)
    assert idx["16-01-19-2602"].doc_type == "sheet"
    assert idx["16-01-19-2602"].title == "VALVE LIST"
    assert idx["16-01-19-2605"].doc_type == "drawing"


def test_empty_cust_ref_skipped_and_first_wins_on_dup(tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, [
        {"customer_ref": "", "doc_type": "document", "title": "no ref"},
        {"customer_ref": "16-01-19-2602", "doc_type": "drawing", "title": "first"},
        {"customer_ref": "16-01-19-2602", "doc_type": "sheet", "title": "second"},
    ])
    idx = load_classified_index(p)
    assert "" not in idx
    assert idx["16-01-19-2602"].title == "first"   # first wins
    assert idx["16-01-19-2602"].doc_type == "drawing"


def test_doc_type_lowercased(tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, [{"customer_ref": "16-01-19-2602", "doc_type": "Drawing", "title": "x"}])
    idx = load_classified_index(p)
    assert idx["16-01-19-2602"].doc_type == "drawing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/io/test_classified_index.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

Create `src/classifier/io/classified_index.py`:

```python
"""Load the classified CSV into a customer_ref -> classification map for the
sort-files router. Read-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from classifier.io.normalize import is_empty, normalize_lookup_key
from classifier.io.schema import validate_schema


@dataclass(frozen=True)
class Classification:
    doc_type: str
    title: str


def load_classified_index(csv_path: Path) -> dict[str, Classification]:
    """Map normalize_lookup_key(customer_ref) -> Classification. First row
    wins on a duplicate normalized key; rows with empty customer_ref are
    skipped; doc_type is lowercased."""
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[])
    validate_schema(df.columns)
    index: dict[str, Classification] = {}
    for _, row in df.iterrows():
        key = normalize_lookup_key(row["customer_ref"])
        if not key:
            continue
        if key in index:
            continue  # first wins
        doc_type = "" if is_empty(row["doc_type"]) else str(row["doc_type"]).strip().lower()
        title = "" if is_empty(row["title"]) else str(row["title"]).strip()
        index[key] = Classification(doc_type=doc_type, title=title)
    return index
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/io/test_classified_index.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/io/classified_index.py tests/io/test_classified_index.py
git commit -m "$(cat <<'EOF'
feat(io): classified-CSV index loader for the router

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: plan — bucket assignment, Unmatched, on-duplicate

**Files:**
- Create: `src/classifier/routing/plan.py`
- Create: `tests/routing/test_plan.py`

- [ ] **Step 1: Write the failing test**

Create `tests/routing/test_plan.py`:

```python
from pathlib import Path
from classifier.io.classified_index import Classification
from classifier.routing.dedup import group_files
from classifier.routing.plan import build_plan, BUCKET_FOR_DOCTYPE


def _plan(paths, index, dest="dest"):
    groups = group_files([Path(p) for p in paths])
    return build_plan(groups, index, Path(dest))


def test_winner_routed_to_class_bucket():
    index = {"16-01-19-2602": Classification("drawing", "P&ID")}
    plan = _plan(["16-01-19-2602-B.pdf", "16-01-19-2602-A.pdf"], index)
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.bucket == "Drawings"
    assert a.dest == Path("dest/Drawings/16-01-19-2602-B.pdf")
    assert a.chosen_format == "pdf"
    assert Path("16-01-19-2602-A.pdf") in a.related


def test_sheet_class_uses_sheet_bucket_and_xlsx_winner():
    index = {"16-01-19-2602": Classification("sheet", "VALVE LIST")}
    plan = _plan(["16-01-19-2602-B.pdf", "16-01-19-2602-B.xlsx"], index)
    a = plan.actions[0]
    assert a.bucket == "Sheets"
    assert a.dest.name == "16-01-19-2602-B.xlsx"


def test_no_cust_ref_match_goes_to_unmatched():
    plan = _plan(["random-doc.pdf"], index={})
    a = plan.actions[0]
    assert a.bucket == "Unmatched"
    assert a.dest == Path("dest/Unmatched/random-doc.pdf")


def test_cust_ref_not_in_index_goes_to_unmatched():
    plan = _plan(["16-01-19-2602-B.pdf"], index={})
    assert plan.actions[0].bucket == "Unmatched"


def test_rows_without_file_reported():
    index = {"16-01-19-2602": Classification("drawing", "x"),
             "16-01-19-2999": Classification("document", "y")}
    plan = _plan(["16-01-19-2602-B.pdf"], index)
    assert plan.rows_without_file == ("16-01-19-2999",)


def test_skipped_no_preferred_format():
    index = {"16-01-19-2602": Classification("drawing", "x")}
    plan = _plan(["16-01-19-2602-B.dwg"], index)
    assert plan.actions == ()
    assert "16-01-19-2602" in plan.skipped_no_preferred_format


def test_same_name_different_dirs_merge_into_one_group():
    # Two files with the same name (hence same group_key) merge into one
    # group: one winner, the other becomes a sibling. This is why dest
    # basenames are unique per bucket and no collision handling is needed.
    plan = _plan(["sub1/doc.pdf", "sub2/doc.pdf"], index={})
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.dest == Path("dest/Unmatched/doc.pdf")
    assert len(a.related) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/routing/test_plan.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

Create `src/classifier/routing/plan.py`:

```python
"""Build the copy plan from grouped files + the classification index. Pure
logic (Path arithmetic only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier.routing.dedup import pick_winner, CANDIDATE_EXTS

BUCKET_FOR_DOCTYPE = {"drawing": "Drawings", "document": "Documents",
                      "sheet": "Sheets"}
UNMATCHED = "Unmatched"


@dataclass(frozen=True)
class CopyAction:
    src: Path
    dest: Path
    bucket: str
    cust_ref: str | None
    title: str
    revision: str | None
    chosen_format: str
    related: tuple[Path, ...]


@dataclass(frozen=True)
class Plan:
    actions: tuple[CopyAction, ...]
    rows_without_file: tuple[str, ...]
    skipped_no_preferred_format: tuple[str, ...]


def build_plan(groups, index, dest_dir: Path) -> Plan:
    """Per group: resolve its cust_ref -> doc_type from the index, pick the
    class-aware winner, and route it to dest_dir/bucket/winner.name.

    No collision handling is needed: a winner's basename is a pure function
    of its stem and the group_key is derived from that same stem, so two
    distinct groups can never yield the same basename in the same bucket.
    """
    actions: list[CopyAction] = []
    skipped: list[str] = []
    matched_refs: set[str] = set()

    for group_key in sorted(groups):
        entries = groups[group_key]
        cust_ref = next((e.cust_ref for e in entries if e.cust_ref), None)
        cls = index.get(cust_ref) if cust_ref else None
        doc_type = cls.doc_type if cls else None

        group = pick_winner(entries, doc_type)
        if group.winner is None:
            skipped.append(group_key)
            continue

        if cls and cls.doc_type in BUCKET_FOR_DOCTYPE:
            bucket = BUCKET_FOR_DOCTYPE[cls.doc_type]
            matched_refs.add(cust_ref)
        else:
            bucket = UNMATCHED

        winner_entry = next(e for e in entries if e.path == group.winner)
        actions.append(CopyAction(
            src=group.winner, dest=dest_dir / bucket / group.winner.name,
            bucket=bucket, cust_ref=cust_ref, title=(cls.title if cls else ""),
            revision=winner_entry.revision, chosen_format=winner_entry.ext,
            related=group.related,
        ))

    rows_without_file = tuple(
        sorted(k for k in index.keys() if k not in matched_refs)
    )
    return Plan(tuple(actions), rows_without_file, tuple(skipped))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/routing/test_plan.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/classifier/routing/plan.py tests/routing/test_plan.py
git commit -m "$(cat <<'EOF'
feat(routing): build copy plan (buckets, Unmatched, on-duplicate)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: execute (copy) + report (sidecar + summary)

**Files:**
- Create: `src/classifier/routing/execute.py`
- Create: `src/classifier/routing/report.py`
- Create: `tests/routing/test_execute_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/routing/test_execute_report.py`:

```python
import csv
from pathlib import Path
from classifier.io.classified_index import Classification
from classifier.routing.dedup import group_files
from classifier.routing.plan import build_plan
from classifier.routing.execute import execute
from classifier.routing.report import report_rows, write_report_csv


def _make(tmp_path, names):
    src = tmp_path / "src"
    src.mkdir()
    for n in names:
        p = src / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    return src


def test_execute_copies_winner_and_creates_buckets(tmp_path):
    src = _make(tmp_path, ["16-01-19-2602-B.pdf", "16-01-19-2602-A.pdf"])
    index = {"16-01-19-2602": Classification("drawing", "P&ID")}
    dest = tmp_path / "dest"
    plan = build_plan(group_files(sorted(src.rglob("*"))), index, dest, on_duplicate="rename")
    done = execute(plan, dry_run=False)
    assert (dest / "Drawings" / "16-01-19-2602-B.pdf").exists()
    assert not (dest / "Drawings" / "16-01-19-2602-A.pdf").exists()  # sibling not copied
    assert len(done) == 1
    # source untouched (copy, not move)
    assert (src / "16-01-19-2602-A.pdf").exists()


def test_dry_run_copies_nothing(tmp_path):
    src = _make(tmp_path, ["16-01-19-2602-B.pdf"])
    index = {"16-01-19-2602": Classification("drawing", "x")}
    dest = tmp_path / "dest"
    plan = build_plan(group_files(sorted(src.rglob("*"))), index, dest, on_duplicate="rename")
    execute(plan, dry_run=True)
    assert not dest.exists()


def test_report_rows_and_csv(tmp_path):
    src = _make(tmp_path, ["16-01-19-2602-B.pdf", "16-01-19-2602-B.dwg",
                           "16-01-19-2999-A.pdf", "random.pdf"])
    index = {"16-01-19-2602": Classification("drawing", "P&ID"),
             "16-01-19-2999": Classification("document", "SPEC"),
             "16-01-19-3000": Classification("sheet", "LIST")}  # no file
    dest = tmp_path / "dest"
    plan = build_plan(group_files(sorted(src.rglob("*"))), index, dest, on_duplicate="rename")
    rows = report_rows(plan, index)
    statuses = {r["status"] for r in rows}
    assert "copied" in statuses
    assert "no-file-for-row" in statuses          # 16-01-19-3000
    # the random.pdf has no cust_ref -> routed Unmatched -> status unmatched-file
    assert "unmatched-file" in statuses
    out = write_report_csv(rows, dest)
    assert out.exists()
    with out.open(encoding="utf-8") as f:
        got = list(csv.DictReader(f))
    assert any(r["customer_ref"] == "16-01-19-3000" and r["status"] == "no-file-for-row"
               for r in got)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/routing/test_execute_report.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement execute**

Create `src/classifier/routing/execute.py`:

```python
"""Perform the planned copies. The only filesystem-mutating module in the
router."""
from __future__ import annotations

import shutil
from pathlib import Path

from classifier.routing.plan import Plan, CopyAction


def execute(plan: Plan, *, dry_run: bool) -> list[CopyAction]:
    """Copy each winner into its dest bucket (shutil.copy2). Creates parent
    dirs. No-op when dry_run. Returns the actions performed."""
    if dry_run:
        return []
    done: list[CopyAction] = []
    for a in plan.actions:
        a.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a.src, a.dest)
        done.append(a)
    return done
```

- [ ] **Step 4: Implement report**

Create `src/classifier/routing/report.py`:

```python
"""Sidecar report rows (pure) + CSV writer + console summary."""
from __future__ import annotations

import csv
from pathlib import Path

from classifier.routing.plan import Plan

REPORT_COLUMNS = (
    "customer_ref", "title", "class", "revision", "chosen_file",
    "chosen_format", "related_files", "related_count", "status",
)


def report_rows(plan: Plan, index) -> list[dict]:
    """One row per copy action plus rows for CSV entries that had no file.
    status: copied | unmatched-file | no-file-for-row.
    (skipped-no-preferred-format groups are summarized in the console, not
    the per-row sidecar, since they have no winner to name.)"""
    rows: list[dict] = []
    for a in plan.actions:
        status = "copied" if a.bucket != "Unmatched" else "unmatched-file"
        rows.append({
            "customer_ref": a.cust_ref or "",
            "title": a.title,
            "class": a.bucket,
            "revision": a.revision or "",
            "chosen_file": a.dest.name,
            "chosen_format": a.chosen_format,
            "related_files": "; ".join(p.name for p in a.related),
            "related_count": str(len(a.related)),
            "status": status,
        })
    for ref in plan.rows_without_file:
        cls = index.get(ref)
        rows.append({
            "customer_ref": ref,
            "title": cls.title if cls else "",
            "class": (cls.doc_type if cls else ""),
            "revision": "", "chosen_file": "", "chosen_format": "",
            "related_files": "", "related_count": "0",
            "status": "no-file-for-row",
        })
    return rows


def write_report_csv(rows: list[dict], dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / "route-report.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out


def print_summary(plan: Plan) -> None:
    copied = sum(1 for a in plan.actions if a.bucket != "Unmatched")
    unmatched = sum(1 for a in plan.actions if a.bucket == "Unmatched")
    dedup_dropped = sum(len(a.related) for a in plan.actions)
    print()
    print(f"groups with a winner:        {len(plan.actions)}")
    print(f"  copied to class buckets:   {copied}")
    print(f"  routed to Unmatched:       {unmatched}")
    print(f"siblings not copied:         {dedup_dropped}")
    print(f"rows with no file:           {len(plan.rows_without_file)}")
    print(f"skipped (no preferred fmt):  {len(plan.skipped_no_preferred_format)}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/routing/test_execute_report.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/classifier/routing/execute.py src/classifier/routing/report.py tests/routing/test_execute_report.py
git commit -m "$(cat <<'EOF'
feat(routing): execute copies + sidecar report and summary

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: CLI entry + console script + smoke test

**Files:**
- Create: `src/classifier/cli/sort.py`
- Modify: `pyproject.toml` (add `sort-files` script)
- Create: `tests/routing/test_cli_smoke.py`

- [ ] **Step 1: Write the smoke test**

Create `tests/routing/test_cli_smoke.py`:

```python
import csv
from pathlib import Path
from classifier.cli import sort as sort_cli
from classifier.io.schema import TARGET_COLUMNS


def _write_classified(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(TARGET_COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in TARGET_COLUMNS])


def test_cli_end_to_end(tmp_path, capsys):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    for n in ["16-01-19-2602-B.pdf", "16-01-19-2602-A.pdf",
              "16-01-19-2602-B.dwg", "16-01-19-2605-B.xlsx",
              "16-01-19-2605-B.pdf", "sub/random.pdf"]:
        (src / n).write_text("x")

    csv_path = tmp_path / "classified.csv"
    _write_classified(csv_path, [
        {"customer_ref": "16-01-19-2602", "doc_type": "drawing", "title": "P&ID"},
        {"customer_ref": "16-01-19-2605", "doc_type": "sheet", "title": "VALVE LIST"},
        {"customer_ref": "16-01-19-2700", "doc_type": "document", "title": "SPEC"},  # no file
    ])
    dest = tmp_path / "dest"

    rc = sort_cli.main([
        "--classified-csv", str(csv_path),
        "--source-dir", str(src),
        "--dest-dir", str(dest),
    ])
    assert rc == 0
    # drawing winner = pdf (latest rev B); sheet winner = xlsx
    assert (dest / "Drawings" / "16-01-19-2602-B.pdf").exists()
    assert (dest / "Sheets" / "16-01-19-2605-B.xlsx").exists()
    # random.pdf -> Unmatched
    assert (dest / "Unmatched" / "random.pdf").exists()
    # sidecar exists and names the no-file row
    report = dest / "route-report.csv"
    assert report.exists()
    with report.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert any(r["customer_ref"] == "16-01-19-2700" and r["status"] == "no-file-for-row"
               for r in rows)


def test_cli_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    (src / "16-01-19-2602-B.pdf").write_text("x")
    csv_path = tmp_path / "classified.csv"
    _write_classified(csv_path, [
        {"customer_ref": "16-01-19-2602", "doc_type": "drawing", "title": "x"}])
    dest = tmp_path / "dest"
    rc = sort_cli.main([
        "--classified-csv", str(csv_path), "--source-dir", str(src),
        "--dest-dir", str(dest), "--dry-run"])
    assert rc == 0
    assert not dest.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/routing/test_cli_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: classifier.cli.sort`).

- [ ] **Step 3: Implement the CLI**

Create `src/classifier/cli/sort.py`:

```python
"""sort-files: route deliverable files into class buckets using the
classified CSV as the source of truth. See
docs/superpowers/specs/2026-06-05-sort-files-router-design.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from classifier.io.classified_index import load_classified_index
from classifier.routing.dedup import group_files
from classifier.routing.plan import build_plan, BUCKET_FOR_DOCTYPE
from classifier.routing.execute import execute
from classifier.routing.report import report_rows, write_report_csv, print_summary

_SKIP_DIRS = set(BUCKET_FOR_DOCTYPE.values()) | {"Unmatched"}


def _iter_source_files(source_dir: Path):
    """All files under source_dir, recursive, skipping any already inside a
    bucket folder (so re-runs against the same tree are safe)."""
    for p in sorted(source_dir.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = set(p.relative_to(source_dir).parts[:-1])
        if rel_parts & _SKIP_DIRS:
            continue
        yield p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sort-files")
    ap.add_argument("--classified-csv", type=Path,
                    default=Path("output/classified.csv"))
    ap.add_argument("--source-dir", type=Path, required=True)
    ap.add_argument("--dest-dir", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.classified_csv.exists():
        raise SystemExit(f"classified CSV not found: {args.classified_csv}")
    if not args.source_dir.exists():
        raise SystemExit(f"source dir not found: {args.source_dir}")

    index = load_classified_index(args.classified_csv)
    files = list(_iter_source_files(args.source_dir))
    groups = group_files(files)
    plan = build_plan(groups, index, args.dest_dir)

    execute(plan, dry_run=args.dry_run)
    if not args.dry_run:
        out = write_report_csv(report_rows(plan, index), args.dest_dir)
        print(f"\nWrote {out}")
    else:
        print("\n[dry-run] no files copied, no report written")
    print_summary(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the console script**

In `pyproject.toml`, under `[project.scripts]`, add:
```toml
sort-files          = "classifier.cli.sort:main"
```
(Place it alongside the existing `classify`/`classify-rds` entries.)

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/routing/test_cli_smoke.py -v`
Expected: PASS (2 passed). Then full suite `python -m pytest -q` — expect 65 + new routing tests all green.

- [ ] **Step 6: Commit**

```bash
git add src/classifier/cli/sort.py pyproject.toml tests/routing/test_cli_smoke.py
git commit -m "$(cat <<'EOF'
feat(cli): sort-files router entry point + console script

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: README — document sort-files

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a sort-files section**

In `README.md`, add `sort-files` to the console-scripts table and a short
section describing: it consumes `output/classified.csv`, matches files by
`customer_ref`, copies one preferred file per logical document into
`dest/<Drawings|Documents|Sheets>/` (pdf preferred for drawing/document,
xlsx for sheet), routes unmatched files to `Unmatched/`, writes
`route-report.csv`, and supports `--dry-run`. Show the invocation:
```bash
sort-files --classified-csv output/classified.csv --source-dir SRC --dest-dir DEST
```

- [ ] **Step 2: Verify suite still green**

Run: `python -m pytest -q` — expect all green (docs change only).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: document the sort-files router

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] `python -m pytest -q` — all green (65 pre-existing + the new routing/io/cli tests).
- [ ] Confirm `core/` and the classify/RDS pipelines are untouched: `git diff --name-only <plan-base>..HEAD` lists only `routing/`, `io/classified_index.py`, `cli/sort.py`, `pyproject.toml`, tests, and docs.
- [ ] Sanity-run the CLI against the real data in `--dry-run`:
  `sort-files --classified-csv output/classified.csv --source-dir <a real dir> --dest-dir /tmp/route --dry-run` (only if a real source dir is available; otherwise rely on the smoke test).
