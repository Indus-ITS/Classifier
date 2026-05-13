# Type-keyword Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mine signature phrases from labeled training titles in `input/classified_csv/**/*.csv`, then score new titles against them in `classify` to fill `type` (and derive `doc_type`) when the lookup tier misses.

**Architecture:** A new `core/type_scoring.py` module owns the shared tokenizer + the at-inference scorer/picker. A new `tools/learn_type_keywords.py` writes the generated `config/type_keywords.py`. `cli/classify.py` calls `pick_type` as the fifth tier in its existing fill chain. A `scripts/eval_type_keywords.py` runs leave-one-out for hand-verification.

**Tech Stack:** Python 3.10+, pandas (already a dep), stdlib only otherwise. No new deps.

**Verification:** No automated tests (standing user direction — commit `e872846`). Each task ends with a hand-verification step (inline smoke check or script output spot-check). Task 6 runs the leave-one-out evaluation.

**Spec:** `docs/superpowers/specs/2026-05-13-type-keyword-classifier-design.md`

---

## File map

**Created:**
- `src/classifier/core/type_scoring.py` — `canonicalize_title`, `score_types`, `pick_type`, `MIN_SCORE`, `MIN_MARGIN`. Built across Tasks 1 + 3.
- `src/classifier/tools/learn_type_keywords.py` — generator entry point.
- `src/classifier/config/type_keywords.py` — generated file (committed; written by Task 2).
- `scripts/eval_type_keywords.py` — developer eval script (not an entry point).

**Modified:**
- `src/classifier/cli/classify.py` — wire `pick_type` into tier 5; add stale-rules warning; extend `_normalize_doc_type` fallback.
- `pyproject.toml` — add `learn-type-keywords` entry point.

---

## Task 1: Tokenizer + module scaffolding

**Files:**
- Create: `src/classifier/core/type_scoring.py`

- [ ] **Step 1: Write the scaffolding module with `canonicalize_title` and the confidence constants**

```python
"""Type-level keyword scoring.

Public API:

* ``canonicalize_title(raw)``  - shared between the learner
  (``classifier.tools.learn_type_keywords``) and the inference scorer.
  Both consumers MUST go through this function so training and
  inference never drift.
* ``score_types(title)`` and ``pick_type(scores)`` - inference. Added
  in a later task (still empty in this commit).
* ``MIN_SCORE`` / ``MIN_MARGIN`` - confidence knobs for ``pick_type``.

See ``docs/superpowers/specs/2026-05-13-type-keyword-classifier-design.md``
for the full design.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Sequence

# Confidence knobs used by pick_type (added in a later task). Tunable
# by editing this file; not exposed on the CLI.
MIN_SCORE: float = 2.0
MIN_MARGIN: float = 1.0

# Connector words that carry no classification signal. Used by both the
# learner (when emitting n-grams) and the scorer (when building
# candidate phrases). Auto-suppressed project-specific tokens (e.g.
# SAHIL, CDS) are computed at learn time from training frequency, not
# stored here.
STOP_TOKENS: frozenset[str] = frozenset({
    "FOR", "AND", "OR", "OF", "THE", "TO", "WITH",
    "ON", "IN", "AT", "FROM", "INTO", "A", "AN",
})

_DASHES = str.maketrans({
    "‐": " ", "‑": " ", "‒": " ",
    "–": " ", "—": " ", "―": " ",
    "−": " ", " ": " ",
})
_PARENS_RE = re.compile(r"\([^)]*\)")
_REV_NOISE_RE = re.compile(
    r"\b("
    r"\d+\s*SHEETS?"
    r"|REV\s*\d+"
    r"|SHEET\s+\d+\s+OF\s+\d+"
    r")\b"
)
_PUNCT_KEEP_AMP_SLASH_RE = re.compile(r"[^A-Z0-9&/ ]+")
_WS_RE = re.compile(r"\s+")


def canonicalize_title(raw: str) -> list[str]:
    """Canonical token list for a document title.

    Pipeline:
      1. NFKC, uppercase, fold dashes / NBSP to space.
      2. Drop parenthesized groups: ``(8 SHEETS)``, ``(NEW)`` -> "".
      3. Drop trailing/embedded revision-and-sheet noise:
         ``5 SHEETS``, ``REV 2``, ``SHEET 3 OF 5``.
      4. Strip remaining punctuation except ``&`` and ``/``
         (preserves "DATA & INSTRUMENT", "DCS/ESD/F&G").
      5. Collapse whitespace; split into tokens.
      6. No stop-word filtering here - that happens at the n-gram step
         in learner / scorer.
    """
    if not raw:
        return []
    s = unicodedata.normalize("NFKC", str(raw))
    s = s.translate(_DASHES)
    s = s.upper()
    s = _PARENS_RE.sub(" ", s)
    s = _REV_NOISE_RE.sub(" ", s)
    s = _PUNCT_KEEP_AMP_SLASH_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return []
    return s.split(" ")


def _ngrams(tokens: Sequence[str], n: int) -> list[tuple[str, ...]]:
    """All length-``n`` token tuples in order. Empty when too few tokens."""
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def candidate_phrases(tokens: Sequence[str],
                       extra_stop: frozenset[str] = frozenset()) -> list[tuple[str, ...]]:
    """1/2/3-grams from ``tokens``, dropping any n-gram containing a stop token.

    ``extra_stop`` extends the curated ``STOP_TOKENS`` set with run-time
    auto-suppressed tokens (e.g. project-specific noise discovered at
    learn time). Used by both the learner and the scorer.
    """
    stop = STOP_TOKENS | extra_stop
    out: list[tuple[str, ...]] = []
    for n in (1, 2, 3):
        for ng in _ngrams(tokens, n):
            if any(tok in stop for tok in ng):
                continue
            out.append(ng)
    return out
```

- [ ] **Step 2: Smoke-test `canonicalize_title` end-to-end**

Run:
```
.venv/Scripts/python -c "
from classifier.core.type_scoring import canonicalize_title, candidate_phrases

# basic cases
assert canonicalize_title('PROCESS DATA SHEET FOR PUMPS') == ['PROCESS','DATA','SHEET','FOR','PUMPS']
assert canonicalize_title('') == []
assert canonicalize_title(None) == []

# punctuation: keep & and /; drop the rest
assert canonicalize_title('PIPING & INSTRUMENT DIAGRAM, NEW') == ['PIPING','&','INSTRUMENT','DIAGRAM','NEW']
assert canonicalize_title('DCS/ESD/F&G - SAHIL CDS') == ['DCS/ESD/F&G','SAHIL','CDS']

# parentheticals dropped wholesale
assert canonicalize_title('SINGLE LINE DIAGRAM (5 SHEETS)') == ['SINGLE','LINE','DIAGRAM']
assert canonicalize_title('MATERIAL SELECTION DIAGRAM (NEW)') == ['MATERIAL','SELECTION','DIAGRAM']

# bare revision-noise tokens dropped
assert canonicalize_title('REPORT REV 3') == ['REPORT']
assert canonicalize_title('LAYOUT SHEET 1 OF 4') == ['LAYOUT']
assert canonicalize_title('LAYOUT 8 SHEETS') == ['LAYOUT']

# dashes fold to space (em-dash, en-dash, hyphen all gone)
assert canonicalize_title('A–B—C-D') == ['A','B','C','D']

# unicode normalization (NBSP)
assert canonicalize_title('A B') == ['A','B']

# candidate_phrases drops n-grams containing stop tokens
toks = ['PROCESS','DATA','SHEET','FOR','PUMPS']
phrases = candidate_phrases(toks)
strs = {' '.join(p) for p in phrases}
assert 'PROCESS DATA SHEET' in strs
assert 'DATA SHEET' in strs
assert 'DATA SHEET FOR' not in strs    # 'FOR' is a stop
assert 'FOR PUMPS' not in strs
assert 'FOR' not in strs
print('canonicalize ok')
"
```
Expected: prints `canonicalize ok` and exits 0.

- [ ] **Step 3: Commit**

```bash
git add src/classifier/core/type_scoring.py
git commit -m "feat(core): canonicalize_title + candidate_phrases for type scoring

Shared tokenizer for the learner and the inference scorer. NFKC,
uppercase, drop parentheticals + revision/sheet noise, preserve & and
/, fold dashes. candidate_phrases emits 1/2/3-grams with stop-token
filtering. score_types and pick_type land in a later task."
```

---

## Task 2: `learn-type-keywords` tool + generated config

**Files:**
- Create: `src/classifier/tools/learn_type_keywords.py`
- Create (generated): `src/classifier/config/type_keywords.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the learner**

```python
"""Generate ``classifier.config.type_keywords`` from labeled CSVs.

Walks ``input/classified_csv/**/*.csv`` (sorted), collects
``(type, title)`` pairs for rows where ``type`` is in the canonical
``KNOWN_TYPES`` enum, and emits a deterministic mapping of
``{type: ((phrase, weight), ...)}`` to
``src/classifier/config/type_keywords.py``.

Scoring per (type, phrase):

    in_class    = rows of this type containing the phrase
    outside     = rows of other types containing the phrase
    precision   = in_class / (in_class + outside)
    support     = log1p(in_class)
    final_score = precision * support

Filters (all must pass):
  * in_class >= MIN_PHRASE_OCCURRENCES
  * outside < in_class
  * precision >= PRECISION_FLOOR

Class eligibility:
  * type has >= MIN_CLASS_DOCS training rows. Classes below the
    threshold appear in UNTRAINED_TYPES with their actual count.

Auto-stopword:
  * Any token appearing in > AUTO_STOP_FREQ of training titles is
    treated as a stop token (in addition to the curated STOP_TOKENS
    in ``classifier.core.type_scoring``).

Run from project root::

    learn-type-keywords
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from classifier.config.type_enum import KNOWN_TYPES
from classifier.core.type_scoring import (
    STOP_TOKENS,
    candidate_phrases,
    canonicalize_title,
)
from classifier.io.normalize import is_empty

CSV_ROOT = Path("input/classified_csv")
OUT_PATH = Path("src/classifier/config/type_keywords.py")

MIN_CLASS_DOCS: int = 4
MIN_PHRASE_OCCURRENCES: int = 2
PRECISION_FLOOR: float = 0.6
AUTO_STOP_FREQ: float = 0.40    # token in > 40% of titles -> stop
TOP_PHRASES_PER_TYPE: int = 10


def _collect_rows() -> list[tuple[str, str, Path]]:
    """Yield ``(type, title, source_path)`` for every eligible row."""
    rows: list[tuple[str, str, Path]] = []
    csv_paths = sorted(CSV_ROOT.rglob("*.csv"), key=lambda p: str(p).lower())
    for p in csv_paths:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[])
        if not {"type", "title"}.issubset(df.columns):
            print(f"  [skip] {p}: missing 'type' or 'title' column")
            continue
        for _, row in df.iterrows():
            if is_empty(row["title"]) or is_empty(row["type"]):
                continue
            t = str(row["type"]).strip().upper()
            if t not in KNOWN_TYPES:
                continue
            rows.append((t, str(row["title"]), p))
    return rows


def _auto_stopwords(token_lists: list[list[str]]) -> frozenset[str]:
    """Tokens appearing in > AUTO_STOP_FREQ of all titles."""
    if not token_lists:
        return frozenset()
    doc_count_for: Counter[str] = Counter()
    for toks in token_lists:
        for tok in set(toks):
            doc_count_for[tok] += 1
    threshold = AUTO_STOP_FREQ * len(token_lists)
    return frozenset(t for t, n in doc_count_for.items() if n > threshold)


def learn(rows: Iterable[tuple[str, str, Path]]
          ) -> tuple[dict[str, tuple[tuple[str, float], ...]],
                      Counter[str],
                      frozenset[str]]:
    """Return ``(rules, class_counts, untrained_types)``.

    rules:           {type_code: ((phrase_text, weight), ...)} sorted within type
    class_counts:    Counter of training-row counts per type code seen
    untrained_types: KNOWN_TYPES minus the rule-eligible classes
    """
    rows = list(rows)
    class_counts: Counter[str] = Counter(t for t, _, _ in rows)

    # Per-row canonical tokens.
    tokenized: list[tuple[str, list[str]]] = [
        (t, canonicalize_title(title)) for t, title, _ in rows
    ]
    auto_stop = _auto_stopwords([toks for _, toks in tokenized])

    # Per-row candidate phrase set (de-duped within row).
    row_phrases: list[tuple[str, set[tuple[str, ...]]]] = []
    for t, toks in tokenized:
        phrases = set(candidate_phrases(toks, extra_stop=auto_stop))
        row_phrases.append((t, phrases))

    # phrase_in_class[(type, phrase)] = count
    phrase_in_class: defaultdict[tuple[str, tuple[str, ...]], int] = defaultdict(int)
    # phrase_total[phrase] = count across all rows
    phrase_total: defaultdict[tuple[str, ...], int] = defaultdict(int)
    for t, phrases in row_phrases:
        for ph in phrases:
            phrase_in_class[(t, ph)] += 1
            phrase_total[ph] += 1

    eligible: set[str] = {t for t, n in class_counts.items() if n >= MIN_CLASS_DOCS}

    rules: dict[str, tuple[tuple[str, float], ...]] = {}
    for t in sorted(eligible):
        bag: list[tuple[float, str]] = []
        for (ct, ph), in_class in phrase_in_class.items():
            if ct != t:
                continue
            if in_class < MIN_PHRASE_OCCURRENCES:
                continue
            outside = phrase_total[ph] - in_class
            if outside >= in_class:
                continue
            precision = in_class / (in_class + outside)
            if precision < PRECISION_FLOOR:
                continue
            score = precision * math.log1p(in_class)
            bag.append((score, " ".join(ph)))
        bag.sort(key=lambda x: (-x[0], x[1]))
        rules[t] = tuple((phrase, round(score, 4)) for score, phrase in bag[:TOP_PHRASES_PER_TYPE])

    untrained = frozenset(KNOWN_TYPES) - eligible
    return rules, class_counts, untrained


def render(rules: dict[str, tuple[tuple[str, float], ...]],
           class_counts: Counter[str],
           untrained: frozenset[str],
           n_rows: int,
           source_root: Path) -> str:
    """Render the generated module text."""
    now = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    untrained_list = ", ".join(
        f"{t} ({class_counts.get(t, 0)})" for t in sorted(untrained)
    )

    lines: list[str] = []
    lines.append('"""Generated by ``learn-type-keywords``. Do not edit by hand.')
    lines.append("")
    lines.append(f"Source: {source_root.as_posix()}/**/*.csv")
    lines.append(f"Generated: {now}")
    lines.append(f"Training rows used: {n_rows}")
    if untrained_list:
        lines.append("")
        lines.append(f"Untrained types (< {MIN_CLASS_DOCS} examples, no rules emitted):")
        lines.append(f"  {untrained_list}")
    lines.append('"""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("UNTRAINED_TYPES: frozenset[str] = frozenset({")
    for t in sorted(untrained):
        lines.append(f"    {t!r},")
    lines.append("})")
    lines.append("")
    lines.append("TYPE_KEYWORD_RULES: dict[str, tuple[tuple[str, float], ...]] = {")
    for t in sorted(rules):
        lines.append(f"    {t!r}: (")
        for phrase, score in rules[t]:
            lines.append(f"        ({phrase!r}, {score}),")
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not CSV_ROOT.exists():
        raise SystemExit(f"csv dir not found: {CSV_ROOT}")

    rows = _collect_rows()
    if not rows:
        raise SystemExit(f"no eligible (type, title) rows found under {CSV_ROOT}")

    rules, class_counts, untrained = learn(rows)
    text = render(rules, class_counts, untrained, len(rows), CSV_ROOT)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8", newline="\n")

    print(f"Wrote {OUT_PATH}")
    print(f"  training rows:    {len(rows)}")
    print(f"  classes eligible: {len(rules)}")
    print(f"  classes untrained: {len(untrained)}")
    print(f"  top phrases per class (sample):")
    for t in sorted(rules)[:3]:
        sample = ", ".join(f"{p!r}" for p, _ in rules[t][:3])
        print(f"    {t}: {sample}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Register the entry point**

Open `pyproject.toml`. In the `[project.scripts]` block, add a fourth line (after `build-type-enum`):

```toml
learn-type-keywords = "classifier.tools.learn_type_keywords:main"
```

Final block should read:
```toml
[project.scripts]
classify            = "classifier.cli.classify:main"
convert-classified  = "classifier.tools.convert_classified:main"
build-type-enum     = "classifier.tools.build_type_enum:main"
learn-type-keywords = "classifier.tools.learn_type_keywords:main"
```

- [ ] **Step 3: Reinstall so the console script registers**

Run: `.venv/Scripts/python -m pip install -e .`
Expected: `Successfully installed classifier-0.1.0`.

(The bare `.venv/Scripts/pip install -e .` form may exit with empty output on Windows; use `python -m pip` per the Task-7 pattern from the previous plan.)

- [ ] **Step 4: Run the learner**

Run: `.venv/Scripts/python -m classifier.tools.learn_type_keywords`
Expected: prints
```
Wrote src\classifier\config\type_keywords.py
  training rows:    256
  classes eligible: 15
  classes untrained: 16
  top phrases per class (sample):
    CAL: ...
    DAL: ...
    DAS: ...
```
(Exact "eligible" count is 15 if all classes with ≥4 examples qualify — DAL, DAS, REP, PID, SPC, DSL, DWG, LST, DGA, REQ, CAL, PFD, MSD, SCH, STD. Untrained = 16: BOD, BOM, DBD, DCE, DHZ, DPP, DSD, DWD, IDX, MTO, PHL, PLN, PRO, PSF, REG, SOW.)

- [ ] **Step 5: Spot-check the generated file**

Run:
```
.venv/Scripts/python -c "
from classifier.config.type_keywords import TYPE_KEYWORD_RULES, UNTRAINED_TYPES
print('eligible:', sorted(TYPE_KEYWORD_RULES))
print('untrained:', sorted(UNTRAINED_TYPES))
print()
for t in ('DAS', 'PID', 'SPC'):
    print(f'{t}:')
    for phrase, score in TYPE_KEYWORD_RULES[t][:5]:
        print(f'  {score:.3f}  {phrase!r}')
"
```
Expected: eligible list contains exactly 15 codes; untrained contains the 16 codes listed above. DAS should include `'PROCESS DATA SHEET'` or `'DATA SHEET'` near the top. PID should include `'PIPING & INSTRUMENT DIAGRAM'` near the top. SPC should include `'SPECIFICATION'` near the top.

- [ ] **Step 6: Determinism check (re-run produces byte-identical file)**

Run:
```
.venv/Scripts/python -c "
import hashlib, pathlib, subprocess, sys
p = pathlib.Path('src/classifier/config/type_keywords.py')
# Strip the volatile 'Generated:' timestamp line for the determinism check;
# everything else (rules, untrained list, row count) must be identical.
def normalize(text):
    return '\n'.join(ln for ln in text.splitlines() if not ln.startswith('Generated:'))
before = hashlib.sha256(normalize(p.read_text(encoding='utf-8')).encode('utf-8')).hexdigest()
subprocess.run([sys.executable, '-m', 'classifier.tools.learn_type_keywords'], check=True, capture_output=True)
after = hashlib.sha256(normalize(p.read_text(encoding='utf-8')).encode('utf-8')).hexdigest()
assert before == after, 'non-deterministic content (timestamp ignored)'
print('deterministic ok')
"
```
Expected: prints `deterministic ok`. (The `Generated:` line legitimately changes per run; everything else — rules, untrained list, source path, row count — must be byte-identical.)

- [ ] **Step 7: Commit**

```bash
git add src/classifier/tools/learn_type_keywords.py \
        src/classifier/config/type_keywords.py \
        pyproject.toml
git commit -m "feat(tools): learn-type-keywords mines signature phrases per type

Walks input/classified_csv/, computes precision*log(support) per
(type, n-gram), and emits TYPE_KEYWORD_RULES + UNTRAINED_TYPES to
src/classifier/config/type_keywords.py. Filters: MIN_CLASS_DOCS=4,
MIN_PHRASE_OCCURRENCES=2, PRECISION_FLOOR=0.6, auto-stop on tokens
>40% global frequency."
```

---

## Task 3: `score_types` and `pick_type`

**Files:**
- Modify: `src/classifier/core/type_scoring.py` (append; nothing in the existing module changes)

- [ ] **Step 1: Append `score_types` and `pick_type` to the module**

Open `src/classifier/core/type_scoring.py` and append the following at the end (after `candidate_phrases`):

```python


def _index_phrases_in(tokens: Sequence[str], phrase_tokens: Sequence[str]) -> int:
    """Return the start index where ``phrase_tokens`` occurs in ``tokens``, or -1.

    Plain linear scan; only the first occurrence is reported (we don't
    score the same phrase twice in one title even if it repeats).
    """
    n, m = len(tokens), len(phrase_tokens)
    if m == 0 or m > n:
        return -1
    for i in range(n - m + 1):
        if all(tokens[i + j] == phrase_tokens[j] for j in range(m)):
            return i
    return -1


def score_types(title: str) -> dict[str, float]:
    """Cumulative score per type code from matching the configured rules.

    Algorithm, per type:
      1. Iterate (phrase, weight) in the order stored in the rules file
         (highest weight first).
      2. For each phrase, find its position in the title's token list.
         If found in a SPAN that hasn't already been consumed (by an
         earlier higher-weight phrase for the same type), record the
         match and consume that span. This prevents an overlapping
         shorter n-gram from double-counting (longest/highest-weight
         match wins).
      3. Span consumption is per-type. Different types match
         independently against the same tokens.

    Types absent from the result dict had no matches.
    """
    # Import lazily so the module is still importable when
    # type_keywords.py hasn't been generated yet.
    from classifier.config.type_keywords import TYPE_KEYWORD_RULES

    tokens = canonicalize_title(title)
    if not tokens:
        return {}

    scores: dict[str, float] = {}
    for type_code, rules in TYPE_KEYWORD_RULES.items():
        consumed: list[tuple[int, int]] = []  # list of (start, end) half-open
        total = 0.0
        for phrase_text, weight in rules:
            phrase = phrase_text.split(" ")
            start = _index_phrases_in(tokens, phrase)
            if start < 0:
                continue
            end = start + len(phrase)
            if any(not (end <= cs or start >= ce) for cs, ce in consumed):
                continue  # overlaps an already-consumed span
            consumed.append((start, end))
            total += weight
        if total > 0:
            scores[type_code] = total
    return scores


def pick_type(scores: dict[str, float]) -> dict:
    """Return ``{type, score, runner_up, runner_up_score, confidence}``.

    Confidence:
      * ``high`` iff top >= MIN_SCORE and (top - runner_up) >= MIN_MARGIN
      * ``low``  iff top >= MIN_SCORE and (top - runner_up) <  MIN_MARGIN
      * ``none`` otherwise (no matches, or top < MIN_SCORE)

    Ties broken alphabetically.
    """
    if not scores:
        return {
            "type": "", "score": 0.0,
            "runner_up": "", "runner_up_score": 0.0,
            "confidence": "none",
        }
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_code, top_score = ranked[0]
    if len(ranked) > 1:
        rup_code, rup_score = ranked[1]
    else:
        rup_code, rup_score = "", 0.0
    if top_score < MIN_SCORE:
        confidence = "none"
    elif (top_score - rup_score) < MIN_MARGIN:
        confidence = "low"
    else:
        confidence = "high"
    return {
        "type": top_code if confidence != "none" else "",
        "score": top_score,
        "runner_up": rup_code,
        "runner_up_score": rup_score,
        "confidence": confidence,
    }
```

- [ ] **Step 2: Smoke-test against the generated rules**

Run:
```
.venv/Scripts/python -c "
from classifier.core.type_scoring import score_types, pick_type

# A representative title for each of three high-coverage classes.
cases = [
    ('PROCESS DATA SHEET FOR WATER DISPOSAL PUMPS', 'DAS'),
    ('PIPING & INSTRUMENT DIAGRAM MULTIPHASE FLOWMETER FT-0604', 'PID'),
    ('SPECIFICATION FOR HV POWER CABLES', 'SPC'),
    ('PROCESS FLOW DIAGRAM - WATER TREATMENT AND FUEL GAS', 'PFD'),
    ('MATERIAL REQUISITION FOR CONTROL VALVES', 'REQ'),
]
for title, expected in cases:
    scores = score_types(title)
    pick = pick_type(scores)
    flag = 'OK' if pick['type'] == expected else 'FAIL'
    print(f'{flag}  expected={expected:5s}  got={pick[\"type\"]:5s}  '
          f'conf={pick[\"confidence\"]:5s}  score={pick[\"score\"]:.2f}  '
          f'runner_up={pick[\"runner_up\"]!s}:{pick[\"runner_up_score\"]:.2f}  '
          f'title={title!r}')
print()

# An adversarial low-signal title - should get 'none' or 'low'.
weak = score_types('UNKNOWN TITLE ABOUT NOTHING IN PARTICULAR')
print('weak title pick:', pick_type(weak))

# An empty title.
empty = score_types('')
print('empty title pick:', pick_type(empty))
"
```
Expected:
- The 5 representative cases all print `OK` with `conf=high`.
- The weak title prints a pick with `confidence=none` (or `low` at worst).
- The empty title prints `{'type': '', 'score': 0.0, ..., 'confidence': 'none'}`.

If a case prints `FAIL`, do not commit — investigate whether the rule weights / threshold need tuning, or whether the spec needs revision.

- [ ] **Step 3: Commit**

```bash
git add src/classifier/core/type_scoring.py
git commit -m "feat(core): score_types + pick_type with absolute-margin confidence

Per-type longest-match span consumption prevents overlapping n-gram
inflation. pick_type gates 'high' on (top - runner_up) >= MIN_MARGIN
in addition to top >= MIN_SCORE so weak-but-distinct cases stay 'low'.
Lazily imports TYPE_KEYWORD_RULES so the module remains importable
before the generator runs the first time."
```

---

## Task 4: Integrate into `classify.py`

**Files:**
- Modify: `src/classifier/cli/classify.py`

- [ ] **Step 1: Add the new import**

Open `src/classifier/cli/classify.py`. Find the import block near the top. Replace:

```python
from classifier.core.scoring import fold_to_class, pick_bucket, score_buckets
```

with:

```python
from classifier.config.buckets import TYPE_TO_BUCKET
from classifier.core.scoring import fold_to_class, pick_bucket, score_buckets
from classifier.core.type_scoring import pick_type, score_types
```

Then under the existing path constants block (where `CLASSIFIED_CSV_DIR` lives), add:

```python
TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")
```

- [ ] **Step 2: Replace `_normalize_doc_type` to use keyword inference before bucket scoring**

Find the existing `_normalize_doc_type` function and replace it entirely with:

```python
def _normalize_doc_type(value: str, title: str, description: str) -> tuple[str, str]:
    """Return ``(normalized, reason)``.

    reason is one of: ``existing``, ``via_keyword``, ``scored``.

    Path:
      1. Existing value normalizes to drawing/document via the aliases.
      2. Else: pick_type(title); if confidence=='high', fold via
         TYPE_TO_BUCKET + BUCKET_TO_CLASS to drawing/document.
      3. Else: bucket-level score_buckets fallback; Undefined -> document.
    """
    if not is_empty(value):
        v = str(value).strip().lower()
        if v in DRAWING_ALIASES:
            return "drawing", "existing"
        if v in DOCUMENT_ALIASES:
            return "document", "existing"
    pick = pick_type(score_types(title))
    if pick["confidence"] == "high":
        bucket = TYPE_TO_BUCKET.get(pick["type"])
        if bucket is not None:
            folded = BUCKET_TO_CLASS[bucket]
            return ("drawing" if folded == "Drawings" else "document"), "via_keyword"
    scores = score_buckets(title, description)
    bucket_pick = pick_bucket(scores)
    folded = fold_to_class(bucket_pick, BUCKET_TO_CLASS)
    return ("drawing" if folded == "Drawings" else "document"), "scored"
```

- [ ] **Step 3: Extend `_fill_type` to add tier 5 (via_keyword)**

Find the existing `_fill_type` function and replace it entirely with:

```python
def _fill_type(row_type: str, doc_no: str, cust_ref: str,
               title: str, lookup: TypeLookup) -> tuple[str, str]:
    """Return ``(value, reason)``.

    reason is one of: ``preserved``, ``via_doc_no``, ``via_cross_ref``,
    ``via_cust_ref``, ``via_keyword``, ``empty``.

    Tiers (first non-empty wins):
      1. existing value (preserved).
      2. ``input.document_no`` against ``lookup.by_doc_no``.
         Reason: ``via_doc_no``.
      3. ``input.customer_ref`` against ``lookup.by_doc_no`` - the
         input's ``customer_ref`` typically carries the original
         document number that appears as ``document_no`` in the
         canonical index. This is the dominant healthy fill path on
         the current dataset, because the input system uses a different
         identifier scheme for the same record.
         Reason: ``via_cross_ref``.
      4. ``input.customer_ref`` against ``lookup.by_cust_ref`` - only
         fires when a canonical CSV ever populates its own
         ``customer_ref`` column (currently always empty on this
         dataset).
         Reason: ``via_cust_ref``.
      5. ``pick_type(title)`` with confidence == 'high'.
         Reason: ``via_keyword``.
      6. Miss -> empty.
    """
    if not is_empty(row_type):
        return str(row_type).strip(), "preserved"
    k_doc = normalize_lookup_key(doc_no)
    if k_doc and k_doc in lookup.by_doc_no:
        return lookup.by_doc_no[k_doc], "via_doc_no"
    k_cust = normalize_lookup_key(cust_ref)
    if k_cust:
        if k_cust in lookup.by_doc_no:
            return lookup.by_doc_no[k_cust], "via_cross_ref"
        if k_cust in lookup.by_cust_ref:
            return lookup.by_cust_ref[k_cust], "via_cust_ref"
    pick = pick_type(score_types(title))
    if pick["confidence"] == "high":
        return pick["type"], "via_keyword"
    return "", "empty"
```

- [ ] **Step 4: Pass `title` into `_fill_type` from `main`**

Inside `main()`, find the call site:

```python
            new_type, t_reason = _fill_type(
                out["type"], out["document_no"], out["customer_ref"], lookup,
            )
```

Replace with:

```python
            new_type, t_reason = _fill_type(
                out["type"], out["document_no"], out["customer_ref"],
                out["title"], lookup,
            )
```

- [ ] **Step 5: Add the stale-rules warning at the top of `main`**

Right after the `df = pd.read_csv(...)` line and the `validate_schema(df.columns)` line, add:

```python
    # Warn if type_keywords.py is older than any training CSV. Non-blocking.
    if TYPE_KEYWORDS_PATH.exists():
        rules_mtime = TYPE_KEYWORDS_PATH.stat().st_mtime
        csv_mtimes = [
            p.stat().st_mtime for p in CLASSIFIED_CSV_DIR.rglob("*.csv")
        ]
        if csv_mtimes and max(csv_mtimes) > rules_mtime:
            print("!! WARNING: type_keywords.py is older than training data. "
                  "Run: learn-type-keywords")
```

Place it directly between `validate_schema(df.columns)` and `lookup = build_lookup(CLASSIFIED_CSV_DIR)`.

- [ ] **Step 6: Update the summary print to include `via_keyword`**

Find the summary block:

```python
    print("type fill outcomes:")
    for k in ("preserved", "via_doc_no", "via_cross_ref", "via_cust_ref", "empty"):
        print(f"  {k:14s} {type_reason.get(k, 0):>6}")
```

Replace with:

```python
    print("type fill outcomes:")
    for k in ("preserved", "via_doc_no", "via_cross_ref",
              "via_cust_ref", "via_keyword", "empty"):
        print(f"  {k:14s} {type_reason.get(k, 0):>6}")
```

And update the `fills` computation a few lines above to include `via_keyword`:

```python
    fills = (type_reason["via_doc_no"]
             + type_reason["via_cross_ref"]
             + type_reason["via_cust_ref"]
             + type_reason["via_keyword"])
```

- [ ] **Step 7: Run classify end-to-end**

Run: `.venv/Scripts/python -m classifier.cli.classify`
Expected: prints `Wrote output\classified.csv  (825 rows)` followed by the summary. The `type fill outcomes` block now has a `via_keyword` line with a non-zero count (likely > 100 on the previously-empty 559 rows).

- [ ] **Step 8: Verify schema preservation invariant still holds**

Run:
```
.venv/Scripts/python -c "
import pandas as pd
from classifier.io.schema import TARGET_COLUMNS, validate_schema
src = pd.read_csv('input/To be classified/document.csv', dtype=str, keep_default_na=False, na_values=[])
dst = pd.read_csv('output/classified.csv', dtype=str, keep_default_na=False, na_values=[])
validate_schema(src.columns); validate_schema(dst.columns)
assert len(src) == len(dst), (len(src), len(dst))
assert list(src.columns) == list(dst.columns) == list(TARGET_COLUMNS)
for c in TARGET_COLUMNS:
    if c in ('doc_type', 'type'): continue
    assert (src[c].fillna('') == dst[c].fillna('')).all(), f'changed: {c}'
print(f'ok: {len(src)} rows, only doc_type/type modified')
"
```
Expected: `ok: 825 rows, only doc_type/type modified`.

- [ ] **Step 9: Spot-check 5 newly-keyword-filled rows**

Run:
```
.venv/Scripts/python -c "
import pandas as pd
src = pd.read_csv('input/To be classified/document.csv', dtype=str, keep_default_na=False, na_values=[])
dst = pd.read_csv('output/classified.csv', dtype=str, keep_default_na=False, na_values=[])

# Rows that were empty in src and now have a type in dst
mask = (src['type'].isin(['', 'NULL'])) & (~dst['type'].isin(['', 'NULL']))
print('rows newly-filled:', mask.sum())
print(dst.loc[mask, ['document_no','title','type','doc_type']].head(5).to_string())
"
```
Expected: `rows newly-filled` > 0; the sample rows show plausible (title → type) pairings.

- [ ] **Step 10: Test the stale-rules warning fires**

Run:
```
touch -d "2020-01-01" src/classifier/config/type_keywords.py
.venv/Scripts/python -m classifier.cli.classify 2>&1 | head -3
```
Expected: the first line is `!! WARNING: type_keywords.py is older than training data. Run: learn-type-keywords`.

Restore the mtime so the warning doesn't fire on subsequent runs:
```
.venv/Scripts/python -m classifier.tools.learn_type_keywords > /dev/null
```

- [ ] **Step 11: Commit**

```bash
git add src/classifier/cli/classify.py output/classified.csv \
        src/classifier/config/type_keywords.py
git commit -m "feat(classify): tier-5 keyword fill + doc_type via_keyword fallback

_fill_type adds via_keyword between cust_ref fallback and empty.
_normalize_doc_type uses pick_type ahead of the bucket scorer when
existing doc_type aliases don't fold. classify warns if
type_keywords.py is older than the training CSV. Summary block adds
the via_keyword line."
```

---

## Task 5: Evaluation script

**Files:**
- Create: `scripts/eval_type_keywords.py`

- [ ] **Step 1: Create the scripts directory**

Run: `mkdir -p scripts`

- [ ] **Step 2: Write the eval script**

```python
"""Leave-one-out evaluation of the type-keyword classifier.

For each training row R:
  * Re-learn rules from all training rows except R.
  * Score R's title against the leave-one-out rules.
  * Compare picked type to R's true type.

Prints:
  * Per-class precision / recall / coverage for classes with rules.
  * Overall confusion matrix (top mistaken pairings).
  * The new end-to-end ``classify`` summary for context.

Not an entry point. Run with::

    .venv/Scripts/python scripts/eval_type_keywords.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from classifier.core.type_scoring import (
    MIN_SCORE,
    candidate_phrases,
    canonicalize_title,
    pick_type,
)
from classifier.tools.learn_type_keywords import _collect_rows, learn


def _score_with_rules(title: str,
                       rules: dict[str, tuple[tuple[str, float], ...]]
                       ) -> dict[str, float]:
    """Mirror of score_types but against an explicitly-provided rules dict.

    Mirrors the per-type longest-match span consumption used by
    ``classifier.core.type_scoring.score_types``.
    """
    tokens = canonicalize_title(title)
    if not tokens:
        return {}
    scores: dict[str, float] = {}
    for type_code, type_rules in rules.items():
        consumed: list[tuple[int, int]] = []
        total = 0.0
        for phrase_text, weight in type_rules:
            phrase = phrase_text.split(" ")
            if not phrase or len(phrase) > len(tokens):
                continue
            found = -1
            for i in range(len(tokens) - len(phrase) + 1):
                if all(tokens[i + j] == phrase[j] for j in range(len(phrase))):
                    found = i
                    break
            if found < 0:
                continue
            end = found + len(phrase)
            if any(not (end <= cs or found >= ce) for cs, ce in consumed):
                continue
            consumed.append((found, end))
            total += weight
        if total > 0:
            scores[type_code] = total
    return scores


def main() -> None:
    rows = _collect_rows()
    print(f"loaded {len(rows)} training rows")

    # Precompute tokenization once.
    tokenized = [(t, title, canonicalize_title(title)) for t, title, _ in rows]

    # Per-class counters
    n_class: Counter[str] = Counter(t for t, _, _ in rows)
    tp: Counter[str] = Counter()          # picked == true (high confidence)
    picked_high: Counter[str] = Counter() # picked anything (high) for class
    confusions: Counter[tuple[str, str]] = Counter()
    coverage_class: defaultdict[str, list[bool]] = defaultdict(list)

    for i, (true_type, _, _) in enumerate(rows):
        loo = rows[:i] + rows[i+1:]
        rules, _, _ = learn(loo)
        title = rows[i][1]
        scores = _score_with_rules(title, rules)
        pick = pick_type(scores)
        if pick["confidence"] == "high":
            picked_high[pick["type"]] += 1
            coverage_class[true_type].append(True)
            if pick["type"] == true_type:
                tp[true_type] += 1
            else:
                confusions[(true_type, pick["type"])] += 1
        else:
            coverage_class[true_type].append(False)

    print()
    print(f"{'type':5s} {'support':>7s} {'prec':>6s} {'recall':>7s} {'cover':>6s}")
    for t in sorted(n_class):
        support = n_class[t]
        prec_denom = picked_high[t]
        prec = (tp[t] / prec_denom) if prec_denom else float("nan")
        rec = tp[t] / support if support else 0.0
        cov_list = coverage_class.get(t, [])
        cov = sum(cov_list) / len(cov_list) if cov_list else 0.0
        prec_str = f"{prec:6.2%}" if prec_denom else "  n/a "
        print(f"{t:5s} {support:>7d} {prec_str} {rec:>6.2%} {cov:>5.1%}")

    total_high = sum(picked_high.values())
    total_tp = sum(tp.values())
    overall_prec = (total_tp / total_high) if total_high else 0.0
    overall_cov = total_high / len(rows)
    print()
    print(f"overall: high-confidence picks = {total_high} / {len(rows)} "
          f"(coverage {overall_cov:.1%})")
    print(f"overall precision (high-confidence only): {overall_prec:.1%}")
    print(f"MIN_SCORE={MIN_SCORE}; one-off classes (< 4 rows) excluded from rules.")

    if confusions:
        print()
        print("top 10 (true -> picked) misclassifications:")
        for (true_t, picked_t), n in confusions.most_common(10):
            print(f"  {true_t:5s} -> {picked_t:5s}  x{n}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the eval**

Run: `.venv/Scripts/python scripts/eval_type_keywords.py`
Expected: prints
- A header `loaded 256 training rows`.
- A per-class table where rule-eligible classes (DAS, PID, SPC, DSL, …) have non-`n/a` precision values, generally above 70%. Tiny classes (BOM, IDX, DHZ, …) show coverage 0% (no rules predict them).
- An `overall` summary line with overall precision and coverage.
- A `top 10 (true -> picked) misclassifications` block, expected to feature PID/PFD and DAL/DGA confusions among the top entries.

If overall precision is below 70%, do not commit. Investigate which class is driving precision down and consider tightening `PRECISION_FLOOR` or `MIN_SCORE` defaults (and re-run learn-type-keywords + this script).

- [ ] **Step 4: Commit**

```bash
git add scripts/eval_type_keywords.py
git commit -m "feat(scripts): leave-one-out eval for type-keyword classifier

Per-class precision/recall/coverage plus top-10 confusion pairs.
Re-learns rules N times by holding each row out; honest-ish accuracy
estimate without writing a pytest suite."
```

---

## Task 6: Final acceptance sweep

**Files:** none (verification only)

- [ ] **Step 1: Acceptance battery**

Run:
```
.venv/Scripts/python -c "
import importlib, pathlib

# 1. New module imports cleanly
from classifier.core.type_scoring import (
    canonicalize_title, candidate_phrases,
    score_types, pick_type, MIN_SCORE, MIN_MARGIN,
)
print('A: type_scoring exports ok')

# 2. Generated config exports
from classifier.config.type_keywords import TYPE_KEYWORD_RULES, UNTRAINED_TYPES
assert len(TYPE_KEYWORD_RULES) >= 12, len(TYPE_KEYWORD_RULES)
assert len(UNTRAINED_TYPES) >= 12, len(UNTRAINED_TYPES)
print(f'B: rules={len(TYPE_KEYWORD_RULES)} types, untrained={len(UNTRAINED_TYPES)} types')

# 3. classify-side wiring imports
from classifier.cli.classify import _normalize_doc_type, _fill_type
import inspect
fill_sig = inspect.signature(_fill_type)
assert 'title' in fill_sig.parameters, list(fill_sig.parameters)
norm_sig = inspect.signature(_normalize_doc_type)
print(f'C: _fill_type params = {list(fill_sig.parameters)}')
print(f'C: _normalize_doc_type params = {list(norm_sig.parameters)}')

# 4. Three eligible-class signature phrases match
from classifier.core.type_scoring import score_types, pick_type
checks = [
    ('PROCESS DATA SHEET FOR FOOBAR', 'DAS'),
    ('PIPING & INSTRUMENT DIAGRAM XYZ', 'PID'),
    ('SPECIFICATION FOR HV POWER CABLES', 'SPC'),
]
for title, expected in checks:
    pick = pick_type(score_types(title))
    assert pick['type'] == expected, (title, pick)
print('D: signature phrases hit expected types')
"
```
Expected: four lines printed, all start with `A:`, `B:`, `C:`, `D:` — none raise.

- [ ] **Step 2: End-to-end pipeline parity check**

Run the three commands and confirm clean exit:
```
.venv/Scripts/python -m classifier.tools.convert_classified > /dev/null
.venv/Scripts/python -m classifier.tools.build_type_enum > /dev/null
.venv/Scripts/python -m classifier.tools.learn_type_keywords > /dev/null
.venv/Scripts/python -m classifier.cli.classify
```
Expected (from `classify`):
- `Wrote output\classified.csv  (825 rows)`
- Type fill outcomes block lists `via_keyword` with a non-zero count.
- No traceback.

- [ ] **Step 3: Determinism — re-run learner + classify, confirm output stable**

Run:
```
.venv/Scripts/python -c "
import hashlib, pathlib, subprocess, sys

p_out = pathlib.Path('output/classified.csv')
before = hashlib.sha256(p_out.read_bytes()).hexdigest()
subprocess.run([sys.executable, '-m', 'classifier.tools.learn_type_keywords'],
               check=True, capture_output=True)
subprocess.run([sys.executable, '-m', 'classifier.cli.classify'],
               check=True, capture_output=True)
after = hashlib.sha256(p_out.read_bytes()).hexdigest()
assert before == after, 'classify output not deterministic across re-learn'
print('deterministic across re-learn: ok')
"
```
Expected: `deterministic across re-learn: ok`.

- [ ] **Step 4: Confirm working tree is clean**

Run: `git status`
Expected: clean (no uncommitted changes).

No commit needed for Task 6 — verification only.
