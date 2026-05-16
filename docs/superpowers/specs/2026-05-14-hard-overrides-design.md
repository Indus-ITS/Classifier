# Hard overrides + negative keywords + taxonomy expansion

Date: 2026-05-14
Status: Draft

## Goal

Add a deterministic override layer in front of the learned keyword
scorer to handle three failure modes surfaced by the
`output/unclassified.md` audit:

1. **Unambiguous domain phrases** that the scorer can't reach because
   the training data is too thin for them (e.g., `PROCEDURE → PRO`,
   `TBE FOR ... → TBE`, `MTO FOR ... → MTO`).
2. **Semantic contamination** where a tokenized signature is true
   *in isolation* but wrong *in context* (`INSTRUMENT` → PID is right
   for "PIPING & INSTRUMENT DIAGRAM" but wrong for "INSTRUMENT BULK
   MTO" / "INSTRUMENT CABLE SCHEDULE").
3. **Missing taxonomy** for codes that exist in EPC convention but
   not in our 31-code enum (`TBE`, `ISO`, `DDT`).

Architecture: hand-curated `HARD_OVERRIDES` table consulted before
scoring, `NEGATIVE_KEYWORDS` consulted after scoring to prune
contaminated picks. Learned rules unchanged.

## Why

- The audit's 180 empties include ~35 TBE rows, ~30 PROCEDURE rows,
  10+ DETAILS rows that the learner can't classify because no
  training row for those types exists.
- INSTRUMENT-driven PID false positives are not a data problem; they
  are a semantic problem ("INSTRUMENT" inside "INSTRUMENT BULK MTO"
  doesn't mean PID even though "INSTRUMENT" is a strong PID signal
  alone). No amount of additional training data fixes this; a
  blocklist does.
- TBE, ISO, DDT aren't in the enum; ~40 rows can't be predicted under
  any algorithm until they exist.

## Out of scope

- No ML.
- No change to the learner (`learn_type_keywords.py`).
- No change to generated `type_keywords.py` schema.
- No removal of the existing scoring path — it still handles
  ambiguous titles after the override layer prunes.
- No automated tests (per standing user direction).
- No `MIN_SCORE` / `SINGLE_PHRASE_FLOOR` / `MIN_MARGIN` retuning.
- No hard override for `DDT` (taxonomy added but overrides deferred —
  see Sub-project A).
- No global anti-keyword framework — `NEGATIVE_KEYWORDS` is targeted
  per the review's "don't prematurely generalize" guidance.

---

## Architecture

```
input title
  │
  ▼  canonicalize_title
tokens
  │
  ▼
1. HARD_OVERRIDES match (sorted longest-phrase-first within type;
   first hit wins)
     │
     ├── hit  → return {type, confidence: "high", n_phrases: 1}
     │           (reason recorded by caller as 'via_override')
     │
     └── miss → continue
  │
  ▼
2. score_types(tokens)  ← existing learned-rule scorer
  │
  ▼
3. NEGATIVE_KEYWORDS prune:
     for each (type, scored_value) in scores.items():
       if any negative phrase for that type matches tokens:
         scores[type] = (0.0, 0)
   Then drop entries with score 0.
  │
  ▼
4. pick_type(scores)  ← existing logic on filtered dict
```

Two new tables in a new config file. One new dispatch function in the
scorer. No call-site changes in `cli/classify.py`.

---

## Sub-project A — taxonomy expansion

### Edit `src/classifier/config/buckets.py`

Append three entries to `TYPE_TO_BUCKET`:

```python
TYPE_TO_BUCKET: dict = {
    ...,
    "TBE": "Documents",     # Technical Bid Evaluation
    "ISO": "Isometrics",    # Isometric drawings (bucket exists)
    "DDT": "Drawings",      # Detail drawings (foundation / structural / roof)
}
```

`BUCKET_TO_CLASS` already covers `Isometrics → Drawings` and
`Drawings/Documents → drawing/document`. No bucket changes needed.

After this edit:

- `KNOWN_TYPES` regenerates from `TYPE_TO_BUCKET.keys()` next time
  `build-type-enum` runs — automatic.
- Total 31 → **34 codes**.

### DDT is taxonomy-only for v1

The reviewer flagged DDT as semantically slippery (PIPELINE CROSSING
DETAILS could be DDT / DWG / DGA depending on convention). We add the
code so the enum exists for future training data and to satisfy the
schema validator, but **do not** add a HARD_OVERRIDES entry. Detail
rows continue through the scorer; most stay empty until training data
disambiguates.

---

## Sub-project B — `config/type_overrides.py` (new file)

### File header and constants

```python
"""Hand-curated overrides for the type classifier.

Two tables, hand-edited not generated. Consulted by
``classifier.core.type_scoring.pick_type_with_overrides`` before
(``HARD_OVERRIDES``) and after (``NEGATIVE_KEYWORDS``) the learned
keyword scorer.

Phrases are tuples of canonicalized tokens — i.e., what
``canonicalize_title`` returns. Match is "all phrase tokens appear in
the title token list as a contiguous subsequence". The phrase
``("PIPING", "&", "INSTRUMENT")`` matches the canonicalized form of
"PIPING & INSTRUMENT DIAGRAM" because the tokenizer preserves ``&``.
"""
from __future__ import annotations
```

### `HARD_OVERRIDES`

```python
HARD_OVERRIDES: dict[str, tuple[tuple[str, ...], ...]] = {
    # P&IDs — every variant the corpus spells
    "PID": (
        ("P&ID",),
        ("PIPING", "&", "INSTRUMENT"),
        ("PIPING", "AND", "INSTRUMENT"),
        ("PIPING", "&", "INSTRUMENTATION"),
        ("PIPING", "AND", "INSTRUMENTATION"),
        ("PIPING", "&", "INSTRUMENTATION", "DIAGRAM"),
        ("PIPING", "AND", "INSTRUMENT", "DIAGRAM"),
    ),

    # Flow diagrams (incl. heat & material balance)
    "PFD": (
        ("PROCESS", "FLOW", "DIAGRAM"),
        ("UTILITY", "FLOW", "DIAGRAM"),
        ("HEAT", "AND", "MATERIAL", "BALANCE"),
        ("HEAT", "AND", "MATERIALS", "BALANCE"),
    ),

    "DCE": (
        ("CAUSE", "&", "EFFECT"),
        ("CAUSE", "&", "EFFET"),      # observed misspelling
        ("CAUSE", "AND", "EFFECT"),
    ),

    "PSF": (
        ("SAFEGUARDING", "DIAGRAM"),
        ("SAFEGUARDING", "MEMORANDUM"),
    ),

    "MSD": (
        ("MATERIAL", "SELECTION", "DIAGRAM"),
    ),

    # General Arrangement — verbose corpus spellings
    "DGA": (
        ("GENERAL", "ARRANGEMENT"),
        ("GENERAL", "ARRANGMENT"),                # observed misspelling
        ("GENERAL", "ARRANGEMENT", "DRAWING"),
        ("PIPING", "GENERAL", "ARRANGEMENT"),
    ),

    # Procedures — single-token PROCEDURE is acceptable per review:
    # in EPC docs the word is overwhelmingly type-bearing.
    "PRO": (
        ("PROCEDURE",),
        ("METHOD", "STATEMENT"),
        ("WORK", "INSTRUCTION"),
    ),

    # Technical Bid Evaluation — incl. corpus misspellings
    "TBE": (
        ("TBE",),
        ("TECHNICAL", "BID", "EVALUATION"),
        ("TECHNICAL", "BID", "EVALATION"),        # observed
        ("TECHNICAL", "BID", "EVALATUION"),       # observed
    ),

    "ISO": (
        ("ISOMETRIC",),
        ("ISOMETRICS",),
    ),

    "MTO": (
        ("MTO",),
    ),

    # Datasheets — explicit qualified forms aid future debug traces
    "DAS": (
        ("DATASHEET",),
        ("DATA", "SHEET"),
        ("MECHANICAL", "DATASHEET"),
        ("INSTRUMENT", "DATASHEET"),
        ("ELECTRICAL", "DATASHEET"),
    ),

    "PHL": (
        ("PHILOSOPHY",),
    ),

    "REG": (
        ("REGISTER",),
    ),

    "SCH": (
        ("SCHEDULE",),
    ),

    # Block diagrams. NOTE: ARCHITECTURE DIAGRAM is a temporary
    # operational mapping (per audit on ICSS SYSTEM ARCHITECTURE
    # DIAGRAM); revisit if a network-architecture variant lands.
    "DBD": (
        ("BLOCK", "DIAGRAM"),
        ("SCHEMATIC", "BLOCK", "DIAGRAM"),
        ("ARCHITECTURE", "DIAGRAM"),
    ),

    "DPP": (
        ("PLOT", "PLAN"),
    ),

    "DAL": (
        ("ELECTRICAL", "EQUIPMENT", "LAYOUT"),
        ("ELECTRICAL", "CABLE", "ROUTING"),
    ),
}
```

### `NEGATIVE_KEYWORDS`

```python
# A title containing any of these phrases blocks the listed type even
# if the scorer would have picked it. Targeted suppression of proven
# semantic contamination only — not a general anti-keyword framework.
# All entries today target PID, which suffers from the "INSTRUMENT"
# token reading as a PID signal in non-P&ID contexts.
NEGATIVE_KEYWORDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "PID": (
        ("MTO",),
        ("SCHEDULE",),
        ("LAYOUT",),
        ("LIST",),
        ("BULK",),
        ("LOCATION",),
    ),
}
```

Empty mapping for any other type means "no negative rules". Iteration
in pick code skips types not in this dict.

### Phrase semantics

A phrase matches if its tokens appear as a contiguous subsequence in
the canonicalized title's token list. Matching is exact equality
per token; no fuzzy / substring matching. The tokenizer
(`canonicalize_title`) handles plural-folding,
punctuation-normalization, and uppercase-folding before phrase
matching runs.

---

## Sub-project C — pick flow rewire in `core/type_scoring.py`

### New helper for override matching

```python
def _phrase_matches(tokens: Sequence[str],
                     phrase: Sequence[str]) -> bool:
    """True iff ``phrase`` appears as a contiguous subsequence in ``tokens``."""
    n, m = len(tokens), len(phrase)
    if m == 0 or m > n:
        return False
    for i in range(n - m + 1):
        if all(tokens[i + j] == phrase[j] for j in range(m)):
            return True
    return False
```

### New top-level pick function

```python
def pick_type_with_overrides(title: str) -> dict:
    """Three-phase pick: override → score → negative prune → choose.

    Returns the same dict shape as ``pick_type`` plus an additional
    field ``reason`` ∈ {"override", "scored", "none"} so callers can
    surface the path in summary reports.
    """
    from classifier.config.type_overrides import (
        HARD_OVERRIDES, NEGATIVE_KEYWORDS,
    )

    tokens = canonicalize_title(title)
    if not tokens:
        result = pick_type({})
        result["reason"] = "none"
        return result

    # Phase 1: hard overrides. Within each type, try phrases by
    # descending length so the most specific phrase for that type
    # wins first. Across types, pick the type whose matched phrase
    # was longest; tie-break alphabetically.
    override_hits: list[tuple[int, str]] = []  # (matched_phrase_len, type_code)
    for type_code, phrases in HARD_OVERRIDES.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            if _phrase_matches(tokens, phrase):
                override_hits.append((len(phrase), type_code))
                break  # first (longest) phrase hit for this type is enough
    if override_hits:
        override_hits.sort(key=lambda t: (-t[0], t[1]))
        chosen_type = override_hits[0][1]
        return {
            "type": chosen_type,
            "score": float("inf"),
            "runner_up": "",
            "runner_up_score": 0.0,
            "n_phrases": 1,
            "confidence": "high",
            "reason": "override",
        }

    # Phase 2: learned keyword scoring.
    scores = score_types(title)

    # Phase 3: negative-keyword prune. Soft suppression via multiplier
    # rather than del — keeps the door open for partial suppression
    # later without redesign.
    NEGATIVE_MULTIPLIER: float = 0.0
    for type_code, neg_phrases in NEGATIVE_KEYWORDS.items():
        if type_code not in scores:
            continue
        for phrase in neg_phrases:
            if _phrase_matches(tokens, phrase):
                cur_score, cur_n = scores[type_code]
                scores[type_code] = (cur_score * NEGATIVE_MULTIPLIER, cur_n)
                break
    # Drop zero-or-less entries so pick_type doesn't see them.
    scores = {t: v for t, v in scores.items() if v[0] > 0}

    # Phase 4: existing picker.
    result = pick_type(scores)
    result["reason"] = "scored" if result["confidence"] != "none" else "none"
    return result
```

### Existing `pick_type` is unchanged

Already takes a `dict[str, tuple[float, int]]` and returns the
standard pick dict. We only wrap it.

### Backwards-compatible export

`pick_type` and `score_types` keep their existing signatures.
`pick_type_with_overrides` is the new dispatcher. Callers migrate
case by case.

---

## Sub-project D — `cli/classify.py` migration

### Switch the two call sites to the new dispatcher

`_normalize_doc_type`:

```python
# old:  pick = pick_type(score_types(title))
# new:
pick = pick_type_with_overrides(title)
```

`_fill_type`:

```python
# old:  pick = pick_type(score_types(title))
# new:
pick = pick_type_with_overrides(title)
```

### Reason-tag mapping in the summary

`_fill_type` returns reason strings to the summary `Counter`. With
the new dispatcher we can distinguish override vs scored fills:

```python
if pick["confidence"] == "high":
    reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
    return pick["type"], reason_tag
return "", "empty"
```

The summary print extends the existing key list:

```python
for k in ("preserved", "via_override", "via_keyword", "empty"):
    print(f"  {k:14s} {type_reason.get(k, 0):>6}")
```

`_normalize_doc_type` already returns a `reason` string in the
`doc_type_reason` counter; add `via_override` similarly so the
doc_type summary stays explainable.

### Import

```python
from classifier.core.type_scoring import (
    pick_type_with_overrides, pick_type, score_types,
)
```

(`pick_type` and `score_types` no longer used directly in `classify`
but stay imported in case future callers want the raw paths.)

---

## Verification

No automated tests. Verify by:

1. **Smoke test on the 13 audit patterns from the user's list** —
   ensure each one now resolves to the expected type via override.
2. **Smoke test on the known-bad cases** —
   `INSTRUMENT BULK MTO`, `INSTRUMENT CABLE SCHEDULE`,
   `INSTRUMENT LOCATION LAYOUT DRAWINGS` must NOT pick PID.
3. **End-to-end run on `input/To be classified/document.csv`** —
   capture the new `type fill outcomes` block. Expect:
   - `via_override` non-zero (significant fraction of 180 empties).
   - `via_keyword` mostly preserved (overrides bypass scoring only
     when a phrase actually matches).
   - `empty` drops substantially — target ≤ 60.
4. **Regenerate `output/unclassified.md`** by re-running the same
   doc-generation step that produced the original 180-row report.
   Visually scan the residual to confirm the override layer didn't
   miss obvious cases.
5. **LOO eval** — overall precision should hold or improve (overrides
   are deterministic). Coverage on the labeled set may shift if any
   override conflicts with a label, but no decrease is acceptable.

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Single-word override `PROCEDURE → PRO` mis-fires on a doc title that uses the word incidentally | Audit-flagged corpus is consistent: every observed `PROCEDURE` title is genuinely a procedure. Edge-case "Procedure Qualification Record" is still closer to PRO than any other code. Acceptable. |
| `ARCHITECTURE DIAGRAM → DBD` over-broad if a network-architecture variant lands | Marked as temporary mapping in the config comment. Revisit when a non-ICSS architecture title appears in the corpus. |
| Hand-table grows unwieldy over time | Two top-level dicts in one file; each entry is one line. Reorganize into per-discipline files only when the file exceeds ~300 lines. |
| `DDT` taxonomy added but no override → detail rows still empty | Acceptable for v1. Reviewer flagged DDT as semantically slippery; deferring override until training data establishes the convention. |
| Negative keywords accidentally suppress a legitimate PID pick | All six negatives target contamination patterns the audit identified. Soft-suppression via `NEGATIVE_MULTIPLIER = 0.0` (instead of `del`) keeps the partial-suppression door open. |
| Override list ordering matters subtly | Within-type sort by descending phrase length; across-type tie-break by alphabetical type code. Both documented and tested via smoke step 1. |

## Acceptance

1. `TYPE_TO_BUCKET` contains `TBE`, `ISO`, `DDT` and `KNOWN_TYPES`
   regenerates to 34 codes.
2. `src/classifier/config/type_overrides.py` exists with the two
   tables above.
3. `pick_type_with_overrides` is exported from
   `classifier.core.type_scoring` and matches the documented flow.
4. `classify` uses the new dispatcher; summary print includes
   `via_override`.
5. Smoke command (Verification step 1) shows all 13 audit phrases
   resolve to the expected type at `confidence == "high"` via
   `reason == "override"`.
6. Smoke command (Verification step 2) shows none of the three
   negative-keyword cases pick PID.
7. End-to-end `classify` run produces `empty ≤ 60` (down from 180).
8. Regenerated `output/unclassified.md` row count matches the new
   empty count and is visually scanned.
9. LOO eval overall precision ≥ 95% (current baseline 96.9%); no
   regression.
