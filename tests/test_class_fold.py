"""Tests for the 10-bucket -> 2-class fold defined in config.BUCKET_TO_CLASS.

The fold is a post-classification view: bucket scoring is unchanged, the
fold just collapses the 10 buckets into 2 classes (Drawings / Documents).
"""
from config import BUCKETS, BUCKET_TO_CLASS
from helpers.classifier_lib import fold_to_class, pick_bucket, score_buckets


def test_fold_covers_every_bucket():
    """Every one of the 10 BUCKETS must have a fold target."""
    missing = [b for b in BUCKETS if b not in BUCKET_TO_CLASS]
    assert missing == [], f"buckets without a fold target: {missing}"


def test_fold_values_are_only_drawings_or_documents():
    """No third class is permitted - this is a 2-class fold."""
    allowed = {"Drawings", "Documents"}
    assert set(BUCKET_TO_CLASS.values()) <= allowed


def test_drawings_bucket_folds_to_drawings():
    assert BUCKET_TO_CLASS["Drawings"] == "Drawings"


def test_isometrics_bucket_folds_to_drawings():
    assert BUCKET_TO_CLASS["Isometrics"] == "Drawings"


def test_datasheets_folds_to_documents():
    assert BUCKET_TO_CLASS["Datasheets"] == "Documents"


def test_specifications_folds_to_documents():
    assert BUCKET_TO_CLASS["Specifications"] == "Documents"


def test_calculations_folds_to_documents():
    assert BUCKET_TO_CLASS["Calculations"] == "Documents"


def test_reports_folds_to_documents():
    assert BUCKET_TO_CLASS["Reports"] == "Documents"


def test_lists_mtos_boms_folds_to_documents():
    assert BUCKET_TO_CLASS["Lists_MTOs_BOMs"] == "Documents"


def test_procedures_plans_folds_to_documents():
    """Per spec: Method Statements, Inspection Plans, Welding Procedures
    are textual documents, not drawings."""
    assert BUCKET_TO_CLASS["Procedures_Plans"] == "Documents"


def test_crs_folds_to_documents():
    assert BUCKET_TO_CLASS["CRS"] == "Documents"


def test_documents_bucket_folds_to_documents():
    assert BUCKET_TO_CLASS["Documents"] == "Documents"


# --- End-to-end: bucket pick -> fold ---

def _class_for(title: str) -> str:
    """Helper: run the full pipeline and return the folded class via the
    same code path classifier.py and evaluate_corpus.py use (so 'Undefined'
    is returned for zero-score titles, not Documents)."""
    pick = pick_bucket(score_buckets(title, ""))
    return fold_to_class(pick, BUCKET_TO_CLASS)


def test_e2e_drawing_title_becomes_drawings_class():
    assert _class_for("P&ID - Production Header") == "Drawings"


def test_e2e_isometric_title_becomes_drawings_class():
    assert _class_for("Piping Isometric for Line 4-PO-0061") == "Drawings"


def test_e2e_report_title_becomes_documents_class():
    assert _class_for("Process Basis Of Design - Sahil") == "Documents"


def test_e2e_method_statement_becomes_documents_class():
    assert _class_for("METHOD STATEMENT FOR INSTALLATION") == "Documents"


def test_e2e_pipeline_profile_becomes_drawings_class():
    """Combines Task 1 (profile keyword) with Task 2 (fold)."""
    assert _class_for("Pipeline Long Profile - 16 inch") == "Drawings"


# -----------------------------------------------------------------------
# Undefined class - titles where no keyword fires must NOT default to
# Documents. The fold rule is: score_sum == 0 -> 'Undefined' so the
# fallthroughs can be audited separately from real Documents.
# -----------------------------------------------------------------------
def test_unrecognized_title_becomes_undefined_not_documents():
    # Real fallthrough title from the schedule corpus - no Drawings or
    # Documents-side keyword fires.
    pick = pick_bucket(score_buckets("Water Disposal Well SA 075 Sahil", ""))
    assert pick["score_sum"] == 0
    assert _class_for("Water Disposal Well SA 075 Sahil") == "Undefined"


def test_recognized_documents_title_stays_documents_not_undefined():
    """Sanity: titles with positive Documents-bucket score must stay
    Documents, not get demoted to Undefined."""
    # 'MATERIAL REQUISITION FOR X' fires \brequ[is]+ition\b weight 5 in
    # the Documents bucket -> score > 0 -> class = Documents.
    pick = pick_bucket(score_buckets("MATERIAL REQUISITION FOR CHAIN HOIST", ""))
    assert pick["score_sum"] > 0
    assert _class_for("MATERIAL REQUISITION FOR CHAIN HOIST") == "Documents"


def test_fold_to_class_helper_zero_score():
    """Direct test of the helper: any pick with score_sum=0 returns Undefined."""
    pick = {"bucket": "Documents", "score_sum": 0, "score_top": 0,
            "confidence": "low", "runner_up_bucket": "", "runner_up_score": 0}
    assert fold_to_class(pick, BUCKET_TO_CLASS) == "Undefined"


def test_fold_to_class_helper_positive_score_uses_mapping():
    """Direct test: any pick with score_sum>0 uses the bucket->class lookup."""
    pick = {"bucket": "Reports", "score_sum": 5, "score_top": 5,
            "confidence": "high", "runner_up_bucket": "", "runner_up_score": 0}
    assert fold_to_class(pick, BUCKET_TO_CLASS) == "Documents"
