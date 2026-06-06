# Fixing sheet mis-classification + CRS exclusion

**Date:** 2026-06-06
**Status:** Approved shape — detail under review

## Problem

The sorter places files into `<doc_source>/<class>/` where `class` ∈
{document, drawing, sheet} is derived **from the title only** by
`classify_record(Record(title=...))`. Content-level validation of the
`sheet/` folders found three defects:

1. **Prose documents sorted as sheets.** Seven files are formal
   engineering documents (page 2 = Table of Contents, page 3 =
   `1. INTRODUCTION` with narrative prose) whose *title* contains
   LIST / SCHEDULE / REGISTER, so the title-only classifier scored a
   sheet type. Examples: `HAZARD & EFFECT REGISTER`,
   `HSE ACTION TRACKING REGISTER`,
   `HAZARDOUS AREA CLASSIFICATION SCHEDULE`,
   `LIST OF PIPING SPECIALTY ITEMS`, `SPECIALITY ITEMS LIST`,
   `RELAY SETTING SCHEDULE`, `LIST OF ENGINEERING DELIVERABLES`.
2. **CRS/CTA artifacts bucketed.** Comment-Response-Sheet /
   transmittal files (names starting `CRS`/`CTA`) were placed in
   `sheet/`. These are never the actual deliverable and must be
   skipped entirely.
3. (Minor) Detector edge-cases unrelated to runtime — out of scope.

## Constraints (from the user)

- **Runtime classification stays title-only.** Opening files at sort
  time is not a viable long-term approach. File content is read **only**
  by an offline verification tool used to check the title rules.
- The content metric threshold is **not hardcoded** — it is a tunable
  parameter, calibrated against known-labelled files (it may be lower
  than the user's initial "40%" guess).
- CRS/CTA: skip the files **and** drop CRS from the taxonomy.

## Part 1 — Verification tool (offline, no runtime effect)

New tool: `src/classifier/tools/verify_sheets.py` (consistent with the
existing `learn_sheet_patterns` tool; offline, not wired into runtime).

Inputs: the documents CSV (title, `doc_type`, `customer_ref`,
`document_no`) and a file-root directory. For each row it locates the
file(s) (same matching key as the sorter), reads content, and computes a
**text ratio**.

### Text-ratio metric

`text_ratio = prose_chars / total_chars`, where:
- `total_chars` = count of non-whitespace characters extracted from the
  file.
- `prose_chars` = characters belonging to **narrative lines** — lines
  that read as sentences rather than table cells. A line is "prose" when
  it has at least `MIN_PROSE_WORDS` words (default tunable, e.g. 6) of
  mostly alphabetic tokens. Table rows (short tokens, numbers, codes)
  are not prose.

Rationale: a genuine sheet is a grid of short cell tokens → low
`text_ratio`; a document carries paragraphs → high `text_ratio`. This
matches the user's framing: processing a sheet keeps the table and
discards incidental text, but a document's prose would be lost.

Per file type:
- **PDF**: `pdfplumber`, first N pages (default all, capped for speed);
  extract text per page and apply the prose-line rule.
- **`.xlsx/.xls`**: read cell values (openpyxl/xlrd); concatenate as
  lines per row. Spreadsheets are almost entirely short cell tokens →
  low ratio → sheet.
- Unreadable/encrypted files → reported as `unknown`, never silently
  dropped.

### Threshold calibration

`THRESHOLD` is a module constant / CLI flag. Calibrate it against a
labelled anchor set (the 7 known documents must score above it; the
known genuine sheets — VALVE LIST, MTO, INSTRUMENT CABLE SCHEDULE — must
score below it). The tool prints, for the anchor set, each file's ratio
so the separating value is visible; pick the threshold in the gap and
record it. No magic 40%.

### Output

A mismatch report (CSV + printed summary):
- Columns: `docnum, title, file, title_class, text_ratio, content_class,
  mismatch`.
- `content_class` = `document` if `text_ratio >= THRESHOLD` else `sheet`.
- `mismatch` = `title_class == "sheet" and content_class == "document"`
  (the defect we care about), plus the inverse flagged separately.
- Summary: counts of agree / sheet→document mismatches /
  document→sheet mismatches, and the anchor-set ratios.

The tool **only reports**. It does not change classification or move
files.

## Part 2 — CRS/CTA exclusion

1. **Taxonomy:** remove `CRS` from `BUCKETS`, `BUCKET_TO_CLASS`,
   `TYPE_TO_BUCKET`, `BUCKET_PRIMARY_CODE` (and any enum derived from
   them) so the classifier can never assign a CRS bucket/type. Any
   existing CRS overrides/keywords are removed.
2. **Sort/routing:** in `routing/source_plan.build_plan`, skip any file
   whose name (case-insensitive, leading whitespace ignored) starts with
   `CRS` or `CTA`. Skipped files are recorded in the plan (a new
   `skipped_crs` tuple) for the report, not silently dropped.

## Part 3 — Title-rule fixes (data-driven)

Runtime stays title-only. Using the verifier's mismatch list, tighten
the rules in `type_scoring.py` / `buckets.py` so the known prose
documents stop scoring a sheet type:
- Move `REG` (registers) out of the sheet-folding bucket into Documents.
- Add negative keywords / overrides for the proven prose patterns:
  `HAZARD`, `HSE`, `HAZARDOUS AREA CLASSIFICATION`, `RELAY SETTING`,
  `LIST OF` (the "LIST OF X" narrative phrasing, distinct from "X LIST").
- Re-run the verifier; iterate until sheet→document mismatches reach ~0
  without dragging genuine sheets (VALVE LIST, MTO, cable schedules) out
  of the sheet class.

Exact rule edits are finalised against the verifier output, not guessed
up front. Each change is justified by a labelled mismatch.

## Testing

- Verifier: unit-test the text-ratio metric on small synthetic inputs (a
  prose blob → high ratio; a grid of short tokens → low ratio) and the
  prose-line classifier.
- Title rules: title-level tests asserting each known prose document
  (`HAZARD & EFFECT REGISTER`, `SPECIALITY ITEMS LIST`, `RELAY SETTING
  SCHEDULE`, `LIST OF ENGINEERING DELIVERABLES`, …) classifies as
  `document`, while genuine sheets (`VALVE LIST`, `MTO FOR PIPES AND
  FITTINGS`, `INSTRUMENT CABLE SCHEDULE`, `TIE-IN LIST`) stay `sheet`.
- CRS: a test that a `CRS …`/`CTA …` filename is skipped by `build_plan`
  and that CRS is absent from the taxonomy maps.

## Out of scope

- No runtime file inspection.
- Detector edge-cases (EARTHING MTO section-header rows; sub-5-row
  tables).
- Re-running the full sort (the user drives that separately).
