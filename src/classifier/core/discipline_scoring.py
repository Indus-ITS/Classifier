"""Discipline-level scoring: thin adapter over the generic phrase engine.

The document type is intentionally NOT mixed into the score here. Type-based
discipline recovery happens once, explicitly, as a gated fallback in
core.classify.fill_discipline, so the keyword score stays a pure title signal.
"""
from __future__ import annotations

from classifier.core.scoring import score as _score, pick as _pick


def score_disciplines(title: str) -> dict[int, tuple[float, int]]:
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
    return _score(title, DISCIPLINE_KEYWORDS)


def pick_discipline(scores: dict[int, tuple[float, int]]) -> dict:
    p = _pick(scores)
    return {"discipline_id": p["key"], "confidence": p["confidence"]}


def pick_discipline_with_overrides(title: str) -> dict:
    pick = pick_discipline(score_disciplines(title))
    pick["reason"] = "keyword" if pick["confidence"] != "none" else "miss"
    return pick
