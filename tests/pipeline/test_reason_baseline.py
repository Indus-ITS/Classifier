"""Locks the reason vocabulary emitted by the core field helpers. These feed
Stats in Phase 2; the CSV golden does not contain reasons.
"""
from classifier.pipeline._row import (
    normalize_doc_type, fill_type, fill_discipline,
)


def test_doc_type_reasons():
    assert normalize_doc_type("drawing", "X")[1] == "existing"
    assert normalize_doc_type("", "ZZZ NONSENSE")[1] == "defaulted"
    # "DIAGRAM" is a drawing marker, so a P&ID title resolves to a drawing
    # via the marker (drawing_title) ahead of the PID type override.
    assert normalize_doc_type("", "PIPING AND INSTRUMENT DIAGRAM")[1] in (
        "via_keyword", "via_override", "drawing_title",
    )
    assert normalize_doc_type("", "PIPING AND INSTRUMENT DIAGRAM")[0] == "drawing"


def test_fill_type_reasons():
    assert fill_type("DWG", "X")[1] == "preserved"
    assert fill_type("", "ZZZ NONSENSE")[1] == "miss"


def test_fill_discipline_reasons():
    assert fill_discipline("7", "X")[1] == "preserved"
    assert fill_discipline("", "ZZZ NONSENSE")[1] == "miss"
