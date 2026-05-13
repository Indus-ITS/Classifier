# Two-class fold (Drawings / Documents)

**Status:** approved 2026-05-01
**Author:** brainstorming session with user

## Summary

Collapse the existing 10-bucket classification into a 2-class label —
`Drawings` or `Documents` — as the primary output. Keep the 10-bucket label
as a `subtype` column for traceability and future sub-routing.

This is a **post-fold layer**: the keyword bank, scoring, and bucket-pick
logic are unchanged. We add a `BUCKET_TO_CLASS` mapping in `config.py` and
derive `class` from `subtype` in the output writer.

## Motivation

The downstream user only needs two piles (drawings vs documents). The
existing 10-bucket discrimination is over-fit for that use, but the bucket
labels remain useful as sub-routing hints (e.g. `Documents/Reports/`,
`Documents/Specifications/`) if needed later. Keeping subtype preserves
optionality at zero cost — the classifier is already producing it.

The user has confirmed:
- All eight non-drawing buckets fold to **Documents** (Specifications,
  Standards, Procedures, Method Statements, Reports, Datasheets,
  Calculations, Lists/MTOs/BOMs, CRS, Documents).
- `Isometrics` and `Drawings` fold to **Drawings**.

## Fold mapping

| Subtype (existing bucket) | Class |
|---|---|
| Drawings | Drawings |
| Isometrics | Drawings |
| Datasheets | Documents |
| Specifications | Documents |
| Calculations | Documents |
| Reports | Documents |
| Lists_MTOs_BOMs | Documents |
| Procedures_Plans | Documents |
| CRS | Documents |
| Documents | Documents |

This mapping lives in `config.py` as `BUCKET_TO_CLASS`. Single source of
truth — every consumer (classifier, evaluator, mapping dump) reads it
from there.

**Note on "Diagrams":** there is no separate Diagrams bucket. P&IDs, PFDs,
BFDs, UFDs, MSDs, loop diagrams, cause & effect diagrams, single-line
diagrams, wiring/schematic/block diagrams, and termination diagrams all
score into the existing `Drawings` subtype via the keyword bank. Under
this fold they correctly land in `class = Drawings`. Verified by sampling
12 representative diagram titles through `pick_bucket()` — all returned
`Drawings`.

**Undefined class (refinement):** the fold has a third value, `Undefined`,
returned when no keyword fired (`score_sum == 0`). Without this, titles
like "Water Disposal Well SA 075 Sahil" — which match nothing in any
bucket — would silently fall through to Documents, polluting the clean
Documents signal. The Undefined class lets the user filter
`class != "Undefined"` for clean classifications, or filter
`class == "Undefined"` for items that need human review. Implemented
via the shared helper `helpers.classifier_lib.fold_to_class()` so
`classifier.py` and `helpers/evaluate_corpus.py` both apply the same rule.
Subtype is left as `"Documents"` for these rows to record what the
fallthrough bucket was.

## Output schema change

`output/classified.csv` column order changes from:

```
title, doc_number, cust_ref, revision, discipline, doc_type,
source_sheet, discipline_inferred, score, top_weight, confidence,
runner_up, runner_up_score
```

to:

```
title, doc_number, cust_ref, revision, discipline, class, subtype,
source_sheet, discipline_inferred, score, top_weight, confidence,
runner_up, runner_up_score
```

Changes:
- Renamed `doc_type` → `subtype`. The user has no external consumers of
  the old column name; renaming now is cheaper than carrying a deprecation.
- New `class` column inserted between `discipline` and `subtype`. Values
  are exactly `Drawings` or `Documents`.

## Component changes

### `config.py`
Two additions:

1. **`BUCKET_TO_CLASS` constant** — a `dict[str, str]` mapping each of
   the 10 bucket names in `BUCKETS` to either `"Drawings"` or `"Documents"`.
   Total of 10 entries.

2. **Profile keyword in `KEYWORD_RULES["Drawings"]`** — add `\bprofile\b`
   weight 4 to fix a real gap surfaced during this brainstorm. Today,
   titles like "Pipeline Approach Profile", "Pipeline Long Profile",
   "Pipeline Profile - 16 inch CDS South" fall through to Documents
   because no Drawings keyword fires. Adding `profile` (weight 4)
   resolves them as Drawings without conflicting with any other bucket
   (no other bucket uses "profile").

### `classifier.py`
Read `BUCKET_TO_CLASS` from config; for each row, set `class =
BUCKET_TO_CLASS[predicted_bucket]`. Update the column tuple. Update the
stdout summary to print both class and subtype distributions.

### `helpers/classifier_lib.py`
No change. Still produces the same 10-bucket pick.

### `helpers/evaluate_corpus.py`
Compute two accuracy numbers in parallel:

- **class accuracy** — `BUCKET_TO_CLASS[predicted] == BUCKET_TO_CLASS[expected]`
- **subtype accuracy** — `predicted == expected` (the existing measure)

Both accuracy numbers print to stdout and to
`output/helpers/evaluation_report.txt`. Per-class confusion matrix is
added (it will be a 2x2: rows = expected class, cols = predicted class).
Per-subtype confusion matrix already exists — keep it.

### `helpers/dump_bucket_mapping.py`
Add a `mapped_class` column so the senior reviewing the doc-code → bucket
mapping also sees the final 2-class assignment for each code. Sort order
unchanged (already sorted by mapped_bucket).

### `output/classified.csv`
Regenerated by running `python classifier.py`. Old column order replaced
by new.

### Tests

- **No existing test changes.** All 122 tests assert subtype-level
  behaviour (e.g. `_bucket("Roof Plan") == "Drawings"`). The bucket name
  `"Drawings"` remains valid as a subtype, so these still pass.
- **New file `tests/test_class_fold.py`**, ~10 smoke tests:
  - `BUCKET_TO_CLASS` keys cover all 10 entries in `BUCKETS`.
  - `BUCKET_TO_CLASS` values are exactly `{"Drawings", "Documents"}`.
  - `Drawings` and `Isometrics` map to `Drawings`.
  - The other eight buckets map to `Documents`.
  - End-to-end: a sample title that scores Reports → fold gives `class=Documents`.
  - End-to-end: a sample title that scores Drawings → fold gives `class=Drawings`.
- **Pin the Profile keyword** in `tests/test_keyword_bank.py`:
  - "Pipeline Approach Profile" → `Drawings`.
  - "Pipeline Long Profile" → `Drawings`.

### `README.md`
Update the output schema table to show `class` and `subtype` instead of
`doc_type`. Update the "Current accuracy" table to add a Class accuracy
row alongside the existing subtype number.

## Non-goals

- **Not** simplifying the keyword bank to a 2-class scoring. Subtype
  scoring is preserved.
- **Not** introducing a per-class confidence (we already have subtype
  confidence; class confidence equals subtype confidence by construction).
- **Not** routing files into `Drawings/` and `Documents/` folders. This
  spec only changes the CSV labelling. Folder routing is a separate
  Phase 2 concern.

## Risks

- **Tests pinning bucket names** — none of the 122 existing tests assert
  a column called `doc_type`. They assert against `score_buckets` /
  `pick_bucket` returns directly, which are unchanged. Verified by
  grepping the test files for `doc_type`.
- **External consumers of `doc_type` column** — user has confirmed there
  are none. The column is renamed in the same change.
- **`BUCKET_TO_CLASS` drift from `BUCKETS`** — the new test asserting
  full coverage prevents this.

## Success criteria

- `output/classified.csv` has both `class` and `subtype` columns; class
  is one of `{"Drawings", "Documents"}` for every row.
- `python helpers/evaluate_corpus.py` prints both class accuracy
  (expected ≥99%) and subtype accuracy (unchanged at 95.7%).
- `output/bucket_mapping.csv` has a `mapped_class` column.
- All 122 existing tests still pass; ~10 new fold tests added.
- `README.md` reflects the new schema.
