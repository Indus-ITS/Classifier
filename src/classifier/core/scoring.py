"""Bucket scoring, winner selection, and fold to user-facing class label."""
from __future__ import annotations

import re

from classifier.config.keywords import KEYWORD_RULES


def score_buckets(title: str, filename: str) -> dict:
    """For each bucket, return (score_sum, score_top).
    Underscores in the filename are treated as spaces so word-separator regex
    keywords match real-world `piping_and_instrument_diagram.pdf` style names.
    """
    text = (title + " " + filename).lower().replace("_", " ")
    out: dict = {}
    for bucket, rules in KEYWORD_RULES.items():
        s_sum = 0
        s_top = 0
        for pattern, weight in rules:
            for _ in re.finditer(pattern, text):
                s_sum += weight
                if weight > s_top:
                    s_top = weight
        out[bucket] = (s_sum, s_top)
    out.setdefault("CRS", (0, 0))
    out.setdefault("Documents", (0, 0))
    return out


def pick_bucket(scores: dict) -> dict:
    """Pick winning bucket by score_sum (lex tiebreak), with runner-up + confidence."""
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    if not ranked:
        return {"bucket": "Documents", "score_sum": 0, "score_top": 0,
                "confidence": "low", "runner_up_bucket": "", "runner_up_score": 0}
    winner_name, (winner_sum, winner_top) = ranked[0]
    if winner_sum == 0:
        runner = next(((n, s) for n, s in ranked if n != "Documents"), ("", (0, 0)))
        return {"bucket": "Documents", "score_sum": 0, "score_top": 0,
                "confidence": "low",
                "runner_up_bucket": runner[0], "runner_up_score": runner[1][0]}
    if winner_top == 5:
        confidence = "high"
    elif winner_top in (3, 4):
        confidence = "medium"
    else:
        confidence = "low"
    runner = ranked[1] if len(ranked) > 1 else ("", (0, 0))
    return {
        "bucket": winner_name,
        "score_sum": winner_sum,
        "score_top": winner_top,
        "confidence": confidence,
        "runner_up_bucket": runner[0],
        "runner_up_score": runner[1][0],
    }


def fold_to_class(pick: dict, bucket_to_class: dict) -> str:
    """Fold a pick_bucket() result to the user-facing class label.

    Returns 'Undefined' when no keyword fired (score_sum == 0). Otherwise
    looks the picked bucket up in bucket_to_class. The Undefined branch
    keeps the fallthrough-to-Documents bucket from polluting the clean
    Drawings/Documents signal - those rows can be audited separately.
    """
    if pick["score_sum"] == 0:
        return "Undefined"
    return bucket_to_class[pick["bucket"]]
