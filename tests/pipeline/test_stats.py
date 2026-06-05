from classifier.core.record import Record, FieldResult, ClassificationResult
from classifier.pipeline.stats import Stats


def _res(dt_r, ty_r, di_r):
    return ClassificationResult(FieldResult("document", dt_r),
                                FieldResult("", ty_r),
                                FieldResult("", di_r))


def test_observe_counts_scanned_updated_skipped():
    s = Stats()
    s.observe(Record(title="X", doc_type=""), _res("defaulted", "miss", "miss"),
              {"doc_type": "document"})
    s.observe(Record(title="Y", doc_type="document"), _res("existing", "miss", "miss"),
              {})
    assert s.rows_scanned == 2
    assert s.rows_updated == 1
    assert s.rows_skipped == 1


def test_reason_counters_and_before_after():
    s = Stats()
    s.observe(Record(title="X", doc_type=""), _res("defaulted", "miss", "miss"),
              {"doc_type": "document"})
    assert s.reasons["doc_type"]["defaulted"] == 1
    assert s.reasons["type"]["miss"] == 1
    assert s.doc_type_before["(empty)"] == 1
    assert s.doc_type_after["document"] == 1
