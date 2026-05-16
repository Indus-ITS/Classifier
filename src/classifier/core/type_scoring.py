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
MIN_SCORE: float = 1.5
MIN_MARGIN: float = 1.0
SINGLE_PHRASE_FLOOR: float = 2.5

# Connector words that carry no classification signal. Used by both the
# learner (when emitting n-grams) and the scorer (when building
# candidate phrases). Auto-suppressed project-specific tokens (e.g.
# SAHIL, CDS) are computed at learn time from training frequency, not
# stored here.
STOP_TOKENS: frozenset[str] = frozenset({
    "FOR", "AND", "OR", "OF", "THE", "TO", "WITH",
    "ON", "IN", "AT", "FROM", "INTO", "A", "AN",
})


# Curated singular forms. canonicalize_title folds the matching plural
# form (token + 'S') down to the singular when the singular is in this
# set. Hand-curated to avoid stem over-generalisation on engineering
# vocabulary (MULTI-PHASE should not become MULTI-PHAS).
SINGULAR_FORMS: frozenset[str] = frozenset({
    "CALCULATION", "DIAGRAM", "DRAWING", "INDEX",
    "LAYOUT", "LIST", "PROCEDURE", "PROCESS",
    "REPORT", "REQUISITION", "SCHEDULE", "SHEET",
    "SPECIFICATION", "STANDARD",
})


def _depluralize(tok: str) -> str:
    """Fold a curated regular-plural to its singular form.

    Only applies when stripping the trailing 'S' yields a token that's in
    the SINGULAR_FORMS allowlist. Length guard (>= 5) keeps short common
    words (IS, AS, OS) unaffected. Not a real stemmer.
    """
    if len(tok) >= 5 and tok.endswith("S") and tok[:-1] in SINGULAR_FORMS:
        return tok[:-1]
    return tok

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
    return [_depluralize(t) for t in s.split(" ")]


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


def score_types(title: str) -> dict[str, tuple[float, int]]:
    """Cumulative ``(score, n_phrases)`` per type from matching the rules.

    Algorithm, per type:
      1. Iterate (phrase, weight) in the order stored in the rules file
         (highest weight first).
      2. For each phrase, find its position in the title's token list.
         If found in a SPAN that hasn't already been consumed (by an
         earlier higher-weight phrase for the same type), record the
         match and consume that span.
      3. Span consumption is per-type. Different types match
         independently against the same tokens.

    Returned tuple is (cumulative score, number of phrases that fired).
    Types with no matches are absent from the result dict.
    """
    # Import lazily so the module is still importable when
    # type_keywords.py hasn't been generated yet.
    from classifier.config.type_keywords import TYPE_KEYWORD_RULES

    tokens = canonicalize_title(title)
    if not tokens:
        return {}

    scores: dict[str, tuple[float, int]] = {}
    for type_code, rules in TYPE_KEYWORD_RULES.items():
        consumed: list[tuple[int, int]] = []  # list of (start, end) half-open
        total = 0.0
        n_phrases = 0
        for phrase_text, weight in rules:
            phrase = phrase_text.split(" ")
            start = _index_phrases_in(tokens, phrase)
            if start < 0:
                continue
            end = start + len(phrase)
            if any(not (end <= cs or start >= ce) for cs, ce in consumed):
                continue  # overlaps an already-consumed span; same concept
            consumed.append((start, end))
            total += weight
            n_phrases += 1
        if total > 0:
            scores[type_code] = (total, n_phrases)
    return scores


def pick_type(scores: dict[str, tuple[float, int]]) -> dict:
    """Return ``{type, score, runner_up, runner_up_score, n_phrases, confidence}``.

    Confidence:
      * ``high`` iff top >= MIN_SCORE AND (top - runner_up) >= MIN_MARGIN
                 AND (n_phrases >= 2 OR top >= SINGLE_PHRASE_FLOOR)
      * ``low``  iff top >= MIN_SCORE AND the high gate failed for any
                 of the above reasons (margin OR single-phrase floor)
      * ``none`` otherwise (no matches, or top < MIN_SCORE)

    Ties broken alphabetically.
    """
    if not scores:
        return {
            "type": "", "score": 0.0,
            "runner_up": "", "runner_up_score": 0.0,
            "n_phrases": 0, "confidence": "none",
        }
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    top_code, (top_score, top_n_phrases) = ranked[0]
    if len(ranked) > 1:
        rup_code, (rup_score, _) = ranked[1]
    else:
        rup_code, rup_score = "", 0.0
    if top_score < MIN_SCORE:
        confidence = "none"
    elif (top_score - rup_score) < MIN_MARGIN:
        confidence = "low"
    elif top_n_phrases < 2 and top_score < SINGLE_PHRASE_FLOOR:
        confidence = "low"
    else:
        confidence = "high"
    return {
        "type": top_code if confidence != "none" else "",
        "score": top_score,
        "runner_up": rup_code,
        "runner_up_score": rup_score,
        "n_phrases": top_n_phrases,
        "confidence": confidence,
    }


def _phrase_matches(tokens: Sequence[str],
                     phrase: Sequence[str]) -> bool:
    """True iff ``phrase`` appears as a contiguous subsequence in ``tokens``.

    Exact per-token equality. No fuzzy / substring matching — the
    shared canonicalizer is responsible for normalization upstream.
    """
    n, m = len(tokens), len(phrase)
    if m == 0 or m > n:
        return False
    for i in range(n - m + 1):
        if all(tokens[i + j] == phrase[j] for j in range(m)):
            return True
    return False


def pick_type_with_overrides(title: str) -> dict:
    """Four-phase pick: override → score → negative prune → choose.

    Returns the same dict shape as ``pick_type`` plus a ``reason``
    field ∈ {"override", "scored", "none"} so callers can surface the
    path in summary reports.

    Phase 1: deterministic HARD_OVERRIDES. Within each type, try
        phrases longest-first so the most specific phrase wins. Across
        types, pick the type whose matched phrase was longest (alpha
        tie-break). On hit, return immediately with confidence=high
        and reason=override.

    Phase 2: learned keyword scoring via the existing ``score_types``.

    Phase 3: NEGATIVE_KEYWORDS prune. For each type still in the
        scored dict, if any negative phrase matches the title, scale
        that type's score by NEGATIVE_MULTIPLIER (currently 0.0 —
        full suppression). Soft-suppression via multiplier keeps the
        door open for partial suppression later without redesign.

    Phase 4: existing ``pick_type`` on the filtered scored dict.
    """
    # Lazy imports so the module stays importable when the config
    # files haven't been written yet.
    from classifier.config.type_overrides import (
        HARD_OVERRIDES, NEGATIVE_KEYWORDS,
    )

    tokens = canonicalize_title(title)
    if not tokens:
        result = pick_type({})
        result["reason"] = "none"
        return result

    # Phase 1
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

    # Phase 2
    scores = score_types(title)

    # Phase 3
    NEGATIVE_MULTIPLIER: float = 0.0
    for type_code, neg_phrases in NEGATIVE_KEYWORDS.items():
        if type_code not in scores:
            continue
        for phrase in neg_phrases:
            if _phrase_matches(tokens, phrase):
                cur_score, cur_n = scores[type_code]
                scores[type_code] = (cur_score * NEGATIVE_MULTIPLIER, cur_n)
                break
    scores = {t: v for t, v in scores.items() if v[0] > 0}

    # Phase 4
    result = pick_type(scores)
    result["reason"] = "scored" if result["confidence"] != "none" else "none"
    return result

