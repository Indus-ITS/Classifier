# Document Classifier

Classifies engineering deliverable rows from project schedule sheets into
three classes — **drawing**, **sheet**, or **document** — by reading a
canonical 28-column CSV, filling `doc_type` from keyword scoring and
`type` from a lookup built from labelled reference indices.

## Quick start

```bash
pip install -e .

classify
```

`classify` reads `input/To be classified/document.csv`, fills `doc_type`
(normalized to `drawing`/`sheet`/`document`) and `type` (filled only when
empty, via the lookup built from `input/classified_csv/`), and writes
[output/classified.csv](output/classified.csv). The output preserves the
input's 28-column schema, column order, and row count.

## Console scripts

| Command              | What it does |
|----------------------|--------------|
| `classify`           | Read `input/To be classified/document.csv`, fill `doc_type` (normalized to `drawing`/`sheet`/`document`) and `type` (filled only when empty, via the lookup built from `input/classified_csv/`), write `output/classified.csv`. Schema-preserving: same 28 columns, same order, same row count. |
| `classify-rds`       | Same classifier logic against a PostgreSQL RDS `documents` table. Selects rows where any of `doc_type` / `type` / `discipline_id` is NULL/empty, fills them from the row `title`, UPDATEs in place. Reads DSN from `PGHOST` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` / `PGPORT` env vars. See [Pipeline use](#pipeline-use-rds) for the in-process API. |
| `convert-classified` | Walk `input/classified/**/*.xls*` (skipping `void/`), convert each parseable sheet to a 28-column CSV under `input/classified_csv/`. Output is committed so the lookup is reproducible offline. |
| `build-type-enum`    | Re-scan `input/classified_csv/` and regenerate `src/classifier/config/type_enum.py` (the canonical 3-letter `type` enum). |
| `learn-type-keywords` | Mine `(title, type)` pairs from `input/classified_csv/` and regenerate `src/classifier/config/type_keywords.py` (the learned phrase→type rules). |
| `learn-discipline-keywords` | Mine `(title, discipline_id)` pairs from `input/classified_csv/` and regenerate `src/classifier/config/discipline_keywords.py`. Trains directly on the labelled ids (validated against `input/disciplines.csv`); no fold. |
| `learn-type-discipline` | Build the `type → discipline_id` majority hint map (`src/classifier/config/type_to_discipline.py`) that nudges discipline scoring. |
| `learn-sheet-patterns` | Diagnostic: scan workbooks for table/sheet structure patterns. |
| `sort-files`         | Consume `output/classified.csv`, match source files by `customer_ref`, copy one preferred file per logical document into `dest/<Drawings\|Documents\|Sheets>/` (pdf preferred for drawing/document, xlsx preferred for sheet), route unmatched files to `Unmatched/`, and write `route-report.csv`. Supports `--dry-run`. |

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
│   ├── config/                       # buckets, generated keyword/type/discipline tables, schema, enum
│   ├── core/                         # pure logic: scoring engine, classify_record, folding, table_detect
│   ├── pipeline/                     # orchestration: run loop, stats, classify_titles, classify_rds
│   ├── io/                           # readers/writers: csv_io, rds, workbook, memory, classified_index, normalize, schema
│   ├── routing/                      # sort-files router: cust_ref, dedup, plan, execute, report
│   ├── cli/                          # console entry points (classify, classify-rds, sort-files)
│   └── tools/                        # offline commands: convert-classified, build-type-enum, learners
│
├── input/
│   ├── To be classified/             # document.csv to classify
│   ├── classified/                   # labelled reference indices (xls/xlsx source)
│   └── classified_csv/               # converted 28-column CSVs (commit-tracked)
│
└── output/
    └── classified.csv                # ← MAIN classifier output
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

`type_keywords.py` and `discipline_keywords.py` are **generated** — don't edit
them by hand. To improve accuracy:

1. **Add labelled examples** to `input/classified_csv/` (more `(title, type)`
   and `(title, discipline_id)` rows), then re-run `learn-type-keywords` and
   `learn-discipline-keywords`.
2. **Force a specific type** deterministically: add the title phrase to
   `HARD_OVERRIDES` (or suppress a false hit with `NEGATIVE_KEYWORDS`) in
   [src/classifier/config/type_overrides.py](src/classifier/config/type_overrides.py).
3. Re-run `classify` and inspect `output/classified.csv`.

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
| `TYPE_KEYWORD_RULES` | [config/type_keywords.py](src/classifier/config/type_keywords.py) | **Generated** `{type: ((phrase, weight), ...)}` — learned phrase→type scoring |
| `HARD_OVERRIDES` / `NEGATIVE_KEYWORDS` | [config/type_overrides.py](src/classifier/config/type_overrides.py) | Hand-maintained deterministic type forcing / suppression |
| `DISCIPLINE_KEYWORDS` | [config/discipline_keywords.py](src/classifier/config/discipline_keywords.py) | **Generated** `{discipline_id: ((phrase, weight), ...)}` — learned per-discipline scoring (fold-free) |
| `TYPE_TO_DISCIPLINE` | [config/type_to_discipline.py](src/classifier/config/type_to_discipline.py) | **Generated** `{type: discipline_id}` hint that nudges discipline scoring |

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
