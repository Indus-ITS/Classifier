# Classifier quality improvements

Date: 2026-05-14
Status: Draft

## Goal

Tighten the type-keyword classifier in three places informed by the
review of commits `3650129..6c3c63c`:

1. **Confidence rule** — require either ≥2 matching phrases OR a
   single phrase with weight ≥ `SINGLE_PHRASE_FLOOR` for `high`
   confidence. Kills `STEEL STRUCTURE`-alone → DAL and `INSTRUMENT`-alone
   → PID false positives.
2. **Junk-phrase filter in the learner** — drop n-grams containing
   digits or anchored by punctuation-only tokens. Removes
   `'01 FT 0605'`, `'2407/2408'`, `'NO 4'`, lone `&`, lone `/`.
3. **Light plural fold in the tokenizer** — fold a small curated list
   of plurals to their singular forms (`CALCULATIONS → CALCULATION`,
   `DRAWINGS → DRAWING`, `SCHEDULES → SCHEDULE`, …). Catches the
   `GRE PIPELINE CROSSING CALCULATIONS` → CAL miss in spot-check B.

Net expectation: ~50% drop in false-positive rate, modest coverage
gain from plural-fold matches.

## Why

- Spot-check A had 2/20 wrong predictions; both trace to single-token
  rules clearing `MIN_SCORE` alone.
- Generated `TYPE_KEYWORD_RULES` contains polluted phrases like
  `'01 FT 0605'` and `'2407/2408'` — project-specific tag fragments
  that won't transfer to new datasets and spuriously inflate scores.
- Spot-check B found `GRE PIPELINE CROSSING CALCULATIONS` (clear CAL)
  uncategorised because the trained rule was `'CALCULATION'` singular.

## Out of scope

- No new training data, no new sources.
- No ML / embeddings.
- No threshold tuning beyond the new `SINGLE_PHRASE_FLOOR` knob.
- No refactor of `_score_with_rules` in the eval script (deferred).
- No change to `MIN_CLASS_DOCS` (DWG stays in even with 0% LOO precision —
  user did not opt in to dropping it).
- No change to the file/CLI surface of `classify`, `learn-type-keywords`,
  or `convert-classified`.

---

## Architecture (touched files)

```
src/classifier/core/type_scoring.py     ← single-phrase floor + plural fold + score_types signature change
src/classifier/tools/learn_type_keywords.py  ← junk-phrase filter
src/classifier/config/type_keywords.py  ← regenerated artifact (committed)
output/classified.csv                   ← regenerated artifact (committed)
```

No new modules. No new entry points. No spec changes to the canonical
28-col CSV.

---

## Sub-project A — single-phrase confidence rule

### New knob

`SINGLE_PHRASE_FLOOR: float = 2.5` added at the top of
`src/classifier/core/type_scoring.py` next to `MIN_SCORE` and
`MIN_MARGIN`. Tunable; not exposed on the CLI.

### `score_types` signature change

Currently returns `dict[str, float]` where each value is the
cumulative score. We need to know **how many phrases fired per type**
to decide single-phrase status.

New return type: `dict[str, tuple[float, int]]` where the tuple is
`(score, n_phrases_fired)`. Inside `score_types`, increment a per-type
counter each time a phrase weight is added.

### `pick_type` rule change

After the existing `top >= MIN_SCORE` and `(top - rup) >= MIN_MARGIN`
checks pass, add:

```python
if n_phrases_for_top == 1 and top_score < SINGLE_PHRASE_FLOOR:
    confidence = "low"
```

(Falling through to `low` rather than `none` preserves the existing
distinction between "saw nothing" and "saw something but distrust it".)

`pick_type` signature accepts the richer `scores` dict; reads both
elements of the tuple. Return dict gains one field:
`n_phrases: int` (number of phrases that fired for the picked type, or 0).

### Callers of the old signature

Two files call `score_types` / `pick_type`:

- `src/classifier/cli/classify.py` — only inspects `pick["type"]` and
  `pick["confidence"]`. No breakage.
- `scripts/eval_type_keywords.py` — has its own `_score_with_rules`
  duplicate of `score_types`. Also needs the per-rule count tracked
  the same way so the eval reflects the new confidence rule.

### Why 2.5 specifically

The learner formula is `precision * log1p(in_class)`. For
`SINGLE_PHRASE_FLOOR = 2.5`, the implied minimum class size at
precision 1.0 is `e^2.5 - 1 ≈ 11.2` rows. Below that, a single phrase
can't clear the floor — multi-phrase support becomes required, which
is exactly the desired guard against tiny-class single-token rules.

For classes with ≥ 12 rows (DAL, DAS, REP, PID, SPC, DSL, DWG, LST,
DGA), highly-specific single phrases (`SPECIFICATION`, `DATA SHEET`)
still clear easily.

---

## Sub-project B — junk-phrase filter in the learner

### New filter

A new pure function `_phrase_is_publishable(ngram: tuple[str, ...]) -> bool`
inside `learn_type_keywords.py`. Returns False if **any** of:

1. Any token contains a digit (`re.search(r"\d", tok)`).
2. The first or last token has no alphabetic character (catches lone
   `&`, `/`, edge punctuation).

Middle tokens may be punctuation-only — preserves `PIPING & INSTRUMENT`
(middle `&` is fine) while dropping `& INSTRUMENT` (leading `&`) and
`PIPING &` (trailing `&`).

### Where it plugs in

Inside `learn()`, after `candidate_phrases(toks, extra_stop=auto_stop)`
returns its per-row phrase set, filter:

```python
phrases = {ph for ph in candidate_phrases(toks, extra_stop=auto_stop)
           if _phrase_is_publishable(ph)}
```

Single change point. `candidate_phrases` itself stays pure.

### Impact preview

From current `type_keywords.py`, this drops (non-exhaustive):
- DAS: `'01 FT'`, `'01 FT 0605'`, `'/ 2408'`
- DAL: `'2407/2408'`, project-area suffixes
- DSL: `'DIAGRAM 16'`, `'DIAGRAM 16 01'`
- Bare-digit unigrams: `'6'`, `'1'`, `'4'` (DAL, MSD, others)

These phrases scored above `MIN_SCORE`/`SINGLE_PHRASE_FLOOR` in some
cases — their removal is a quality win and a correctness win (project
IDs aren't transferable signals).

### Risk

Phrases like `'AREA 2'`, `'PHASE 2'`, `'SUBSTATION 4'` are dropped.
Acceptable: they encode project-specific naming, not document-type
signal.

---

## Sub-project C — light plural fold in the tokenizer

### Implementation

Inside `src/classifier/core/type_scoring.py`, add module-level:

```python
SINGULAR_FORMS: frozenset[str] = frozenset({
    "CALCULATION", "DIAGRAM", "DRAWING", "INDEX",
    "LAYOUT", "LIST", "PROCEDURE", "PROCESS",
    "REPORT", "REQUISITION", "SCHEDULE", "SHEET",
    "SPECIFICATION", "STANDARD",
})

def _depluralize(tok: str) -> str:
    """Fold a small curated list of regular plurals to singular.

    Only applies when stripping the trailing 'S' yields a token that's
    in the SINGULAR_FORMS allowlist. Not a real stemmer — by design,
    we miss irregular plurals and tolerate occasional non-folded plurals.
    """
    if len(tok) >= 5 and tok.endswith("S") and tok[:-1] in SINGULAR_FORMS:
        return tok[:-1]
    return tok
```

Apply at the end of `canonicalize_title`, after the existing
`s.split(" ")`:

```python
    return [_depluralize(t) for t in s.split(" ")]
```

Both the learner and the scorer go through `canonicalize_title`, so
both train and infer in the singular form — no drift.

### Why a static allowlist, not a stemmer

A real stemmer (Porter, Snowball) would overgeneralise on engineering
vocabulary — `MULTI-PHASE` shouldn't become `MULTI-PHAS`. A 14-item
allowlist captures the plurals seen in spot-check B (and the obvious
ones in document indexes) without surprise.

### Edge cases

- `BASIS` → no fold (`BASI` not in list).
- `PROCESS` → unchanged (`PROCES` not in list, and no trailing `S` to
  strip on `PROCESS` itself if it ends `SS`). Actually `PROCESS` ends
  in `S`; `PROCESS[:-1] = PROCES`; `PROCES` is not in `SINGULAR_FORMS`;
  no fold. ✓
- `STATUS` → unchanged.
- `DRAWINGS` → fold to `DRAWING`. ✓
- `LISTS` → fold to `LIST`. ✓
- Length guard `>= 5` keeps `IS`, `AS`, `OS`, etc. unaffected.

### Risk

Negligible — the allowlist is curated and the length guard prevents
over-folding short common words.

---

## Verification

No automated tests (standing user direction). Verification by:

1. Re-run the learner; confirm `type_keywords.py` no longer contains
   any phrase token with a digit (`grep "[0-9]" src/classifier/config/type_keywords.py`
   should match only the `'support'` weights, not phrase strings).
   Manually spot-check a couple of types.
2. Re-run `classify`. Diff the new `output/classified.csv` against the
   pre-change version. Expect:
   - Fewer `via_keyword` fills (some 1-phrase low-weight picks now
     drop to `low` confidence → empty).
   - Some new `via_keyword` fills from plural-form matches (CAL,
     SCHEDULE, etc.).
   - Both `STEEL STRUCTURE` → DAL and `INSTRUMENT` → DAL/PID false
     positives gone from the test rows the review flagged.
3. Re-run leave-one-out eval. Compare new precision / recall /
   coverage to the prior:
   - Precision should rise (87.5% → ≥ 90% target).
   - Coverage may drop modestly (68.8% → ~60-65% expected).
   - DAL and PID confusion-row counts should drop.
4. Spot-check the same 20 newly-classified rows from the previous
   review. Confirm the 2 WRONG cases are now empty/low-confidence,
   and the 17 OK cases remain OK.

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| `SINGLE_PHRASE_FLOOR = 2.5` is too high; legitimate single-phrase REP/CAL picks drop to `low` | Tunable knob; if eval shows precision improved but coverage tanks below ~55%, tune to 2.2 and re-run |
| Plural-fold allowlist misses domain-specific plurals (e.g. `MTOS` → `MTO`) | Add to `SINGULAR_FORMS` when observed; keep allowlist hand-curated and small |
| Junk filter drops legitimate phrases that contain digits in name | None observed in current data; if a future document index uses `OPERATION 1` as a type signature we'll add a deliberate carve-out |
| Score change breaks downstream consumers expecting `dict[str, float]` | Only consumers are `classify.py` and `eval_type_keywords.py`; both inspected and updated together |

## Acceptance

1. `score_types` returns `dict[str, tuple[float, int]]` and is sorted /
   deterministic.
2. `pick_type` returns a dict containing `n_phrases` and applies the
   `SINGLE_PHRASE_FLOOR` guard.
3. `learn-type-keywords` produces a `type_keywords.py` with no
   phrase-string containing a digit and no phrase anchored by a
   punctuation-only token.
4. `canonicalize_title` folds the 14 plurals listed in `SINGULAR_FORMS`
   and leaves others alone.
5. Re-running learner + classify is byte-identical on re-run
   (determinism).
6. LOO eval reports overall precision ≥ 90% (target — not a hard gate;
   actual number recorded in the commit message).
7. The two specific review false-positives (`STEEL STRUCTURE` → DAL,
   `INSTRUMENT` → PID) no longer fire on their original test titles.
