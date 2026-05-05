# sort-files Dedup + Related-Documents XLSX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `sort-files` copy exactly one file per logical document (latest revision, format priority `pdf > doc/docx > xls/xlsx`), emit `<dest>/related-documents.xlsx`, and drop the in-place / non-recursive code paths.

**Architecture:** New pure-logic module `routing/dedup.py` runs before `match_files` and reduces the source-file set to one winner per group. Siblings are tracked and written to an Excel sidecar via new `io/related_xlsx.py`. CLI in `cli/sort.py` is simplified — `--mode`, `--recursive`, `--clean-empty-dirs` removed; `--dest-dir` becomes required; `routing/execute.py` loses its `move` branch.

**Tech Stack:** Python 3.10+, pandas + openpyxl (already deps), pytest (added as optional dev dep).

**Spec:** [docs/superpowers/specs/2026-05-05-sort-files-dedup-and-related-xlsx-design.md](../specs/2026-05-05-sort-files-dedup-and-related-xlsx-design.md)

---

## File Map

**Create:**
- `src/classifier/routing/dedup.py` — pure-logic grouping and winner selection
- `src/classifier/io/related_xlsx.py` — write the sidecar xlsx
- `tests/__init__.py` — empty
- `tests/routing/__init__.py` — empty
- `tests/routing/test_dedup.py`
- `tests/io/__init__.py` — empty
- `tests/io/test_related_xlsx.py`

**Modify:**
- `src/classifier/cli/sort.py` — strip flags, wire dedup, call xlsx writer
- `src/classifier/cli/prompts.py` — remove mode prompt usage (no code change needed; just stop calling)
- `src/classifier/routing/execute.py` — drop `mode` parameter, drop `clean_empty_dirs`
- `src/classifier/routing/matching.py` — `_iter_source_files` always recursive (drop `recursive` param) OR keep param but always pass True from CLI; we choose the former for simplicity
- `pyproject.toml` — add `[project.optional-dependencies] dev = ["pytest>=7"]`
- `README.md` — update sort-files section

---

## Task 1: Scaffold dedup module + tests

**Files:**
- Create: `src/classifier/routing/dedup.py`
- Create: `tests/__init__.py`, `tests/routing/__init__.py`, `tests/routing/test_dedup.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pytest dev dep**

Edit `pyproject.toml`. After the `dependencies = [...]` block, before `[project.scripts]`, add:

```toml
[project.optional-dependencies]
dev = ["pytest>=7"]
```

- [ ] **Step 2: Create empty test packages**

Create `tests/__init__.py` with empty content.
Create `tests/routing/__init__.py` with empty content.

- [ ] **Step 3: Write the first failing test for `parse_stem`**

Create `tests/routing/test_dedup.py`:

```python
from classifier.routing.dedup import parse_stem


def test_parse_stem_dash_letter_rev():
    assert parse_stem("16-01-39-2602-B") == ("16-01-39-2602", "B")


def test_parse_stem_underscore_rev_dot_letter():
    assert parse_stem("16-01-27-2604_Rev.A") == ("16-01-27-2604", "A")


def test_parse_stem_dash_digit_rev():
    assert parse_stem("16-99-90-2601-1") == ("16-99-90-2601", "1")


def test_parse_stem_rev_with_trailing_text():
    assert parse_stem("16-01-52-2609_B-MR for MPFM") == ("16-01-52-2609", "B")


def test_parse_stem_no_rev():
    assert parse_stem("16-99-91-2620") == ("16-99-91-2620", None)


def test_parse_stem_does_not_strip_cust_ref_tail():
    # bare cust_ref must not be confused for "rev 2"
    assert parse_stem("16-99-91-2602") == ("16-99-91-2602", None)


def test_parse_stem_prefix_text_kept():
    assert parse_stem("CRS 16-99-90-2601-B") == ("crs 16-99-90-2601", "B")


def test_parse_stem_no_cust_ref_fallback():
    assert parse_stem("Drawing-A") == ("drawing", "A")


def test_parse_stem_no_cust_ref_no_rev():
    assert parse_stem("Some Random File") == ("some random file", None)
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `pip install -e ".[dev]"` (one time).
Run: `pytest tests/routing/test_dedup.py -v`
Expected: 9 failures, all `ImportError: cannot import name 'parse_stem'`.

- [ ] **Step 5: Implement `parse_stem`**

Create `src/classifier/routing/dedup.py`:

```python
"""Group source files by logical document and pick a single winner per group.

A logical document = files that share a stem after revision suffix is
stripped. Within a group, the winner is the latest revision in the
preferred format (pdf > doc/docx > xls/xlsx). Everything else in the
group is captured as `related[]` for audit.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")
_REV_AFTER_CUST_REF = re.compile(
    r"^[\s_-]+(?:Rev\.?)?([A-Z]|\d)(?:[\s_.-].*)?$",
    flags=re.IGNORECASE,
)
_REV_TAIL_FALLBACK = re.compile(
    r"[\s_-]+(?:Rev\.?)?([A-Z]|\d)(?:[\s_.-].*)?$",
    flags=re.IGNORECASE,
)


def parse_stem(stem: str) -> tuple[str, str | None]:
    """Return ``(group_key, revision)`` for a filename stem.

    The group key is lower-cased and whitespace-normalised. Revision is
    upper-cased letter or digit. Returns ``(stem.lower(), None)`` if no
    revision suffix is detected.
    """
    m = CUST_REF.search(stem)
    if m:
        prefix, suffix = stem[: m.end()], stem[m.end() :]
        rev = _REV_AFTER_CUST_REF.match(suffix)
        if rev:
            return prefix.strip().lower(), rev.group(1).upper()
        # No rev after cust_ref - keep full stem (extra prefix + cust_ref + any trailing text)
        return (stem).strip().lower(), None
    rev = _REV_TAIL_FALLBACK.search(stem)
    if rev:
        return stem[: rev.start()].strip().lower(), rev.group(1).upper()
    return stem.strip().lower(), None
```

- [ ] **Step 6: Run tests, verify they pass**

Run: `pytest tests/routing/test_dedup.py -v`
Expected: 9 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tests src/classifier/routing/dedup.py
git commit -m "feat(dedup): parse_stem with cust_ref-anchored revision strip"
```

---

## Task 2: `group_and_pick` — winner selection

**Files:**
- Modify: `src/classifier/routing/dedup.py`
- Modify: `tests/routing/test_dedup.py`

- [ ] **Step 1: Write failing tests for grouping + picking**

Append to `tests/routing/test_dedup.py`:

```python
from pathlib import Path

from classifier.routing.dedup import group_and_pick, FileEntry, DedupResult


def _p(name: str) -> Path:
    return Path("/src") / name


def test_group_and_pick_pdf_beats_docx_same_rev():
    files = [_p("16-01-39-2602-B.pdf"), _p("16-01-39-2602-B.docx")]
    result = group_and_pick(files)
    assert len(result) == 1
    [(_, r)] = result.items()
    assert r.primary == _p("16-01-39-2602-B.pdf")
    assert list(r.related) == [_p("16-01-39-2602-B.docx")]


def test_group_and_pick_digit_rev_beats_letter_rev():
    files = [_p("16-99-90-2601-B.docx"), _p("16-99-90-2601-1.pdf")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("16-99-90-2601-1.pdf")
    assert _p("16-99-90-2601-B.docx") in r.related


def test_group_and_pick_higher_letter_wins():
    files = [_p("16-99-90-2601-A.pdf"), _p("16-99-90-2601-B.pdf")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("16-99-90-2601-B.pdf")


def test_group_and_pick_doc_beats_xls():
    files = [_p("16-01-27-2604_Rev.A.xlsx"), _p("16-01-27-2604-A.doc")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("16-01-27-2604-A.doc")


def test_group_and_pick_skips_non_candidate_extensions_as_winners():
    # dwg/rar present alongside pdf — pdf wins; dwg/rar are related.
    files = [
        _p("16-99-91-2620-A.dwg"),
        _p("16-99-91-2620-A.pdf"),
        _p("Attachments.rar"),
    ]
    result = group_and_pick(files)
    pdf_group = [r for r in result.values() if r.primary.suffix == ".pdf"]
    assert len(pdf_group) == 1
    assert _p("16-99-91-2620-A.dwg") in pdf_group[0].related


def test_group_and_pick_group_with_only_non_candidate_has_no_winner():
    files = [_p("16-99-91-2620-A.dwg"), _p("16-99-91-2620-A.rar")]
    result = group_and_pick(files)
    # the spec says: such groups produce no entry in the result
    assert result == {}


def test_group_and_pick_xlsx_only_group_still_wins():
    files = [_p("CRS 16-99-90-2601-B.xlsx")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("CRS 16-99-90-2601-B.xlsx")
    assert r.related == ()


def test_group_and_pick_deterministic_lexical_tiebreak():
    files = [_p("a.pdf"), _p("b.pdf")]  # different stems, no rev
    result = group_and_pick(files)
    assert len(result) == 2
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/routing/test_dedup.py -v`
Expected: 8 new failures (`ImportError` on `group_and_pick`/`FileEntry`/`DedupResult`).

- [ ] **Step 3: Implement `FileEntry`, `DedupResult`, `group_and_pick`**

Append to `src/classifier/routing/dedup.py`:

```python
PREFERRED_EXTS: tuple[str, ...] = ("pdf", "doc", "docx", "xls", "xlsx")
FORMAT_PRIORITY: dict[str, int] = {
    "pdf": 0,
    "doc": 1,
    "docx": 1,
    "xls": 2,
    "xlsx": 2,
}


@dataclass(frozen=True)
class FileEntry:
    path: Path
    group_key: str
    revision: str | None
    rev_rank: tuple[int, str]
    ext: str  # lowercase, no leading dot


@dataclass(frozen=True)
class DedupResult:
    primary: Path
    related: tuple[Path, ...]


def _rev_rank(revision: str | None) -> tuple[int, str]:
    """Sort key for revisions. Larger == newer.

    Bucket -1: no revision detected.
    Bucket 0: letter revision (draft).
    Bucket 1: digit revision (issued).
    Within a bucket, lexical comparison of the value picks the latest.
    """
    if revision is None:
        return (-1, "")
    if revision.isdigit():
        return (1, revision)
    return (0, revision.upper())


def parse_entry(path: Path) -> FileEntry:
    group_key, revision = parse_stem(path.stem)
    ext = path.suffix.lstrip(".").lower()
    return FileEntry(
        path=path,
        group_key=group_key,
        revision=revision,
        rev_rank=_rev_rank(revision),
        ext=ext,
    )


def group_and_pick(files: Iterable[Path]) -> dict[str, DedupResult]:
    """Group files by ``group_key`` and pick one winner per group.

    Returns a mapping ``group_key -> DedupResult``. Groups with no
    candidate in ``PREFERRED_EXTS`` are omitted from the result.
    """
    groups: dict[str, list[FileEntry]] = defaultdict(list)
    for f in files:
        entry = parse_entry(f)
        groups[entry.group_key].append(entry)

    out: dict[str, DedupResult] = {}
    for key, entries in groups.items():
        candidates = [e for e in entries if e.ext in PREFERRED_EXTS]
        if not candidates:
            continue
        candidates.sort(
            key=lambda e: (
                # higher rev_rank first  -> negate via sort + reverse below
                e.rev_rank,
                # lower format priority first
                -FORMAT_PRIORITY[e.ext],
                # lexical fallback (string for determinism)
                str(e.path),
            ),
            reverse=True,
        )
        winner = candidates[0]
        related = tuple(
            sorted(
                (e.path for e in entries if e.path != winner.path),
                key=str,
            )
        )
        out[key] = DedupResult(primary=winner.path, related=related)
    return out
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/routing/test_dedup.py -v`
Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add src/classifier/routing/dedup.py tests/routing/test_dedup.py
git commit -m "feat(dedup): group_and_pick chooses one winner per logical doc"
```

---

## Task 3: `io/related_xlsx.py`

**Files:**
- Create: `src/classifier/io/related_xlsx.py`
- Create: `tests/io/__init__.py`, `tests/io/test_related_xlsx.py`

- [ ] **Step 1: Create `tests/io/__init__.py` (empty)**

- [ ] **Step 2: Write failing test**

Create `tests/io/test_related_xlsx.py`:

```python
from pathlib import Path

import pandas as pd

from classifier.io.related_xlsx import RelatedRow, write_related_xlsx


def test_write_related_xlsx_writes_expected_columns(tmp_path: Path):
    rows = [
        RelatedRow(
            cust_ref="16-01-39-2602",
            title="Doc title",
            class_label="Documents",
            discipline="INST",
            revision="B",
            chosen_file="16-01-39-2602-B.pdf",
            chosen_format="pdf",
            related_files=["16-01-39-2602-B.docx"],
            source_group_dir="C-A-ED-SA-15760.01-0068",
        ),
    ]
    out = write_related_xlsx(tmp_path, rows)
    assert out == tmp_path / "related-documents.xlsx"
    assert out.exists()

    df = pd.read_excel(out, engine="openpyxl")
    assert list(df.columns) == [
        "cust_ref",
        "title",
        "class",
        "discipline",
        "revision",
        "chosen_file",
        "chosen_format",
        "related_files",
        "related_count",
        "source_group_dir",
    ]
    assert df.iloc[0]["chosen_file"] == "16-01-39-2602-B.pdf"
    assert df.iloc[0]["related_files"] == "16-01-39-2602-B.docx"
    assert int(df.iloc[0]["related_count"]) == 1


def test_write_related_xlsx_joins_multiple_related_with_semicolon(tmp_path: Path):
    rows = [
        RelatedRow(
            cust_ref="x",
            title="t",
            class_label="Drawings",
            discipline="CIVIL",
            revision="1",
            chosen_file="a.pdf",
            chosen_format="pdf",
            related_files=["a.dwg", "a.docx", "Attachments.rar"],
            source_group_dir=".",
        ),
    ]
    out = write_related_xlsx(tmp_path, rows)
    df = pd.read_excel(out, engine="openpyxl")
    assert df.iloc[0]["related_files"] == "a.dwg; a.docx; Attachments.rar"
    assert int(df.iloc[0]["related_count"]) == 3


def test_write_related_xlsx_empty_rows_writes_header_only(tmp_path: Path):
    out = write_related_xlsx(tmp_path, [])
    assert out.exists()
    df = pd.read_excel(out, engine="openpyxl")
    assert len(df) == 0
    assert "cust_ref" in df.columns
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `pytest tests/io/test_related_xlsx.py -v`
Expected: 3 failures, `ImportError` on `RelatedRow`/`write_related_xlsx`.

- [ ] **Step 4: Implement `io/related_xlsx.py`**

Create `src/classifier/io/related_xlsx.py`:

```python
"""Write the related-documents.xlsx sidecar listing winners + dropped siblings."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

OUTPUT_FILENAME = "related-documents.xlsx"

COLUMNS = [
    "cust_ref",
    "title",
    "class",
    "discipline",
    "revision",
    "chosen_file",
    "chosen_format",
    "related_files",
    "related_count",
    "source_group_dir",
]


@dataclass(frozen=True)
class RelatedRow:
    cust_ref: str
    title: str
    class_label: str
    discipline: str
    revision: str | None
    chosen_file: str
    chosen_format: str
    related_files: list[str] = field(default_factory=list)
    source_group_dir: str = ""


def write_related_xlsx(dest_dir: Path, rows: list[RelatedRow]) -> Path:
    """Write ``<dest_dir>/related-documents.xlsx`` and return the path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / OUTPUT_FILENAME
    records = [
        {
            "cust_ref": r.cust_ref,
            "title": r.title,
            "class": r.class_label,
            "discipline": r.discipline,
            "revision": r.revision or "",
            "chosen_file": r.chosen_file,
            "chosen_format": r.chosen_format,
            "related_files": "; ".join(r.related_files),
            "related_count": len(r.related_files),
            "source_group_dir": r.source_group_dir,
        }
        for r in rows
    ]
    df = pd.DataFrame(records, columns=COLUMNS)
    df.to_excel(out, engine="openpyxl", index=False)
    return out
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `pytest tests/io/test_related_xlsx.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/classifier/io/related_xlsx.py tests/io
git commit -m "feat(io): write related-documents.xlsx sidecar"
```

---

## Task 4: Drop in-place / non-recursive code paths

**Files:**
- Modify: `src/classifier/routing/execute.py`
- Modify: `src/classifier/routing/matching.py`

- [ ] **Step 1: Simplify `execute.py`**

Replace contents of `src/classifier/routing/execute.py` with:

```python
"""Execute a route plan: copy files into class folders."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from classifier.routing.plan import RoutePlan, _class_folder_for

ProgressCallback = Callable[[int, int, Path], None]


def execute_plan(
    plan: RoutePlan,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, int]:
    """Copy each planned source -> dest. Returns counts per class folder."""
    counts: dict[str, int] = {}
    total = len(plan.operations)
    for i, (src, dst) in enumerate(plan.operations, start=1):
        cls = _class_folder_for(dst)
        if src.resolve() == dst.resolve():
            counts[cls] = counts.get(cls, 0) + 1
            if on_progress:
                on_progress(i, total, src)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        counts[cls] = counts.get(cls, 0) + 1
        if on_progress:
            on_progress(i, total, src)
    return counts
```

- [ ] **Step 2: Simplify `matching.py` — always recursive**

In `src/classifier/routing/matching.py`:

Replace the `_iter_source_files` function with:

```python
def _iter_source_files(source_dir: Path) -> list[Path]:
    """Yield files under source_dir recursively. Files already inside a
    class folder (Drawings/Documents/Undefined/Unmatched) are skipped so
    re-runs are safe.
    """
    out: list[Path] = []
    for f in source_dir.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(source_dir)
        except ValueError:
            continue
        if any(part in _CLASS_DIR_NAMES for part in rel.parts[:-1]):
            continue
        out.append(f)
    return sorted(out)
```

Replace the `match_files` signature and body header:

```python
def match_files(
    schedule_refs: dict[str, tuple[str, str]],
    source_dir: Path,
    files: list[Path] | None = None,
) -> MatchResult:
    """Match files against the schedule by cust_ref.

    If ``files`` is provided, match those exact paths (used after dedup).
    Otherwise walk ``source_dir`` recursively, skipping class folders.
    """
    if not source_dir.is_dir():
        raise ValueError(f"source_dir is not a directory: {source_dir}")

    matched: list[FileMatch] = []
    unmatched_unrecognized: list[Path] = []
    unmatched_not_in_schedule: list[Path] = []
    refs_seen: set[str] = set()

    iter_files = files if files is not None else _iter_source_files(source_dir)
    for f in iter_files:
```

(The rest of the loop body stays identical.)

- [ ] **Step 3: Run existing CLI smoke check**

Run: `python -c "from classifier.cli.sort import main"` to confirm imports still resolve.
Expected: no error.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/routing/execute.py src/classifier/routing/matching.py
git commit -m "refactor: drop in-place mode and non-recursive walk"
```

---

## Task 5: Wire dedup + xlsx into `cli/sort.py`

**Files:**
- Modify: `src/classifier/cli/sort.py`

- [ ] **Step 1: Replace `cli/sort.py` argparse + main**

Replace the entire contents of `src/classifier/cli/sort.py` with:

```python
"""Interactive CLI to sort schedule-referenced files into class folders.

Reads a schedule.xls and a directory of files named by reference number.
For each logical document (group of files that share a stem after the
revision suffix is stripped), one winner is copied: latest revision in
the preferred format (pdf > doc/docx > xls/xlsx). Everything else
(older revisions, alternate formats, .dwg, .rar, attachments) is
recorded in <dest>/related-documents.xlsx.

Resulting layout under --dest-dir:

    Drawings/<discipline>/...
    Documents/<discipline>/...
    Undefined/<discipline>/...
    Unmatched/...
    related-documents.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from classifier.cli.colors import _Color, _color_enabled
from classifier.cli.prompts import _prompt, _prompt_path
from classifier.cli.reporting import (
    _print_match_summary,
    _print_plan_summary,
    _print_progress,
)
from classifier.io.related_xlsx import RelatedRow, write_related_xlsx
from classifier.routing.analysis import find_collisions
from classifier.routing.dedup import group_and_pick
from classifier.routing.execute import execute_plan
from classifier.routing.matching import _iter_source_files, match_files
from classifier.routing.plan import build_plan
from classifier.routing.resolution import resolve_duplicates
from classifier.routing.schedule_refs import load_schedule_refs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sort-files",
        description="Copy schedule-referenced files into Drawings / Documents / "
                    "Undefined / Unmatched folders. One file per logical "
                    "document (latest revision; pdf > doc > xls).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  Interactive (prompts for dest-dir if omitted):
    sort-files --schedule schedule.xls --source-dir ./docs

  Non-interactive:
    sort-files --schedule schedule.xls --source-dir ./docs \\
        --dest-dir ./sorted --yes
""",
    )
    p.add_argument(
        "--schedule", required=True, type=Path,
        help="Path to the schedule .xls file (must have Sheet1 with a "
             "'Cust Ref #' and 'Title' column).",
    )
    p.add_argument(
        "--source-dir", required=True, type=Path,
        help="Directory containing the files to sort. Walked recursively. "
             "Files already inside class folders (Drawings/Documents/"
             "Undefined/Unmatched) are skipped so re-runs are safe.",
    )
    p.add_argument(
        "--dest-dir", type=Path, default=None,
        help="Destination directory. If omitted, you will be prompted.",
    )
    p.add_argument(
        "--include-title", action="store_true",
        help="Append the schedule's Title to the destination filename: "
             "'<original_stem> - <title><ext>'. Sanitized and truncated to "
             "--title-max-len chars. Unmatched files keep their original name.",
    )
    p.add_argument(
        "--title-max-len", type=int, default=100,
        help="Max characters of the title to include in the filename "
             "(default: 100). Only applies when --include-title is set.",
    )
    p.add_argument(
        "--on-duplicate", choices=("error", "skip", "rename"), default="error",
        help="What to do when two source files would land at the same "
             "destination. 'error' (default): abort. 'skip': keep first by "
             "path order. 'rename': append numeric suffix.",
    )
    p.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the final confirmation prompt and execute immediately.",
    )
    p.add_argument(
        "--no-color", action="store_true",
        help="Disable ANSI color output (also disabled automatically when "
             "stdout is not a TTY or when NO_COLOR is set).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    c = _Color(_color_enabled(args.no_color))

    # ---- Validate paths --------------------------------------------------
    if not args.schedule.exists():
        print(c.red(f"error: schedule not found: {args.schedule}"), file=sys.stderr)
        return 2
    if not args.source_dir.is_dir():
        print(c.red(f"error: source-dir is not a directory: {args.source_dir}"), file=sys.stderr)
        return 2

    # ---- Load schedule ---------------------------------------------------
    print(c.bold(f"Reading schedule: {args.schedule}"))
    try:
        refs = load_schedule_refs(args.schedule)
    except Exception as e:
        print(c.red(f"error reading schedule: {e}"), file=sys.stderr)
        return 2
    print(f"  {len(refs)} rows with valid cust_refs")

    # ---- Walk + dedup ----------------------------------------------------
    print(c.bold(f"Scanning {args.source_dir} (recursive)"))
    all_files = _iter_source_files(args.source_dir)
    groups = group_and_pick(all_files)
    winners = [r.primary for r in groups.values()]
    related_by_winner = {r.primary: list(r.related) for r in groups.values()}
    skipped_no_preferred = sum(
        1
        for f in all_files
        if f not in winners and not any(f in r.related for r in groups.values())
    )
    print(f"  {len(all_files)} file(s) found, {len(winners)} winner(s) after dedup")
    if skipped_no_preferred:
        print(c.yellow(f"  {skipped_no_preferred} file(s) skipped (no preferred format in group)"))

    # ---- Match winners only ---------------------------------------------
    result = match_files(refs, args.source_dir, files=winners)
    _print_match_summary(result, c)

    if not result.matched and not result.unmatched:
        print(c.yellow("\nno files to sort - exiting."))
        return 0

    # ---- Determine destination ------------------------------------------
    dest = args.dest_dir or _prompt_path("\nDestination directory")
    dest = Path(dest).expanduser().resolve()

    # ---- Build plan + resolve duplicates + check collisions -------------
    plan = build_plan(
        result,
        dest,
        include_title=args.include_title,
        title_max_len=args.title_max_len,
    )
    plan, dropped, renamed = resolve_duplicates(plan, args.on_duplicate)
    if dropped or renamed:
        print()
        if dropped:
            print(c.yellow(f"  --on-duplicate skip: {dropped} duplicate-name file(s) dropped"))
        if renamed:
            print(c.yellow(f"  --on-duplicate rename: {renamed} file(s) renamed with numeric suffix"))

    _print_plan_summary(plan, c)

    collisions = find_collisions(plan)
    if collisions:
        print()
        print(c.red(f"error: {len(collisions)} file(s) would overwrite existing destinations."))
        print(c.red("Use --on-duplicate skip to drop duplicates, or --on-duplicate rename to keep all."))
        for p in collisions[:10]:
            print(f"  {p}")
        if len(collisions) > 10:
            print(f"  ...and {len(collisions) - 10} more")
        print(c.red("\naborting."))
        return 1

    # ---- Confirm ---------------------------------------------------------
    print()
    print(c.bold(f"Ready to copy {len(plan.operations)} file(s) into {dest}"))
    if not args.yes:
        if _prompt(f"Proceed?", valid=("yes", "no"), default="no") != "yes":
            print(c.yellow("cancelled."))
            return 0

    # ---- Execute ---------------------------------------------------------
    print()
    print(c.bold("Copying files..."))
    counts = execute_plan(
        plan,
        on_progress=lambda d, t, s: _print_progress(d, t, s, c),
    )

    # ---- Build + write related-documents.xlsx ---------------------------
    rows = _build_related_rows(plan, result, related_by_winner, args.source_dir)
    xlsx_path = write_related_xlsx(dest, rows)

    # ---- Done ------------------------------------------------------------
    print()
    print(c.green(c.bold("Done.")))
    print(f"  destination: {dest}")
    for name in ("Drawings", "Documents", "Undefined", "Unmatched"):
        n = counts.get(name, 0)
        if n:
            print(f"  {name:<12s} {n}")
    print(f"  related sidecar: {xlsx_path}")
    return 0


def _build_related_rows(plan, result, related_by_winner, source_root):
    """Build RelatedRow list from the executed plan + dedup map."""
    from classifier.routing.dedup import parse_stem

    matched_by_path = {m.path: m for m in result.matched}
    rows: list[RelatedRow] = []
    for src, dst in plan.operations:
        m = matched_by_path.get(src)
        _, revision = parse_stem(src.stem)
        ext = src.suffix.lstrip(".").lower()
        try:
            rel_dir = src.parent.relative_to(source_root).as_posix() or "."
        except ValueError:
            rel_dir = str(src.parent)
        rows.append(
            RelatedRow(
                cust_ref=m.cust_ref if m else "",
                title=m.title if m else "",
                class_label=m.class_label if m else "",
                discipline=m.discipline if m else "",
                revision=revision,
                chosen_file=dst.name,
                chosen_format=ext,
                related_files=[p.name for p in related_by_winner.get(src, [])],
                source_group_dir=rel_dir,
            )
        )
    return rows


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke test imports**

Run: `python -c "from classifier.cli.sort import main, parse_args; parse_args(['--schedule','x.xls','--source-dir','y','--dest-dir','z','--yes'])"`
Expected: no error, no output.

- [ ] **Step 3: Verify removed flags are rejected**

Run: `python -c "from classifier.cli.sort import parse_args; parse_args(['--schedule','x','--source-dir','y','--mode','copy'])"` — but wrap in shell to capture exit:

```bash
python -c "
from classifier.cli.sort import parse_args
try:
    parse_args(['--schedule','x','--source-dir','y','--mode','copy'])
    print('FAIL: --mode should error')
except SystemExit as e:
    print('OK: --mode rejected with exit', e.code)
"
```

Expected: `OK: --mode rejected with exit 2`.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/cli/sort.py
git commit -m "feat(sort-files): wire dedup + related-documents.xlsx, drop in-place flags"
```

---

## Task 6: End-to-end smoke test

**Files:**
- Create: `tests/test_sort_files_e2e.py`

- [ ] **Step 1: Write the e2e test**

Create `tests/test_sort_files_e2e.py`:

```python
"""End-to-end test: build a tiny source tree + minimal schedule and run sort-files."""
from pathlib import Path

import pandas as pd
import pytest

from classifier.cli.sort import main


def _make_schedule(path: Path) -> None:
    """Write a minimal Sheet1 with the columns load_schedule_refs needs."""
    df = pd.DataFrame(
        [
            {"Cust Ref #": "16-01-39-2602", "Title": "MR for MPFM",   "Discip": "INST",  "Revision": "B"},
            {"Cust Ref #": "16-99-91-2620", "Title": "Plot Plan",     "Discip": "CIVIL", "Revision": "A"},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Sheet1", index=False)


def _touch(p: Path, content: bytes = b"") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_sort_files_dedup_and_xlsx(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "out"
    schedule = tmp_path / "schedule.xlsx"

    _make_schedule(schedule)

    # Group A: pdf wins over docx
    _touch(src / "C-A-ED-SA-15760.01-0068" / "16-01-39-2602-B.pdf")
    _touch(src / "C-A-ED-SA-15760.01-0068" / "16-01-39-2602-B.docx")
    _touch(src / "C-A-ED-SA-15760.01-0068" / "Comment Response Sheet-16-01-39-2602.xlsx")

    # Group B: dwg + pdf in same group; pdf wins, dwg becomes related
    _touch(src / "C-A-ED-SA-15760.01-0074" / "16-99-91-2620-A.dwg")
    _touch(src / "C-A-ED-SA-15760.01-0074" / "16-99-91-2620-A.pdf")

    rc = main([
        "--schedule", str(schedule),
        "--source-dir", str(src),
        "--dest-dir", str(dest),
        "--yes",
    ])
    assert rc == 0

    # Two PDFs copied under their class+discipline folders.
    assert (dest / "Documents" / "INST" / "16-01-39-2602-B.pdf").exists()
    assert (dest / "Drawings" / "CIVIL" / "16-99-91-2620-A.pdf").exists()

    # No docx, no dwg copied
    assert not list((dest / "Documents").rglob("*.docx"))
    assert not list((dest).rglob("*.dwg"))

    # Sidecar xlsx exists with both winners
    xlsx = dest / "related-documents.xlsx"
    assert xlsx.exists()
    df = pd.read_excel(xlsx, engine="openpyxl")
    assert len(df) == 2
    pdf_row = df[df["chosen_file"] == "16-01-39-2602-B.pdf"].iloc[0]
    assert "16-01-39-2602-B.docx" in str(pdf_row["related_files"])
    dwg_row = df[df["chosen_file"] == "16-99-91-2620-A.pdf"].iloc[0]
    assert "16-99-91-2620-A.dwg" in str(dwg_row["related_files"])
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_sort_files_e2e.py -v`
Expected: 1 passed.
If it fails because `load_schedule_refs` requires `.xls` not `.xlsx`, inspect [src/classifier/routing/schedule_refs.py](../../../src/classifier/routing/schedule_refs.py) — adjust the test to write `.xls` via `xlwt` or use the actual extension the loader expects. (If `.xls` is hardcoded, change the schedule path to `schedule.xlsx` AND verify the loader accepts xlsx; otherwise skip the e2e on this platform.)

- [ ] **Step 3: Run the entire test suite**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_sort_files_e2e.py
git commit -m "test: e2e smoke test for sort-files dedup + related xlsx"
```

---

## Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the `sort-files` section**

In `README.md`, replace the entire `## sort-files — interactive file routing` section (lines 106-166 roughly) with:

```markdown
## sort-files — file routing

Given a schedule and a directory whose filenames embed the schedule's
`cust_ref` numbers, this CLI copies one file per logical document into
class folders, plus an Excel sidecar listing the siblings that were not
copied.

```bash
# Interactive (prompts for dest-dir)
sort-files --schedule schedule.xls --source-dir ./docs

# Non-interactive
sort-files --schedule schedule.xls --source-dir ./docs \
           --dest-dir ./sorted --yes
```

| Flag | Purpose |
|---|---|
| `--schedule PATH` | Schedule `.xls` (must have Sheet1 with `Cust Ref #` and `Title`) |
| `--source-dir PATH` | Directory containing the files. Walked recursively. Files already inside class folders (`Drawings/`, `Documents/`, etc.) are skipped so re-runs are safe. |
| `--dest-dir PATH` | Destination directory. Prompted if omitted. |
| `--on-duplicate {error\|skip\|rename}` | What to do when two source files would land at the same destination. `error` (default): abort. `skip`: keep first by path order. `rename`: append numeric suffix (`foo.pdf`, `foo-2.pdf`, ...). |
| `--include-title` | Append the schedule's Title to the destination filename: `<original_stem> - <safe_title><ext>`. The title is sanitized and truncated to `--title-max-len`. Unmatched files keep their original name. |
| `--title-max-len N` | Max characters of the title to include (default 100). |
| `--yes`, `-y` | Skip the final confirmation |
| `--no-color` | Disable ANSI color (auto-disabled when not a TTY or `NO_COLOR` is set) |

**Dedup behaviour:**
- Files are grouped by stem with the revision suffix stripped.
- Within a group, the latest revision wins (digit revs supersede letter
  revs; within a bucket, lexically larger wins).
- Within the latest revision, format priority: `pdf > doc/docx > xls/xlsx`.
- Other extensions (`.dwg`, `.rar`, `.lnk`, ...) are never copied.
- Groups with no PDF/DOC/XLS candidate produce no output (a console
  counter reports the count).

**Resulting layout:**

The output is a **two-level `class / discipline / file`** tree, plus
the sidecar:

```
<dest>/
├── Drawings/
│   ├── CIVIL/
│   ├── PIPNG/
│   └── ...
├── Documents/
├── Undefined/
├── Unmatched/                  # no schedule match — kept flat
└── related-documents.xlsx      # one row per logical document
```

**`related-documents.xlsx` columns:**
`cust_ref`, `title`, `class`, `discipline`, `revision`, `chosen_file`,
`chosen_format`, `related_files` (semicolon-joined basenames),
`related_count`, `source_group_dir`.

Safety:
- **Collision detection** — aborts before any I/O if a destination path
  already exists or two source files would map to the same destination.
- **Honest reporting** — separately counts files with no `cust_ref`,
  files whose ref isn't in the schedule, and schedule rows with no
  matching file.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update sort-files section for dedup + related xlsx"
```

---

## Self-Review Checklist (run after writing all tasks)

1. **Spec coverage:**
   - Group key derivation → Task 1 ✓
   - Winner selection (rev rank + format priority) → Task 2 ✓
   - Related xlsx schema → Task 3 ✓
   - CLI flag removal → Task 5 ✓
   - In-place / clean-empty removal → Task 4 ✓
   - Always-recursive walk → Task 4 ✓
   - Pipeline order → Task 5 ✓
   - README update → Task 7 ✓
2. **Placeholders:** none. All code blocks complete; all commands explicit.
3. **Type consistency:** `RelatedRow.class_label` (Python attr) ↔ `class` (xlsx column) — handled in `write_related_xlsx`. `DedupResult.primary` is a `Path`; e2e and CLI both consume it as a `Path`. `parse_stem` returns `(str, str | None)` — used the same way in `parse_entry` and `_build_related_rows`.
