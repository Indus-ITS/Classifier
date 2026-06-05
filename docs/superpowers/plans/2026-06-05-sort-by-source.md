# sort-by-source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** A `sort-by-source` CLI that copies one preferred file per logical document from labelled source folders into `doc_source` buckets, using the documents table to split matched vs unmatched. Reuses `routing/cust_ref` + `routing/dedup`.

**Spec:** `docs/superpowers/specs/2026-06-05-sort-by-source-design.md`

**Conventions:** `python -m pytest` from repo root; Windows (PowerShell-via-Bash BLOCKED — use Read/Write/Edit + `python`/`git`); do NOT stage `docs/superpowers/plans/2026-06-05-sheets-class-phase2.md` or untracked `input/_document__*.csv`; commit trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Baseline: 91 tests pass.

---

### Task 1: Pure planner `routing/source_plan.py` (+ tests)

**Files:** Create `src/classifier/routing/source_plan.py`, `tests/routing/test_source_plan.py`.

- [ ] **Step 1: Write the failing tests**

`tests/routing/test_source_plan.py`:
```python
from pathlib import Path
from classifier.routing.source_plan import build_source_plan


def test_matched_goes_to_label_bucket_unmatched_to_unmatched():
    sources = [("feed", [Path("16-01-19-2602-B.pdf"), Path("99-99-99-9999-A.pdf")])]
    plan = build_source_plan(sources, {"16-01-19-2602": "document"})
    by_ref = {a.customer_ref: a for a in plan.actions}
    assert by_ref["16-01-19-2602"].bucket == "feed"
    assert by_ref["16-01-19-2602"].matched is True
    assert by_ref["99-99-99-9999"].bucket == "unmatched"
    assert by_ref["99-99-99-9999"].matched is False


def test_dedup_one_winner_pdf_for_document():
    sources = [("deliverable", [
        Path("d/16-01-19-2602-B.pdf"),
        Path("d/16-01-19-2602-B.docx"),
        Path("d/16-01-19-2602-A.pdf"),
    ])]
    plan = build_source_plan(sources, {"16-01-19-2602": "document"})
    acts = [a for a in plan.actions if a.customer_ref == "16-01-19-2602"]
    assert len(acts) == 1
    assert acts[0].src.name == "16-01-19-2602-B.pdf"
    assert acts[0].chosen_format == "pdf"


def test_sheet_prefers_xlsx():
    sources = [("deliverable", [
        Path("16-01-19-2602-B.pdf"), Path("16-01-19-2602-B.xlsx")])]
    plan = build_source_plan(sources, {"16-01-19-2602": "sheet"})
    a = next(a for a in plan.actions if a.customer_ref == "16-01-19-2602")
    assert a.src.name == "16-01-19-2602-B.xlsx"


def test_only_non_candidate_ext_is_skipped():
    sources = [("feed", [Path("16-01-19-2602-B.dwg")])]
    plan = build_source_plan(sources, {"16-01-19-2602": "drawing"})
    assert plan.actions == ()
    assert ("feed", "16-01-19-2602") in plan.skipped_no_preferred
```

- [ ] **Step 2: Run → FAIL** (`python -m pytest tests/routing/test_source_plan.py -v`).

- [ ] **Step 3: Implement `src/classifier/routing/source_plan.py`**
```python
"""Pure planner for sort-by-source: route one preferred file per logical
document into doc_source buckets, splitting matched vs unmatched by the
documents table. No I/O (Path arithmetic only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier.routing.dedup import group_files, pick_winner

UNMATCHED = "unmatched"


@dataclass(frozen=True)
class SourceCopyAction:
    src: Path
    bucket: str
    customer_ref: str | None
    matched: bool
    chosen_format: str
    related: tuple[Path, ...]


@dataclass(frozen=True)
class SourcePlan:
    actions: tuple[SourceCopyAction, ...]
    skipped_no_preferred: tuple[tuple[str, str], ...]


def build_source_plan(sources, doc_index: dict[str, str]) -> SourcePlan:
    """sources: iterable of (label, [Path]). doc_index: normalized
    customer_ref -> doc_type (membership decides matched)."""
    actions: list[SourceCopyAction] = []
    skipped: list[tuple[str, str]] = []
    for label, paths in sources:
        groups = group_files(list(paths))
        for group_key in sorted(groups):
            entries = groups[group_key]
            cust_ref = next((e.cust_ref for e in entries if e.cust_ref), None)
            matched = cust_ref is not None and cust_ref in doc_index
            bucket = label if matched else UNMATCHED
            doc_type = doc_index.get(cust_ref) if matched else None
            g = pick_winner(entries, doc_type)
            if g.winner is None:
                skipped.append((label, group_key))
                continue
            we = next(e for e in entries if e.path == g.winner)
            actions.append(SourceCopyAction(
                src=g.winner, bucket=bucket, customer_ref=cust_ref,
                matched=matched, chosen_format=we.ext, related=g.related,
            ))
    return SourcePlan(tuple(actions), tuple(skipped))
```

- [ ] **Step 4: Run → PASS (4).** Then `python -m pytest -q` → 95 passed.

- [ ] **Step 5: Commit**
```bash
git add src/classifier/routing/source_plan.py tests/routing/test_source_plan.py
git commit -m "$(cat <<'EOF'
feat(routing): source_plan — one winner per doc into source buckets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: CLI `cli/sort_source.py` + console script + smoke test

**Files:** Create `src/classifier/cli/sort_source.py`, `tests/cli/test_sort_source.py`; modify `pyproject.toml`.

- [ ] **Step 1: Write the smoke test**

`tests/cli/test_sort_source.py`:
```python
import csv
from pathlib import Path
from classifier.cli import sort_source as ss


def _docs(path, rows):
    cols = ["customer_ref", "doc_type"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(cols)
        for r in rows: w.writerow(r)


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x")


def test_cli_copies_into_buckets(tmp_path):
    feed = tmp_path / "FEED"; deliv = tmp_path / "DELIV"
    _touch(feed / "16-01-19-2602-B.pdf")
    _touch(feed / "16-01-19-2602-B.docx")        # sibling, not copied
    _touch(deliv / "sub" / "16-01-19-2605-A.pdf")
    _touch(deliv / "sub" / "99-99-99-9999-A.pdf")  # unmatched
    docs = tmp_path / "docs.csv"
    _docs(docs, [("16-01-19-2602", "document"), ("16-01-19-2605", "sheet")])
    dest = tmp_path / "out"

    rc = ss.main(["--documents", str(docs), "--dest", str(dest),
                  "--source", f"feed={feed}", "--source", f"deliverable={deliv}"])
    assert rc == 0
    assert (dest / "feed" / "16-01-19-2602-B.pdf").exists()
    assert not (dest / "feed" / "16-01-19-2602-B.docx").exists()  # deduped
    assert (dest / "deliverable" / "16-01-19-2605-A.pdf").exists()
    assert (dest / "unmatched" / "99-99-99-9999-A.pdf").exists()
    assert (dest / "route-by-source-report.csv").exists()


def test_dry_run_copies_nothing(tmp_path):
    feed = tmp_path / "FEED"; _touch(feed / "16-01-19-2602-B.pdf")
    docs = tmp_path / "docs.csv"; _docs(docs, [("16-01-19-2602", "document")])
    dest = tmp_path / "out"
    rc = ss.main(["--documents", str(docs), "--dest", str(dest),
                  "--source", f"feed={feed}", "--dry-run"])
    assert rc == 0
    assert not dest.exists()
```

- [ ] **Step 2: Run → FAIL** (no module).

- [ ] **Step 3: Implement `src/classifier/cli/sort_source.py`**
```python
"""sort-by-source: copy one preferred file per logical document from labelled
source folders into doc_source buckets, splitting matched/unmatched via the
documents table. See docs/superpowers/specs/2026-06-05-sort-by-source-design.md.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import pandas as pd

from classifier.io.normalize import is_empty, normalize_lookup_key
from classifier.routing.source_plan import build_source_plan

REPORT_COLS = ("source", "customer_ref", "bucket", "matched",
               "chosen_file", "chosen_format", "related_count", "status")


def _load_doc_index(path: Path) -> dict[str, str]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
    for c in ("customer_ref", "doc_type"):
        if c not in df.columns:
            raise SystemExit(f"{path}: missing required column {c!r}")
    index: dict[str, str] = {}
    for _, row in df.iterrows():
        key = normalize_lookup_key(row["customer_ref"])
        if not key:
            continue
        index.setdefault(key, "" if is_empty(row["doc_type"])
                         else str(row["doc_type"]).strip().lower())
    return index


def _parse_source(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise SystemExit(f"--source must be LABEL=DIR, got {spec!r}")
    label, _, path = spec.partition("=")
    label = label.strip()
    if not label:
        raise SystemExit(f"--source missing label: {spec!r}")
    return label, Path(path.strip())


def _collect(d: Path) -> list[Path]:
    if not d.exists():
        raise SystemExit(f"source dir not found: {d}")
    return sorted(p for p in d.rglob("*") if p.is_file())


def _unique_dest(dest: Path, taken: set[Path]) -> Path:
    if dest not in taken:
        return dest
    n = 2
    while True:
        cand = dest.with_name(f"{dest.stem}-{n}{dest.suffix}")
        if cand not in taken:
            return cand
        n += 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sort-by-source")
    ap.add_argument("--source", action="append", default=[], metavar="LABEL=DIR",
                    help="repeatable; e.g. feed=/path/to/feed")
    ap.add_argument("--documents", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not args.source:
        raise SystemExit("at least one --source LABEL=DIR is required")
    if not args.documents.exists():
        raise SystemExit(f"documents CSV not found: {args.documents}")

    doc_index = _load_doc_index(args.documents)
    sources = [(label, _collect(path)) for label, path in
               (_parse_source(s) for s in args.source)]
    plan = build_source_plan(sources, doc_index)

    taken: set[Path] = set()
    rows: list[dict] = []
    per_bucket: dict[str, int] = {}
    for a in plan.actions:
        dest = _unique_dest(args.dest / a.bucket / a.src.name, taken)
        taken.add(dest)
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(a.src, dest)
        per_bucket[a.bucket] = per_bucket.get(a.bucket, 0) + 1
        rows.append({
            "source": a.bucket if a.matched else "(unmatched)",
            "customer_ref": a.customer_ref or "",
            "bucket": a.bucket,
            "matched": a.matched,
            "chosen_file": dest.name,
            "chosen_format": a.chosen_format,
            "related_count": len(a.related),
            "status": "copied",
        })

    if not args.dry_run:
        args.dest.mkdir(parents=True, exist_ok=True)
        report = args.dest / "route-by-source-report.csv"
        with report.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=REPORT_COLS, lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    print(f"\n{'[dry-run] ' if args.dry_run else ''}planned {len(plan.actions)} copies "
          f"({len(plan.skipped_no_preferred)} groups skipped: no preferred format)")
    for b in sorted(per_bucket):
        print(f"  {b:14s} {per_bucket[b]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add console script** — in `pyproject.toml` `[project.scripts]`:
```toml
sort-by-source      = "classifier.cli.sort_source:main"
```

- [ ] **Step 5: Run** `python -m pytest tests/cli/test_sort_source.py -v` → PASS (2); then `python -m pytest -q` → 97 passed.

- [ ] **Step 6: Commit**
```bash
git add src/classifier/cli/sort_source.py pyproject.toml tests/cli/test_sort_source.py
git commit -m "$(cat <<'EOF'
feat(cli): sort-by-source copies winners into doc_source buckets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification
- [ ] `python -m pytest -q` — all green (97).
- [ ] `core/` untouched: `git diff --name-only <base>..HEAD -- src/classifier/core` empty.
- [ ] (Controller-run, not a code task) `--dry-run` on the real Sahil folders; review counts; then real copy into `D:\Sahil_input`.
