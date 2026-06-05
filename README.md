# Document Classifier

Classifies engineering deliverable rows into three classes — **drawing**,
**sheet**, or **document** — plus a 3-letter `type` code and a
`discipline_id`, all inferred from the row's `title` via hand-maintained
keyword rules. Works on CSV exports, a documents-table snapshot, or a live
PostgreSQL table.

## Quick start

```bash
pip install -e .

# Process a documents-table export (the primary flow):
update-snapshot --input path/to/documents_export.csv
```

`update-snapshot` fills `doc_type` (all rows), `type` (non-`feed` rows), and
`discipline_id` (missing/invalid rows, validated against
`input/disciplines.csv`) from each row's `title`, writing
`output/documents_updated.csv` + `output/documents_changes.csv`.

`classify` is the schema-fixed CSV variant: given a 28-column CSV (see
`io/schema.py`) it fills `doc_type` and `type` from the `title` via the keyword
rules and writes [output/classified.csv](output/classified.csv), preserving the
28-column schema, order, and row count. (The old sample input was removed; pass
your own 28-column CSV.)

## Console scripts

| Command              | What it does |
|----------------------|--------------|
| `classify`           | Given a 28-column CSV, fill `doc_type` (normalized to `drawing`/`sheet`/`document`) and `type` from the `title` via the keyword rules; write `output/classified.csv`. Schema-preserving: same 28 columns, same order, same row count. |
| `classify-rds`       | Same classifier logic against a PostgreSQL RDS `documents` table. Selects rows where any of `doc_type` / `type` / `discipline_id` is NULL/empty, fills them from the row `title`, UPDATEs in place. Reads DSN from `PGHOST` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` / `PGPORT` env vars. See [Pipeline use](#pipeline-use-rds) for the in-process API. |
| `convert-classified` | Walk `input/classified/**/*.xls*` (skipping `void/`), convert each parseable sheet to a 28-column CSV. Dormant — its `input/classified/` source is not currently populated. |
| `build-type-enum`    | Re-scan `input/classified_csv/` and regenerate `src/classifier/config/type_enum.py` (the canonical 3-letter `type` enum). Dormant — its input source is not currently populated. |
| `learn-sheet-patterns` | Diagnostic: scan workbooks for table/sheet structure patterns. |
| `update-snapshot`    | Process a documents-table export (DB snapshot CSV): recompute `doc_type` for all rows, recompute `type` for non-feed rows (feed rows kept), fill `discipline_id` where missing or now-invalid (validated against `input/disciplines.csv`). Writes `output/documents_updated.csv` + `output/documents_changes.csv`. Run: `update-snapshot --input <snapshot.csv>`. |
| `sort-files`         | Consume `output/classified.csv`, match source files by `customer_ref`, copy one preferred file per logical document into `dest/<Drawings\|Documents\|Sheets>/` (pdf preferred for drawing/document, xlsx preferred for sheet), route unmatched files to `Unmatched/`, and write `route-report.csv`. Supports `--dry-run`. |

> **No training step.** The rule configs (`type_keywords.py`, `type_overrides.py`,
> `discipline_keywords.py`, `type_to_discipline.py`, `type_enum.py`) are now
> **hand-maintained** — they are not regenerated from data. The former
> `learn-type-keywords` / `learn-discipline-keywords` / `learn-type-discipline`
> tools have been retired.

## sort-files router

`sort-files` consumes `output/classified.csv` (the output of `classify`) and
physically routes source deliverable files into organised destination buckets.

**What it does:**

- Reads the classified CSV to build a `customer_ref → doc_type` index.
- Walks `--source-dir` recursively; skips files already inside a bucket folder
  (`Drawings/`, `Documents/`, `Sheets/`, `Unmatched/`) so re-runs are safe.
- Groups files by logical document (via `customer_ref` + revision parsing) and
  picks one winner per group: latest revision wins; for drawing/document the
  preferred format is pdf; for sheet the preferred format is xlsx.
- Copies the winner into `dest/<Drawings|Documents|Sheets>/`; files with no
  matching `customer_ref` in the CSV go to `dest/Unmatched/`.
- Writes a `route-report.csv` sidecar in `dest/` with one row per action plus
  rows for CSV entries that had no matching source file (`no-file-for-row`).
- `--dry-run` prints the summary without copying anything or writing the report.

```bash
sort-files --classified-csv output/classified.csv --source-dir SRC --dest-dir DEST
```

## Layout

```
classifier/
├── pyproject.toml                    # package metadata + console scripts
├── README.md
│
├── src/classifier/                   # the package
│   ├── config/                       # buckets, hand-maintained keyword/type/discipline rules, schema, enum
│   ├── core/                         # pure logic: scoring engine, classify_record, folding, table_detect
│   ├── pipeline/                     # orchestration: run loop, stats, classify_titles, classify_rds
│   ├── io/                           # readers/writers: csv_io, rds, workbook, memory, disciplines, normalize, schema
│   ├── routing/                      # sort-files router: cust_ref, dedup, plan, execute, report
│   ├── cli/                          # console entry points (classify, classify-rds, update-snapshot, sort-files)
│   └── tools/                        # offline diagnostics (convert-classified, build-type-enum — dormant)
│
├── input/
│   └── disciplines.csv               # disciplines table export (discipline_id FK target)
│
└── output/                           # generated CSVs (documents_updated.csv, documents_changes.csv, ...)
```

<a id="pipeline-use-rds"></a>
## Pipeline use (RDS)

The classifier exposes a callable function for embedding in another
Python pipeline that already owns a psycopg2 connection:

```python
import psycopg2
from classifier.pipeline.classify_rds import classify_from_rds

with psycopg2.connect(dsn) as conn:
    stats = classify_from_rds(
        conn,
        table="documents",
        pk="document_id",
        commit_every=500,
        fetch_size=1000,
        on_done=lambda s: print(s),  # optional, exception-isolated
    )
```

`classify_from_rds` streams unclassified rows via a server-side cursor,
classifies `doc_type`, `type`, and `discipline_id` from each row's
`title`, and UPDATEs only the fields that were NULL/empty. The caller
owns the connection lifecycle; the function commits every
`commit_every` *processed* rows and a final commit before returning.
Returns a stats dict (see [spec](docs/superpowers/specs/2026-05-25-rds-pipeline-design.md)).

The RDS write boundary uses NULL — never empty string — for missing
text fields. Empty CSV-style `""` values from existing rows are
treated as unclassified on read; this pipeline never writes `''` back.

For large tables, add partial indexes on the three filtered columns
(see §6.5 of the spec).

## How to iterate on accuracy

The rule configs are **hand-maintained** (training retired) — edit them
directly:

1. **Type phrases:** add/adjust `(phrase, weight)` entries in
   [config/type_keywords.py](src/classifier/config/type_keywords.py) under the
   target type code, or force/suppress deterministically via `HARD_OVERRIDES` /
   `NEGATIVE_KEYWORDS` in
   [config/type_overrides.py](src/classifier/config/type_overrides.py).
2. **Discipline phrases:** add/adjust entries in
   [config/discipline_keywords.py](src/classifier/config/discipline_keywords.py)
   — keyed by a `discipline_id` that **must exist** in
   [input/disciplines.csv](input/disciplines.csv) — and the `type → discipline`
   hints in [config/type_to_discipline.py](src/classifier/config/type_to_discipline.py).
3. Re-run the relevant CLI (`classify` / `update-snapshot`) and inspect the output.

A type fires only when its top phrase score clears the margin/floor thresholds
in [`core/scoring.py`](src/classifier/core/scoring.py); otherwise `type` stays
empty. For a human-readable summary of the title→type patterns, see
[docs/type-classification-patterns.md](docs/type-classification-patterns.md).

### Typo tolerance policy

Type matching is **exact tokenised phrase matching** on a canonicalised title
(uppercased; dash/parenthesis/revision-noise stripped; regular plurals folded
to singular — see `core/scoring.canonicalize_title`). There is **no fuzzy
matching** (Levenshtein/soundex): it introduces unpredictable false positives
that are expensive to debug. When a real typo must match, add the exact typo'd
phrase to `HARD_OVERRIDES` in
[src/classifier/config/type_overrides.py](src/classifier/config/type_overrides.py).

## Tunables

| Constant | Where | What it does |
|---|---|---|
| `BUCKETS` | [config/buckets.py](src/classifier/config/buckets.py) | The 10 internal content buckets (don't reorder) |
| `BUCKET_TO_CLASS` | [config/buckets.py](src/classifier/config/buckets.py) | 10-bucket → 3-class fold (Drawings, Sheets, or Documents) |
| `TYPE_TO_BUCKET` | [config/buckets.py](src/classifier/config/buckets.py) | 3-letter Type code → bucket |
| `TYPE_KEYWORD_RULES` | [config/type_keywords.py](src/classifier/config/type_keywords.py) | Hand-maintained `{type: ((phrase, weight), ...)}` — phrase→type scoring |
| `HARD_OVERRIDES` / `NEGATIVE_KEYWORDS` | [config/type_overrides.py](src/classifier/config/type_overrides.py) | Hand-maintained deterministic type forcing / suppression |
| `DISCIPLINE_KEYWORDS` | [config/discipline_keywords.py](src/classifier/config/discipline_keywords.py) | Hand-maintained `{discipline_id: ((phrase, weight), ...)}` — per-discipline scoring (ids must be in `input/disciplines.csv`) |
| `TYPE_TO_DISCIPLINE` | [config/type_to_discipline.py](src/classifier/config/type_to_discipline.py) | Hand-maintained `{type: discipline_id}` hint that nudges discipline scoring |

## Bucket → Class mapping

The 10-bucket → 3-class fold lives in `BUCKET_TO_CLASS`:

| Bucket | Class |
|---|---|
| Drawings | **Drawings** |
| Isometrics | **Drawings** |
| Datasheets | Documents |
| Specifications | Documents |
| Calculations | Documents |
| Reports | Documents |
| Lists_MTOs_BOMs | **Sheets** |
| Procedures_Plans | Documents |
| CRS | Documents |
| Documents | Documents |

This fold is implemented in
[`doc_type_for_bucket()`](src/classifier/core/folding.py).

## Architecture

The package is layered, with imports flowing in one direction only:

```
presentation (cli)
    ↓
application (pipeline)
    ↓
domain (core)
    ↓
infrastructure (io)
```

- **`core/`** is pure logic: regex extraction, scoring, revisions. No
  I/O, no upward imports. The per-row entry point is
  `classifier.core.classify.classify_record`; the generic scoring engine
  is `classifier.core.scoring`; bucket-to-doc_type folding is
  `classifier.core.folding.doc_type_for_bucket`.
- **`io/`** wraps file readers/writers (CSV, RDS, workbooks). Execution
  backends (CSV/RDS/in-memory) implement reader/writer duck-typed
  protocols and run through `classifier.pipeline.run.run`; adding a new
  output producer implements a `write(rec, result, writes)`/`close()`
  writer and requires no core changes.
- **`pipeline/`** orchestrates `core/` + `io/` for the enrich/audit flows.
- **`cli/`** is presentation only — argparse, prompts, ANSI colors,
  progress bars, formatted reports.
- **`tools/`** is the home of standalone diagnostic commands
  (`convert-classified`, `build-type-enum`).
