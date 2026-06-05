from pathlib import Path
from classifier.routing.source_plan import build_source_plan


def test_matched_goes_to_label_bucket_unmatched_to_unmatched():
    sources = [("feed", [Path("16-01-19-2602-B.pdf"), Path("99-99-99-9999-A.pdf")])]
    plan = build_source_plan(sources, {"16-01-19-2602": "document"})
    by_ref = {a.customer_ref: a for a in plan.actions}
    assert by_ref["16-01-19-2602"].bucket == "feed"
    assert by_ref["16-01-19-2602"].matched is True
    assert by_ref["99-99-99-9999"].bucket == "unmatched"
    assert by_ref["99-99-99-9999"].matched is False


def test_no_cust_ref_stays_in_source_bucket():
    # Proposal write-ups have no cust_ref -> they belong in their source bucket,
    # NOT unmatched. unmatched is only for a cust_ref the table doesn't know.
    sources = [("proposal", [Path("Write up Elec 220414.doc")])]
    plan = build_source_plan(sources, {"16-01-19-2602": "document"})
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.bucket == "proposal"
    assert a.customer_ref is None
    assert a.matched is False


def test_dedup_one_winner_pdf_for_document():
    sources = [("deliverable", [
        Path("d/16-01-19-2602-B.pdf"),
        Path("d/16-01-19-2602-B.docx"),
        Path("d/16-01-19-2602-A.pdf"),
    ])]
    plan = build_source_plan(sources, {"16-01-19-2602": "document"})
    acts = [a for a in plan.actions if a.customer_ref == "16-01-19-2602"]
    assert len(acts) == 1
    assert acts[0].src.name == "16-01-19-2602-B.pdf"
    assert acts[0].chosen_format == "pdf"


def test_sheet_prefers_xlsx():
    sources = [("deliverable", [
        Path("16-01-19-2602-B.pdf"), Path("16-01-19-2602-B.xlsx")])]
    plan = build_source_plan(sources, {"16-01-19-2602": "sheet"})
    a = next(a for a in plan.actions if a.customer_ref == "16-01-19-2602")
    assert a.src.name == "16-01-19-2602-B.xlsx"


def test_only_non_candidate_ext_is_skipped():
    sources = [("feed", [Path("16-01-19-2602-B.dwg")])]
    plan = build_source_plan(sources, {"16-01-19-2602": "drawing"})
    assert plan.actions == ()
    assert ("feed", "16-01-19-2602") in plan.skipped_no_preferred
