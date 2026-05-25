"""Discipline-level keyword scoring.

Public API:
  * ``score_disciplines(title)``  - {discipline_id: (score, n_phrases)}
  * ``pick_discipline(scores)``   - confidence-gated single choice
  * ``pick_discipline_with_overrides(title)`` - convenience wrapper
    returning the standard
    ``{discipline_id, confidence, reason}`` shape.

No overrides table in this iteration. ``reason`` is always
``"keyword"`` or ``"miss"``.
"""
from __future__ import annotations

from classifier.core.type_scoring import (
    MIN_MARGIN, MIN_SCORE, SINGLE_PHRASE_FLOOR,
    _index_phrases_in, canonicalize_title,
)


def score_disciplines(title: str) -> dict[int, tuple[float, int]]:
    """Cumulative ``(score, n_phrases)`` per discipline."""
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS

    tokens = canonicalize_title(title)
    if not tokens:
        return {}

    scores: dict[int, tuple[float, int]] = {}
    for disc_id, rules in DISCIPLINE_KEYWORDS.items():
        consumed: list[tuple[int, int]] = []
        total = 0.0
        n_phrases = 0
        for phrase_text, weight in rules:
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
            scores[disc_id] = (total, n_phrases)
    return scores


def pick_discipline(scores: dict[int, tuple[float, int]]) -> dict:
    """Return ``{discipline_id, confidence}``. Same gates as pick_type."""
    if not scores:
        return {"discipline_id": None, "confidence": "none"}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    top_id, (top_score, top_n) = ranked[0]
    rup_score = ranked[1][1][0] if len(ranked) > 1 else 0.0
    if top_score < MIN_SCORE:
        confidence = "none"
    elif (top_score - rup_score) < MIN_MARGIN:
        confidence = "low"
    elif top_n < 2 and top_score < SINGLE_PHRASE_FLOOR:
        confidence = "low"
    else:
        confidence = "high"
    return {
        "discipline_id": top_id if confidence != "none" else None,
        "confidence": confidence,
    }


def pick_discipline_with_overrides(title: str) -> dict:
    """No overrides yet; thin wrapper for API symmetry with type scoring."""
    pick = pick_discipline(score_disciplines(title))
    pick["reason"] = "keyword" if pick["confidence"] != "none" else "miss"
    return pick
