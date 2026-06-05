# Fold-free discipline classification (label-driven) — design

**Date:** 2026-06-05
**Status:** Approved (design).
**Pivot note:** An earlier draft of this spec proposed hand-curated keyword
rules because the discipline labels were assumed unreliable. The user has
since confirmed the training discipline labels in `input/classified_csv/`
**are trustworthy** and **are already `disciplines.csv` ids**. This spec is
rewritten accordingly: keep the existing label-learning tools, just **remove
the client→DEST fold** and train directly on the labelled `discipline_id`.

**Scope:** Discipline learning only. Type classification, the scoring engine,
and the schema are unchanged.

## Problem

Discipline rules were learned from the `discipline_id` column of the labelled
CSVs, then remapped through `input/discipline_fold.csv` (client-id → DEST-id),
which (a) collapsed the taxonomy into a coarse 7-bucket set and (b) "corrected"
labels the user considers authoritative. The fold is unwanted.

## Decision

- **Delete the fold.** Train discipline keyword rules keyed **directly** by the
  labelled `discipline_id`, treating each value as a `disciplines.csv` id.
- **Validate against `disciplines.csv`.** A labelled id not present in
  `disciplines.csv` is dropped as an orphan (keeps `documents.discipline_id`
  FK-safe). Today all labelled ids (1, 4, 7, 10, 13, 17, 20, 23, 25, 26) exist
  in `disciplines.csv`, so none are dropped.
- **Full taxonomy, only where supported:** a discipline gets rules only when it
  has ≥ `MIN_CLASS_DOCS` labelled examples (existing threshold); others emit no
  rules and simply never fire (discipline stays NULL). This is the natural
  outcome of training on the labels present.

The runtime is untouched — `core/discipline_scoring.py` consumes the two
generated config dicts exactly as before; they now contain the real
`disciplines.csv` ids instead of folded buckets.

## Changes

### `src/classifier/tools/learn_discipline_keywords.py`
- Remove `DISCIPLINE_FOLD_CSV`, `_load_fold`, and all fold usage.
- Rename/repurpose `_load_valid_dest_ids` → `_load_valid_discipline_ids`
  (loads the id set from `input/disciplines.csv`). Keep `_parse_discipline`.
- `_collect_rows(valid_ids)`: for each labelled row, parse `discipline_id`;
  if the id is **not** in `valid_ids`, count it as an orphan and skip;
  otherwise emit `(discipline_id, title, source_path)` using the id **as-is**
  (no fold).
- `main`: load valid ids; collect rows; learn; render. Update the prints to
  drop fold/DEST-bucket language (report: rows kept, disciplines trained,
  disciplines untrained `< MIN_CLASS_DOCS`, orphan ids not in
  `disciplines.csv`).
- Rewrite the module docstring (no fold; trains directly on labelled ids
  validated against `disciplines.csv`).

### `src/classifier/tools/learn_type_discipline.py`
- Drop the fold: import `_load_valid_discipline_ids`, `_parse_discipline`,
  `DISCIPLINES_TABLE_CSV` from `learn_discipline_keywords` (no `_load_fold`,
  no `DISCIPLINE_FOLD_CSV`).
- `_collect_pairs(valid_ids)`: count `discipline_id` per type using the raw
  id, skipping ids not in `valid_ids` (orphans). The majority/min-occurrence
  logic and emitted shape are unchanged (`TYPE_TO_DISCIPLINE: {TYPE: id}`).
- `main`: load valid ids instead of the fold; update prints.

### `input/discipline_fold.csv`
- Deleted.

### Stale-config wiring
**No change needed.** Both discipline configs are still learned from
`input/classified_csv/`, so the existing freshness check (type_keywords,
discipline_keywords, type_to_discipline all vs `input/classified_csv/`,
naming the three `learn-*` tools) remains correct.

### `pyproject.toml`
**No change.** The `learn-discipline-keywords` and `learn-type-discipline`
console scripts are kept (the tools remain, just fold-free).

## Regeneration (deliberate, scoped behavior change)

1. Run `learn-discipline-keywords` and `learn-type-discipline` → regenerate
   `config/discipline_keywords.py` and `config/type_to_discipline.py` with real
   `disciplines.csv` ids.
2. **Golden** `tests/golden/classified.csv`: re-run `classify`, copy output to
   the golden. **Verify only the `discipline_id` column changed** vs the prior
   golden (doc_type/type/other columns identical).
3. **Scoring baseline** `tests/core/scoring_baseline.json`: delete and
   regenerate via the snapshot test. **Verify `type`/`type_conf`/`cr_type`/
   `cr_doc_type` are byte-identical** to the prior baseline (only `disc`/
   `disc_conf`/`cr_disc` change), proving the change is scoped to discipline.

## Testing

- `learn_discipline_keywords` unit tests (tmp CSVs): rows with a valid
  `disciplines.csv` id are trained under that id (no remap); an id absent from
  `disciplines.csv` is counted as an orphan and dropped; `< MIN_CLASS_DOCS`
  disciplines are reported untrained. Confirm NO reference to a fold remains
  (no `discipline_fold` import; the function signatures take `valid_ids`).
- `learn_type_discipline` unit test: a type whose labelled rows are a clear
  majority of one valid id emits that id; ids not in `disciplines.csv` are
  skipped.
- After regeneration, the new `config/discipline_keywords.py` keys are a
  subset of `disciplines.csv` ids (FK-safety assertion).
- Regenerated golden + baseline are the going-forward regression locks.

## Docs

Update `INTEGRATION.md` and `README.md` discipline sections:
- Remove the fold narrative and `discipline_fold.csv` references.
- Describe: discipline rules are learned directly from the labelled
  `discipline_id` (which are `disciplines.csv` ids), validated against
  `disciplines.csv`; ids not in the table are dropped; disciplines with too few
  examples emit no rules and stay NULL. To improve coverage, add labelled rows
  (or a new discipline to `disciplines.csv`) and re-run the two learners.

## Out of scope

- Type classification, `type_keywords`, the scoring engine, the schema.
- The RDS/CSV/router pipelines (consume the configs unchanged).
- Curated/hand-authored discipline keyword banks (dropped with the pivot — the
  trusted labels are the source of truth).
