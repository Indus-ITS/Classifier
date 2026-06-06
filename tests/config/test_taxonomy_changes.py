from classifier.config.buckets import (
    BUCKETS, BUCKET_TO_CLASS, TYPE_TO_BUCKET, BUCKET_PRIMARY_CODE,
)


def test_crs_removed_from_taxonomy():
    assert "CRS" not in BUCKETS
    assert "CRS" not in BUCKET_TO_CLASS
    assert "CRS" not in BUCKET_PRIMARY_CODE


def test_reg_folds_to_document():
    bucket = TYPE_TO_BUCKET["REG"]
    assert BUCKET_TO_CLASS[bucket] == "Documents"


def test_genuine_sheet_types_still_sheets():
    for code in ("LST", "MTO", "BOM", "IDX", "SCH"):
        assert BUCKET_TO_CLASS[TYPE_TO_BUCKET[code]] == "Sheets"
