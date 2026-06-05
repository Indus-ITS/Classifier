from classifier.core.record import Record, FieldResult, ClassificationResult


def test_record_defaults():
    r = Record(title="X")
    assert r.doc_type == "" and r.type == "" and r.discipline_id == ""
    assert r.handle is None


def test_classification_result_holds_field_results():
    cr = ClassificationResult(
        doc_type=FieldResult("drawing", "via_keyword"),
        type=FieldResult("DWG", "via_keyword"),
        discipline_id=FieldResult("7", "via_keyword"),
    )
    assert cr.doc_type.value == "drawing"
    assert cr.type.reason == "via_keyword"
