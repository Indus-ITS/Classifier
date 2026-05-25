# RDS Classifier Pipeline — Design

**Date:** 2026-05-25
**Status:** Approved
**Authors:** Kamran + Claude

> Revision 2026-05-25 (post-review): applied 9 review fixes —
> dynamic SET clause, NULL-only sentinels at DB boundary, identifier
> safety via `psycopg2.sql`, `cursor.itersize`, defined commit_every
> semantics, exception-isolated callback, logging story, indexing note.

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
- DB index creation / migration scripts (operational note only).

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
import logging

log = logging.getLogger("classifier.rds")

def classify_from_rds(
    conn,
    *,
    table: str = "documents",
    pk: str = "document_id",
    commit_every: int = 500,
    fetch_size: int = 1000,
    on_done: Callable[[dict], None] | None = None,
) -> dict:
    """Classify and update all rows in `table` where doc_type, type,
    or discipline_id is empty/NULL. Returns a stats dict. If on_done
    is given, also calls on_done(stats) at the end (exception-isolated;
    see §4.3).

    The caller owns the connection lifecycle. The function does not
    open or close `conn`; it commits at most every `commit_every`
    *processed* rows plus a final commit before returning.
    """
```

### 4.1 Stats dict shape

```python
{
    "rows_scanned":  int,   # rows pulled from cursor
    "rows_updated":  int,   # rows where at least one field changed
    "rows_skipped":  int,   # rows where no field needed writing
    "doc_type":      {"via_keyword": int, "via_override": int, "defaulted": int, "preserved": int},
    "type":          {"via_keyword": int, "via_override": int, "miss": int,       "preserved": int},
    "discipline_id": {"via_keyword": int, "miss": int,         "preserved": int},
    "callback_error": str | None,   # repr() of on_done exception if any
}
```

Reason tags now use `miss` (not `empty`) for "inference produced no
value", since the DB representation is NULL, not empty string.

### 4.2 `commit_every` semantics

`commit_every` counts **processed rows** (i.e. every row pulled from
the cursor, whether or not it produced an UPDATE). This bounds the
duration of any single open transaction even when the update rate is
very low. Default 500.

### 4.3 `on_done` callback behaviour

The pipeline performs its final commit *before* calling `on_done`. If
`on_done(stats)` raises, the exception is caught, logged at WARNING,
and `stats["callback_error"]` is set to the exception repr. The
exception does **not** propagate to the caller. This guarantees a
classification run that successfully committed cannot be reported as
failed by a buggy callback.

### 4.4 Caller pattern

```python
import psycopg2
from classifier.pipeline.classify_rds import classify_from_rds

with psycopg2.connect(dsn) as conn:
    stats = classify_from_rds(conn, on_done=lambda s: print(s))
```

## 5. NULL vs empty-string policy

The CSV pipeline has historically used `''` as the empty sentinel
because pandas/CSV blurs NULL and empty. The RDS pipeline does **not**
preserve that convention.

| Field           | DB type | Empty sentinel | When inference misses |
|-----------------|---------|----------------|-----------------------|
| `doc_type`      | text    | NULL           | written as `document` (existing defaulted behaviour) |
| `type`          | text    | NULL           | leave field out of SET clause; preserves NULL |
| `discipline_id` | int FK  | NULL           | leave field out of SET clause; preserves NULL |

Inside the per-row classifier the value-in/value-out type is still
`str` (so the shared logic stays compatible with the CSV CLI). The
boundary translation lives in `io/rds.py`:

- On read: `None` from psycopg2 → `""` for the classifier helpers.
- On write: `""` from the classifier → omit the column from the SET
  clause (do not send `''`). Only non-empty strings and ints are
  actually written.

This means analytics in the RDS table can reliably use
`WHERE doc_type IS NULL` etc; empty strings are never written by this
pipeline.

## 6. SQL contract

### 6.1 Identifier safety

`table` and `pk` are parameters, so they MUST be wrapped with
`psycopg2.sql.Identifier`. The function uses `psycopg2.sql.SQL(...)`
composition for every statement that interpolates an identifier.
Bare f-strings or `%`-formatting of identifiers is forbidden.

```python
from psycopg2 import sql

select_q = sql.SQL(
    "SELECT {pk}, doc_type, type, discipline_id, title "
    "FROM {tbl} "
    "WHERE doc_type IS NULL OR doc_type = '' "
    "   OR type     IS NULL OR type     = '' "
    "   OR discipline_id IS NULL"
).format(
    pk=sql.Identifier(pk),
    tbl=sql.Identifier(table),
)
```

The `= ''` clauses on text fields are defensive: they catch rows that
predate this policy where the CSV-imported value was the empty string.
After this pipeline runs once, only `IS NULL` would be needed in
practice — but the dual check is cheap and keeps the read idempotent.

### 6.2 Read — server-side cursor with itersize

```python
with conn.cursor(name="classify_cur") as cur:
    cur.itersize = fetch_size   # default 1000
    cur.execute(select_q)
    for row in cur:
        ...
```

Named (server-side) cursor avoids loading the whole result into
memory. `itersize` tunes how many rows psycopg2 buffers per network
round-trip; without it the default of 2000 is acceptable but
implementation-dependent across versions, so we set it explicitly.

### 6.3 Write — dynamic SET clause

The UPDATE is **built per row** from only the fields that actually
need a write. This guarantees we never overwrite a populated field
with NULL or an empty string.

```python
def update_row(cur, table, pk, pk_value, writes: dict) -> bool:
    """writes maps column -> value for fields that must be written.
       Returns True if an UPDATE was sent."""
    if not writes:
        return False
    cols = list(writes.keys())
    set_clause = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in cols
    )
    stmt = sql.SQL("UPDATE {tbl} SET {sets} WHERE {pk} = %s").format(
        tbl=sql.Identifier(table),
        sets=set_clause,
        pk=sql.Identifier(pk),
    )
    cur.execute(stmt, [*writes.values(), pk_value])
    return True
```

Decision rules feeding `writes`:

- `doc_type`: included whenever the inferred normalised value differs
  from the row's existing value (handles both "was empty" and "was a
  non-canonical alias like 'DWG'" cases).
- `type`: included only when existing was empty AND inference returned
  a high-confidence pick.
- `discipline_id`: included only when existing was NULL AND inference
  returned a high-confidence pick.

If `writes` ends up empty, the row is counted in `rows_skipped` and no
UPDATE fires.

### 6.4 Transactions

- `conn.autocommit` is left at the caller's setting; the function
  calls `conn.commit()` every `commit_every` *processed* rows (§4.2)
  and once more before invoking `on_done`.
- On exception, the function lets it propagate (the caller is
  responsible for rollback) — except for exceptions raised by
  `on_done`, which are isolated per §4.3.

### 6.5 Operational note: indexing

The read query filters on three columns. On large tables this becomes
a sequential scan unless supported by indexes. This pipeline does not
create indexes; that is a DB-admin task. Recommended:

```sql
CREATE INDEX CONCURRENTLY documents_doc_type_null_idx
  ON documents (doc_type) WHERE doc_type IS NULL OR doc_type = '';
CREATE INDEX CONCURRENTLY documents_type_null_idx
  ON documents (type)     WHERE type     IS NULL OR type     = '';
CREATE INDEX CONCURRENTLY documents_disc_null_idx
  ON documents (discipline_id) WHERE discipline_id IS NULL;
```

Partial indexes keep the index small (only unclassified rows). If the
table is small (<100k rows), skip the indexes.

## 7. Per-row logic

Shared module `pipeline/_row.py` exposes three pure functions used by
both the CSV CLI and the RDS pipeline:

```python
def normalize_doc_type(value: str, title: str) -> tuple[str, str]: ...
def fill_type(row_type: str, title: str) -> tuple[str, str]: ...
def fill_discipline(row_disc: str, title: str) -> tuple[str, str]: ...
```

The first two are lifted verbatim from `cli/classify.py` (renamed to
drop the leading underscore). The third is new and follows the same
shape: returns `(value, reason_tag)` where `reason_tag` is one of
`preserved`, `via_keyword`, `miss`.

All three functions operate on strings (matching CSV semantics).
`fill_discipline` returns the discipline_id as a decimal string when
found, else `""`. The RDS layer converts `""` → omit-from-SET and a
non-empty string → `int(value)` before parameterising.

`cli/classify.py` is updated to import from `pipeline/_row.py`; its
externally observable behaviour does not change.

## 8. Discipline inference

### 8.1 Training data

`input/classified_csv/*.csv` rows where `discipline_id` is non-empty
become the training set: each row contributes the pair
`(title, int(float(discipline_id)))` — handling the `13.0` floats
observed in the labelled CSVs.

### 8.2 Learner — `learn-discipline-keywords`

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

### 8.3 Scorer — `pick_discipline_with_overrides(title)`

`src/classifier/core/discipline_scoring.py` exposes one function:

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

## 9. CLI wrapper

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

## 10. Logging

The pipeline uses the standard `logging` module under the
`classifier.rds` logger. No handlers are configured by the library
(per Python logging best practice — let the caller decide).

Events emitted:

| Level   | Event |
|---------|-------|
| INFO    | start: table, expected scope (`unclassified rows`) |
| INFO    | every `commit_every` rows: progress (`scanned=N updated=M elapsed=Ts rate=R rows/s`) |
| WARNING | stale-rules check failed (training data newer than generated module) |
| WARNING | `on_done` raised — repr attached to stats |
| INFO    | done: final stats one-liner |

No per-row logging (would flood at scale).

## 11. Stale-rules warning

The existing CSV CLI prints a warning when `type_keywords.py` is older
than any training CSV. The RDS pipeline performs the same check at
startup and additionally warns if `discipline_keywords.py` is older
than any training CSV. The warning is logged at WARNING level (see
§10); it does not abort the run.

## 12. Non-goals / explicit rejections

- No automated tests are added in this iteration. The user has
  explicitly opted out of test scaffolding for this spec.
- No discipline overrides table; only the keyword-learned scorer.
- No re-classification of already-populated fields, even on demand.
  If a future need arises, it gets its own spec.
- No batching beyond per-row UPDATE plus periodic commit.
- No DB migrations / index creation from this code (operational note
  in §6.5 only).
