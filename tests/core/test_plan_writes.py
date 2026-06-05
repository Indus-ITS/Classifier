from classifier.core.record import Record, FieldResult, ClassificationResult
from classifier.core.classify import plan_writes


def _result(dt, ty, di):
    return ClassificationResult(FieldResult(dt, "x"), FieldResult(ty, "x"),
                                FieldResult(di, "x"))


def test_writes_doc_type_when_changed():
    rec = Record(title="X", doc_type="", type="DWG", discipline_id="7")
    w = plan_writes(rec, _result("document", "DWG", "7"))
    assert w == {"doc_type": "document"}


def test_no_doc_type_write_when_same():
    rec = Record(title="X", doc_type="drawing", type="DWG", discipline_id="7")
    w = plan_writes(rec, _result("drawing", "DWG", "7"))
    assert "doc_type" not in w


def test_type_written_only_when_was_empty():
    rec = Record(title="X", doc_type="document", type="", discipline_id="7")
    assert plan_writes(rec, _result("document", "DWG", "7")) == {"type": "DWG"}
    rec2 = Record(title="X", doc_type="document", type="DDT", discipline_id="7")
    assert "type" not in plan_writes(rec2, _result("document", "DDT", "7"))


def test_discipline_written_only_when_was_empty_and_hit():
    rec = Record(title="X", doc_type="document", type="DWG", discipline_id="")
    assert plan_writes(rec, _result("document", "DWG", "7")) == {"discipline_id": "7"}
    rec_miss = Record(title="X", doc_type="document", type="DWG", discipline_id="")
    assert "discipline_id" not in plan_writes(rec_miss, _result("document", "DWG", ""))
