"""Type-level scoring: thin adapter over the generic engine in core.scoring.

Re-exports the canonicalizer and primitives so existing importers (learners,
discipline_scoring) keep working.
"""
from __future__ import annotations

from typing import Sequence

from classifier.core.scoring import (  # noqa: F401  (re-exported)
    MIN_SCORE, MIN_MARGIN, SINGLE_PHRASE_FLOOR,
    STOP_TOKENS, SINGULAR_FORMS, _depluralize,
    canonicalize_title, candidate_phrases,
    _ngrams, _index_phrases_in, _phrase_matches,
    score as _score, pick as _pick,
)


def score_types(title: str) -> dict[str, tuple[float, int]]:
    from classifier.config.type_keywords import TYPE_KEYWORD_RULES
    return _score(title, TYPE_KEYWORD_RULES)


def pick_type(scores: dict[str, tuple[float, int]]) -> dict:
    p = _pick(scores)
    return {
        "type": p["key"] if p["key"] is not None else "",
        "score": p["score"],
        "runner_up": p["runner_up"] if p["runner_up"] is not None else "",
        "runner_up_score": p["runner_up_score"],
        "n_phrases": p["n_phrases"],
        "confidence": p["confidence"],
    }


def pick_type_with_overrides(title: str) -> dict:
    from classifier.config.type_overrides import HARD_OVERRIDES, NEGATIVE_KEYWORDS

    tokens = canonicalize_title(title)
    if not tokens:
        result = pick_type({})
        result["reason"] = "none"
        return result

    # Phase 1: hard overrides (longest phrase wins; alpha tie-break).
    override_hits: list[tuple[int, str]] = []
    for type_code, phrases in HARD_OVERRIDES.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            if _phrase_matches(tokens, phrase):
                override_hits.append((len(phrase), type_code))
                break
    if override_hits:
        override_hits.sort(key=lambda t: (-t[0], t[1]))
        return {
            "type": override_hits[0][1], "score": float("inf"),
            "runner_up": "", "runner_up_score": 0.0,
            "n_phrases": 1, "confidence": "high", "reason": "override",
        }

    # Phase 2: learned scoring.
    scores = score_types(title)

    # Phase 3: negative-keyword suppression.
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

    # Phase 4: pick.
    result = pick_type(scores)
    result["reason"] = "scored" if result["confidence"] != "none" else "none"

    # Phase 5: DRAWING / SKETCH fallback.
    if result["confidence"] == "none":
        if "DRAWING" in tokens or "SKETCH" in tokens:
            return {
                "type": "DWG", "score": float("inf"),
                "runner_up": "", "runner_up_score": 0.0,
                "n_phrases": 1, "confidence": "high", "reason": "fallback",
            }
    return result
