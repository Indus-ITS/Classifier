# Type-keyword classifier

Date: 2026-05-13
Status: Draft

## Goal

Add a deterministic, keyword-based scorer that predicts the 3-letter
`type` (and derives `doc_type`) from a document `title`, using the
labeled rows in `input/classified_csv/**/*.csv` as the source of truth.
Slot it into `classify` as a fallback tier *after* the existing lookup
path, never before. Empty stays the answer when confidence is low.

## Why

- The lookup tier only fires on `document_no` / `customer_ref` matches.
  559 rows in the current to-be-classified CSV still have empty `type`
  because they don't match the lookup keyspace.
- Engineering document titles are heavily templated ("PROCESS DATA SHEET
  FOR ...", "PIPING & INSTRUMENT DIAGRAM ..."). Hand-curated keyword
  rules backed by a tiny scorer recover most of these without ML.
- 256 labeled rows is far too few for any embedding / transformer
  approach to be honest about its confidence. A rule-based path with
  explicit confidence gating preserves the "leave empty rather than
  guess wrong" invariant from the existing spec.

## Out of scope

- ML / embeddings / vector DBs.
- Per-discipline rules (operate on title text only).
- Touching the existing bucket-level scorer (`core/scoring.py`); it
  stays as the doc_type fallback.
- Auto-regenerating `type_keywords.py` during `classify` (re-run is
  manual; `classify` just warns when the generated file is stale).
- Convincing single-example classes to classify themselves.

---

## Architecture

```
input/classified_csv/**/*.csv   ← training data (today: 1 CSV, future: all)
            │
            │ (learn-type-keywords)
            ▼
src/classifier/config/type_keywords.py   ← generated, committed
            │
            │ (imported)
            ▼
src/classifier/core/type_scoring.py       ← canonicalize_title, score_types, pick_type
            │
            │ (used by)
            ▼
src/classifier/cli/classify.py            ← new tier-5 fill path + doc_type fallback
```

Two new modules + one extended. One new CLI entry point.

---

## Cross-cutting invariants

### Shared canonicalization

A single function `canonicalize_title(raw: str) -> list[str]` lives at
`src/classifier/core/type_scoring.py` and is the **only** path titles
ever take into tokenized form. Used by both the learner and the
scorer; otherwise training and inference can drift.

Pipeline:

1. NFKC, uppercase, replace dashes / non-breaking spaces with single space.
2. Drop parenthesized groups entirely: `(8 SHEETS)`, `(NEW)`, `(ACES)` → `""`.
3. Drop trailing revision/sheet tokens: `\d+ SHEETS`, `REV \d+`, `SHEET \d+ OF \d+`.
4. Strip remaining punctuation except `&` and `/` (preserve "DATA & INSTRUMENT", "DCS/ESD/F&G").
5. Collapse whitespace.
6. Split on whitespace → token list.
7. **No stop-word filtering at the tokenize step.** Stop-words are
   handled at the n-gram step (next section) so the tokenizer stays
   pure and reusable.

### Deterministic ordering

Every generated artifact sorts:
- Outer dict by type code (alpha).
- Inner list of phrases by `(-score, phrase)` so highest-weight first,
  stable on ties.
- Tokenizer is pure (no random sampling, no thread-local state).

---

## Sub-project A — `learn-type-keywords`

### Inputs

- All CSVs under `input/classified_csv/**/*.csv`, walked in sorted
  case-insensitive order.
- Each row contributes a `(type, title)` pair when both columns are
  non-empty and `type` is in `KNOWN_TYPES` (from `config/type_enum.py`).

### N-gram extraction

For each row, compute `tokens = canonicalize_title(title)`, then emit
1-grams, 2-grams, 3-grams (no 4-grams — the gain over 3-grams is small
and the noise grows fast on small datasets).

### Stop-word handling (hybrid)

A stop-word is **never** part of an emitted n-gram. Two layers:

1. **Curated list** (small, conservative):
   `{"FOR", "AND", "OR", "OF", "THE", "TO", "WITH", "ON", "IN", "AT",
   "FROM", "INTO", "A", "AN"}`.
   These are pure connectors; their presence inside a phrase doesn't
   carry signal.
2. **Auto-suppression**: any token that appears in **> 40%** of all
   training titles is automatically added to the stop-word set for this
   run. Catches project-specific noise like `SAHIL`, `CDS`, `AREA`
   without requiring a hand-maintained allowlist.

The combined stop-word set is the union of (1) and (2). An n-gram is
emitted only if **none** of its tokens are in the set.

### Class eligibility

Only classes with **at least 4 training examples** generate rules.
Classes below the threshold are listed in the generated file under
`UNTRAINED_TYPES` as a comment so it's obvious why they get no rules.

Rationale: BOM/IDX/DHZ/PLN/REG with 1 example, BOD/DBD/DCE/MTO/SOW with
2, DPP/PSF/PRO/PHL/DSD with 3 are too few to distinguish "the rule" from
"the noise in two titles". They stay empty under the new path, same as
today.

### Per-phrase scoring

For each (type, n-gram) candidate:

```
in_class      = count of rows of THIS type whose tokens contain the n-gram
outside_class = count of rows of OTHER types whose tokens contain the n-gram
in_class_docs = total rows of THIS type
out_class_docs = total rows of OTHER types

precision      = in_class / (in_class + outside_class)
support        = log1p(in_class)                # natural log, +1 to avoid log(0)
final_score    = precision * support
```

Filters applied in order:

1. `in_class >= 2`     — phrase must appear in at least 2 examples of the class.
2. `outside_class < in_class` — phrase must be more common inside the class than outside.
3. `precision >= 0.6`  — at least 60% of occurrences must be inside the class.

Any phrase that fails all three filters is dropped before scoring.

Per type, retain the top **10** phrases by `final_score`. Cap is a
guardrail against generated bloat; in practice most types have 3-6
useful phrases.

### Longest-match preference at scoring time (not learn time)

The learner emits all eligible 1/2/3-grams; deduplication of overlapping
n-grams happens at scoring time (see Sub-project B). Storing all of
them keeps the generated file self-describing — readers can see exactly
which phrases the system knows about.

### Generated file format

`src/classifier/config/type_keywords.py`:

```python
"""Generated by ``learn-type-keywords``. Do not edit by hand.

Source: input/classified_csv/**/*.csv
Generated: 2026-05-13T12:34:56Z
Training rows used: 240 (of 256 — 16 rows dropped: type below MIN_CLASS_DOCS=4)
"""
from __future__ import annotations

# Types with < 4 training rows; they get no rules and will not be predicted:
# BOD (2), BOM (1), DBD (2), DCE (2), DHZ (1), DPP (3), DSD (3), DWD (1),
# IDX (1), MTO (2), PHL (3), PLN (1), PRO (3), PSF (3), REG (1), SOW (2)
UNTRAINED_TYPES: frozenset[str] = frozenset({...})

TYPE_KEYWORD_RULES: dict[str, tuple[tuple[str, float], ...]] = {
    "CAL": (("CALCULATION", 2.4), ...),
    "DAL": (("ELECTRICAL LAYOUT", 3.2), ...),
    "DAS": (("PROCESS DATA SHEET", 3.4), ("DATA SHEET FOR", 3.1), ...),
    "DGA": (("PIPING LAYOUT DRAWING", 3.0), ...),
    "DSL": (("SINGLE LINE DIAGRAM", 3.3), ...),
    "DWG": (...),
    "LST": (("LINE SCHEDULE", 2.1), ("EQUIPMENT LIST", 2.0), ...),
    "MSD": (("MATERIAL SELECTION DIAGRAM", 2.7), ...),
    "PFD": (("PROCESS FLOW DIAGRAM", 2.8), ...),
    "PID": (("PIPING & INSTRUMENT DIAGRAM", 3.5), ...),
    "REP": (...),
    "REQ": (("MATERIAL REQUISITION", 2.4), ...),
    "SCH": (("CABLE SCHEDULE", 2.3), ...),
    "SPC": (("SPECIFICATION", 2.6), ...),
    "STD": (("INSTALLATION STANDARDS", 2.2), ...),
}
```

Inner type is `tuple[tuple[str, float], ...]` (not `list`) — immutable
and hashable, hammers home "do not edit".

### Code shape

- New module: `src/classifier/tools/learn_type_keywords.py`
- New entry point: `learn-type-keywords = "classifier.tools.learn_type_keywords:main"`
- Pure function `learn(training_rows: Iterable[tuple[str, str]]) -> dict[str, tuple[tuple[str, float], ...]]`
  separated from the file walker / writer.

### Done when

- File exists at the path above.
- `python -c "from classifier.config.type_keywords import TYPE_KEYWORD_RULES; print(len(TYPE_KEYWORD_RULES))"` prints between 12 and 16 (the eligible classes from current data).
- Re-running the tool produces a byte-identical file (determinism).

---

## Sub-project B — `core/type_scoring.py`

### `score_types(title: str) -> dict[str, float]`

1. `tokens = canonicalize_title(title)`.
2. Build the candidate phrase set: all 1/2/3-grams from `tokens`, with
   stop-word filtering using the same curated list as the learner (the
   auto-suppression list from learn-time isn't applied here — at inference
   we don't have global frequency, and the curated list captures the
   useful subset).
3. For each `type_code` in `TYPE_KEYWORD_RULES`:
   - Iterate the type's `(phrase, weight)` list in order (highest weight
     first; that's how the file is sorted).
   - Track which token spans have been consumed.
   - On first match where the phrase's tokens fall in an unconsumed span,
     add weight to `scores[type_code]` and mark that span consumed
     (longest-match-wins; later overlapping phrases for the same type
     don't re-fire).
   - **Critical detail:** the span-consumption is per-type, not global.
     Different types can independently match overlapping spans (a title
     could legitimately match phrases from both PID and DAL).
4. Return `scores` (a `dict[str, float]`; types with no matches absent).

### `pick_type(scores: dict[str, float]) -> dict`

Returns a record:
```python
{
    "type": str | "",           # picked code or empty
    "score": float,             # winner's score (0 if no winner)
    "runner_up": str | "",
    "runner_up_score": float,
    "confidence": "high" | "low" | "none",
}
```

Decision logic:

- If `scores` is empty → `confidence="none"`, `type=""`.
- Let `top, rup` be the top two by score (rup may be missing if only one
  type matched; treat as 0.0).
- `confidence = "high"` iff `top.score >= MIN_SCORE` AND `(top.score - rup.score) >= MIN_MARGIN`.
- `confidence = "low"` iff `top.score >= MIN_SCORE` AND `(top.score - rup.score) < MIN_MARGIN`.
- Else `confidence = "none"`.

Defaults (constants in the same module):
- `MIN_SCORE = 2.0` (sum-of-weights threshold; calibrated against the
  generated rule weights — most signature phrases score 2-3.5, so
  `2.0` requires at least one solid hit).
- `MIN_MARGIN = 1.0` (absolute gap, not ratio — addresses the
  "2.1 vs 1.6 both weak" failure mode).

Both knobs are module constants, not function args. Tunable by editing
the file; v1 doesn't expose them on the CLI.

### Determinism

- `score_types` iterates `TYPE_KEYWORD_RULES.items()` (dict insertion
  order, which matches the sorted generated file).
- `pick_type` breaks score ties by alphabetical type code.

### Code shape

- New module: `src/classifier/core/type_scoring.py`.
- Exports: `canonicalize_title`, `score_types`, `pick_type`,
  `MIN_SCORE`, `MIN_MARGIN`.
- ~80 lines.

---

## Sub-project C — integrate into `classify.py`

### New `type` fill ladder

```
1. existing value           → "preserved"
2. lookup.by_doc_no[doc_no] → "via_doc_no"
3. lookup.by_doc_no[cust_ref] → "via_cross_ref"
4. lookup.by_cust_ref[cust_ref] → "via_cust_ref"
5. pick_type(title), confidence == "high" → "via_keyword"          ← NEW
6. ""                       → "empty"
```

Reason `via_cross_ref` keeps its short name even though the longer
`via_customer_ref_as_doc_no` would be more self-documenting. The
existing docstring in `_fill_type` explains the semantics; the column
in the summary stays short for readability. The risk of misreading is
mitigated by the docstring change in this spec, which tightens to:

> ``via_cross_ref`` — the input row's ``customer_ref`` matched a
> ``document_no`` in the canonical CSV. This is the dominant healthy
> fill path on the current dataset, because the input's ``customer_ref``
> typically *is* the canonical-index document number (the two systems
> use different identifiers for the same record).

### New `doc_type` derivation

`_normalize_doc_type` keeps the existing alias-fold-then-score behavior,
but inserts a new step between "alias fold failed" and "fall back to
bucket scorer":

```
1. existing value normalizes to drawing|document → return as-is
2. else: pick_type(title); if confidence=="high",
       fold via TYPE_TO_BUCKET + BUCKET_TO_CLASS, return singular        ← NEW
3. else: bucket-level score_buckets → fold; Undefined → document         (existing fallback)
```

Reason: when keyword inference is confident enough to fill `type`, it's
authoritative on `doc_type` too. When it's not, we don't trust it for
doc_type either; the existing coarser bucket scorer remains the safety
net.

### Stale-rules warning

At startup, after loading `TYPE_KEYWORD_RULES`, `classify` compares
`mtime(src/classifier/config/type_keywords.py)` against
`max(mtime(p) for p in input/classified_csv/**/*.csv)`. If the CSV is
newer, print:

```
!! WARNING: type_keywords.py is older than training data
   ({csv_mtime} > {rules_mtime}). Run: learn-type-keywords
```

Non-blocking — keyword inference still runs, but the user is told.

### Summary print extension

The existing "type fill outcomes" block grows one line:

```
type fill outcomes:
  preserved         266
  via_doc_no          0
  via_cross_ref       0
  via_cust_ref        0
  via_keyword         N
  empty               M
```

The cust-ref-fallback >10% warning unchanged.

### Code shape

- Modify: `src/classifier/cli/classify.py`.
- Two new imports: `pick_type` from `core.type_scoring`,
  `TYPE_KEYWORD_RULES` only for the stale check (lazy: use mtime, not
  attr).
- Estimated diff: +30 lines, -2 lines (the `via_cross_ref` docstring fix).

---

## Sub-project D — verification (no automated tests, but spec it)

Per standing user direction we don't write a pytest suite, but the
implementation plan must include a one-shot verification script the
implementer runs by hand. The script outputs three artifacts:

### 1. Leave-one-out evaluation

For each labeled row in the training set:
- Build rules from the other N−1 rows.
- Run `pick_type` on this row's title.
- Record (true_type, picked_type, confidence).

Prints per-class precision/recall/coverage and an overall summary:
- **Precision** = correct-high-confidence-picks / total-high-confidence-picks
- **Recall** = correct-high-confidence-picks / total-rows-of-this-class
- **Coverage** = high-confidence-picks / total-rows-of-this-class

Aim: ≥ 80% precision overall on classes with ≥ 4 training rows. Coverage
will vary by class; bucket-rich classes (DAS, PID, DAL) likely > 70%,
phrase-thin classes (DWG, LST) maybe 30-50%. That's a feature, not a
bug — keyword classifier is appropriately humble.

Rebuilding the rules N times is fast for N=256 (single-digit seconds).

### 2. Confusion matrix

Print the top 10 (true, picked) misclassification pairs and their
counts. Expected hot spots based on phrase overlap:
- `PID ↔ PFD` (both contain "DIAGRAM")
- `DAL ↔ DGA` (both contain "LAYOUT")
- `LST ↔ SCH` (both contain list-like keywords)

The matrix surfaces taxonomy bleed early so we can either tune weights
or accept the limit.

### 3. End-to-end pipeline check

Re-run the full pipeline against `input/To be classified/document.csv`
and capture the new `type fill outcomes` block. Expectation: a
non-trivial `via_keyword` count on the previously-559-empty rows.

The script lives at `scripts/eval_type_keywords.py` and is **not** an
entry point — it's a developer tool. Output is printed to stdout; no
files written.

---

## Risks and mitigations

| Risk                                                          | Mitigation |
|---------------------------------------------------------------|------------|
| Training data is one project (sahild)                         | Walker already supports `classified_csv/**`; today it's one CSV, future CSVs land transparently |
| Project-specific tokens (`SAHIL`, `CDS`) skew scores          | Auto-stopword (>40% frequency) catches them; no manual maintenance |
| Tiny classes generate fragile rules                            | `MIN_CLASS_DOCS = 4` excludes them entirely; documented in `UNTRAINED_TYPES` |
| Overlapping n-gram inflation                                  | Longest-match span consumption at scoring time |
| `precision_like = in / (in + out)` rewards rare phrases unfairly | `log1p(in_class)` support term tempers this; minimum-occurrence filter (`in_class >= 2`) catches the worst |
| Training/inference token drift                                | Single `canonicalize_title` function; both consumers import from `core/type_scoring` |
| Generated file goes stale silently                            | `classify` warns at startup if CSV newer than rules file |
| User edits `type_keywords.py` by hand                          | File header explicitly says "Do not edit by hand"; type signature is `tuple[tuple, ...]` to discourage mutation |

## Acceptance

1. `learn-type-keywords` produces `src/classifier/config/type_keywords.py`
   with rules for the 12-16 eligible classes; `UNTRAINED_TYPES` lists
   the others.
2. Re-running `learn-type-keywords` is byte-identical (determinism).
3. `classify` uses `pick_type` as tier-5 fill, with `via_keyword`
   reported in the summary; the existing four tiers are unchanged.
4. `classify` falls back to `pick_type → BUCKET_TO_CLASS` for
   `doc_type` when alias fold fails and confidence is high.
5. `classify` prints a one-line warning if `type_keywords.py` is older
   than the training CSV.
6. `scripts/eval_type_keywords.py` runs leave-one-out, prints precision /
   recall / coverage per class, and shows the top-10 confusion pairs.
7. Generated file metadata header includes source-paths line, ISO-8601
   timestamp, training row count, and dropped-class list.
