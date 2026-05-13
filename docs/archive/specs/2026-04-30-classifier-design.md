# Document Classifier — Design Spec (v2)

**Date:** 2026-04-30
**Project root:** `c:\Users\MrError\Desktop\classifier\`
**Phase 1 scope:** Produce a single CSV classifying every file under the `TO CLIENT` directory. Phase 2 (later) will use the CSV to copy and rename files into a structured output tree.

**Revision history:**
- **v1** — initial design: 9-bucket taxonomy, first-match-wins keyword chain, single-axis revision ordering, 24-column CSV.
- **v2** — splits *form* from *content bucket*; replaces first-match keyword resolution with weighted scoring; reworks revision parsing to recognise letter-rev and numeric-rev as independent axes; adds CRS as its own bucket; sibling-inherited rev for ref-less CRS/attachments; filename-keyword discipline tier; CI self-test gate against dossier; collision detection for proposed target filenames; filename normalisation pass.
- **v3** — surgical fixes from review: confidence based on max single weight (not sum); removes dead "+5 dossier-ref boost"; unifies CRS regex into a single named pattern based on empirical filename audit; sibling rev inheritance keyed on `cust_ref` not folder; `is_latest` precedence rule (numeric supersedes letter); two-pass form resolution made explicit; idempotency includes overrides; CI gate threshold separated from v2 target; missing-value semantics specified; override CSV unknown-ref behaviour specified. Schedule Rev format empirically confirmed single-axis (A-C letter or 1-12 numeric, no compounds), so `cross_axis` definition retained.
- **v4** (this version) — post-implementation review fixes: (1) Bug — `is_latest_letter` was set true on stale letter-rev files even when the group had been promoted to a numeric rev; now suppressed when any numeric exists in the group. (2) Bug — refs with zero parseable revisions had no row marked latest, silently dropping the doc from "latest of each ref" filters; now the lex-first `source_path` in such groups is marked `is_latest=true`. (3) Refinement — `revision_drift = cross_axis` was firing on 53% of files; reclassified the dominant case (schedule numeric, disk letter only) as a new `pre_issue` state — *normal* during IFA review cycles, not drift. `cross_axis` reserved for the rare genuine inversion (schedule letter, disk numeric only). (4) Keyword bank: tolerate common typos (`REQUSITION`, `EVALATUION`); broaden `\bplan\b` -> `\bplan(ning)?\b`; broaden `\bdetails\b` -> `\bdetails?\b`; add `MR FOR <X>` (Material Requisition abbrev); add `alignment sheet` alternation; add a `PROC` discipline keyword tier. (5) Audit: split fallthrough into titled (regex-tunable) vs untitled (attachments — inherently unclassifiable from filename). (6) Confidence target recalibrated from 75% high to 65% high — empirical evidence shows the 18% structural-low floor (archives + cover sheets) plus the actual title vocabulary supports ~60% high realistically.

---

## 1. Problem

A Sahil-CDS EPC project has produced ~3,900 deliverable files across ~870 transmittal submissions to the client (`TO CLIENT/`). Files are named inconsistently, contain mixed revisions, and span 10 disciplines and ~30 document type codes. There is no single source of truth that maps every file to its title, discipline, document type, and revision status.

We have three reference inputs:

1. **`4. List of DOC + Schedule (Correct doc).xls`** — the master schedule. Sheet1 has 559 documents with `PCS Doc No.`, `Discip`, `Title`, `Rev.`, `Cust Ref #`. **Authoritative for title + discipline + current revision.** Has no document-type column.
2. **`50703-EPC Dossier Index - PDF (Updated on 27-03-2014).xlsx`** (sheet `PDF`) — 256 dossier entries with `Document No.`, `Title`, `Rev.`, `Status`, `Type` (one of ~30 codes: `PID`, `PFD`, `DAS`, `DAL`, `DWG`, `REP`, `SPC`, `LST`, `CAL`, `REQ`, etc.), `VOLUME`. **Different document population than the schedule** (zero ref-number overlap), so it is used as a labelled training set for keyword inference and as a CI gate, not as a join table.
3. **`Transmittals.txt`** — a `tree` listing of `D:\...\TO CLIENT\` capturing every submission folder and file. Files inside `FROM CLIENT/` are out of scope.

## 2. Goal

Phase 1: produce **one row per physical file** under `TO CLIENT` in `output/classified_files.csv`, with columns sufficient to:

- Tell, for any file, what document it belongs to (title, discipline, content bucket, form).
- Group files into bundles so the PDF + native + CRS for one revision travel together.
- Identify the latest revision per logical document on each rev axis (letter-rev / numeric-rev), and flag schedule mismatches by direction.
- Drive a Phase 2 copy/rename script (every row carries `proposed_target_folder`, `proposed_target_filename`, and a collision flag).

Plus `output/classification_audit.txt` summarising bucket distribution, confidence breakdown, fallthrough titles, unmatched refs, and schedule docs with no files — for human iteration on the rules. **CI self-test:** the same classifier rules are run against the labelled dossier; the script fails if dossier-bucket accuracy drops below the v1 baseline of 85.5%.

## 3. Empirical baseline (measured against the real data)

| Metric | Value |
|---|---|
| Files under `TO CLIENT` | 3,902 |
| Submission folders | 869 |
| Files with extractable Cust Ref # (`\d{2}-\d{2}-\d{2}-\d{4}`) | 3,574 (92%) |
| Files **without** ref (cover sheets, attachments, .rar bundles, scans) | 328 (8%) |
| Schedule docs with ≥1 file present | 453 / 559 (81%) |
| Schedule docs with no file | 106 (19%) |
| File refs not in schedule | 29 |
| Baseline (v1) keyword classifier accuracy on dossier | 85.5% (219 / 256) |
| Target (v2) accuracy on dossier | ≥92% |
| Files with explicit `_A` / `-1` rev suffix | 856 (24%) — most files lack a parseable rev |
| `Cust Ref segment-2 → discipline` purity | >95% across all segments |

## 4. Architecture

```
[Schedule.xls]   [Dossier.xlsx]   [Transmittals.txt]
      │                │                  │
      └──────┬─────────┘                  │
             ▼                            ▼
     load_labels()                parse_tree()
   (schedule rows +              (one record per file,
    dossier-derived               relative paths under
    keyword bank +                 TO CLIENT/)
    seg2->discip map)                  │
             │                         │
             └────────┬────────────────┘
                      ▼
               normalise_filenames()        # NFKC + dash variants + whitespace
                      │
                      ▼
               enrich_files()
       ├─ extract_ref(filename)
       ├─ extract_revs(filename)            # 5-tier patterns; returns (letter_rev, numeric_rev)
       ├─ resolve_form(record)              # Drawing/Sheet/Document/Archive/CoverSheet
       ├─ score_buckets(record)             # weighted scoring across all buckets
       ├─ pick_bucket(scores, ties)         # max + tiebreaker
       ├─ derive_discipline(...)            # 5-tier chain
       ├─ assign_bundle_id(...)             # rev-aware, with sibling rev inheritance
       ├─ compute_is_latest(group)          # per-axis (letter / numeric)
       ├─ classify_revision_drift(...)      # disk_newer / schedule_newer / aligned
       ├─ build_target_path(...)
       └─ detect_target_collisions(records) # flag duplicates
                      │
                      ▼
   ┌─────────────────────────┬──────────────────────────┐
   ▼                         ▼                          ▼
output/classified_files.csv  output/classification_     output/dossier_selftest.txt
                              audit.txt                  (CI gate report)
```

Single Python file `classifier.py`, organised in three clearly-marked sections with `# REFACTOR HINT: split here` markers between them — so a future split into `core_classifier.py` + `sahil_enrichment.py` is mechanical:

- **Section A — Project-agnostic core.** Filename normalisation, ref/rev extraction, form resolution by extension, weighted bucket scoring, bundle/collision logic, output writers.
- **Section B — Project-specific enrichment.** Schedule loader, dossier loader, seg2-discipline map builder, dossier-derived keyword bank, dossier CI self-test.
- **Section C — Orchestration.** `main()` glues A + B together for this project.

## 5. Form vs content bucket (two columns, orthogonal)

### 5.1 Form (5 values)

Form = the *physical artifact type*, resolved primarily from extension and filename pattern:

| Form | Extensions | Filename signals | Notes |
|---|---|---|---|
| `Drawing` | `.dwg`, `.dgn`, plus `.pdf` when bucket ∈ {Drawings, Isometrics} | n/a | CAD/diagram artifact |
| `Sheet` | `.xlsx`, `.xls`, `.xlsm`, plus `.pdf` when bucket ∈ {Datasheets, Lists_MTOs_BOMs} | n/a | Tabular |
| `Document` | `.docx`, `.doc`, plus `.pdf` for narrative buckets | n/a | Narrative |
| `Archive` | `.rar`, `.zip` | n/a | Bundle |
| `CoverSheet` | any | filename matches `^(CTA-\|C-A-ED-SA-)` and **does not** also contain a Cust Ref # | Transmittal cover |

Form resolution runs in **two passes**:

- **Pass 1 (pre-scoring, structural).** Set form to `Archive` (`.rar`/`.zip`), `CoverSheet` (`COVER_RE` matches and no ref present), or — informally — leave PDFs/Office docs unset. Files pinned in pass 1 also have their bucket pinned (see §6.2 step 2) and skip scoring entirely.
- **Pass 2 (post-scoring, content-driven).** For everything not pinned in pass 1, derive form from extension *and* the just-decided bucket:
  - `.dwg`, `.dgn` → `Drawing`
  - `.xlsx`, `.xls`, `.xlsm` → `Sheet`
  - `.docx`, `.doc` → `Document`
  - `.pdf` → `Drawing` if bucket ∈ {`Drawings`, `Isometrics`}; `Sheet` if bucket ∈ {`Datasheets`, `Lists_MTOs_BOMs`}; else `Document`
  - anything else → `Document`

### 5.2 Content bucket (10 buckets)

| Bucket | Dossier Type codes mapped to it | Title-keyword regex set (with weight) |
|---|---|---|
| `Drawings` | `PID`, `PFD`, `PSF`, `DGA`, `DSD`, `DWG`, `DAL`, `DWD`, `DSL`, `DBD`, `DCE`, `DHZ`, `DPP`, `MSD` | `P&ID`(5), `PIPING (AND\|&) INSTRUMENT`(5), `FLOW DIAGRAM`(4), `MATERIAL SELECTION DIAGRAM`(5), `LAYOUT`(2), `ARRANGEMENT`(3), `PLOT PLAN`(4), `SINGLE LINE`(4), `BLOCK DIAGRAM`(4), `CAUSE (AND\|&) EFFECT`(5), `WIRING DIAGRAM`(4), `LOOP /? SEGMENT`(4), `ARCHITECTURE`(3), `SAFEGUARDING`(4), `HAZARDOUS AREA`(3), `INTERCONNECTION DIAGRAM`(4), `INSTALLATION DRAWING`(3), `HOOK UP`(3), `JUNCTION BOX`(3), `STRUCTURAL DETAIL`(3), `FOUNDATION`(2), `PIPE SUPPORT`(2), `ELEVATION`(2), `\bDETAILS\b`(1) |
| `Isometrics` | (none in dossier) | `ISOMETRIC`(5), `\bISO\b`(2) |
| `Datasheets` | `DAS` | `DATA ?SHEET`(5), `PROCESS DATA`(4) |
| `Specifications` | `SPC`, `STD` | `SPECIFICATION`(5), `STANDARDS?\b`(3), `GENERAL NOTES`(3) |
| `Calculations` | `CAL` | `CALCULATION`(5), `CACULATION`(5), `SIZING`(3), `WALL THICKNESS`(4), `STRESS ANALYSIS`(4), `CALC NOTE`(4) |
| `Reports` | `REP`, `BOD`, `SOW` | `\bREPORT\b`(5), `DESIGN BASIS`(5), `STUDY`(3), `\bREVIEW\b`(2), `CLOSE OUT`(4), `TOPOGRAPH`(4), `SCOPE OF WORK`(4), `HAZID`(5), `HAZOP`(5), `PHSER`(4), `PROCESS .*DESCRIPTION`(3) |
| `Lists_MTOs_BOMs` | `LST`, `MTO`, `BOM`, `IDX`, `REG`, `SCH` | `\bMTO\b`(5), `BILL OF QUANTITIES`(5), `BILL OF MATERIAL`(5), `\bLIST\b`(3), `\bSCHEDULE\b`(2), `EQUIPMENT LIST`(5), `LINE LIST`(5), `\bINDEX\b`(3), `REGISTER`(3), `TIE-?IN`(4), `I/O LIST`(5), `LOAD LIST`(4), `CONSUMPTION SUMMARY`(4) |
| `Procedures_Plans` | `PRO`, `PLN`, `PHL` | `PROCEDURE`(5), `\bPLAN\b`(3), `PHILOSOPHY`(5), `EXECUTION`(3), `CHANGE OVER`(4), `WORK BREAKDOWN`(4), `INVOICING`(4), `METHOD STATEMENT`(5), `LOOK AHEAD`(4), `\bTRA-`(4) |
| `CRS` | (none) | filename matches `CRS_RE` (see §6.1a). Pinned in §6.2 step 2 — bypasses title scoring entirely. |
| `Documents` | `REQ` + everything not mapped above | (default fallback when score=0) |

CRS is now a peer bucket. It is **not** "inherit parent's bucket"; it stands on its own. Audit counts will reflect actual CRS volume rather than silently inflating other buckets.

## 6. Resolution chains

### 6.1 Filename normalisation (preprocessing)

Before any regex runs, normalise filenames:

1. Strip leading/trailing whitespace (artifact of tree parsing).
2. Unicode NFKC (collapses width/compatibility variants).
3. Replace dash variants (`–`, `—`, `−`, `‒`) with ASCII `-`.
4. Replace non-breaking spaces (` `) with regular space.
5. Collapse runs of whitespace to a single space.
6. Lowercase a copy for keyword matching; keep the original for output.

### 6.1a Named regexes (defined once, referenced everywhere)

Empirically tuned against the real `TO CLIENT` corpus (576 CRS-related filenames audited; chosen pattern catches 564 = 98%):

```python
REF_RE = r'(\d{2}-\d{2}-\d{2}-\d{4})'

CRS_RE = (
    r'(?ix)('
    r'  ^crs[\s_\-]                  '
    r'| ^crs(?=\d{2}-)               '
    r'| ^crsheet[\s_\-]              '
    r'| ^comment[\s_]response        '
    r'| ^copy[\s_]of[\s_]comment     '
    r'| [\s_\-]crs(?=[\s_\-]|\.)     '
    r')'
)

COVER_RE = r'(?i)^(cta|c-a-ed-sa)'
```

Single source of truth: `is_crs` (CSV column 6), the CRS bucket pin in §6.2 step 2, and any audit prose all reference `CRS_RE`. The 12 unmatched cases (2%) are atypical filename shapes like `CRS16-99-91-2650_A.xlsx` (no separator and the continuation isn't `\d{2}-`); these are flagged in audit "ambiguous CRS candidates" for manual triage.

Without this, `16–01–19–2602` (em-dash) and `16-01-19-2602` (ASCII) won't match.

### 6.2 Bucket resolution (weighted scoring, not first-match)

For each file:

1. **Override pass.** If `cust_ref` is in `overrides/ref_to_bucket.csv`, use that bucket. `bucket_source = override`, confidence `high`. Done.
2. **Form pin.** If the file is a CRS (filename match), bucket = `CRS`. If form = `Archive`, bucket = `Documents`, `bucket_source = archive`, confidence `low`. Done. If form = `CoverSheet`, bucket = `Documents`, `bucket_source = cover_sheet`. Done.
3. **Score every bucket.** Use the title (schedule preferred, dossier fallback) plus the filename. For each bucket, two numbers are computed (note: there is *no* "+5 boost for dossier-Type match" — the dossier and the disk-file refs share zero overlap, so such a boost would be dead code):
   - `score_sum` = sum of weights of all keyword regex hits (used for picking the winner and for tiebreaking).
   - `score_top` = the **highest single weight** that fired in that bucket (used for confidence). A title with one weight-5 hit is just as confident as one with three weight-5 hits.
4. **Pick winner.** Highest `score_sum` wins. Confidence is set from the winner's `score_top`:
   - `high` if any weight-5 keyword fired (`score_top = 5`).
   - `medium` if `score_top ∈ {3, 4}`.
   - `low` if `score_top ∈ {1, 2}` or score_sum = 0 (fallback to `Documents`).
5. **Record runner-up.** Always log the second-highest bucket's name and its `score_sum` in `runner_up_bucket` / `runner_up_score`. Tie-break: lexicographic on bucket name.

### 6.3 Discipline resolution (first match wins, 5 tiers)

1. Schedule's `Discip` column when ref matches schedule.
2. `seg2 → discipline` lookup table built from the schedule (>95% pure across segments). `seg2` is the third hyphen-segment of the Cust Ref #; e.g. `16-01-23-2659` → `seg2 = 23` → `PIPNG`.
3. **Filename/title keyword tier.** `STRESS|HYDRAULIC|PIPING` → `PIPNG`; `\bSLD\b|HV\b|LV\b|EARTH|SUBSTATION` → `ELEC`; `FOUNDATION|STRUCTURAL|CIVIL|REBAR` → `CIVIL`; `HAZOP|HAZID|HSE|FIRE|F&G|SAFETY` → `HSE`; `INSTRUMENT|DCS|ESD|F&G|JUNCTION BOX|LOOP` → `INST`; `PUMP|VESSEL|EXCHANGER|MECHANICAL` → `MECH`; `PROCEDURE|PLAN|SCHEDULE|WBS|INVOICE` → `PROJECTS` or `ENGG MGMT`.
4. Submission folder's majority discipline if siblings have one **and** the submission spans ≤2 disciplines (otherwise unreliable — saw submission `0099` with 19 different P&IDs from multiple disciplines).
5. `UNK`.

## 7. Revision parsing (two independent axes)

In WorleyParsons / ADCO practice, letter and numeric revisions are **independent dimensions**, not points on one axis:

- **Letter rev** = revision of the *content* during review cycle (A, B, C, D as comments come back).
- **Numeric rev** = formal *issue* counter (1 = first issued for design / construction, 2 = re-issued).
- A `Rev 1` and a `Rev B` of the same doc are not directly comparable. Often `Rev B` is promoted to `Rev 1` at IFD/IFC.

The parser extracts **both** if present, separately. CSV columns: `letter_rev` and `numeric_rev`.

### 7.1 Extraction tiers (run for letter and numeric independently)

1. `<ref>[-_ ]([A-Z])(?:[ _.-]\|$)` → letter rev (e.g. `…-2602-A.pdf`)
2. `<ref>[-_ ](\d{1,2})(?:[ _.-]\|$)` → numeric rev (e.g. `…-2606_1.pdf`)
3. `(?i)REV[._ \-]?([A-Z])` anywhere in filename → letter rev (e.g. `…_Rev.A.pdf`, `… REV-A.xlsx`, `…IFA-D.xlsx` via the `IF[ARDCU][- ]?([A-Z])` alternate). Empirically, `REV-A` is the dominant CRS rev form (136 hits in the corpus), so the hyphen separator is required.
4. `(?i)REV[._ \-]?(\d{1,2})` anywhere in filename → numeric rev (e.g. `… REV-2.xlsx`, `…IFC-2.xlsx`).
5. **Sibling inheritance.** If neither letter nor numeric rev is found, look at sibling files (same submission folder + subfolder) **with the same `cust_ref`** as this file. Among those siblings, if any have a parseable rev, inherit the highest under the §7.2 ordering. If no sibling shares the ref, no inheritance — the file keeps both revs empty. Records the inheritance in `notes` ("rev inherited from sibling `<filename>`").

If after all five tiers neither is found: both `letter_rev` and `numeric_rev` empty. The bundle id falls back to `<ref>__R0`.

### 7.2 `is_latest` (per axis, per ref)

Two booleans, computed independently:

- `is_latest_letter`: true for the file with the highest letter_rev within its `cust_ref` group (lexicographic order, A < B < … < Z). False if no letter_rev or another sibling has a higher one.
- `is_latest_numeric`: true for the file with the highest numeric_rev within its `cust_ref` group (numeric order). False if no numeric_rev or another sibling has a higher one.

A single derived column `is_latest` is also written, computed with **numeric-supersedes-letter** precedence:

- If any file in the `cust_ref` group has a non-empty `numeric_rev`, then `is_latest = is_latest_numeric`.
- Otherwise, `is_latest = is_latest_letter`.

Rationale: at IFD/IFC the letter-rev sequence is closed and a numeric rev is opened. A `Rev 1` succeeds `Rev B`. A naive `letter OR numeric` would mark both as latest and double-count downstream filters.

### 7.3 `revision_drift` (v4 — `pre_issue` split out from `cross_axis`)

Compare the file's revs against the schedule's `Rev.` value:

- `aligned` — the relevant axis matches.
- `disk_newer` — disk has a higher rev than the schedule on the same axis (informational; the schedule is just behind).
- `schedule_newer` — schedule has a higher rev on its axis than any disk file. **Actionable** — likely missing files.
- `pre_issue` — schedule says numeric (post-issue, e.g. `Rev 1`) but disk has only a letter rev. This is the **normal** state during the IFA review cycle: the file on disk is the active letter revision being commented on, while the schedule has already recorded the promoted numeric issue. Informational, not actionable. Empirically dominates this corpus (~53% of files).
- `cross_axis` — genuine inversion: schedule says letter, disk has only numeric. Rare; means the file was promoted but the schedule wasn't updated. **Actionable**.
- `unknown` — ref not in schedule, or both axes empty.

The audit ranks `schedule_newer` and `cross_axis` as actionable; `disk_newer` and `pre_issue` are informational.

### 7.2 — addendum (v4 fixes)

- `is_latest_letter` is **suppressed (set False on every row)** within a group when any row in that group has a `numeric_rev`. Rationale: numeric supersedes letter; reporting `is_latest_letter=true` on a stale Rev C file would make a downstream filter pick the wrong revision when the doc has been promoted to Rev 1.
- Within a `cust_ref` group where **no** row has any parseable rev (neither letter nor numeric), the lexicographically-first row by `source_path` is marked `is_latest=true`. This prevents docs with no rev annotation in any of their files from being silently dropped by "give me the latest of each ref" filters.

## 8. Bundling

`bundle_id` algorithm:

1. If file has a `cust_ref`:
   - If both letter_rev and numeric_rev present → `<ref>__N<numeric>L<letter>` (e.g. `16-01-19-2602__N1LA`).
   - Else if numeric_rev only → `<ref>__N<numeric>` (e.g. `…__N2`).
   - Else if letter_rev only → `<ref>__L<letter>` (e.g. `…__LB`).
   - Else → `<ref>__R0`.
2. If no ref → `unmatched__<submission_folder>`.

Sibling-inheritance (section 7.1 tier 5) means CRS files now correctly land in the same bundle as their parent doc/native pair. Without it, a CRS xlsx with no rev in its name would have been split into a `__R0` bundle and broken apart from `…__LA` siblings.

## 9. CSV schema (`output/classified_files.csv`)

33 columns total (32 structured + free-text `notes`). New in v2 are marked **(new)**.

| # | Column | Description |
|---|---|---|
| 1 | `source_path` | Path relative to `TO CLIENT/`, e.g. `C-A-ED-SA-15760.01-0068/16-01-39-2602-B.pdf` |
| 2 | `source_filename` | Original filename |
| 3 | `submission_folder` | Top-level transmittal folder |
| 4 | `subfolder` | Nested folder, if any |
| 5 | `cust_ref` | Extracted `\d{2}-\d{2}-\d{2}-\d{4}` or empty |
| 6 | `is_crs` | true if filename starts with `CRS_` or contains `Comment Response` |
| 7 | `is_transmittal_cover` | matches `^(CTA\|C-A-ED-SA)` and lacks a ref |
| 8 | `is_archive` | extension is `.rar` or `.zip` |
| 9 | `letter_rev` | **(new)** Parsed letter rev (A/B/C/…) or empty |
| 10 | `numeric_rev` | **(new)** Parsed numeric rev (1/2/12/…) or empty |
| 11 | `extension` | Lowercase, with leading dot |
| 12 | `pcs_doc_no` | From schedule (if matched) |
| 13 | `title` | Schedule Title preferred; dossier Title fallback; empty otherwise |
| 14 | `discipline` | Resolved via 5-step chain |
| 15 | `schedule_rev` | Schedule's `Rev.` column for this ref |
| 16 | `type_code` | Dossier Type if matched, else bucket's primary code |
| 17 | `form` | **(new)** `Drawing` / `Sheet` / `Document` / `Archive` / `CoverSheet` |
| 18 | `type_bucket` | One of the 10 buckets |
| 19 | `bucket_score` | **(new)** Total weight of keyword hits for the winning bucket |
| 20 | `runner_up_bucket` | **(new)** Second-place bucket |
| 21 | `runner_up_score` | **(new)** Second-place score (gap = bucket_score − runner_up_score; small gap = ambiguous) |
| 22 | `bucket_source` | `override` / `schedule_kw` / `dossier_type` / `crs_pin` / `archive` / `cover_sheet` / `weighted` / `fallback` |
| 23 | `bucket_confidence` | `high` (score≥5) / `medium` (1≤score<5) / `low` (score=0 or special-case) |
| 24 | `bundle_id` | See section 8 |
| 25 | `is_latest_letter` | **(new)** true within ref group on letter axis |
| 26 | `is_latest_numeric` | **(new)** true within ref group on numeric axis |
| 27 | `is_latest` | OR of the two above (ergonomic) |
| 28 | `revision_drift` | `aligned` / `disk_newer` / `schedule_newer` / `pre_issue` / `cross_axis` / `unknown` (v4 added `pre_issue`) |
| 29 | `match_status` | `matched` / `ref_in_schedule_only` / `ref_in_dossier_only` / `ref_unknown` / `crs_orphan` / `cover_sheet` / `archive` / `attachment` |
| 30 | `proposed_target_folder` | `<form>/<type_bucket>/<discipline>/` |
| 31 | `proposed_target_filename` | `<cust_ref>_<numericLetter>_<TYPE>_<short_title><ext>` |
| 32 | `target_collision` | **(new)** true if another row produces the same `proposed_target_folder + proposed_target_filename`; the colliding row's `bundle_id` is recorded in `notes` |
| 33 | `notes` | Free text — diagnostics, sibling-inherited revs, collision peer, etc. |


### Proposed filename template

`<cust_ref>_<rev_token>_<TYPE>_<short_title><ext>`

- `cust_ref`: `16-01-19-2602`
- `rev_token`: combined rev — `N1LA` if both present, `N1` / `LA` if only one, `R0` if none
- `TYPE`: dossier `Type` when known, else bucket's primary code
- `short_title`: schedule Title, uppercased, alphanumerics + underscores, truncated to 60 chars
- Example: `16-01-19-2602_LA_DAS_VALVE_LIST.pdf`

For unmatched files: `<submission_folder>__<original_filename>`.

When `target_collision = true`, Phase 2 will append `__<submission_folder>` as a disambiguator. This is decided in Phase 2 design; Phase 1 just flags.

### Missing-value semantics

CSV cells use the **empty string** for "not applicable" — never `null`, `None`, `NaN`, or `N/A`. Specifically: `pcs_doc_no`, `title`, `discipline`, `schedule_rev`, `letter_rev`, `numeric_rev`, `runner_up_bucket`, `notes` may all be empty. `discipline` additionally uses the literal `UNK` when no resolution tier fired (see §6.3 step 5). Boolean columns (`is_crs`, `is_transmittal_cover`, `is_archive`, `is_latest_*`, `revision_drift` is an enum, `target_collision`) are always `true` or `false`, never blank.

## 10. Audit output (`output/classification_audit.txt`)

Plain-text report:

1. **Counts** — total files; per `match_status`; per `bucket_confidence`; per `bucket_source`; per `form`.
2. **Bucket × discipline matrix** — file count per (`type_bucket`, `discipline`).
3. **Schedule coverage** — schedule docs with files (per discipline); list of 106 (or current count) docs with no file.
4. **Refs not in schedule** — file refs that don't match schedule.
5. **Fallthrough titles** — rows with `bucket_source = fallback` (score = 0). These are the rules-improvement candidates.
6. **Ambiguous classifications** — rows where `bucket_score − runner_up_score ≤ 1`. Worth a manual look.
7. **Revision drift** — `schedule_newer` and `cross_axis` listed first (actionable); `disk_newer` and `aligned` summarised by count.
8. **Multi-discipline submissions** — submission folders containing files from >2 disciplines (where the folder-majority fallback was disabled).
9. **Target collisions** — list of (target_path, contributing_bundles).
10. **Override hits** — count of rows resolved via `overrides/ref_to_bucket.csv`.

## 11. CI self-test (`output/dossier_selftest.txt`)

Run the same classifier against the 256 labelled dossier rows. Each row has a known `Type` → bucket. Compute:

- Accuracy: `correct / total`.
- Per-bucket confusion matrix.
- List of mismatches (Type, expected bucket, predicted bucket, title).

**Gate:** the gate threshold and the v3 target are deliberately separated, in two phases:

- **Initial gate** (until first real run completes): **85.5%** (the v1 baseline). This unblocks the first run without a hand-tuned target.
- **Post-first-run gate** (locked in immediately after the first run): set to `(measured_v3_accuracy − 2pp)`. The −2pp leaves room for legitimate keyword changes that have small local regressions while still catching real degradation.
- **v3 target** (acceptance criterion §14): ≥92%.

If accuracy falls below the active gate, `classifier.py` exits non-zero.

A `--no-selftest` flag is available for one-off ad-hoc runs.

## 12. Out of scope (Phase 1)

- No file copying. The `proposed_target_folder` / `proposed_target_filename` columns are for Phase 2.
- No archive (`.rar` / `.zip`) extraction.
- No PDF/DOCX content inspection — classification is filename + title metadata only.
- No `FROM CLIENT` processing.
- No deduplication by content hash. Only structural collision detection (same target path).

## 13. Tech stack

- Python 3.13 in `.venv/`
- `pandas`, `openpyxl`, `xlrd`
- Stdlib `re`, `pathlib`, `csv`, `collections`, `unicodedata` (for NFKC).

Single file: `classifier.py`, sectioned A/B/C as in section 4.

## 14. Acceptance criteria (Phase 1)

1. `classifier.py` runs to completion against the three real input files in **<15 seconds** and produces the three output files.
2. CSV has exactly one row per file in the parsed `TO CLIENT` tree (3,902 ± parse-noise of <5 rows).
3. `cust_ref` populated on ≥90% of rows.
4. `discipline` populated (non-`UNK`) on ≥95% of rows (was 90% in v1; tier 3.5 should bump it).
5. `bucket_confidence = high` on ≥58% of rows; `medium` on ≥15%; `low` on ≤27%. The `low` total decomposes structurally:
   - **Structural floor (~18%, unimprovable)**: archives (`.rar`/`.zip`) and cover sheets (CTA-/C-A-ED-SA-) are pinned to low confidence by design — there is no title to classify.
   - **Untitled-attachment floor (~3%, would need parent inheritance)**: `Appendix-N.pdf`, `Attachment-N.pdf`, `Scan100.PDF`, etc. — files with no ref and no title. These would only become improvable with a parent-submission inheritance pass (deferred — see §15).
   - **Regex-tunable portion (~6%)**: titled rows that hit only weight-1 or weight-2 keywords, or no keywords at all. These are the rows that can move to medium/high by editing `KEYWORD_RULES` in `config.py`.

   So future readers know: chasing `low` below ~21% requires implementing parent inheritance for untitled attachments; below ~18% is impossible without changing what counts as a "classifiable" row.
6. **CI gate:** dossier-selftest accuracy ≥85.5% (v1 baseline). Target ≥92% with v2 changes.
7. Audit lists ≤120 fallthrough titles (down from v1's expected ~150).
8. Idempotent: rerun on unchanged inputs **including `overrides/ref_to_bucket.csv`** produces byte-identical CSV (modulo timestamps in audit header).
9. Adding N rows to `overrides/ref_to_bucket.csv` whose refs all exist in the tree reduces `low`-confidence count by ≥N.
10. Override rows referencing refs **not** present in the tree are logged in the audit's "override hits" section as `override defined for unknown ref <REF> — no effect`. They do not cause the script to exit non-zero.

## 15. Open questions / future work

- **Phase 2 (copy/rename):** designed once user provides the absolute path of `TO CLIENT/` and the desired output root. Phase 2 will use `target_collision` flags to decide rename strategy.

  **DECISION GATE (must resolve before any Phase 2 coding starts):** the current Phase 1 run shows 869 rows (22%) with `target_collision=true`. Almost all are identical content (same `cust_ref`, same `letter_rev`/`numeric_rev`, same proposed filename) appearing in multiple submission folders because the same deliverable was re-submitted in multiple transmittals. The strategy fork:

  - **Option A — Hash dedup.** Phase 2 hashes file content; identical hashes produce one output file. The audit records which submissions contributed.
  - **Option B — Submission-suffix.** Phase 2 appends `__<submission_folder>` to the proposed filename whenever `target_collision=true`. Output tree contains all 3-4 copies of duplicated docs.
  - **Option C — Latest-only.** Phase 2 only copies rows where `is_latest=true` (482 rows, one per ref). Drops historical revisions. Smallest output tree.

  These shape the entire output structure differently (Option A: ~2,800 unique files; Option B: ~3,900; Option C: 482). Pick before coding, not during.
- **Reading inside `.rar` / `.zip`:** out of scope unless audit shows significant deliverable volume only inside archives.
- **OCR / content-based classification:** not needed at 92%+ filename accuracy. Revisit only if audit shows the keyword approach plateauing.
- **Refactor split** into `core_classifier.py` + `sahil_enrichment.py`: deferred until a second project is in scope. Section markers in `classifier.py` make the split mechanical.
