"""Locks the classify_titles public contract before refactoring.

Critical invariants: discipline_id is int|None (NOT a string), doc_type is
always set, existing populated fields are preserved, and include_reasons
attaches (value, reason) tuples.
"""
from classifier.pipeline.classify_titles import classify_titles


def test_doc_type_always_set_and_defaults_to_document():
    out = classify_titles([{"title": "ZZZ NONSENSE TOKEN"}])
    assert out[0]["doc_type"] == "document"


def test_drawing_title_classifies_as_drawing():
    out = classify_titles([{"title": "PIPING AND INSTRUMENT DIAGRAM"}])
    assert out[0]["doc_type"] == "drawing"


def test_discipline_id_is_int_or_none_never_string():
    out = classify_titles([{"title": "EQUIPMENT REQUISITION"}])
    val = out[0]["discipline_id"]
    assert val is None or isinstance(val, int)


def test_existing_fields_preserved():
    out = classify_titles([
        {"title": "", "doc_type": "drawing", "type": "DWG", "discipline_id": 7},
    ])
    assert out[0]["doc_type"] == "drawing"
    assert out[0]["type"] == "DWG"
    assert out[0]["discipline_id"] == 7


def test_include_reasons_returns_tuples():
    out = classify_titles([{"title": "P&ID AREA 01"}], include_reasons=True)
    value, reason = out[0]["doc_type"]
    assert isinstance(reason, str)
    assert value in ("drawing", "document", "sheet")
