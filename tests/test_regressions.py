"""Regression tests for the four bugs found in v3-output review.

Each test is grounded in a real failing case from the v3 output. Re-emerging
from an "innocent" config tweak would silently regress the classifier; these
tests pin the fixes.
"""
from helpers.classifier_lib import (
    score_buckets,
    pick_bucket,
    compute_is_latest_for_group,
    classify_revision_drift,
)


# --------------------------------------------------------------------------
# Bug 1: word-boundary regex too tight on PLAN/PLANNING, REQUSITION typo,
# EVALATION/EVALATUION typos, MR FOR <X>, ALIGNMENT SHEET phrasing,
# DETAILS singular form.
# --------------------------------------------------------------------------
def test_bug1_planning_package_matches_procedures():
    # Real fallthrough title from v3 output: PLANNING PACKAGE for ...
    scores = score_buckets("PLANNING PACKAGE FOR PROJECT X", "")
    picked = pick_bucket(scores)
    assert picked["bucket"] == "Procedures_Plans", \
        f"expected Procedures_Plans, got {picked['bucket']}"


def test_bug1_requsition_typo_matches_documents():
    # Real misspelling seen 10+ times: REQUSITION instead of REQUISITION
    scores = score_buckets("MATERIAL REQUSITION FOR VALVES", "")
    picked = pick_bucket(scores)
    assert picked["bucket"] == "Documents"
    assert picked["score_top"] == 5  # high confidence


def test_bug1_evalation_typo_matches_reports():
    scores = score_buckets("TECHNICAL BID EVALATION REPORT", "")
    picked = pick_bucket(scores)
    assert picked["bucket"] == "Reports"


def test_bug1_evalatuion_typo_matches_reports():
    scores = score_buckets("TECHNICAL BID EVALATUION FOR PUMPS", "")
    picked = pick_bucket(scores)
    assert picked["bucket"] == "Reports"


def test_bug1_mr_for_abbreviation_matches_documents():
    # Filename pattern '16-01-23-2603-A-Ball valve MR.doc' - "MR" alone is
    # ambiguous, but "MR FOR <X>" in title is a clear Material Requisition.
    scores = score_buckets("MR FOR BALL VALVE", "")
    picked = pick_bucket(scores)
    assert picked["bucket"] == "Documents"


def test_bug1_alignment_sheet_matches_drawings():
    # Real fallthrough: 'ALIGNMENT SHEET 6" WATER DISPOSAL PIPELINE...'
    scores = score_buckets('ALIGNMENT SHEET 6" WATER DISPOSAL PIPELINE', "")
    picked = pick_bucket(scores)
    assert picked["bucket"] == "Drawings"
    assert picked["score_top"] == 5


def test_bug1_singular_detail_matches_drawings():
    # 'VERTICAL LADDER DETAIL' - singular DETAIL not plural DETAILS
    scores = score_buckets("VERTICAL LADDER DETAIL", "")
    picked = pick_bucket(scores)
    # detail(s) is weight 2 -> Drawings if nothing else fires
    assert picked["bucket"] == "Drawings"


# --------------------------------------------------------------------------
# Bug 2: is_latest_letter must be False on every row when the group has any
# numeric_rev. Concrete case from v3 output: ref 16-01-39-2602 had Rev C
# (letter) and Rev 1 (numeric). Rev C was incorrectly flagged is_latest_letter.
# --------------------------------------------------------------------------
def test_bug2_letter_suppressed_when_group_has_numeric():
    rows = [
        {"cust_ref": "16-01-39-2602", "letter_rev": "A", "numeric_rev": "",
         "source_path": "S/2602-A.docx"},
        {"cust_ref": "16-01-39-2602", "letter_rev": "B", "numeric_rev": "",
         "source_path": "S/2602-B.docx"},
        {"cust_ref": "16-01-39-2602", "letter_rev": "C", "numeric_rev": "",
         "source_path": "S/2602-C.docx"},
        {"cust_ref": "16-01-39-2602", "letter_rev": "", "numeric_rev": "1",
         "source_path": "S/2602-1.docx"},
    ]
    compute_is_latest_for_group(rows)
    # No letter row should claim is_latest_letter when a numeric exists.
    assert all(r["is_latest_letter"] is False for r in rows), \
        f"a stale letter row was flagged latest: {[r for r in rows if r['is_latest_letter']]}"
    # The Rev 1 row is the canonical latest.
    latest = [r for r in rows if r["is_latest"]]
    assert len(latest) == 1
    assert latest[0]["numeric_rev"] == "1"


# --------------------------------------------------------------------------
# Bug 3: refs where every file lacks a parseable rev had zero is_latest=true
# rows, silently dropping the doc from "latest of each ref" filters. Concrete
# case: 16-01-08-2606 had three identical no-rev PDFs in three submissions.
# Fix: lex-first source_path wins.
# --------------------------------------------------------------------------
def test_bug3_all_empty_rev_group_marks_first_latest():
    rows = [
        {"cust_ref": "16-01-08-2606", "letter_rev": "", "numeric_rev": "",
         "source_path": "Z-submission/16-01-08-2606.pdf"},
        {"cust_ref": "16-01-08-2606", "letter_rev": "", "numeric_rev": "",
         "source_path": "A-submission/16-01-08-2606.pdf"},
        {"cust_ref": "16-01-08-2606", "letter_rev": "", "numeric_rev": "",
         "source_path": "M-submission/16-01-08-2606.pdf"},
    ]
    compute_is_latest_for_group(rows)
    latest = [r for r in rows if r["is_latest"]]
    assert len(latest) == 1, \
        f"expected exactly 1 is_latest=true, got {len(latest)}"
    # Lex-first by source_path is A-submission/...
    assert latest[0]["source_path"] == "A-submission/16-01-08-2606.pdf", \
        "expected lex-first source_path to win the tiebreak"


def test_bug3_zero_revs_singleton_marks_self_latest():
    # Edge case: single ref-less row.
    rows = [{"cust_ref": "16-99-99-9999", "letter_rev": "", "numeric_rev": "",
             "source_path": "S/x.pdf"}]
    compute_is_latest_for_group(rows)
    assert rows[0]["is_latest"] is True


# --------------------------------------------------------------------------
# Bug 4: schedule numeric + disk letter is the NORMAL pre-issue state during
# IFA review cycles, NOT cross_axis drift. cross_axis is reserved for the
# rare genuine inversion (schedule letter + disk numeric).
# --------------------------------------------------------------------------
def test_bug4_schedule_numeric_disk_letter_is_pre_issue():
    # Real case: schedule says Rev 1, disk has Rev B (still under review).
    drift = classify_revision_drift(
        file_letter="B", file_numeric="", schedule_rev="1",
    )
    assert drift == "pre_issue", \
        f"expected pre_issue (normal IFA state), got {drift}"


def test_bug4_schedule_letter_disk_numeric_is_cross_axis():
    # Genuine inversion: schedule wasn't updated after the doc was promoted.
    drift = classify_revision_drift(
        file_letter="", file_numeric="2", schedule_rev="A",
    )
    assert drift == "cross_axis"


def test_bug4_aligned_letter():
    drift = classify_revision_drift(
        file_letter="B", file_numeric="", schedule_rev="B",
    )
    assert drift == "aligned"


def test_bug4_aligned_numeric():
    drift = classify_revision_drift(
        file_letter="", file_numeric="2", schedule_rev="2",
    )
    assert drift == "aligned"


def test_bug4_disk_newer_letter():
    drift = classify_revision_drift(
        file_letter="C", file_numeric="", schedule_rev="A",
    )
    assert drift == "disk_newer"


def test_bug4_schedule_newer_letter():
    drift = classify_revision_drift(
        file_letter="A", file_numeric="", schedule_rev="C",
    )
    assert drift == "schedule_newer"
