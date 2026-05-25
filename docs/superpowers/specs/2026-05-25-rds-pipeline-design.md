# RDS Classifier Pipeline — Design

**Date:** 2026-05-25
**Status:** Approved (pending user review of spec)
**Authors:** Kamran + Claude

## 1. Purpose

Convert the existing CSV-only classifier into a callable pipeline that
reads documents directly from a PostgreSQL RDS `documents` table,
classifies each row's `doc_type`, `type`, and `discipline_id` from the
row `title`, and writes the inferred values back into the same table.

The function will be invoked by another Python codebase that already
owns a database connection. The existing CSV CLI continues to work
unchanged for offline runs.

## 2. Scope

In scope:
- New module: `src/classifier/io/rds.py` (psycopg2 read/write helpers).
- New module: `src/classifier/pipeline/classify_rds.py` exposing
  `classify_from_rds(conn, ...) -> dict`.
- New module: `src/classifier/core/discipline_scoring.py` with
  `pick_discipline_with_overrides(title)`.
- New generated config: `src/classifier/config/discipline_keywords.py`.
- New offline tool: `learn-discipline-keywords` (mirrors
  `learn-type-keywords`).
- New CLI entry point: `classify-rds` (env-var driven thin wrapper).
- Promote `_normalize_doc_type` and `_fill_type` from `cli/classify.py`
  to `pipeline/_row.py` so CSV CLI and RDS pipeline share one
  implementation.

Out of scope:
- Discipline overrides table (defer until needed).
- Batching strategies beyond per-row UPDATE + commit-every-N.
- Replacing or removing the CSV CLI (`classify` stays as-is).
- Automated tests for the pipeline (explicitly excluded by user).
- Re-classifying rows whose target fields are already non-empty.

## 3. Architecture

```
src/classifier/
├── core/
│   ├── type_scoring.py              (unchanged)
│   └── discipline_scoring.py        NEW
├── config/
│   ├── type_keywords.py             (unchanged)
│   └── discipline_keywords.py       NEW (generated)
├── io/
│   ├── schema.py                    (unchanged)
│   └── rds.py                       NEW
├── pipeline/
│   ├── _row.py                      NEW (shared per-row logic)
│   └── classify_rds.py              NEW
├── cli/
│   ├── classify.py                  refactored to import from _row.py
│   └── classify_rds.py              NEW
└── tools/
    └── learn_discipline_keywords.py NEW
```

Layering preserved: `cli → pipeline → core / io`. No upward imports.

## 4. Public API

```python
# src/classifier/pipeline/classify_rds.py

from typing import Callable

def classify_from_rds(
    conn,
    *,
    table: str = "documents",
    pk: str = "document_id",
    commit_every: int = 500,
    on_done: Callable[[dict], None] | None = None,
) -> dict:
    """Classify and update all rows in `table` where doc_type, type,
    or discipline_id is empty/NULL. Returns a stats dict. If on_done
    is given, also calls on_done(stats) at the end.

    The caller owns the connection lifecycle. The function does not
    open or close `conn`; it commits at most every `commit_every`
    rows plus a final commit before returning.
    """
```

Stats dict shape:

```python
{
    "rows_scanned": int,
    "rows_updated": int,
    "doc_type":      {"via_keyword": int, "via_override": int, "defaulted": int, "preserved": int},
    "type":          {"via_keyword": int, "via_override": int, "empty": int, "preserved": int},
    "discipline_id": {"via_keyword": int, "empty": int, "preserved": int},
}
```

Caller pattern:

```python
import psycopg2
from classifier.pipeline.classify_rds import classify_from_rds

with psycopg2.connect(dsn) as conn:
    stats = classify_from_rds(conn, on_done=lambda s: print(s))
```

## 5. SQL contract

### 5.1 Read

Server-side (named) cursor so the function streams instead of loading
the whole table:

```sql
SELECT document_id, doc_type, type, discipline_id, title
FROM   documents
WHERE  doc_type IS NULL OR doc_type = ''
   OR  type     IS NULL OR type     = ''
   OR  discipline_id IS NULL;
```

`title` is treated as text. Rows with NULL/empty `title` skip
classification but still count toward `rows_scanned`.

### 5.2 Write

One UPDATE per row, parameterised:

```sql
UPDATE documents
SET    doc_type      = %s,
       type          = %s,
       discipline_id = %s
WHERE  document_id   = %s;
```

Field-level rules:
- `doc_type`: if existing value was empty → write the inferred value;
  otherwise re-write the (normalised) existing value. This is
  idempotent and matches the CSV CLI behaviour today.
- `type`: if existing was empty AND inference confidence is `high` →
  write the picked type; if existing was empty AND inference missed →
  write empty string; otherwise preserve.
- `discipline_id`: if existing was NULL AND inference confidence is
  `high` → write the picked discipline_id (int); otherwise leave the
  field out of the SET clause (do not overwrite with NULL).

If a row's classification produces no change to any of the three
fields, skip the UPDATE entirely and do not increment `rows_updated`.

### 5.3 Transactions

- `conn.autocommit` is left at the caller's setting; the function
  calls `conn.commit()` every `commit_every` rows and once more before
  returning.
- On exception, the function lets it propagate; the caller is
  responsible for rollback.

## 6. Per-row logic

Shared module `pipeline/_row.py` exposes three pure functions used by
both the CSV CLI and the RDS pipeline:

```python
def normalize_doc_type(value: str, title: str) -> tuple[str, str]: ...
def fill_type(row_type: str, title: str) -> tuple[str, str]: ...
def fill_discipline(row_disc, title: str) -> tuple[int | None, str]: ...
```

The first two are lifted verbatim from `cli/classify.py` (renamed to
drop the leading underscore). The third is new and follows the same
shape: returns `(value, reason_tag)` where `reason_tag` is one of
`preserved`, `via_keyword`, `empty`.

`cli/classify.py` is updated to import from `pipeline/_row.py`; its
externally observable behaviour does not change.

## 7. Discipline inference

### 7.1 Training data

`input/classified_csv/*.csv` rows where `discipline_id` is non-empty
become the training set: each row contributes the pair
`(title, int(discipline_id))`.

### 7.2 Learner — `learn-discipline-keywords`

Mirrors `learn-type-keywords`:

1. Walk `input/classified_csv/`, build `(title, discipline_id)` pairs.
2. Tokenise titles and compute per-discipline keyword weights using
   the same scoring approach `learn_type_keywords.py` uses today.
3. Write `src/classifier/config/discipline_keywords.py` as a generated
   module containing one dict:

```python
DISCIPLINE_KEYWORDS: dict[int, list[tuple[str, int]]] = {
    13: [(r"valve", 5), (r"piping", 3), ...],
    ...
}
```

The generated file carries a header comment indicating it is
auto-generated and lists the source CSVs and timestamp, matching
the convention used by `type_keywords.py`.

### 7.3 Scorer — `pick_discipline_with_overrides(title)`

`src/classifier/core/discipline_scoring.py` exposes one function that
returns a dict with the same shape as `pick_type_with_overrides`:

```python
{
    "discipline_id": int | None,
    "confidence":    "high" | "low",
    "reason":        "keyword" | "miss",
}
```

`high` requires at least one weight-5 hit (same threshold as type
scoring). No overrides table in this iteration — `reason` is always
`keyword` or `miss`.

## 8. CLI wrapper

`classify-rds` console script entry point:

```python
# src/classifier/cli/classify_rds.py

def main() -> None:
    import os, psycopg2
    from classifier.pipeline.classify_rds import classify_from_rds

    conn = psycopg2.connect(
        host=os.environ["PGHOST"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        port=os.environ.get("PGPORT", "5432"),
    )
    try:
        stats = classify_from_rds(conn, on_done=_print_stats)
    finally:
        conn.close()
```

`pyproject.toml` gets a new entry under `[project.scripts]`:

```toml
classify-rds = "classifier.cli.classify_rds:main"
```

`psycopg2-binary` is added to project dependencies.

## 9. Stale-rules warning

The existing CSV CLI prints a warning when `type_keywords.py` is older
than any training CSV. The RDS pipeline performs the same check at
startup and additionally warns if `discipline_keywords.py` is older
than any training CSV. The warning is informational; it does not abort
the run.

## 10. Non-goals / explicit rejections

- No automated tests are added in this iteration. The user has
  explicitly opted out of test scaffolding for this spec.
- No discipline overrides table; only the keyword-learned scorer.
- No re-classification of already-populated fields, even on demand.
  If a future need arises, it gets its own spec.
- No batching beyond per-row UPDATE plus periodic commit.
