# sort-by-source — copy files into doc_source buckets

**Date:** 2026-06-05
**Status:** Approved (design).
**Scope:** A new `sort-by-source` CLI that copies one preferred file per
logical document from labelled source folders into `doc_source` buckets under
a destination, using the documents table to split matched vs unmatched. Reuses
the existing router internals; no change to the classifier core.

## Goal

Given three source folders, each tied to a `doc_source`:
- feed → `D:\…\1.2 FEED\CD April 02\PDF`
- proposal → `D:\…\2.1 Proposal Writeups`
- deliverable → `D:\…\5. … \Transmittals\TO CLIENT`

copy one preferred file per logical document into
`D:\Sahil_input\{feed,deliverable,proposal,unmatched}\`, where a file is
**unmatched** when its `customer_ref` is not present in the documents table.

## Locked decisions

- **Bucket = source label**; **unmatched = customer_ref not in the documents
  table**.
- **One preferred file per logical document** (latest revision; format
  preference pdf for drawing/document, xlsx for sheet — using the matched
  row's `doc_type`; uniform pdf-preference when unmatched).
- **Flat** layout inside each bucket; `-2`/`-3` suffix on a name collision.
- **Copy** (non-destructive). Source key = `customer_ref`
  (`\d{2}-\d{2}-\d{2}-\d{4}`) embedded in filenames (the `file_name` column is
  empty in the export).

## Reuse

- `routing/cust_ref.py` — `extract_cust_ref`, `parse_group_and_revision`.
- `routing/dedup.py` — `group_files`, `pick_winner(entries, doc_type)`,
  `FileEntry`, `Group`, `CANDIDATE_EXTS`.

## New components

### `src/classifier/routing/source_plan.py` (pure)
```python
@dataclass(frozen=True)
class SourceCopyAction:
    src: Path
    bucket: str                 # feed/proposal/deliverable/unmatched
    customer_ref: str | None    # normalized
    matched: bool
    chosen_format: str
    related: tuple[Path, ...]

@dataclass(frozen=True)
class SourcePlan:
    actions: tuple[SourceCopyAction, ...]
    skipped_no_preferred: tuple[tuple[str, str], ...]   # (label, group_key)

def build_source_plan(
    sources: list[tuple[str, list[Path]]],     # (label, file paths)
    doc_index: dict[str, str],                 # norm customer_ref -> doc_type
) -> SourcePlan:
    """Per source: group files by logical document; a group is matched iff its
    customer_ref is a key in doc_index. Bucket = the source label when matched,
    else "unmatched". Winner picked with the matched row's doc_type (None when
    unmatched). Groups with no candidate-ext file are recorded as skipped."""
```

### `src/classifier/cli/sort_source.py` (CLI + I/O)
Console script `sort-by-source`. Flags:
- `--source LABEL=DIR` (repeatable; e.g. `feed=…`)
- `--documents PATH` (the documents-table CSV; must have `customer_ref` +
  `doc_type` columns — read with pandas, NO 28-col schema validation since the
  export is wider)
- `--dest PATH`
- `--dry-run`

Flow: load `doc_index` (`{normalize_lookup_key(customer_ref): doc_type.lower()}`)
→ per `--source`, recursively collect files → `build_source_plan` → execute
copies (`shutil.copy2` into `dest/<bucket>/<name>`, flat, `-2` collision guard;
skipped under `--dry-run`) → write `dest/route-by-source-report.csv` (unless
dry-run) → print summary.

Report columns: `source, customer_ref, bucket, matched, chosen_file,
chosen_format, related_count, status` (`status ∈ copied | skipped-no-preferred-format`).

Summary: per bucket — groups, copied; plus total unmatched and
skipped-no-preferred-format.

## Testing

- `tests/routing/test_source_plan.py` (pure): matched cust_ref → label bucket;
  cust_ref absent from doc_index → `unmatched`; dedup picks one winner;
  `doc_type == "sheet"` prefers xlsx; a group with only non-candidate exts →
  `skipped_no_preferred`.
- `tests/cli/test_sort_source.py` (tmp dirs): two labelled source dirs + a tiny
  documents CSV; run `main([...])`; assert winners land in the right buckets,
  an unmatched cust_ref lands in `unmatched/`, the report exists, and
  `--dry-run` copies nothing.

## Run plan (Sahil)

1. Build + test the CLI (committed to the repo).
2. **Dry-run** on the real folders; review matched/unmatched/copied counts per
   bucket with the user.
3. On approval, real copy into `D:\Sahil_input`.

```
sort-by-source --documents input/_document__202606051455.csv --dest "D:/Sahil_input" \
  --source "feed=D:/Indus/DEST Pilot DATA/KR/HISTORIC Projects/SAHIL (Clean)/1.2 FEED/CD April 02/PDF" \
  --source "proposal=D:/Indus/DEST Pilot DATA/KR/HISTORIC Projects/SAHIL (Clean)/2.1 Proposal Writeups" \
  --source "deliverable=D:/Indus/DEST Pilot DATA/KR/HISTORIC Projects/SAHIL (Clean)/5. Deliverables + Correspondence - Execution/Transmittals/TO CLIENT"
```

## Out of scope

- Moving files (copy only); preserving sub-folder structure (flat only).
- Bucketing by the table's doc_source rather than the source folder (the
  folder is authoritative; the table only decides matched/unmatched + the
  winner's format preference).
- The `planned` doc_source (no source folder; those rows have no files).
