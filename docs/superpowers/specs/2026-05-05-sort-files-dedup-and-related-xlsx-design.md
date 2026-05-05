# sort-files: Dedup, Format Preference, and Related-Documents Excel

**Date:** 2026-05-05
**Status:** Approved (design)
**Scope:** `sort-files` CLI only. Schedule classification (`classify`) unchanged.

## Problem

`sort-files` currently copies every file under `--source-dir` whose name
embeds a schedule `cust_ref`. This produces noise:

- Multiple revisions of the same logical document are all copied.
- Multiple formats of the same document (PDF + DOC + XLS) are all copied.
- Non-deliverable artifacts (`.dwg`, `.rar`, `.lnk`, attachments) are copied.

Operators want **one file per logical document** — the latest revision,
in the most preferred format — with a sidecar Excel listing the siblings
that were left behind so nothing is silently lost.

## Goals

1. Per logical document, copy exactly one file: latest revision, format
   priority `pdf > doc/docx > xls/xlsx`.
2. Skip every other extension entirely (no `.dwg`, no `.rar`, no `.lnk`).
3. Emit `<dest>/related-documents.xlsx` listing winner + siblings per group.
4. Simplify the CLI: `copy` is the only mode; recursion is always on.

## Non-goals

- Changing `classify` output or schema.
- Changing matching logic (`cust_ref` extraction stays as-is).
- Cross-source-dir grouping (groups are computed within one run).

## Logical document grouping

A "logical document" = files that share a stem after revision suffix is
stripped.

**Group key derivation.** Naive end-anchored stripping would clip the
trailing 4-digit segment of a bare `cust_ref` (e.g. `16-01-39-2602` →
`16-01-39-260`). The algorithm anchors on the `cust_ref` first, then
strips a revision only from the tail that follows it:

```python
CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")
REV_TAIL = re.compile(
    r"^[\s_-]+(?:Rev\.?)?([A-Z]|\d)(?:[\s_.-].*)?$",
    flags=re.IGNORECASE,
)

def parse_stem(stem: str) -> tuple[str, str | None]:
    """Return (group_key, revision)."""
    m = CUST_REF.search(stem)
    if m:
        prefix, suffix = stem[: m.end()], stem[m.end() :]
        rev = REV_TAIL.match(suffix)
        if rev:
            return prefix.strip().lower(), rev.group(1).upper()
        return (prefix + suffix).strip().lower(), None
    # No cust_ref: fall back to whole-stem strip.
    rev = re.search(
        r"[\s_-]+(?:Rev\.?)?([A-Z]|\d)(?:[\s_.-].*)?$", stem, re.IGNORECASE
    )
    if rev:
        return stem[: rev.start()].strip().lower(), rev.group(1).upper()
    return stem.strip().lower(), None
```

Digit revisions are limited to 1 character so a `-2602` cust_ref tail
cannot be misread as rev `2`.

Examples (from `Transmittals-To-Client.txt`):

| filename | stem | group_key | revision |
|---|---|---|---|
| `16-01-39-2602-B.pdf` | `16-01-39-2602-B` | `16-01-39-2602` | `B` |
| `16-01-39-2602-B.docx` | `16-01-39-2602-B` | `16-01-39-2602` | `B` |
| `16-01-27-2604_Rev.A.xlsx` | `16-01-27-2604_Rev.A` | `16-01-27-2604` | `A` |
| `16-99-90-2601-1.docx` | `16-99-90-2601-1` | `16-99-90-2601` | `1` |
| `16-99-90-2601-B.docx` | `16-99-90-2601-B` | `16-99-90-2601` | `B` |
| `16-01-52-2609_B-MR for MPFM.docx` | `16-01-52-2609_B-MR for MPFM` | `16-01-52-2609` | `B` |
| `CRS 16-99-90-2601-B.xlsx` | `CRS 16-99-90-2601-B` | `crs 16-99-90-2601` | `B` |

The CRS row above is **not** the same group as `16-99-90-2601` because
its stem has a `CRS ` prefix — it lands in its own group and (since no
PDF/DOC sibling exists in *that* group) becomes a winner in its own
right or, if no PDF/DOC, an XLSX winner. That is acceptable: CRS sheets
are independent deliverables in the schedule.

## Winner selection

Within a group, candidates are limited to the five preferred extensions:
`.pdf .doc .docx .xls .xlsx`. Files with other extensions never win.

**Sort key (descending = winner first):**

1. `rev_rank` — `(bucket, value)` where digit revisions get bucket `1`
   and letter revisions get bucket `0`. Within a bucket, larger value
   wins. Files with no parsed revision get bucket `-1`.
   *Rationale:* in this project's convention, numeric revisions are
   issued/approved versions and supersede alphabetic draft revisions.
2. `format_priority` — `pdf=0, doc=1, docx=1, xls=2, xlsx=2`. Lower wins.
3. Fallback: lexical filename for determinism.

Everything else in the group (older revisions, non-winning formats among
the five, plus *all* non-candidate extensions sharing the same
`group_key`) is captured as `related[]`.

## Module layout

### New: `src/classifier/routing/dedup.py`

Pure logic, no I/O beyond `Path` operations.

```python
PREFERRED_EXTS = ("pdf", "doc", "docx", "xls", "xlsx")
FORMAT_PRIORITY = {"pdf": 0, "doc": 1, "docx": 1, "xls": 2, "xlsx": 2}

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

def parse_entry(path: Path) -> FileEntry: ...
def group_and_pick(files: Iterable[Path]) -> dict[str, DedupResult]: ...
```

### New: `src/classifier/io/related_xlsx.py`

```python
def write_related_xlsx(
    dest_dir: Path,
    rows: list[RelatedRow],
) -> Path:
    """Write <dest>/related-documents.xlsx. Returns the path."""
```

`RelatedRow` is a small dataclass with the columns listed below. Uses
`pandas.DataFrame.to_excel(engine="openpyxl")`.

### Modified

- `src/classifier/cli/sort.py` — drops `--mode`, `--recursive`,
  `--clean-empty-dirs`; calls dedup before matching; calls
  `write_related_xlsx` after execute.
- `src/classifier/cli/prompts.py` — drops the mode prompt and the
  in-place confirmation. Keeps the dest-dir prompt.
- `src/classifier/routing/execute.py` — drops `mode` parameter; only
  `shutil.copy2` path remains; drops the `--clean-empty-dirs` cleanup.
- `src/classifier/routing/matching.py` — input set is winners only.
  Public signature unchanged (still takes `Iterable[Path]`).

## CLI surface (after change)

| Flag | Status |
|---|---|
| `--schedule PATH` | kept (required) |
| `--source-dir PATH` | kept (required) |
| `--dest-dir PATH` | kept; required (no in-place fallback) |
| `--on-duplicate {error\|skip\|rename}` | kept |
| `--include-title` | kept |
| `--title-max-len N` | kept |
| `--yes`, `-y` | kept |
| `--no-color` | kept |
| `--mode {in-place\|copy}` | **removed** |
| `--recursive`, `-r` | **removed** (always on) |
| `--clean-empty-dirs` | **removed** (was in-place only) |

Walking the source dir is always recursive. Files already inside a
class folder (`Drawings/`, `Documents/`, `Undefined/`, `Unmatched/`)
under `--source-dir` are still skipped so re-runs are safe.

## Pipeline order

```
1. read schedule         io/schedule_reader.py        unchanged
2. walk source dir       cli/sort.py                  always recursive
3. DEDUP                 routing/dedup.py             NEW — winners + related[]
4. match winners→rows    routing/matching.py          input = winners only
5. plan destinations     routing/plan.py              unchanged
6. analyze + report      routing/analysis.py          unchanged
7. confirm               cli/prompts.py               simplified
8. execute (copy only)   routing/execute.py           in-place branch deleted
9. write related xlsx    io/related_xlsx.py           NEW
```

## related-documents.xlsx schema

Written to `<dest-dir>/related-documents.xlsx`. One row per group whose
winner was copied (matched or unmatched). Columns:

| Column | Source |
|---|---|
| `cust_ref` | schedule match (blank if unmatched) |
| `title` | schedule match (blank if unmatched) |
| `class` | schedule match (blank if unmatched) |
| `discipline` | schedule match (blank if unmatched) |
| `revision` | parsed rev of winner |
| `chosen_file` | basename of copied winner |
| `chosen_format` | `pdf`/`doc`/`docx`/`xls`/`xlsx` |
| `related_files` | `; `-joined basenames of all siblings |
| `related_count` | `len(related)` |
| `source_group_dir` | parent dir of winner relative to `--source-dir` |

A group with zero candidates among the five preferred extensions is
**not** copied and **not** listed in the xlsx. It is reported in the
console output under a new "Skipped (no preferred format)" counter so
nothing is silently lost.

## Reporting changes

`routing/analysis.py` console summary gains two counters:

- `dedup_dropped` — count of source files not copied because a sibling
  in the same group won.
- `skipped_no_preferred_format` — count of groups with no PDF/DOC/XLS
  candidate.

The existing counters (matched / unmatched / no-cust-ref) continue to
operate on **winners only** so totals remain consistent.

## Testing approach

Unit tests for `dedup.py`:

- group key derivation across the patterns in
  `Transmittals-To-Client.txt`.
- revision parse + rank ordering: `B > A`, `1 > B`, `2 > 1`, `B > none`.
- format priority within a single revision.
- non-candidate extensions never win but always appear in `related`.
- empty-group / single-file group / all-non-candidate group.

Smoke test for the full pipeline against the existing
`Transmittals-To-Client.txt` tree (or a synthetic copy): assert the
winner basenames and the rendered xlsx columns.

## Out of scope / not changing

- `classify` console script and CSV output.
- `harvest`, `evaluate`, `dump-buckets`, `dump-undefined`.
- Schedule reading and matching logic.
- `core/revisions.py` — current revision logic (schedule-side) is
  separate from filename-side parsing introduced here. We do **not**
  unify them in this change; doing so would expand scope.

## Migration / breaking changes

`sort-files` is breaking:

- `--mode`, `--recursive`, `--clean-empty-dirs` removed (argparse error
  if passed).
- `--dest-dir` becomes required.
- Output set shrinks (1 file per group instead of N).

The README's `sort-files` section is updated to reflect the new flags
and the new `related-documents.xlsx` output.
