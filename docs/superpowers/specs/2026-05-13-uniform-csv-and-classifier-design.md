# Uniform CSV pipeline + classifier rewrite

Date: 2026-05-13
Status: Draft

## Goal

Convert all classified xlsx indices into the same 28-column CSV schema as
`input/To be classified/document.csv`, build a `type` enum from those CSVs,
then rewrite the classifier so it only fills the `doc_type` and `type`
columns of the to-be-classified CSV (no new columns, no other edits).
Also clean up repo cruft picked up along the way.

## Why

- Mixed xlsx schemas across `input/classified/` make every downstream step
  branchy and brittle. One canonical CSV schema eliminates the format axis.
- The to-be-classified CSV already carries `doc_type` and `type` columns;
  filling them in-place is what consumers actually want.
- The current `BUCKET_PRIMARY_CODE` (DWG/DOC/ISO/…) is too coarse; the real
  enum is the 31 three-letter codes used in the classified indices.
- Lookup against a consolidated reference CSV is deterministic — better to
  leave `type` empty than to guess wrong, per user direction.

## Out of scope

- No folder sorting changes (separate workstream).
- No new classifier columns (score/confidence/discipline_inferred etc.).
- No keyword-based prediction of the 3-letter `type` code (left for a
  later classifier-improvement pass).
- No schema changes to the 28-column CSV.
- No automated tests (per standing user direction — see commit `e872846`).
  Verification is by hand: row-count parity, per-rule counts in the
  summary printout, spot-check of sample rows.

## Cross-cutting invariants

These apply to every sub-project and every helper.

### String-only I/O

All CSV and Excel reads use `dtype=str, keep_default_na=False, na_values=[]`.
The literal four-character string `NULL` is treated as empty by the rules
in C; it is never converted to a Python `None` during I/O. Empty cells
are the empty string `""`, never `NaN`. This preserves leading zeros,
prevents scientific-notation mangling, and keeps JSON blobs intact.

### Schema validation

Shared helper `validate_schema(columns: Sequence[str]) -> None` lives at
`src/classifier/io/schema.py`. It asserts:

- exact length 28
- exact order matching `TARGET_COLUMNS`
- no extras, no duplicates

Invoked at the start of every CSV write (A, C output) and every CSV read
of a canonical CSV (B, C input). Hard-fail on mismatch.

### Lookup-key normalization

Shared helper `normalize_lookup_key(value: str) -> str` lives at
`src/classifier/io/normalize.py`:

- if input is empty or the literal `NULL` → return `""`
- Unicode-normalize NFKC (folds fullwidth, ligatures)
- strip leading/trailing whitespace
- collapse internal whitespace runs to a single space
- replace en/em dashes and minus-sign with ASCII hyphen
- uppercase

All lookup-map builders and consumers must use this helper. No ad-hoc
`.strip().upper()` calls.

### Header-token normalization

Shared helper `normalize_header_token(value: str) -> str` at
`src/classifier/io/normalize.py`:

- strip, lowercase, NFKC, collapse whitespace, drop trailing punctuation
- examples: `"Document No."`, `"Document No"`, `"Document No :"` all map to `"document no"`

Header detection in A compares normalized tokens, not raw strings.

### Deterministic file ordering

Any code that walks a directory uses
`sorted(path.glob(pattern), key=lambda p: str(p).lower())`. No reliance
on filesystem traversal order. This makes A and B's outputs identical
across OSes and CI.

---

## Architecture (3 sub-projects + cleanup)

```
input/classified/**/*.xls*  ──A──▶  input/classified_csv/**/*.csv
                                            │
                                            ▼
                                       (concatenate)
                                            │
                                            ▼
                                  ──B──▶  type enum (config)
                                            │
input/To be classified/document.csv ──┐     │
                                      ▼     ▼
                                     ──C──▶ output/classified.csv
                                     (doc_type normalized, type filled-if-empty)
```

A and B are mechanical/data tasks. C is the user-visible classifier. Order:
A → B → C → cleanup.

---

## Sub-project A — xlsx → CSV normalizer

### Target schema

Exact 28 columns from `input/To be classified/document.csv`, identical order:

```
document_id, entity_id, document_no, doc_type, status, description,
date_modified, modified_by, category, discipline_id, title, rev,
reference_link, volume, book, customer_ref, doc_source,
parent_discipline_id, type, entity_source, hash, metadata,
extracted_at, extractor_version, last_updated_at, updated_by,
rfp_id, toc_json
```

All cells are strings. Empty = `""` (never the literal `NULL`).

### Column mapping (source → target)

| Source header (case/whitespace tolerant)                          | Target          |
|-------------------------------------------------------------------|-----------------|
| Document No., Doc No., PCS Doc No.                                | `document_no`   |
| Title                                                              | `title`         |
| Rev., Rev, Revision                                                | `rev`           |
| Status                                                             | `status`        |
| Type                                                               | `type`          |
| VOLUME, Volume                                                     | `volume`        |
| BOOK, Book                                                         | `book`          |
| Cust Ref #, Customer Ref, Customer Reference                       | `customer_ref`  |
| Discip, Discipline                                                 | (drop — no clean target; `discipline_id` is numeric in target schema) |
| (sheet name)                                                       | `doc_source`    |
| Section header above row (Documents / Drawings / Documents/Drawings) | `doc_type` (see derivation below) |

Unmapped source columns are dropped (with a count logged per file).
Unmapped target columns stay empty.

### `doc_type` derivation per row

- Nearest preceding section header equals `Documents` / `Document` (case-insensitive) → `document`
- Equals `Drawings` / `Drawing` → `drawing`
- Mixed (`Documents/Drawings`) or absent → derive from row's `Type` via `TYPE_TO_BUCKET` then `BUCKET_TO_CLASS`, lowercased
- Otherwise empty

### Header auto-detection

- Read each sheet headerless. Scan first **50** rows.
- For each row, build the set `{normalize_header_token(cell) for cell in row}`.
- First row whose normalized tokens contain both `"document no"` and
  `"type"` (via the alias map) is the header row. Subsequent rows are data.
- If no candidate header → log + skip the sheet (do not error).

### Section header detection

A row is treated as a section label only when **all** of these hold:

- Column A is populated.
- All header-defined data columns (`Document No.`, `Type`, `Title`, `Rev.`)
  are blank in that row.
- Column A's value is short (≤ 40 chars after strip).
- Column A's value contains only letters, spaces, slashes, ampersands, and
  hyphens (no digits, no colons). Rejects "Prepared by John 2014" and
  "Subtotal: 12".

Carry last-seen label down to subsequent data rows until replaced. If the
label exactly matches a known category (case-insensitive set of
`{"Project Management", "Process", "Mechanical", "Electrical", "Instrumentation",
"Piping", "Civil", "Structural", "Safety", "Telecom", "HVAC"}`), also write
it to the `category` column; otherwise leave `category` empty and log the
unmatched label.

### File walk

- Glob `input/classified/**/*.xls*`, sorted lexicographically.
- Skip any path containing a `void/` segment.
- Per workbook, iterate every sheet in workbook order.

### Output layout

- Mirror tree under `input/classified_csv/`.
- One CSV per sheet. Filename: `<workbook-stem>__<sheet-slug>.csv`.
- Sheet slug: lowercase, NFKC, replace any character not in `[a-z0-9_-]`
  with `_`, collapse consecutive `_`, trim leading/trailing `_`.
- On slug collision within a workbook, append `_2`, `_3`, … in sheet order.
- CSV written with `csv.QUOTE_MINIMAL`, UTF-8, LF line endings.

### Code shape

- New module: `src/classifier/tools/convert_classified.py`.
- New entry point in `pyproject.toml`: `convert-classified`.
- Reuses `pd.read_excel(..., header=None, dtype=str, keep_default_na=False)`.
- One pure function `xlsx_to_rows(workbook_path) -> Iterable[(sheet, list[dict])]`
  separated from the file walker so it can be exercised on a single file.

### Done when

- Every non-void xlsx under `input/classified/` produces at least one CSV.
- Summary printed: per file → sheet → rows-written, header-row-index,
  unmapped-source-columns, unknown-section-labels.

---

## Sub-project B — type enum from consolidated CSVs

### Inputs

- All CSVs produced by A: `input/classified_csv/**/*.csv`.

### Process

- Read every CSV, collect `(type, doc_type)` distinct values + counts.
- Normalize: uppercase, strip; drop empty.
- Compare against `TYPE_TO_BUCKET.keys()` (the 31 known codes).

### Output

- `src/classifier/config/type_enum.py` containing:
  - `KNOWN_TYPES: frozenset[str]` — the 31 mapped codes (synced with
    `TYPE_TO_BUCKET`). Listed sorted in the generated source.
  - `OBSERVED_OUTLIERS: dict[str, int]` — codes seen in classified CSVs that
    are not in `KNOWN_TYPES`, mapped to occurrence count. Keys emitted in
    sorted order for stable diffs. Intended as a todo list for future
    classifier-improvement work (e.g. ITB → still unmapped pending bucket
    decision).
  - `ALL_OBSERVED_TYPES: frozenset[str]` — `KNOWN_TYPES | OBSERVED_OUTLIERS.keys()`.
- Module is generated by a one-shot tool, not hand-edited. Re-running
  the tool overwrites the file. Generator writes a header comment with
  the generation date and the number of source CSVs read so users can
  tell when the file is stale.

### Code shape

- New module: `src/classifier/tools/build_type_enum.py`.
- New entry point: `build-type-enum`.

### Done when

- `type_enum.py` exists and `python -c "from classifier.config.type_enum import KNOWN_TYPES; print(len(KNOWN_TYPES))"` prints 31.
- `OBSERVED_OUTLIERS` is empty for sahild-only data; populates if other
  classified xlsx files contain non-31 codes.

---

## Sub-project C — classifier rewrite

### Input / output

- Input: `input/To be classified/document.csv` (fixed path).
- Output: `output/classified.csv` — identical 28 columns, identical order,
  identical row count. Only `doc_type` and `type` may differ from input.

### `doc_type` rule (always normalized)

- Normalize existing values via case/spelling map:
  - drawing-ish: `drawing`, `drawings`, `dwg` → `drawing`
  - document-ish: `document`, `documents`, `doc`, `docs` → `document`
- If unrecognized / empty / `NULL`:
  - Run `score_buckets(title, description)`, pick bucket.
  - Fold via `BUCKET_TO_CLASS`. `Drawings` → `drawing`. Everything else
    (including `Undefined`) → `document`.

**Business rule (intentional bias):** `Undefined` folds to `document`, not
to empty. Rationale: drawing-classification carries higher operational
risk (drawings drive procurement, fabrication, MOC), so the conservative
fallback is to label uncertain rows as document. Empty `doc_type` is
reserved for future use; do not introduce it as a fallback without
revisiting this spec.

### `type` rule (fill only if empty)

- If row's existing `type` is non-empty (after strip, ignoring literal
  `NULL`) → leave verbatim.
- If empty, consult two **separate** lookup maps, built once at startup
  from `input/classified_csv/**/*.csv` (paths walked in deterministic
  sorted order):

  1. `doc_no_lookup: dict[str, str]` — keyed on `normalize_lookup_key(document_no)`.
  2. `cust_ref_lookup: dict[str, str]` — keyed on `normalize_lookup_key(customer_ref)`.

  Both maps include only rows where `type ∈ ALL_OBSERVED_TYPES` after
  normalization.

  **Duplicate-key conflict resolution** (applied identically to both maps):

  - Intermediate build accumulates `dict[str, set[str]]`.
  - After the walk, for each key:
    - `len(types) == 1` → entry accepted, value is the sole type.
    - `len(types) > 1` → entry **dropped** and added to a conflict list.
      Conflicts are printed in the summary so the user can clean source
      data. The classifier never emits a guessed type from a conflicted
      key.

  **Lookup order per row:**

  - Try `doc_no_lookup[normalize_lookup_key(row.document_no)]` first.
  - Fall back to `cust_ref_lookup[normalize_lookup_key(row.customer_ref)]`.
  - Miss in both → leave `type` empty.

  **Per-source hit accounting:** the summary reports `type` fills broken
  down as `via_doc_no`, `via_cust_ref`, `empty`. If `via_cust_ref` ever
  exceeds 10% of total fills, print a loud warning — customer refs are
  reused / human-entered, and a sudden spike usually means a bad source
  CSV, not a classifier win.

### CSV I/O

- `pd.read_csv(..., dtype=str, keep_default_na=False, na_values=[])` so
  literal `NULL` stays as the string `"NULL"`.
- Treat `"NULL"`, `""`, whitespace-only as empty when applying the rules.
- Write with `csv.writer`, matching input quoting (`QUOTE_MINIMAL`).
- JSON-blob columns (`metadata`, `toc_json`) pass through untouched.

### Code shape

- Rewrite `src/classifier/cli/classify.py`:
  - Drop xls glob and multi-sheet loop.
  - Drop appended diagnostic columns and old summary tables.
  - Keep using `score_buckets` / `BUCKET_TO_CLASS` from existing modules.
- New helper `src/classifier/io/type_lookup.py` containing
  `build_lookup(csv_dir) -> dict[str, str]`.
- New summary on stdout: total rows, doc_type counts (before/after),
  `type` filled count, `type` preserved count, `type` left-empty count,
  lookup map size, lookup hit rate.

### Done when

- `classify` runs end-to-end against `document.csv` and writes
  `output/classified.csv` with only `doc_type` and `type` modified.
- Hand-inspecting 5 random rows shows: existing non-empty `type` preserved
  verbatim; previously-empty `type` filled only when `document_no` matches
  the classified lookup; `doc_type` always non-empty and lowercase.

---

## Sub-project D — repo cleanup

Cleanup is opportunistic — only items observed during this work.

### Drop

- `Feed.txt` (untracked sandbox file at repo root). Add to `.gitignore`
  if it keeps reappearing.
- `scripts/sort_by_dossier.py` — untracked one-off script. Delete; the
  functionality has moved into `classifier.cli.sort`.
- Empty `scripts/` directory after the file is removed.

### Move

- None planned. Source layout under `src/classifier/{cli,core,io,routing,pipeline,tools,config}/`
  stays as-is.

### Update

- `pyproject.toml` `[project.scripts]` gains `convert-classified` and
  `build-type-enum` entry points.
- `README.md` short pointer to the new entry points and the
  `input/classified_csv/` artifact directory.
- `.gitignore` to ignore `input/classified_csv/` if user prefers not to
  commit derived data (open question — see below).

### Decision: commit `input/classified_csv/`

`input/classified_csv/` is committed to the repo. CSV artifacts are
cheap, the lookup becomes reproducible without re-running A on every
machine, and source-xlsx changes show up as reviewable diffs. The A
walker uses sorted/deterministic ordering precisely so commits stay
clean.

---

## Risks and mitigations

| Risk                                                              | Mitigation |
|-------------------------------------------------------------------|------------|
| Other classified xlsx files have header layouts unlike sahild     | Auto-detect by content (look for "Document No." + "Type"), skip + log on miss instead of crashing |
| Duplicate `document_no` across classified CSVs with different `type` | First-seen wins; warn loudly so user can clean source data |
| Section-header detection misses or mis-classifies                 | `doc_type` falls back to `Type`-via-`TYPE_TO_BUCKET`; if still empty, classifier C will fill via title scoring |
| `description` (used by C scorer) is a JSON-ish blob, not free text | Verified: input rows have plain-text `description` or NULL; metadata JSON is in `metadata`/`toc_json` columns |
| User adds outlier `type` codes manually (e.g. ITB) — classifier overwrites | C only fills when empty; existing non-empty values are preserved verbatim |

## Acceptance

1. `convert-classified` produces a CSV for every non-void xlsx under `input/classified/`, all conforming to the 28-column schema; `validate_schema` passes on every output.
2. `build-type-enum` writes `src/classifier/config/type_enum.py` listing 31 known codes (sorted) + any outliers (sorted), with a generation-date header.
3. `classify` reads `document.csv`, writes `output/classified.csv` with only `doc_type` and `type` modified, row-count and column-order identical to input, and prints a summary covering: total rows, doc_type counts before/after, `type` preserved / filled-via-doc_no / filled-via-cust_ref / empty, conflicted-key list, and a customer-ref-fallback ratio warning if applicable.
4. `Feed.txt` and `scripts/sort_by_dossier.py` no longer present in the working tree.
5. Re-running A and B back-to-back on the same source xlsx files produces a byte-identical `input/classified_csv/` tree and a byte-identical `type_enum.py` (determinism check).
