from helpers.classifier_lib import KEYWORD_RULES, TYPE_TO_BUCKET, BUCKET_PRIMARY_CODE, BUCKETS


def test_buckets_count():
    assert len(BUCKETS) == 10


def test_required_buckets_present():
    expected = {"Drawings", "Isometrics", "Datasheets", "Specifications",
                "Calculations", "Reports", "Lists_MTOs_BOMs", "Procedures_Plans",
                "CRS", "Documents"}
    assert set(BUCKETS) == expected


def test_keyword_rules_keyed_by_bucket():
    for bucket in BUCKETS:
        if bucket in {"CRS", "Documents"}:
            continue
        assert bucket in KEYWORD_RULES
        assert len(KEYWORD_RULES[bucket]) > 0


def test_keyword_weights_in_range():
    for bucket, rules in KEYWORD_RULES.items():
        for pattern, weight in rules:
            assert isinstance(pattern, str)
            assert 1 <= weight <= 5


def test_type_to_bucket_known_codes():
    assert TYPE_TO_BUCKET["PID"] == "Drawings"
    assert TYPE_TO_BUCKET["DAS"] == "Datasheets"
    assert TYPE_TO_BUCKET["CAL"] == "Calculations"
    assert TYPE_TO_BUCKET["REP"] == "Reports"
    assert TYPE_TO_BUCKET["MTO"] == "Lists_MTOs_BOMs"
    assert TYPE_TO_BUCKET["PRO"] == "Procedures_Plans"


def test_bucket_primary_code_for_each_bucket():
    for bucket in BUCKETS:
        assert bucket in BUCKET_PRIMARY_CODE
        assert len(BUCKET_PRIMARY_CODE[bucket]) >= 3


# --- Task 6: scoring ---
from helpers.classifier_lib import score_buckets


def test_score_single_keyword():
    scores = score_buckets("VALVE LIST", "16-01-19-2602.pdf")
    assert scores["Lists_MTOs_BOMs"] == (3, 3)


def test_score_two_keywords_same_bucket():
    scores = score_buckets("EQUIPMENT LIST AND LINE LIST", "")
    s_sum, s_top = scores["Lists_MTOs_BOMs"]
    assert s_top == 5
    assert s_sum >= 10


def test_score_uses_score_top_for_signal_strength():
    a_sum, a_top = score_buckets("DATA SHEET", "")["Datasheets"]
    b_sum, b_top = score_buckets("DATA SHEET DATA SHEET DATA SHEET", "")["Datasheets"]
    assert a_top == b_top == 5
    assert b_sum > a_sum


def test_score_zero_when_no_match():
    scores = score_buckets("RANDOM XYZ TEXT", "foo.pdf")
    assert scores["Lists_MTOs_BOMs"] == (0, 0)
    assert scores["Drawings"] == (0, 0)


def test_score_filename_contributes():
    scores = score_buckets("", "PIPING_AND_INSTRUMENT_DIAGRAM_FOO.pdf")
    s_sum, s_top = scores["Drawings"]
    assert s_top == 5
    assert s_sum >= 5


# --- Task 7: picking ---
from helpers.classifier_lib import pick_bucket


def test_pick_winner_high_confidence():
    scores = {"Drawings": (5, 5), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["bucket"] == "Drawings"
    assert res["score_sum"] == 5
    assert res["confidence"] == "high"
    assert res["runner_up_bucket"] == "Documents"
    assert res["runner_up_score"] == 0


def test_pick_medium_confidence():
    scores = {"Drawings": (3, 3), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["confidence"] == "medium"


def test_pick_low_confidence_weight1():
    scores = {"Drawings": (1, 1), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["confidence"] == "low"


def test_pick_fallback_to_documents_on_zero():
    scores = {b: (0, 0) for b in ("Drawings", "Reports", "Documents")}
    res = pick_bucket(scores)
    assert res["bucket"] == "Documents"
    assert res["confidence"] == "low"
    assert res["score_sum"] == 0


def test_pick_runner_up_with_three_buckets():
    scores = {"Drawings": (5, 5), "Reports": (3, 3), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["bucket"] == "Drawings"
    assert res["runner_up_bucket"] == "Reports"
    assert res["runner_up_score"] == 3


def test_pick_tiebreak_lexicographic():
    scores = {"Reports": (5, 5), "Drawings": (5, 5), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["bucket"] == "Drawings"
    assert res["runner_up_bucket"] == "Reports"


# --- Task 8: form resolution ---
from helpers.classifier_lib import resolve_form_pre, resolve_form_post


def test_form_pre_archive_rar():
    assert resolve_form_pre("foo.rar", has_ref=False) == "Archive"


def test_form_pre_archive_zip():
    assert resolve_form_pre("foo.zip", has_ref=False) == "Archive"


def test_form_pre_cover_no_ref():
    assert resolve_form_pre("CTA-ED-SA-15760.01-008.pdf", has_ref=False) == "CoverSheet"


def test_form_pre_cover_with_ref_is_not_cover():
    assert resolve_form_pre("CTA-X-16-01-19-2602.pdf", has_ref=True) is None


def test_form_pre_default_unset():
    assert resolve_form_pre("16-01-19-2602-A.pdf", has_ref=True) is None


def test_form_post_dwg():
    assert resolve_form_post("foo.dwg", "Drawings") == "Drawing"


def test_form_post_xlsx_lists():
    assert resolve_form_post("foo.xlsx", "Lists_MTOs_BOMs") == "Sheet"


def test_form_post_docx():
    assert resolve_form_post("foo.docx", "Reports") == "Document"


def test_form_post_pdf_in_drawings_bucket():
    assert resolve_form_post("foo.pdf", "Drawings") == "Drawing"


def test_form_post_pdf_in_isometrics_bucket():
    assert resolve_form_post("foo.pdf", "Isometrics") == "Drawing"


def test_form_post_pdf_in_datasheets_bucket():
    assert resolve_form_post("foo.pdf", "Datasheets") == "Sheet"


def test_form_post_pdf_in_lists_bucket():
    assert resolve_form_post("foo.pdf", "Lists_MTOs_BOMs") == "Sheet"


def test_form_post_pdf_in_reports_bucket():
    assert resolve_form_post("foo.pdf", "Reports") == "Document"


def test_form_post_unknown_extension():
    assert resolve_form_post("foo.xyz", "Documents") == "Document"
