# Core / execution / output separation — design

**Date:** 2026-06-05
**Status:** Approved (design); implementation not started.
**Goal:** Separate the invariant classification core from the variant
execution backends (input sources) and output producers, so a new
execution path or output producer can be added without touching the core.

This is a **structural, behavior-preserving** refactor. No feature work.

## Scope decisions (locked)

- **Single global model.** The scoring rule-tables (`type_keywords`,
  `discipline_keywords`, `type_overrides`, `type_to_discipline`) stay as
  direct module imports inside the engine. We do **not** invert the config
  dependency behind a `RuleSet` interface — there is one model, so
  injection would add plumbing with no payoff.
- **Collapse the duplicated scorers** into one generic engine.

---

## Phase 1 — Map

### Dependency map

Import direction (top depends on bottom):

```
   cli/classify.py        cli/classify_rds.py        tools/convert_classified.py   tools/learn_*.py
   (CSV in/out+stats)     (env DSN → pipeline)        (xls→csv producer)            (offline trainers)
        │                      │                            │                           │
        ▼                      ▼                            ▼                           ▼
   pipeline/_row.py      pipeline/classify_rds.py     (writes config/*.py generated files)
   classify_titles.py ──▶ _row.py                      core/table_detect.py
        │                      │                            │
        ▼                      ▼                            ▼
   core/type_scoring.py   io/rds.py  io/normalize.py   openpyxl / xlrd
   core/discipline_scoring.py (← type_scoring privates)
        │
        ▼
   config/* (type_keywords, discipline_keywords, type_overrides,
             type_to_discipline, buckets, type_enum)  — lazy-imported data
```

### Core (invariant) vs variant axes

**Core (invariant):**
- Phrase-scoring + confidence gating (`score_types`/`pick_type`,
  `score_disciplines`/`pick_discipline`).
- Per-row decision sequence: `normalize_doc_type → fill_type →
  fill_discipline(type_hint=…)` (the type→discipline feedback). **The**
  business logic.
- Canonicalization, fold-to-class, schema constant, string normalization.

**Variant axis A — execution backends / input sources:**

| Backend | Where |
|---|---|
| CSV file (pandas) | `cli/classify.py:47` |
| PostgreSQL stream | `io/rds.py:26 iter_unclassified` |
| In-memory dicts | `pipeline/classify_titles.py:20` |
| xls/xlsx workbooks | `core/table_detect.py:89 iter_grids`, `convert_classified.py:120` |

**Variant axis B — output / result producers:**

| Producer | Where |
|---|---|
| CSV writer + stdout stats | `cli/classify.py:65-105` |
| RDS UPDATE + stats dict | `io/rds.py:62 update_row`, `classify_rds.py:110-128` |
| Returned list of dicts | `classify_titles.py:75-87` |

### Coupling points

1. **Row-orchestration sequence copy-pasted three times** (the central
   problem). No single "classify a record" core entry; each backend
   re-derives the doc_type→type→discipline wiring including the
   "use just-inferred type as discipline hint" rule:
   `classify_titles.py:69-71`, `classify_rds.py:99-104`,
   `cli/classify.py:75-86`. They have **already drifted** (discipline as
   `int|None` vs str vs `int`; differing stat vocab).
2. **Fold-to-class duplicated** as inline dict literal:
   `_row.py:38` and `convert_classified.py:117`. (README claims a
   `core/scoring.py:fold_to_class()` that does not exist — doc drift.)
3. **Stale-rules check duplicated**: `cli/classify.py:51-56` and
   `classify_rds.py:33-45`.
4. **Two near-identical scoring engines**: `score_types:150-192` vs
   `score_disciplines:35-79`; identical gates `pick_type:195-234` vs
   `pick_discipline:82-100`. Discipline borrows type_scoring privates
   (`discipline_scoring.py:23-26`).
5. **`table_detect.py` mixes pure logic with I/O**: `find_table` (pure)
   beside `iter_grids` importing openpyxl/xlrd (`:96-111`).
6. **Orchestrators bind directly to concretes**: `classify_rds.py:14`
   imports `io.rds`; `cli/classify.py:27,31` import pandas+csv. Hardcoded
   paths at `classify_rds.py:21-24`, `cli/classify.py:37-40`.
7. **`is_empty` duplicated**: `io/normalize.py:22` vs
   `table_detect.py:29 _is_empty`.

### SoC violations → SOLID

| # | Violation | File:line | Principle |
|---|---|---|---|
| V1 | `cli/classify.py:main()` does read+validate+stale-check+classify+write+present | `classify.py:43-105` | SRP |
| V2 | New backend requires re-implementing the row loop, not extending one | three sites | OCP (+DRY) |
| V3 | Orchestrators depend on concrete I/O with no interface between | `classify_rds.py:14`, `classify.py:27-31` | DIP |
| V4 | `table_detect.py` couples pure detection to workbook I/O | `table_detect.py:89-115` | SRP |
| V5 | Two copies of scoring engine + gates | type/discipline_scoring | DRY/SRP |
| V6 | Duplicated fold + stale-check + `is_empty` | see above | DRY |

**Already adequate — leave alone:** `io/rds.py` (clean, injection-safe,
already Reader/Writer-shaped); `config/*` data tables;
`io/schema.py:validate_schema`; `find_table`'s pure logic.

---

## Phase 2 — Target design

### Layered separation

```
   CLI edge (cli/*)  — constructs concretes, wires them, prints
        │
        ▼
   orchestration  pipeline/run.py : run(reader, writer) → Stats   (the ONE loop)
        │
        ▼
   core  classify_record(Record) → ClassificationResult          (pure, no I/O)
         core/scoring.py  score()/pick()  (one engine)
         canonicalize / fold_to_class / schema / normalize
        ▲                         ▲
        │ implements              │ implements
   RecordReader (backends)   ResultWriter (producers)
   CsvReader / RdsReader /   CsvWriter / RdsWriter /
   InMemoryReader / Workbook InMemoryWriter / (future: JsonlWriter…)
```

Core depends on nothing above it and knows nothing about CSV/RDS/dicts.
Config rule-tables stay as direct imports inside the engine (single model).

### Interfaces

```python
# core/record.py  — pure data, no I/O
@dataclass(frozen=True)
class Record:
    title: str
    doc_type: str = ""          # raw existing values; "" means empty/unclassified
    type: str = ""
    discipline_id: str = ""
    handle: object = None       # opaque passthrough a writer may need (pk, full row, index)

@dataclass(frozen=True)
class FieldResult:
    value: object
    reason: str                 # existing/via_keyword/via_override/defaulted/...

@dataclass(frozen=True)
class ClassificationResult:
    doc_type: FieldResult
    type: FieldResult
    discipline_id: FieldResult
```

```python
# core/classify.py  — THE invariant entry; the row sequence lives here once
def classify_record(rec: Record) -> ClassificationResult:
    dt = normalize_doc_type(rec.doc_type, rec.title)
    ty = fill_type(rec.type, rec.title)
    di = fill_discipline(rec.discipline_id, rec.title, type_hint=ty[0])
    return ClassificationResult(FieldResult(*dt), FieldResult(*ty), FieldResult(*di))
```

**The `_row.py` functions already return `(value, reason)` tuples** with a
shared, documented reason vocabulary (`_row.py:22-72`); all three current
call sites already call them, so the reasons are already consistent across
backends. `FieldResult(*dt)` therefore composes them unchanged — no
behavioral edit to `_row.py` in Phase 1. (Verified 2026-06-05.)

**Who decides what gets persisted (the only-fill-empty / diff rule).**
This rule must NOT live in the writers — it is core business logic and is
the duplication the refactor removes. Extract it once, pure, from the
inline block at `classify_rds.py:110-128`:

```python
# core/classify.py  — pure; decides which fields a sink should write
def plan_writes(rec: Record, result: ClassificationResult) -> dict[str, object]:
    """Fields to persist, applying only-fill-empty + doc_type diff.
       Returns {} when nothing should change (→ a 'skipped' row)."""
    writes: dict[str, object] = {}
    if result.doc_type.value != rec.doc_type.strip().lower():
        writes["doc_type"] = result.doc_type.value
    if rec.type == "" and result.type.value != "":
        writes["type"] = result.type.value
    if rec.discipline_id == "" and result.discipline_id.value not in ("", None):
        writes["discipline_id"] = result.discipline_id.value
    return writes
```

```python
# execution backend contract (input variant)
class RecordReader(Protocol):
    def __iter__(self) -> Iterator[Record]: ...   # each Record carries its own .handle
    def close(self) -> None: ...                  # release file/cursor; no-op if none

# output producer contract (output variant)
class ResultWriter(Protocol):
    def write(self, rec: Record, result: ClassificationResult,
              writes: Mapping[str, object]) -> None: ...
    def close(self) -> None: ...
```

`writes` is computed by `run()` via `plan_writes`; the writer only
**persists** — it never re-derives the fill rule. A writer free to persist
everything (the CSV full-row rewriter) may ignore `writes` and read
`result` directly; a diff writer (RDS) persists exactly the `writes` keys.

**Ownership / cleanup.** `run()` owns the lifecycle of both reader and
writer and closes both even on a mid-loop exception. `CsvReader`/`CsvWriter`
own their file handles (closed in their `close()`); `RdsReader`/`RdsWriter`
do **not** own the injected `conn` (caller's lifecycle, per `io/rds.py`
policy) — they own only their cursors.

**RDS transaction boundary (pinned).** `RdsWriter.write` issues one
per-row `UPDATE` (current `update_row` behavior). Commits are owned by
`RdsWriter`: every `commit_every` *processed* rows and a final commit in
`close()` — identical to today's `classify_rds.py:130-139`. `run()` knows
nothing about commits; `commit_every` is `RdsWriter` config. Other writers
have no transaction semantics.

**Per-record error policy (pinned): fail-fast.** `run()` does not wrap
per-record work in try/except — an exception propagates, matching current
behavior in all three backends (RDS lets the caller `rollback`; CSV/pandas
aborts). Partial RDS work committed up to the last `commit_every` boundary
stays committed; re-running resumes via idempotence. This is a documented
non-change, not a new policy.

```python
# pipeline/run.py — the only orchestration loop
def run(reader: RecordReader, writer: ResultWriter, *, on_progress=None) -> Stats:
    stats = Stats()
    try:
        for rec in reader:
            result = classify_record(rec)
            writes = plan_writes(rec, result)        # core decides; writer obeys
            writer.write(rec, result, writes)
            stats.observe(rec, result, writes)       # updated iff writes non-empty
            if on_progress: on_progress(stats)
    finally:
        reader.close()
        writer.close()
    return stats
```

### Stats schema (the superset that maps back to every legacy shape)

The "external dict shapes preserved" guarantee requires `Stats` to be a
strict superset of all three legacy vocabularies. Legacy fields:

- **RDS** (`classify_rds.py:48-57`): `rows_scanned`, `rows_updated`,
  `rows_skipped`, `doc_type`/`type`/`discipline_id` reason Counters,
  `callback_error`.
- **CSV** (`cli/classify.py:58-105`): `doc_type` value distribution
  *before* and *after*, plus `doc_type`/`type`/`discipline_id` reason
  Counters.
- **titles** (`classify_titles.py`): no stats — returns rows; with
  `include_reasons=True` attaches `(value, reason)` per field (covered by
  the per-field reasons already in the result).

`Stats` fields:

```
rows_scanned: int
rows_updated: int                 # writes non-empty
rows_skipped: int                 # writes empty
reasons: {field: Counter[str]}    # field ∈ {doc_type, type, discipline_id}
doc_type_before: Counter[str]     # rec.doc_type (normalized) per row
doc_type_after:  Counter[str]     # result.doc_type.value per row
callback_error:  str | None       # set by the RdsWriter edge only
```

Per-backend mapping at the edge (no public contract changes):

| Legacy field | Source in `Stats` |
|---|---|
| RDS `rows_scanned/updated/skipped` | same fields |
| RDS `doc_type/type/discipline_id` | `reasons[field]` (as plain dict) |
| RDS `callback_error` | `callback_error` |
| CSV `doc_type before/after` | `doc_type_before` / `doc_type_after` |
| CSV `*_reason` Counters | `reasons[field]` |
| titles `(value, reason)` | already in `ClassificationResult` |

`Stats.observe(rec, result, writes)` updates all of the above; aggregation
lives once in `pipeline/stats.py`.

### Adding a variant with zero core changes (worked example)

To add JSONL output from the RDS stream, write one class:

```python
# io/jsonl_io.py  (new file, nothing else touched)
class JsonlWriter:                       # structurally a ResultWriter
    def __init__(self, path): self._f = open(path, "w")
    def write(self, rec, result, writes):   # full-record sink: ignores `writes`
        self._f.write(json.dumps({"title": rec.title,
            "doc_type": result.doc_type.value,
            "type": result.type.value,
            "discipline_id": result.discipline_id.value}) + "\n")
    def close(self): self._f.close()
```

At the CLI edge: `run(RdsReader(conn), JsonlWriter("out.jsonl"))`. No edit
to `core/`, `pipeline/run.py`, or any other reader/writer. Same for a new
input backend (implement `RecordReader.__iter__`).

### SOLID applied vs not

**Applied:** DIP (orchestrator ← Reader/Writer protocols, removes V3);
OCP+DRY (single `run` loop + `classify_record`, removes V2/coupling #1);
SRP (split `cli/classify.py` V1 and `table_detect.py` V4); DRY (one
scoring engine V5; one fold/stale/`is_empty` V6).

**Deliberately NOT applied:**
- **DIP on the model/ruleset** — rules stay global imports (single model).
  No `RuleSet` interface.
- **ISP** — `RecordReader`/`ResultWriter` stay single-method; splitting
  buys nothing for ~4 implementations.
- **LSP / inheritance** — Protocol + composition; no base classes.
- **No plugin registry / entry-point discovery** — concretes constructed
  explicitly at the CLI edge. A registry would be speculative.

---

## Phase 3 — Migration plan

Each phase is independently shippable and behavior-preserving.

**Phase 0 — Safety net (no production code change).** Capture current
`output/classified.csv` as a golden file; golden test driving
`cli/classify` against a fixture input. `classify_titles` fixture tests
(lock the `int|None` discipline contract). Fake-`conn` test around
`iter_unclassified`/`update_row` to lock RDS SQL + stats shape (fills the
gap noted in INTEGRATION.md). **Add reason-coverage assertions**: legacy
golden output does not contain reasons, but reasons drive `Stats`, so add a
fixture asserting the `*_reason` Counters from the current CSV/RDS runs
(these become the `Stats.reasons` baseline). Guard for everything below.

**Phase 1 — Extract the core row entry.** New `core/record.py` +
`core/classify.py:classify_record`, composing existing `_row.py` functions
unchanged (they already return `(value, reason)` — verified). Repoint the
three call sites. Files: +`core/record.py`, +`core/classify.py`; edit
`classify_titles.py`, `pipeline/classify_rds.py`, `cli/classify.py`.
Behavior identical. Guard: Phase 0 golden + fixtures. *Note: these call-site
edits are partly throwaway — Phase 2 rewrites the same sites to use `run()`.
Accepted: Phase 1 is shippable on its own and de-risks Phase 2 by isolating
the core-entry extraction from the protocol introduction.*

**Phase 2 — Protocols + generic loop.** New `pipeline/run.py` (`run` +
`plan_writes` wiring), `pipeline/stats.py` (the `Stats` superset above),
`io/csv_io.py` (`CsvReader`/`CsvWriter`), thin `RdsReader`/`RdsWriter`
adapters wrapping existing `io/rds.py`, and an `InMemory` reader/writer. Add
`plan_writes` to `core/classify.py`. Rewrite `classify_from_rds`,
`cli/classify`, `classify_titles` to construct reader+writer and call
`run`. Centralize the stale-rules check. Each backend maps `Stats` → its
current public dict at the boundary. `RdsWriter` owns commit cadence;
`run()` owns reader+writer cleanup. Files: +`pipeline/run.py`,
+`pipeline/stats.py`, +`io/csv_io.py`; edit `core/classify.py`,
`io/rds.py` (adapters), `classify_rds.py`, `classify_titles.py`,
`cli/classify.py`. Guard: golden CSV + RDS stats-shape test (incl. commit
cadence + cleanup-on-exception) + classify_titles contract test.

**Phase 3 — Collapse the scoring engine.** New `core/scoring.py` with
generic `score()`/`pick()`; repoint `score_types/pick_type` and
`score_disciplines/pick_discipline`; drop the duplicated gate and the
cross-module private import. Files: +`core/scoring.py`, edit
`type_scoring.py`, `discipline_scoring.py`. Guard: snapshot `pick_*` over
every training title before/after and assert identical results.

**Phase 4 — Tidy SoC leftovers (low risk).** Split `table_detect.py` into
pure `find_table` (core) + new `io/workbook.py`
(`iter_grids`/`file_has_table`); point `convert_classified` at it. Replace
`table_detect._is_empty` with `io.normalize.is_empty`. Move fold-to-class
into one `core` function used by both `_row.normalize_doc_type` and
`convert_classified`. Update `README.md`/`INTEGRATION.md` to match reality
— do not just delete the stale references but **point them at the real new
locations**: the scoring engine at `core/scoring.py` (created in Phase 3),
the fold-to-class function at its new `core` home (this phase), and the
scorers at `core/type_scoring.py` / `core/discipline_scoring.py`. (Stale
refs today: `core/scoring.py:fold_to_class`, `config/keywords.py`,
`config/patterns.py`.) Files: `table_detect.py`, +`io/workbook.py`,
`convert_classified.py`, `_row.py`, docs.

### Behavior-change risks & guards

- **Discipline type drift** (`int|None` vs str vs `int`): keep the
  difference at the writer, not the core — `classify_record` returns one
  typed value; each writer formats for its sink. Locked by per-backend
  tests.
- **Stat vocabulary differences**: do not unify the public stats dicts
  (that would be a behavior change) — map `Stats`→existing shape per
  backend.
- **Business rules** (`doc_type` defaults to `document`; only-fill-empty;
  conservative type/discipline): untouched inside `_row.py`; golden tests
  catch regressions.
