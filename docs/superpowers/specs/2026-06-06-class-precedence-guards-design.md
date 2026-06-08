# Class-precedence guards: drawing-title, index→sheet, prefer-sheet

**Date:** 2026-06-06
**Status:** Approved rule set — detail under review

## Problem

Content-validation (2 files per type) confirmed most types classify
correctly, but several genuine sheets/drawings fall through to the wrong
class because of the title scorer's confidence gate and keyword
precedence:

| Title | Now | Should be | Cause |
|---|---|---|---|
| `INSTRUMENT INDEX` | document | sheet | IDX single-phrase score (1.62) < high-confidence floor |
| `LINE LIST` | document | sheet | LST 3.50 vs DSL 2.79 — margin 0.71 < 1.0 → low |
| `ISO INDEX` / `ISOMETRIC INDEX` | document / drawing | sheet | low IDX, or ISO override wins over INDEX |
| `STANDARD DRAWING REBAR…` | document | drawing | STD → Specifications, but it is a *drawing* |

## Rules (user-approved)

Implement as **ordered, class-level guards** in `normalize_doc_type`
(extending the existing `prose_guard` pattern), so the many already-
correct types are untouched. Order matters:

1. **Prose-document guard** (existing) — `document` for narrative titles
   (HSE / HAZARDOUS AREA / RELAY SETTING / LIST OF …).
2. **Drawing-title rule** (new) — if the canonicalized title contains a
   drawing marker (`DRAWING` or `SKETCH`), classify as **drawing**.
   "If the title says drawing, it is a drawing." A specific drawing type
   may still be picked for the `type` column, but the class is `drawing`;
   when no specific drawing type matches, the type is `DWG`. Drawing wins
   over INDEX (so `MODEL INDEX DRAWING` and `STANDARD DRAWING MEMBER LIST`
   are drawings).
3. **Index rule** (new) — if the title contains `INDEX` (and rule 2 did
   not fire), classify as **sheet** (e.g. `INSTRUMENT INDEX`,
   `ISO INDEX`, `ISOMETRIC INDEX`).
4. **Type fold** (existing) — for a *high-confidence* picked type, fold
   `type → bucket → class` (drawing / sheet / document) as today.
5. **Prefer-sheet on borderline** (new) — if no high-confidence result,
   but the top picked type (at *low* confidence) folds to the `Sheets`
   bucket, return **sheet** instead of the `document` default. The user
   will add a content-parse fallback in the next phase that demotes a
   non-parseable "sheet" to document, so leaning sheet here is safe.
   Low-confidence non-sheet types still default to `document`.

## Why class-level guards (not scorer retuning)

Lowering the global `SINGLE_PHRASE_FLOOR` / `MIN_MARGIN` in the type
scorer would shift every type's behavior and risk regressing the ~20
types that are already correct. The four problems are specific and
title-pattern-driven, so localized guards are safer and testable. They
also encode the user's explicit precedence (drawing > index > scored
type), which a single confidence knob cannot express.

## Components

- `src/classifier/config/drawing_markers.py` — `DRAWING_TITLE_MARKERS`
  (`("DRAWING",)`, `("SKETCH",)`) and `INDEX_MARKERS` (`("INDEX",)`),
  matched as contiguous token subsequences against the canonicalized
  title. Kept as data, like `prose_guard.PROSE_DOC_PHRASES`.
- `src/classifier/core/classify.py` — `normalize_doc_type` gains, in
  order: the drawing-title guard (returns `"drawing"`), the index guard
  (returns `"sheet"`), and the borderline prefer-sheet branch after the
  existing high-confidence fold. Helper `_title_has(title, markers)`
  reuses `canonicalize_title` + `_phrase_matches`.

Pseudocode for the revised `normalize_doc_type` body (after the
existing-value alias block):
```
if _is_prose_document(title):            # rule 1 (existing)
    return "document", "prose_guard"
if _title_has(title, DRAWING_TITLE_MARKERS):   # rule 2
    return "drawing", "drawing_title"
if _title_has(title, INDEX_MARKERS):           # rule 3
    return "sheet", "index"
pick = pick_type_with_overrides(title)
bucket = TYPE_TO_BUCKET.get(pick["type"])
if pick["confidence"] == "high" and bucket is not None:   # rule 4
    return doc_type_for_bucket(bucket), <reason>
if bucket is not None and BUCKET_TO_CLASS.get(bucket) == "Sheets":  # rule 5
    return "sheet", "prefer_sheet"
return "document", "defaulted"
```
(`pick_type` returns the top `type` even at `low` confidence, so rule 5
can read `pick["type"]`; it is `""` only when nothing scored above
`MIN_SCORE`.)

## Edge cases (verified in `documents_updated.csv`)

- `STANDARD DRAWING MEMBER LIST` → drawing (rule 2 over the LIST signal) —
  intended; it is a standard drawing.
- `MODEL INDEX DRAWING` → drawing (rule 2 over rule 3) — matches the
  existing Phase-2 behavior.
- `PIPING ISOMETRICS FOR SAHIL CDS` → drawing (no INDEX/DRAWING marker;
  ISO type) — correct: plain isometrics are drawings. Only explicit
  `… INDEX` isometric titles become sheets. (Title-based cannot tell a
  text-heavy isometric index file from the drawings when the title lacks
  "INDEX"; that residue is accepted.)
- No `DRAWING LIST` / `DRAWING REGISTER` sheet titles exist, so rule 2
  has no false positives in the data.

## Testing

- Drawing-title: `STANDARD DRAWING REBAR ARRANGEMENT`,
  `STANDARD DRAWING MEMBER LIST` → drawing; `MODEL INDEX DRAWING` →
  drawing.
- Index: `INSTRUMENT INDEX`, `ISO INDEX`, `ISOMETRIC INDEX` → sheet.
- Prefer-sheet: `LINE LIST` → sheet; a low-confidence IDX title → sheet.
- Regression: genuine drawings (`PIPING & INSTRUMENT DIAGRAM`,
  `PLOT PLAN`), documents (`CABLE SIZING CALCULATION`,
  `MATERIAL REQUISITION`, `SPECIFICATION FOR …`), and existing sheets
  (`VALVE LIST`, `MTO FOR PIPES AND FITTINGS`) keep their class.
- Prose guard still wins over the new rules (`HAZARDOUS AREA
  CLASSIFICATION SCHEDULE` → document; `RELAY SETTING SCHEDULE` →
  document).

## Out of scope

- No runtime file inspection (title-only).
- No change to the learned type scorer's weights or thresholds.
- The next-phase content-parse fallback (demote non-parseable sheets to
  document) is separate work.
