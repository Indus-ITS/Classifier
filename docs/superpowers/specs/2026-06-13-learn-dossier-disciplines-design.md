# Learn Disciplines & Type Fallback from Dossiers — Design

**Date:** 2026-06-13
**Status:** Approved for planning
**Branch:** feat/sort-files-dedup-related-xlsx (or a fresh branch)

## Problem

On a fresh/blank dataset the classifier leaves **170+ documents with a null
`discipline_id`** — roughly half the corpus. Root cause:
[discipline_keywords.py](../../../src/classifier/config/discipline_keywords.py)
holds scoring rules for only **5 discipline ids (1, 4, 7, 10, 13)**, and four of
those five are keyed to the **wrong id** relative to the authoritative taxonomy
in [input/disciplines.csv](../../../input/disciplines.csv). Any title whose true
discipline has no rules cannot be scored, so it is null by construction. Type
classification, by contrast, is rich (~30 codes) and nearly every document has a
type — that signal is currently wasted for discipline recovery (it only adds a
+2 bonus, never acts as a fallback).

The `learn/` directory contains two curated **EPC/FEED dossiers** that label
titles by discipline (and, for the EPC dossier, by type). They are high-quality
ground truth for re-deriving the keyword buckets and a type→discipline map.

## Ground truth: the dossiers

- **EPC Dossier** — `learn/50703-EPC Dossier Index - PDF (Updated on 27-03-2014).xlsx`,
  sheet `PDF`. Rows are grouped under **discipline section headers**
  (Project Management, Process, Electrical, Instrumentation, Mechanical, Piping,
  Pipeline, Safety/Risk, Civil). Each data row carries `Title` and a 3-letter
  `Type` code.
- **FEED Dossier** — `learn/P03433 - EPC  DOSSIER.xlsx`, sheet `FEED DOSSIER`.
  Rows carry an explicit `DISCIPLINE` column (PROJECT, HSE, CIVIL, …) plus a
  `DESCRIPTION` (title).

Combined: **309 labeled records**, every one folding to a canonical discipline.

## Authoritative taxonomy & discipline fold

`input/disciplines.csv` is authoritative (confirmed: matches the DB table).
Relevant `code → id`:

| code | id | name | code | id | name |
|------|----|------|------|----|------|
| CIV | 1 | Civil | PIP | 8 | Piping |
| ELE | 3 | Electrical | PRJ | 10 | Project Management |
| EMT | 4 | Engineering Management | PRO | 11 | Process |
| HSE | 5 | HSE | QAC | 13 | QA/QC |
| INC | 6 | I&C | MEC | 7 | Mechanical |

**Discipline fold** (dossier label/code → canonical code, case-insensitive,
whitespace-trimmed). Lives in the throwaway miner only — not permanent code.

```
Process, PRO                      -> PRO   (11)
HSE, HSE and Process, Safety/Risk -> PRO   (11)   # HSE/safety roll up to Process
Civil, CIVIL, structural          -> CIV   (1)
Piping, PIPING, Pipeline          -> PIP   (8)
Electrical                        -> ELE   (3)
Instrumentation, Instrument       -> INC   (6)
Mechanical, Rotating, rotary      -> MEC   (7)
Project Management, PROJECT       -> EMT   (4)   # PRJ rolls up to Engineering Mgmt
```

### Dossier coverage (validated)

Per-discipline title counts after folding: **Process-11 (95), Piping-8 (86),
Electrical-3 (46), I&C-6 (38), Civil-1 (33), Mechanical-7 (7), Eng-Mgmt-4 (3).**

Disciplines **not** present in the dossiers — QA/QC-13, Procurement-12,
Telecom-37, HVAC-39, Package-9, Construction Mgmt-2 — are **left untouched** by
this work (no rules invented without evidence).

## Decisions (confirmed with user)

1. **Approach B**: learn per-discipline title keywords *and* add a gated
   type→discipline fallback. (The fallback is what structurally attacks the null
   rate, since nearly every doc has a type.)
2. **Mechanism**: one-time mine via a throwaway script, results **hand-authored**
   into the committed config. No permanent learner is added to the package.
3. **Re-key mis-keyed buckets** to canonical ids per disciplines.csv. Today's
   Electrical keywords sit under id 4 (→ should be **3**), Piping under 13
   (→ **8**), instrumentation under 7 (→ **6**), tank/vessel under 10. This
   changes outputs and requires updating tuned tests.
4. **Honor the dossiers' PID → Process-11** mapping (both dossiers agree).

## Components

### 1. `scripts/mine_dossiers.py` (throwaway, untracked)

Reads both `learn/*.xlsx`, applies the discipline fold, and emits:
- per-canonical-discipline candidate phrases (n=1..3) with frequency-based
  weights, reusing the project canonicalizer
  (`classifier.core.scoring.canonicalize_title` / `candidate_phrases`) so the
  mined phrases match what the scorer will see at classify time;
- a type→discipline purity table (top discipline share + support per type).

Output is printed/written for human review; **not imported by the package**.

### 2. `config/discipline_keywords.py` — regenerated

`DISCIPLINE_KEYWORDS` is rewritten for the **7 covered ids** with corrected
keys. Bucket re-mapping summary:

| current id (kw theme) | corrected id |
|-----------------------|--------------|
| 1 (Civil) | 1 (unchanged) |
| 4 (Electrical kw) | 3 (Electrical) |
| 7 (Instrumentation kw) | 6 (I&C) |
| 10 (Tank/vessel kw) | 7 (Mechanical) — folded MEC; verify vs Static-36 during impl |
| 13 (Piping kw) | 8 (Piping) |
| — (new) | 11 (Process), 4 (Eng-Mgmt) from dossier titles |

Weights follow the existing convention (log-frequency-ish floats, highest-weight
phrase per key consumes its span — see `scoring.score`). Hand-authored from the
miner output; the spec does not pin exact phrase lists (that is the
implementation/plan's job, driven by the mined candidates).

### 3. `config/type_to_discipline.py` — replaced

Only **pure, well-supported** types qualify (purity 100%, support ≥3 in the
dossiers):

```
PID -> 11   (n=24)      DSL -> 3   (n=14)      DGA -> 8  (n=12)
PFD -> 11   (n=6)       MSD -> 11  (n=5)       DSD -> 3  (n=3)
PSF -> 11   (n=3)
```

Ambiguous types are **excluded** (validated shares): DAS 46%, REP 54%, SPC 35%,
LST 42%, DAL 53%, CAL 50%, DWG 46%, REQ 55%, SCH 50%. Including them would inject
discipline errors. `support_count`/`share` comments are retained for audit.

### 4. `core/classify.py::fill_discipline` — gated type fallback

The `+2` bonus inside `score_disciplines` (driven by `TYPE_TO_DISCIPLINE`) is
**preserved** — when the title *does* score a discipline, the type hint still
nudges it, and with the table now holding 7 pure types it reinforces the right
discipline.

The fallback is added at the **write gate**, `fill_discipline`, because that is
the only place that currently demands `confidence == "high"` before writing a
discipline. New logic, after the existing keyword branch:

```python
pick = pick_discipline_with_overrides(title, type_hint=type_hint or None)
if pick["confidence"] == "high" and pick["discipline_id"] is not None:
    return str(pick["discipline_id"]), "via_keyword"
fb = TYPE_TO_DISCIPLINE.get(type_hint.strip().upper()) if type_hint else None
if fb is not None:
    return str(fb), "via_type"
return "", "miss"
```

- Fires only when the keyword pick is **not** high-confidence (i.e. the value
  that would otherwise be dropped as a miss). It never overrides a *written*
  keyword discipline.
- `reason = "via_type"` (consistent with the existing `via_keyword` /
  `preserved` / `miss` vocabulary) so the source is auditable.
- Only the 7 pure types are in `TYPE_TO_DISCIPLINE`, so ambiguous types
  (DAS/REP/SPC/…) never trigger it.

## Data flow

```
fill_discipline(row_disc, title, type_hint)
   │ row_disc present ──► (row_disc, "preserved")
   ▼
score_disciplines(title, type_hint) -> pick   # keyword scores + (+2 hint bonus)
   │ pick high ──► (discipline_id, "via_keyword")
   ▼ pick not high
type_hint in TYPE_TO_DISCIPLINE (7 pure types) ?
   │ yes ──► (mapped discipline_id, "via_type")
   │ no  ──► ("", "miss")
```

## Error handling & edge cases

- **No type / unknown type** with a missing title score → stays null (`"miss"`).
  Acceptable; better null than wrong.
- **Type fallback vs. a low-but-present keyword pick**: fallback only fires on
  `none`, so a genuine (even low) keyword signal always wins.
- **Uncovered disciplines** (QA/QC etc.): no rules; behavior unchanged.
- **Span consumption / weights**: unchanged — reuse `scoring.score`/`pick`.

## Testing

- Update `tests/core/test_class_precedence.py` and any scoring snapshot to the
  **corrected discipline ids** (3/6/7/8/11 instead of legacy 4/7/10/13).
- Add cases for the type fallback: (a) blank/garbage title + `PID` → 11 with
  `reason="via_type"`; (b) ambiguous type (`DAS`) + blank title → null
  (`"miss"`); (c) title that scores a discipline + conflicting type hint →
  keyword wins.
- Add a regression asserting Electrical titles (e.g. "SINGLE LINE DIAGRAM")
  now resolve to **id 3**, not 4.
- Re-run the full suite; expect intentional snapshot churn from the re-key.

## Success criteria

- Null `discipline_id` rate on the snapshot drops substantially from the ~50%
  baseline (target: the 170+ nulls materially reduced — exact figure measured
  during implementation, reported, not asserted blindly).
- No discipline is assigned from an ambiguous type.
- Electrical/Piping/I&C/Process titles resolve to canonical ids.
- Full test suite green after intentional snapshot updates.

## Results (measured 2026-06-13 on input snapshot)

On `input/_document__202606051455.csv`, treating every source-null row as blank:

- **266** rows null in source → **126 filled (47%)**, **140 still null**.
- Fill reasons: `via_keyword` **124**, `via_type` **2**. The keyword re-key +
  expansion did the heavy lifting; most pure-type docs already classify by
  title, so the fallback only rescues the few with blank/garbage titles.
- Full test suite: **159 passed**. No existing test needed id reconciliation —
  the prior tests treat `discipline_id` as a preserved input, not a classifier
  output, so the re-key introduced no regressions.

The remaining 140 nulls are dominated by the intentionally-excluded ambiguous
types (REP 25, DAS 17, DAL 14, SPC 13, LST 11). Many carry title-level
discipline signals (e.g. `EARTHING INSTALLATION STANDARDS`, `INSTRUMENT JUNCTION
BOX SCHEDULE`, `CABLE ROUTING LAYOUT`) that a future keyword-tuning pass could
capture — see "Follow-up opportunities".

## Follow-up opportunities (not in this scope)

- Lift near-floor single-token weights that currently miss (`EARTHING` 2.4 just
  under the 2.5 solo floor) or add corroborating phrases.
- Add I&C/Electrical phrases for the still-null instrument/cable docs
  (`CABLE ROUTING`, `INSTRUMENT JUNCTION BOX`, `CABLE TRENCH`).
- Resolve `PROCESS`-token collisions that drop margin below 1.0 (e.g.
  `PROCESS DATA SHEET FOR WATER DISPOSAL TANK` ties Process vs Mechanical).
- Extend keyword coverage to dossier-absent disciplines (QA/QC, Procurement,
  Telecom, HVAC) when labeled data becomes available.

## Out of scope

- Disciplines absent from the dossiers (no invented rules).
- A permanent in-repo learner CLI (explicitly one-time mining).
- Type-keyword (`TYPE_KEYWORD_RULES`) relearning — only type→discipline and
  discipline keywords change here.
- The input-data legacy id scheme (17/20/23/25/26); we target disciplines.csv.
