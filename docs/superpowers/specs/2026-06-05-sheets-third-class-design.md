# Sheets: a third top-level class

**Date:** 2026-06-05
**Status:** Approved design — Phase 1 gates Phase 2

## Problem

The classifier currently folds every document into one of two user-facing
classes: **Drawings** or **Documents** (see
[buckets.py](../../../src/classifier/config/buckets.py),
`BUCKET_TO_CLASS`). We want a **third class, `Sheets`**, for tabular
deliverables — MTO files, BOM/material take-offs, line lists, ISO
indexes, registers, and similar.

The defining rule from the user: **a "Sheet" must contain a real table.**
A spreadsheet that is actually a fixed form (e.g. a Comment Response
Sheet, or a datasheet form) is *not* a Sheet, even though it is an
`.xlsx`. Evidence: in the sample directory, the `.xlsx` population is a
mix of genuine tables (ISO INDEX with 367 data rows, MTOs, line lists)
and label-value forms (CRS / Comment Response Sheets — sparse 7-column
key/value templates with no repeating records).

## Hard constraint

**The runtime classifier stays 100% title-based.** It never opens files
at classify time. File inspection happens only during a one-off
*learning* pass whose purpose is to discover which **title patterns /
type codes** are reliably table-sheets. The learned evidence is then
encoded as ordinary title rules / a fold change.

## Source data & linkage

- Runtime input/label source: `output/classified.csv` (825 rows). Each
  row has `customer_ref` (e.g. `16-01-19-2602`), a descriptive `title`
  (e.g. `VALVE LIST`, `MTO FOR PIPES AND FITTINGS`), and a 3-letter
  `type` (LST, MTO, DAS, SCH, DSL, …).
- Evidence directory:
  `D:\Indus\DEST Pilot DATA\KR\HISTORIC Projects\SAHIL (Clean)\5. Deliverables + Correspondence - Execution\Transmittals\TO CLIENT`
  — 826 spreadsheets (`.xlsx/.xls/.xlsm`) plus PDFs/DOCX/DWG.
- Linkage: the `16-01-xx-xxxx` doc-number embedded in each spreadsheet's
  filename matches `customer_ref`. Measured overlap: **365 of 386**
  distinct dir doc-numbers join to the CSV. Good enough to learn from.

## Phase 1 — Learning / exploration

New tool: `src/classifier/tools/learn_sheet_patterns.py`.

Steps:
1. Walk the evidence dir; collect every spreadsheet file.
2. Extract the `16-01-xx-xxxx` doc-number from each filename (regex).
3. Join to `classified.csv` on `customer_ref` → attach `title`, `type`,
   `discipline_id`.
4. Open each spreadsheet and run the **table detector** across *all*
   worksheets (not just the active one — real tables frequently sit
   behind a `Cover`/`Notes`/`Index` tab). Produce `has_table` (bool) and
   supporting detail (which sheet, header width, data-row count).
5. Emit:
   - a per-file labelled CSV
     (`docnum, file, title, type, has_table, table_sheet, n_data_rows`)
     to `output/sheet_learning.csv`;
   - an aggregation report: for each `type` code and each common title
     n-gram, the count and fraction of joined files that are real
     tables.

### Table detector criterion (initial; tunable)

A workbook qualifies as a table-sheet if **any** worksheet contains:
- a header row of **≥3 adjacent non-empty text cells**, followed by
- **≥5 data rows** in which the majority of those header columns remain
  populated (i.e. a repeating-record structure).

This passes MTOs/INDEXes/line lists (tens–hundreds of rows) and rejects
CRS / datasheet forms (label-value, no repeating records). The `≥5`
row threshold and `≥3` column width are constants at the top of the
tool; we eyeball borderline cases against the report and tune before
Phase 2.

Phase 1 output is **evidence only** — it changes no classification
behavior.

## Decision gate (between phases)

After Phase 1 we review the aggregation together and decide:
- **Promotion rule:** re-route whole buckets vs. per-type threshold
  (e.g. promote a `type` only if ≥90% of its real files were tables).
- **Final table-strictness threshold.**

Both were deferred by the user pending real numbers.

## Phase 2 — Add the `Sheets` class

Smallest change consistent with the existing architecture. The
title→type scoring path is **unchanged**; only the **bucket→class fold**
moves.

1. Add `"Sheets"` to the user-facing class set.
2. In `BUCKET_TO_CLASS`, re-route the bucket(s)/type(s) that Phase 1
   proves are reliably tabular (candidate: `Lists_MTOs_BOMs`, possibly
   others) from `Documents` → `Sheets`.
3. If Phase 1 shows the split is finer than a whole bucket, introduce a
   dedicated `Sheets` bucket and move the qualifying `type` codes
   (MTO/BOM/LST/IDX/SCH/DSL/…) into it via `TYPE_TO_BUCKET`, then fold
   that bucket to the `Sheets` class. Exact membership decided at the
   gate.
4. Update any consumer that hard-codes the two-class set (CLI output,
   the HTML viewer, `convert_classified`, schema/enums) to handle three
   classes.
5. Regenerate `output/classified.csv` and spot-check that MTO/INDEX rows
   land in `Sheets` and CRS/datasheet-form rows do **not**.

## Repo cleanup (independent, do first)

Delete the 13 untracked ad-hoc root scripts that are throwaway
exploration: `analyze2.py`, `audit_missing.py`, `audit_wholetree.py`,
`build_chunking_input.py`, `check_example.py`, `copy_docs.py`,
`copy_notincsv.py`, `fuzzy_find.py`, `move_to_dsahil.py`, `probe.py`,
`reconcile.py`, `reconcile_full.py`, `scripts/_gen_validation_report.py`.
None are tracked in git; none are imported by `src/`.

## Out of scope

- No change to discipline inference.
- No change to the title→type scoring algorithm itself.
- No file inspection at classify time, ever.

## Testing

- Phase 1 tool: spot-check the labelled CSV — a handful of known MTOs
  must be `has_table=true`; known CRS files must be `false`.
- Phase 2: a small title-level table asserting representative titles map
  to the expected class (Drawing / Document / Sheet), driven through
  `pick_type_with_overrides` + the fold.
