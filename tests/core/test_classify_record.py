from classifier.core.record import Record
from classifier.core.classify import classify_record


def test_classify_record_drawing():
    res = classify_record(Record(title="PIPING AND INSTRUMENT DIAGRAM"))
    assert res.doc_type.value == "drawing"


def test_classify_record_preserves_existing():
    res = classify_record(Record(title="", doc_type="drawing", type="DWG",
                                 discipline_id="7"))
    assert res.doc_type.value == "drawing"
    assert res.type.value == "DWG"
    assert res.type.reason == "preserved"
    assert res.discipline_id.value == "7"


def test_classify_record_uses_type_as_discipline_hint():
    # An ISO type should bias discipline scoring; assert it does not crash and
    # returns a FieldResult triple with reasons.
    res = classify_record(Record(title="ISOMETRIC DRAWING"))
    assert res.doc_type.reason in ("via_keyword", "via_override", "defaulted",
                                   "existing")
