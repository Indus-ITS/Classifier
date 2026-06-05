"""Discipline-level scoring: thin adapter over the generic engine, plus the
type-hint bonus. See module history for the calibration rationale.
"""
from __future__ import annotations

from classifier.core.scoring import score as _score, pick as _pick

TYPE_HINT_BONUS: float = 2.0


def score_disciplines(title: str, type_hint: str | None = None
                      ) -> dict[int, tuple[float, int]]:
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
    scores = _score(title, DISCIPLINE_KEYWORDS)

    if type_hint:
        try:
            from classifier.config.type_to_discipline import TYPE_TO_DISCIPLINE
        except ImportError:
            TYPE_TO_DISCIPLINE = {}
        hint_disc = TYPE_TO_DISCIPLINE.get(type_hint.strip().upper())
        if hint_disc is not None:
            cur_score, cur_n = scores.get(hint_disc, (0.0, 0))
            scores[hint_disc] = (cur_score + TYPE_HINT_BONUS, cur_n)
    return scores


def pick_discipline(scores: dict[int, tuple[float, int]]) -> dict:
    p = _pick(scores)
    return {"discipline_id": p["key"], "confidence": p["confidence"]}


def pick_discipline_with_overrides(title: str, type_hint: str | None = None
                                   ) -> dict:
    pick = pick_discipline(score_disciplines(title, type_hint=type_hint))
    pick["reason"] = "keyword" if pick["confidence"] != "none" else "miss"
    return pick
