from classifier.core.folding import doc_type_for_bucket


def test_drawings_bucket_folds_to_drawing():
    assert doc_type_for_bucket("Drawings") == "drawing"
    assert doc_type_for_bucket("Isometrics") == "drawing"


def test_lists_bucket_folds_to_sheet():
    assert doc_type_for_bucket("Lists_MTOs_BOMs") == "sheet"


def test_other_buckets_fold_to_document():
    assert doc_type_for_bucket("Specifications") == "document"
    assert doc_type_for_bucket("Reports") == "document"
