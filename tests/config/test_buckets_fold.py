from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET


def test_lists_mtos_boms_folds_to_sheets():
    assert BUCKET_TO_CLASS["Lists_MTOs_BOMs"] == "Sheets"


def test_sheet_types_reach_sheets_class():
    # REG intentionally moved to Documents (see feat: drop CRS bucket; fold REG to Documents)
    for code in ("LST", "MTO", "BOM", "IDX", "SCH"):
        bucket = TYPE_TO_BUCKET[code]
        assert BUCKET_TO_CLASS[bucket] == "Sheets", code


def test_drawings_and_documents_unchanged():
    assert BUCKET_TO_CLASS["Drawings"] == "Drawings"
    assert BUCKET_TO_CLASS["Isometrics"] == "Drawings"
    assert BUCKET_TO_CLASS["Datasheets"] == "Documents"
    assert BUCKET_TO_CLASS["Specifications"] == "Documents"


def test_three_distinct_classes_exist():
    assert set(BUCKET_TO_CLASS.values()) == {"Drawings", "Documents", "Sheets"}
