"""Discipline-level keyword scoring.

Public API:
  * ``score_disciplines(title, type_hint=None)`` - {discipline_id: (score, n_phrases)}
  * ``pick_discipline(scores)`` - confidence-gated single choice
  * ``pick_discipline_with_overrides(title, type_hint=None)`` - convenience
    wrapper returning the standard
    ``{discipline_id, confidence, reason}`` shape.

The ``type_hint`` is the row's classified ``type`` code (e.g. ``ISO``,
``PFD``). When the type maps deterministically to a single DEST
discipline (see ``classifier.config.type_to_discipline``), a fixed
``TYPE_HINT_BONUS`` is added to that discipline's score. The bonus is
calibrated below ``SINGLE_PHRASE_FLOOR`` so the type alone cannot
produce a ``high`` confidence verdict; it only tips a weak keyword
signal into a confident decision.

``reason`` is ``"keyword"`` (top discipline scored, possibly with a
type-hint boost) or ``"miss"``.
"""
from __future__ import annotations

from classifier.core.type_scoring import (
    MIN_MARGIN, MIN_SCORE, SINGLE_PHRASE_FLOOR,
    _index_phrases_in, canonicalize_title,
)

# Booster added to a discipline's score when the row's type maps to it.
# Intentionally below SINGLE_PHRASE_FLOOR (2.5) so a type hint without
# any title keyword cannot fire on its own -- pick_discipline's
# single-phrase gate stays in effect.
TYPE_HINT_BONUS: float = 2.0


def score_disciplines(title: str, type_hint: str | None = None
                      ) -> dict[int, tuple[float, int]]:
    """Cumulative ``(score, n_phrases)`` per discipline.

    If ``type_hint`` is provided and matches an entry in
    ``TYPE_TO_DISCIPLINE``, ``TYPE_HINT_BONUS`` is added to that
    discipline's score (creating the entry if no keyword matched).
    The bonus is not counted toward ``n_phrases`` -- only literal
    phrase matches in the title contribute to phrase count.
    """
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS

    tokens = canonicalize_title(title)
    scores: dict[int, tuple[float, int]] = {}

    if tokens:
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


def pick_discipline_with_overrides(title: str, type_hint: str | None = None
                                   ) -> dict:
    """Score title keywords plus optional type-hint boost; pick the best.

    ``type_hint`` is the row's classified ``type`` code; when it maps
    to a DEST discipline via ``TYPE_TO_DISCIPLINE``, it adds a fixed
    booster to that discipline's score. See module docstring.
    """
    pick = pick_discipline(score_disciplines(title, type_hint=type_hint))
    pick["reason"] = "keyword" if pick["confidence"] != "none" else "miss"
    return pick
