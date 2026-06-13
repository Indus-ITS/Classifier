"""Generic phrase-scoring engine shared by type and discipline classification.

Holds the canonicalizer, n-gram/phrase primitives, the confidence knobs, and
the generic score()/pick(). type_scoring and discipline_scoring are thin
callers that supply a rule table and adapt the result shape.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Sequence

MIN_SCORE: float = 1.5
MIN_MARGIN: float = 1.0
SINGLE_PHRASE_FLOOR: float = 2.5

STOP_TOKENS: frozenset[str] = frozenset({
    "FOR", "AND", "OR", "OF", "THE", "TO", "WITH",
    "ON", "IN", "AT", "FROM", "INTO", "A", "AN",
})

SINGULAR_FORMS: frozenset[str] = frozenset({
    "CALCULATION", "DIAGRAM", "DRAWING", "INDEX",
    "LAYOUT", "LIST", "PROCEDURE", "PROCESS",
    "REPORT", "REQUISITION", "SCHEDULE", "SHEET",
    "SKETCH", "SPECIFICATION", "STANDARD",
})


def _depluralize(tok: str) -> str:
    if len(tok) >= 5 and tok.endswith("S"):
        if tok[:-1] in SINGULAR_FORMS:
            return tok[:-1]
        if tok.endswith("ES") and tok[:-2] in SINGULAR_FORMS:
            return tok[:-2]
    return tok


_DASHES = str.maketrans({
    "‐": " ", "‑": " ", "‒": " ",
    "–": " ", "—": " ", "―": " ",
    "−": " ", "\xa0": " ",
})
_PARENS_RE = re.compile(r"\(([^)]*)\)")
_REV_NOISE_RE = re.compile(
    r"\b(\d+\s*SHEETS?|REV\s*\d+|SHEET\s+\d+\s+OF\s+\d+)\b"
)
_PUNCT_KEEP_AMP_SLASH_RE = re.compile(r"[^A-Z0-9&/ ]+")
_WS_RE = re.compile(r"\s+")

# Parenthetical groups are usually rev/issue/sheet noise — "(Rev Rev-2)",
# "(11 SHEETS)", "(NEW)", "(3.3kV)". Those are dropped. A group carrying a
# real word (e.g. "(SS-N LV SLD Mod)", "(Vendor Scheme-Spare Feeders)") is
# unwrapped and kept, so the signal inside it survives canonicalization.
_PAREN_NOISE_WORDS = frozenset({
    "REV", "REVISION", "REVISED", "SHEET", "SHEETS", "SHT", "SHTS",
    "TYP", "TYPICAL", "DRAFT", "FINAL", "DRAWN", "ISSUE", "ISSUED",
    "IFD", "IFC", "IFR", "IFA", "IFI", "IFT", "AFC", "AFD", "HOLD", "CIRC",
    "NEW", "OLD", "PHASE", "STATUS", "DATED", "DATE", "REVISE", "EXISTING",
})
_PAREN_ALPHA_RE = re.compile(r"[A-Z]{2,}")


def _strip_noise_parens(s: str) -> str:
    """Drop noise-only parentheticals; unwrap (keep) ones with a real word."""
    def repl(m: "re.Match[str]") -> str:
        inner = m.group(1)
        words = [w for w in _PAREN_ALPHA_RE.findall(inner)
                 if w not in _PAREN_NOISE_WORDS]
        return f" {inner} " if words else " "
    return _PARENS_RE.sub(repl, s)


def canonicalize_title(raw: str) -> list[str]:
    if not raw:
        return []
    s = unicodedata.normalize("NFKC", str(raw))
    s = s.translate(_DASHES)
    s = s.upper()
    s = _strip_noise_parens(s)
    s = _REV_NOISE_RE.sub(" ", s)
    s = _PUNCT_KEEP_AMP_SLASH_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return []
    return [_depluralize(t) for t in s.split(" ")]


def _ngrams(tokens: Sequence[str], n: int) -> list[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def candidate_phrases(tokens: Sequence[str],
                      extra_stop: frozenset[str] = frozenset()) -> list[tuple[str, ...]]:
    stop = STOP_TOKENS | extra_stop
    out: list[tuple[str, ...]] = []
    for n in (1, 2, 3):
        for ng in _ngrams(tokens, n):
            if any(tok in stop for tok in ng):
                continue
            out.append(ng)
    return out


def _index_phrases_in(tokens: Sequence[str], phrase_tokens: Sequence[str]) -> int:
    n, m = len(tokens), len(phrase_tokens)
    if m == 0 or m > n:
        return -1
    for i in range(n - m + 1):
        if all(tokens[i + j] == phrase_tokens[j] for j in range(m)):
            return i
    return -1


def _phrase_matches(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    return _index_phrases_in(tokens, phrase) >= 0


def score(title: str, rules: dict) -> dict:
    """Cumulative ``(score, n_phrases)`` per key from matching the rules.

    Generic over the key type (str type-code or int discipline-id). Span
    consumption is per-key: a higher-weight phrase consumes its span so an
    overlapping lower-weight phrase for the same key cannot re-score it.
    """
    tokens = canonicalize_title(title)
    if not tokens:
        return {}
    scores: dict = {}
    for key, krules in rules.items():
        consumed: list[tuple[int, int]] = []
        total = 0.0
        n_phrases = 0
        for phrase_text, weight in krules:
            phrase = phrase_text.split(" ")
            start = _index_phrases_in(tokens, phrase)
            if start < 0:
                continue
            end = start + len(phrase)
            if any(not (end <= cs or start >= ce) for cs, ce in consumed):
                continue
            consumed.append((start, end))
            total += weight
            n_phrases += 1
        if total > 0:
            scores[key] = (total, n_phrases)
    return scores


def pick(scores: dict) -> dict:
    """Generic confidence-gated choice. Returns
    ``{key, score, runner_up, runner_up_score, n_phrases, confidence}``.
    Ties broken by natural key order.
    """
    if not scores:
        return {"key": None, "score": 0.0, "runner_up": None,
                "runner_up_score": 0.0, "n_phrases": 0, "confidence": "none"}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    top_key, (top_score, top_n) = ranked[0]
    if len(ranked) > 1:
        rup_key, (rup_score, _) = ranked[1]
    else:
        rup_key, rup_score = None, 0.0
    if top_score < MIN_SCORE:
        confidence = "none"
    elif (top_score - rup_score) < MIN_MARGIN:
        confidence = "low"
    elif top_n < 2 and top_score < SINGLE_PHRASE_FLOOR:
        confidence = "low"
    else:
        confidence = "high"
    return {
        "key": top_key if confidence != "none" else None,
        "score": top_score,
        "runner_up": rup_key,
        "runner_up_score": rup_score,
        "n_phrases": top_n,
        "confidence": confidence,
    }
