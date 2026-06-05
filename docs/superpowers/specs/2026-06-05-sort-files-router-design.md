# sort-files — classification-driven file router

**Date:** 2026-06-05
**Status:** Approved (design).
**Amendment (during planning):** `--on-duplicate` was dropped as YAGNI. A
winner's destination basename is a pure function of its filename stem, and a
group's key is derived from that same stem, so two distinct groups can never
produce the same basename in the same bucket — destination collisions are
impossible by construction. The implementation therefore omits the
`--on-duplicate` flag and any collision-resolution logic. Everything else
below stands.
**Scope:** A new standalone `sort-files` CLI + a loosely-coupled `routing/`
package. It CONSUMES the classified CSV (the source of truth) and routes
deliverable files into per-class bucket folders. It does not compute
classifications and does not touch the classify `run()` loop, the RDS
pipeline, or the schema.

## Goal

Pipeline #3 of the execution matrix: given the classified CSV and a source
directory of files, **copy one preferred file per logical document** into
`dest/<Drawings|Documents|Sheets>/`, choosing the format that suits the
document's class, and emit a report so nothing is silently dropped.

The other three pipelines already exist or are out of scope: #1 RDS→update
(`classify_from_rds`) ✅, #2 CSV→classified CSV (`classify`) ✅, #4 RDS→CSV
(explicitly skipped).

## Locked decisions

- **Source of truth:** the classified CSV (28-column, user-maintained).
  Each row carries `customer_ref` and `doc_type`. The router does NOT
  re-classify — it reads `doc_type` from the CSV.
- **Join key:** `customer_ref` (the `\d{2}-\d{2}-\d{2}-\d{4}` pattern, 100%
  populated), matched against the same pattern embedded in filenames.
- **Operation:** copy (non-destructive). Source dir is left intact.
- **One preferred file per logical document** (dedup + class-aware format
  preference).
- **Buckets** by `doc_type`: `drawing→Drawings/`, `document→Documents/`,
  `sheet→Sheets/`. Unmatched files → `Unmatched/`.
- **Sidecar:** a CSV report (`route-report.csv`). On-duplicate default
  `rename`. A `--dry-run` previews without copying.

## Data flow

```
1. Load classified CSV    io/classified_index.py   -> {norm cust_ref: Classification}
2. Walk source dir        cli/sort.py              recursive, all files
3. Group files            routing/dedup.py         by cust_ref (fallback: rev-stripped stem)
4. Pick winner per group  routing/dedup.py         latest rev, then class-aware format priority
5. Plan destinations      routing/plan.py          winner -> bucket / Unmatched; rows-with-no-file
6. Execute (copy)         routing/execute.py       shutil.copy2 (skipped on --dry-run)
7. Report + sidecar       routing/report.py        console summary + route-report.csv
```

The router is its own pipeline shape (CSV rows + files on disk → file
copies). It deliberately does NOT route through `pipeline/run.py` /
`classify_record`, because classification is already done in the CSV. It
reuses only pure helpers: `io/normalize` (key normalization) and
`io/schema` (column names).

## Components

### `io/classified_index.py`
```python
@dataclass(frozen=True)
class Classification:
    doc_type: str            # "drawing" | "document" | "sheet" (lowercased)
    title: str

def load_classified_index(csv_path: Path) -> dict[str, Classification]:
    """Map normalize_lookup_key(customer_ref) -> Classification.

    Reads the 28-col CSV (validate_schema). Rows with empty customer_ref are
    skipped. On a duplicate normalized customer_ref, the FIRST row wins and a
    count of conflicts is available to the caller (returned via a companion
    function or logged). doc_type is lowercased; unknown doc_type values
    (not in {drawing,document,sheet}) are kept as-is and will route to
    Unmatched at plan time.
    """
```
Uses `normalize_lookup_key` from `io/normalize` for the key and
`validate_schema`/`TARGET_COLUMNS` from `io/schema`.

### `routing/cust_ref.py` (pure)
```python
CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")

def extract_cust_ref(stem: str) -> str | None:
    """First cust_ref match in the filename stem, else None."""

def parse_group_and_revision(stem: str) -> tuple[str, str | None]:
    """Return (group_key, revision).

    If a cust_ref is present: group_key = the stem up to and including the
    cust_ref (lowercased, stripped), with a revision stripped only from the
    tail that FOLLOWS the cust_ref. revision is a single letter or single
    digit (so a 4-digit cust_ref tail is never misread as a revision).
    If no cust_ref: fall back to whole-stem revision stripping; group_key =
    rev-stripped stem (lowercased).
    """
```
Revision tail regex (letter OR single digit), anchored after the cust_ref,
mirroring the prior project convention:
`^[\s_-]+(?:Rev\.?)?([A-Z]|\d)(?:[\s_.-].*)?$` (IGNORECASE).

### `routing/dedup.py` (pure)
```python
CANDIDATE_EXTS = ("pdf", "doc", "docx", "xls", "xlsx")

# Lower priority value = preferred. Chosen by the matched row's class.
FORMAT_PRIORITY_DOC = {"pdf": 0, "doc": 1, "docx": 1, "xls": 2, "xlsx": 2}
FORMAT_PRIORITY_SHEET = {"xlsx": 0, "xls": 1, "pdf": 2, "doc": 3, "docx": 3}

def format_priority(ext: str, doc_type: str | None) -> int:
    """FORMAT_PRIORITY_SHEET for doc_type=='sheet', else FORMAT_PRIORITY_DOC.
       Unknown/Unmatched (doc_type None) uses FORMAT_PRIORITY_DOC (uniform
       pdf-first)."""

@dataclass(frozen=True)
class FileEntry:
    path: Path
    group_key: str                 # for dedup grouping (may carry a prefix)
    cust_ref: str | None           # normalize_lookup_key(extracted cust_ref) for index lookup
    revision: str | None
    rev_rank: tuple[int, object]   # (bucket, value); see below
    ext: str                       # lowercase, no leading dot

@dataclass(frozen=True)
class Group:
    group_key: str
    winner: Path | None            # None if no candidate-ext file in group
    related: tuple[Path, ...]      # everything else (older revs, non-winning
                                   # formats, AND all non-candidate exts)

def parse_entry(path: Path) -> FileEntry: ...
def group_files(paths: Iterable[Path]) -> dict[str, list[FileEntry]]: ...
def pick_winner(entries: list[FileEntry], doc_type: str | None) -> Group: ...
```

**rev_rank** = `(bucket, value)`: digit revision → `(1, int(value))`;
letter revision → `(0, value)`; no revision → `(-1, "")`. Larger tuple =
newer. (Cross-bucket comparisons never compare the heterogeneous `value`
field, so this is a safe total order.)

**Winner selection** within a group (two-step, unambiguous):
1. Restrict to candidate-ext files. If none → `winner=None`, all files
   become `related` (group is "skipped — no preferred format").
2. Among candidates: take max `rev_rank`; among those ties, min
   `format_priority(ext, doc_type)`; among those ties, lexically smallest
   filename. That single file is `winner`; every other file in the group
   (including non-candidate exts) is `related`.

### `routing/plan.py` (pure)
```python
BUCKET_FOR_DOCTYPE = {"drawing": "Drawings", "document": "Documents",
                      "sheet": "Sheets"}

@dataclass(frozen=True)
class CopyAction:
    src: Path
    dest: Path                 # dest_dir / bucket / filename (post on-duplicate)
    bucket: str                # Drawings/Documents/Sheets/Unmatched
    cust_ref: str | None
    title: str
    revision: str | None
    chosen_format: str
    related: tuple[Path, ...]
    status: str                # "copied" (planned) — set finally by execute

@dataclass(frozen=True)
class Plan:
    actions: tuple[CopyAction, ...]
    rows_without_file: tuple[str, ...]   # normalized cust_refs in index, no file
    skipped_no_preferred_format: tuple[str, ...]  # group_keys

def build_plan(groups, index, dest_dir, *, on_duplicate) -> Plan:
    """`groups` is dict[group_key -> list[FileEntry]] from group_files.
       For each group: take the cust_ref from its entries (all entries in a
       group share one cust_ref), resolve doc_type = index[cust_ref].doc_type
       (or None if cust_ref is None / not in index), then call
       pick_winner(entries, doc_type).
       - matched + known doc_type -> bucket = BUCKET_FOR_DOCTYPE[doc_type]
       - matched but unknown doc_type, or no cust_ref, or cust_ref not in
         index -> bucket = "Unmatched"
       Resolve dest = dest_dir/bucket/winner.name; on a dest collision apply
       on_duplicate (skip/rename/error). rename appends -2,-3,... to the stem.
       rows_without_file = index keys never matched by any group with a winner.
    """
```
Bucket assignment uses the matched row's class for format priority during
winner selection (so plan needs the class BEFORE winner pick — therefore
`build_plan` calls `pick_winner(entries, doc_type)` per group with the
class resolved from the index; `group_files` only groups, `pick_winner` is
called inside `build_plan`).

### `routing/execute.py` (I/O)
```python
def execute(plan: Plan, *, dry_run: bool) -> list[CopyAction]:
    """Create dest bucket dirs and shutil.copy2 each winner. Returns the
       actions actually performed (status set). No-op for dry_run."""
```

### `routing/report.py` (I/O for the sidecar; pure row-building separable)
```python
def report_rows(plan, index) -> list[dict]: ...      # pure
def write_report_csv(rows, dest_dir) -> Path: ...    # writes route-report.csv
def print_summary(plan, counts) -> None: ...         # console
```
Sidecar columns: `customer_ref, title, class, revision, chosen_file,
chosen_format, related_files (; -joined basenames), related_count, status`.
`status` ∈ `copied | unmatched-file | no-file-for-row |
skipped-no-preferred-format`.

### `cli/sort.py`
```
sort-files
  --classified-csv PATH   (default: output/classified.csv)
  --source-dir PATH       (required)
  --dest-dir PATH         (required)
  --on-duplicate {skip,rename,error}   (default: rename)
  --dry-run
```
Wires: load index → walk source → group → build plan → (execute unless
dry-run) → write sidecar (unless dry-run) → print summary. Skips files
already inside a `Drawings/Documents/Sheets/Unmatched` folder under
`--source-dir` so re-runs are safe.

New console script in `pyproject.toml`:
`sort-files = "classifier.cli.sort:main"`.

## Console summary counters

`groups`, `copied`, `dedup_dropped` (candidate-ext siblings not copied),
`unmatched_files` (winners routed to Unmatched/), `rows_without_file`,
`skipped_no_preferred_format`. Totals stay consistent: every source file is
accounted for as winner / related / skipped.

## Edge cases (resolved)

- **File with cust_ref not in CSV** → group deduped with uniform (doc)
  priority; winner → `Unmatched/`; siblings listed.
- **File with no cust_ref** → fallback grouping by rev-stripped stem;
  winner → `Unmatched/`.
- **CSV row with no matching file** → `rows_without_file`; sidecar status
  `no-file-for-row`.
- **Group with only non-candidate extensions** (.dwg/.rar/.lnk only) → not
  copied; `skipped_no_preferred_format`; files listed as related.
- **Duplicate dest name** → `--on-duplicate`: `rename` (stem-2, stem-3…),
  `skip` (don't copy, count it), `error` (raise).
- **Duplicate cust_ref in CSV with conflicting doc_type** → first row wins;
  conflict count surfaced in the summary.

## Testing

Pure unit tests (no I/O):
- `cust_ref`: extract on present/absent; `parse_group_and_revision` across
  `16-01-39-2602-B`, `16-01-27-2604_Rev.A`, `16-99-90-2601-1`,
  `16-01-52-2609_B-MR for MPFM`, a no-cust_ref stem.
- `dedup`: rev_rank ordering (`2>1`, `1>B`, `B>A`, `B>none`); class-aware
  format priority (`sheet`→xlsx wins; `drawing`→pdf wins); non-candidate
  exts never win but appear in related; empty/single/all-non-candidate
  groups.
- `plan`: bucket assignment per doc_type; Unmatched for no-match;
  rows_without_file; on-duplicate rename/skip/error.
- `classified_index`: cust_ref normalization; first-wins on dup; empty
  cust_ref skipped.

Smoke test (`tmp_path`): create a small classified CSV + a source tree with
multiple formats/revisions per cust_ref (incl. a `.dwg` and an unmatched
file), run the planner+execute, assert the dest tree layout, the chosen
winners, and the sidecar rows.

## Out of scope

- Re-classifying files (the CSV is authoritative).
- The RDS→CSV export (#4) — skipped per decision.
- Moving (only copy). Cross-run grouping (groups are per single run).
- Any change to `classify`, `classify_from_rds`, scoring, or the schema.
