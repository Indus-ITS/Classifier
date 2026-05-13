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
