# Sheet-folder validation report — 2026-06-06

**What was checked:** every file the sorter placed under a `sheet/` folder in
`D:/Sahil_input/{feed,deliverable,planned}/sheet/`, by reading the actual file
content (not just the title).

**Method:**
- Spreadsheets (`.xlsx/.xls`): opened; a real data table (header + ≥5 data rows
  across the key columns, any worksheet) = genuine sheet.
- PDFs: extracted text from the first 6 pages. A `TABLE OF CONTENTS` **plus** an
  `INTRODUCTION` section = a prose **document** (narrative report), regardless of
  the title keyword. No such narrative + tabular body = genuine sheet.
- Files whose name starts with `CRS`/`CTA` = comment-response / transmittal
  artifacts → must be **skipped** entirely (per user rule).

## Headline

| Verdict | Count | Meaning |
|---|---|---|
| Genuine sheet | ~37 | Real data table (mostly `.xlsx`, plus tabular PDFs) |
| **Document mis-sorted as sheet** | **7** | Prose doc (ToC + Introduction) with a list/schedule/register *title* |
| **CRS/CTA to skip** | **5** | Should never be bucketed at all |
| Detector edge-case | 2 | `.xls/.xlsx` whose real table wasn't detected (1 truly tiny, 1 false-negative) |

## Documents mis-sorted as sheets (the real bug)

These are formal engineering documents — page 2 is a Table of Contents, page 3
is `1. INTRODUCTION` with narrative prose. The title contains LIST / SCHEDULE /
REGISTER, so the title-only classifier called them sheets.

| Doc no | Type | Title | Source | Why it's a document |
|---|---|---|---|---|
| 16-99-91-1128 | REP | HAZARD & EFFECT REGISTER | feed | ToC + Intro, 23 pp |
| 16-99-91-1129 | REG | HSE ACTION TRACKING REGISTER | feed | ToC + Intro, 15 pp |
| 16-01-01-1136 | LST | HAZARDOUS AREA CLASSIFICATION SCHEDULE | feed | ToC + Intro, 13 pp |
| 16-01-17-0991 | LST | LIST OF PIPING SPECIALTY ITEMS | feed | ToC + Intro, 9 pp |
| 16-01-23-2647 | LST | SPECIALITY ITEMS LIST | deliverable | ToC + Intro, 9 pp |
| 16-01-67-2604 | SCH | RELAY SETTING SCHEDULE SUBSTATION 4 | deliverable | ToC + Intro, 9 pp |
| 16-99-91-2628 | LST | LIST OF ENGINEERING DELIVERABLES | deliverable | partial narrative |

Observations:
- HSE/safety deliverables (`HAZARD…`, `HSE…`, `HAZARDOUS AREA…`) are narrative
  reports even when titled REGISTER/SCHEDULE.
- `REG` (registers) and `REP` (reports) are document types, not tabular sheets
  (Phase-1 evidence also showed REG = 0/3 tables).
- "LIST OF X" phrasing (LIST OF PIPING SPECIALTY ITEMS, LIST OF ENGINEERING
  DELIVERABLES) tends to be a narrative document; "X LIST" (VALVE LIST, TIE-IN
  LIST, I/O LIST) tends to be a real data sheet.
- The single most reliable separator is **content**: ToC + Introduction ⇒
  document. Title keywords alone cannot tell `VALVE LIST` (sheet) from
  `SPECIALITY ITEMS LIST` (document).

## CRS/CTA files found in sheet folders (must skip)

| File | Underlying type |
|---|---|
| CRS 16-01-89-2603 REV-B.xlsx | REG |
| CRS-16-01-89-2604 REV-A.xlsx | REG |
| CRS_16-01-55-2601 REV-B.xlsx | LST |
| CRS_16-01-63-2602 REV-A.xlsx | SCH |
| CRS_16-01-84-2602 REV-C.xlsx | SCH |

## Detector edge-cases (low priority)

| Doc no | Type | Note |
|---|---|---|
| 16-01-63-2607 | MTO | Real EARTHING MTO; missed because of interspersed section-header rows |
| 16-01-26-2602 | SCH | Genuinely tiny (2 data rows) — below the ≥5 threshold |

## Root cause

The runtime classifier is **title-only** and cannot open files, so a prose
document titled `… REGISTER/SCHEDULE/LIST` scores a sheet type and is sorted as a
sheet. The fix has to look at content — which is feasible because the **sort step
has the actual files**.

## Options to fix (for decision)

1. **Content gate at sort time (recommended):** when the sorter is about to place
   a file in `sheet/`, open it and confirm it's a genuine table-sheet (spreadsheet
   with a real table; PDF with no ToC+Introduction narrative). If it fails, route
   to `document/`. Robust; uses the files already on hand.
2. **Tighten title rules:** drop `REG`/`REP` from the Sheets set and add negative
   keywords (HAZARD, HSE, HAZARDOUS AREA, RELAY SETTING, "LIST OF"). Cheaper, but
   title-only — will still miss novel prose docs with sheet-like titles.
3. **Both:** tighten the obvious title rules *and* add the content gate as a
   backstop.

CRS/CTA skip is orthogonal and should be applied regardless.
