from classifier.core.scoring import score, pick


def test_score_matches_phrases_with_span_consumption():
    rules = {"AAA": [("VALVE LIST", 5), ("VALVE", 2)]}
    scores = score("VALVE LIST", rules)
    # "VALVE LIST" consumes the span; the lower-weight "VALVE" cannot re-score it
    assert scores["AAA"] == (5.0, 1)


def test_pick_high_confidence_gate():
    out = pick({"AAA": (5.0, 2), "BBB": (1.0, 1)})
    assert out["key"] == "AAA"
    assert out["confidence"] == "high"


def test_pick_none_when_below_min_score():
    out = pick({"AAA": (1.0, 1)})
    assert out["confidence"] == "none"
    assert out["key"] is None
