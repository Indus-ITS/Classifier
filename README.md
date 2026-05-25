# Document Classifier

Classifies engineering deliverable rows from project schedule sheets into
two classes — **Drawings** or **Documents** — by reading a canonical
28-column CSV, filling `doc_type` from keyword scoring and `type` from a
lookup built from labelled reference indices.

## Quick start

```bash
pip install -e .

classify
```

`classify` reads `input/To be classified/document.csv`, fills `doc_type`
(normalized to `drawing`/`document`) and `type` (filled only when empty,
via the lookup built from `input/classified_csv/`), and writes
[output/classified.csv](output/classified.csv). The output preserves the
input's 28-column schema, column order, and row count.

## Console scripts

| Command              | What it does |
|----------------------|--------------|
| `classify`           | Read `input/To be classified/document.csv`, fill `doc_type` (normalized to `drawing`/`document`) and `type` (filled only when empty, via the lookup built from `input/classified_csv/`), write `output/classified.csv`. Schema-preserving: same 28 columns, same order, same row count. |
| `classify-rds`       | Same classifier logic against a PostgreSQL RDS `documents` table. Selects rows where any of `doc_type` / `type` / `discipline_id` is NULL/empty, fills them from the row `title`, UPDATEs in place. Reads DSN from `PGHOST` / `PGDATABASE` / `PGUSER` / `PGPASSWORD` / `PGPORT` env vars. See [Pipeline use](#pipeline-use-rds) for the in-process API. |
| `convert-classified` | Walk `input/classified/**/*.xls*` (skipping `void/`), convert each parseable sheet to a 28-column CSV under `input/classified_csv/`. Output is committed so the lookup is reproducible offline. |
| `build-type-enum`    | Re-scan `input/classified_csv/` and regenerate `src/classifier/config/type_enum.py` (the canonical 3-letter `type` enum). |
| `learn-discipline-keywords` | Re-scan `input/classified_csv/` for `(title, discipline_id)` pairs and regenerate `src/classifier/config/discipline_keywords.py`. Mirrors `learn-type-keywords`. |

## Layout

```
classifier/
├── pyproject.toml                    # package metadata + console scripts
├── README.md
│
├── src/classifier/                   # the package
│   ├── config/                       # tunables (paths, buckets, keywords, patterns, schema)
│   ├── core/                         # pure logic (scoring, extraction, normalisation, ...)
│   ├── pipeline/                     # orchestration (enrich, audit, classify_from_rds)
│   ├── io/                           # readers/writers (csv, rds)
│   ├── cli/                          # console entry points + presentation helpers
│   └── tools/                        # offline diagnostic commands (convert-classified, build-type-enum)
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

1. Edit keyword rules in
   [src/classifier/config/keywords.py](src/classifier/config/keywords.py) —
   `KEYWORD_RULES[bucket]` is the main lever. Weights are 1-5; weight 5
   is required for `high` confidence.
2. Re-run `classify` and inspect `output/classified.csv`.

### Typo tolerance policy

The keyword bank uses targeted regex tolerance for real typos seen in
the data (e.g. `arra?n?g(e)?ment` for ARRANGEMENT/ARRANGMENT/ARRAGEMENT,
`requ[a-z]{2,5}tion` for REQUISITION/REQUSITION/REQUISTION/REQUISTATION).

**Generic fuzzy matching (Levenshtein/soundex) is intentionally not
used** — it introduces unpredictable false positives that are expensive
to debug. When a new typo surfaces, the fix is to relax the relevant
regex pattern in
[src/classifier/config/keywords.py](src/classifier/config/keywords.py).

## Tunables

| Constant | Where | What it does |
|---|---|---|
| `BUCKETS` | [config/buckets.py](src/classifier/config/buckets.py) | The 10 internal content buckets (don't reorder) |
| `BUCKET_TO_CLASS` | [config/buckets.py](src/classifier/config/buckets.py) | 10-bucket → 2-class fold (Drawings or Documents) |
| `KEYWORD_RULES` | [config/keywords.py](src/classifier/config/keywords.py) | `{bucket: [(regex, weight 1-5), ...]}` — bucket scoring |
| `TYPE_TO_BUCKET` | [config/buckets.py](src/classifier/config/buckets.py) | 3-letter dossier Type code → bucket |
| `BUCKET_PRIMARY_CODE` | [config/buckets.py](src/classifier/config/buckets.py) | Bucket → 3-letter code used in proposed target filename |
| `DISCIPLINE_KEYWORD_RULES` | [config/keywords.py](src/classifier/config/keywords.py) | `[(regex, discipline), ...]` — fallback discipline inference |
| `REF_PATTERN`, `CRS_PATTERN`, `COVER_PATTERN` | [config/patterns.py](src/classifier/config/patterns.py) | Regex strings for ref / CRS / cover-sheet detection |

## Bucket → Class mapping

The 10-bucket → 2-class fold lives in `BUCKET_TO_CLASS`:

| Bucket | Class |
|---|---|
| Drawings | **Drawings** |
| Isometrics | **Drawings** |
| Datasheets | Documents |
| Specifications | Documents |
| Calculations | Documents |
| Reports | Documents |
| Lists_MTOs_BOMs | Documents |
| Procedures_Plans | Documents |
| CRS | Documents |
| Documents | Documents |

This fold is implemented in
[`fold_to_class()`](src/classifier/core/scoring.py).

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
  I/O, no upward imports.
- **`io/`** wraps file readers/writers (CSV).
- **`pipeline/`** orchestrates `core/` + `io/` for the enrich/audit flows.
- **`cli/`** is presentation only — argparse, prompts, ANSI colors,
  progress bars, formatted reports.
- **`tools/`** is the home of standalone diagnostic commands
  (`convert-classified`, `build-type-enum`).
