from pathlib import Path
from classifier.io.classified_index import Classification
from classifier.routing.dedup import group_files
from classifier.routing.plan import build_plan, BUCKET_FOR_DOCTYPE


def _plan(paths, index, dest="dest"):
    groups = group_files([Path(p) for p in paths])
    return build_plan(groups, index, Path(dest))


def test_winner_routed_to_class_bucket():
    index = {"16-01-19-2602": Classification("drawing", "P&ID")}
    plan = _plan(["16-01-19-2602-B.pdf", "16-01-19-2602-A.pdf"], index)
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.bucket == "Drawings"
    assert a.dest == Path("dest/Drawings/16-01-19-2602-B.pdf")
    assert a.chosen_format == "pdf"
    assert Path("16-01-19-2602-A.pdf") in a.related


def test_sheet_class_uses_sheet_bucket_and_xlsx_winner():
    index = {"16-01-19-2602": Classification("sheet", "VALVE LIST")}
    plan = _plan(["16-01-19-2602-B.pdf", "16-01-19-2602-B.xlsx"], index)
    a = plan.actions[0]
    assert a.bucket == "Sheets"
    assert a.dest.name == "16-01-19-2602-B.xlsx"


def test_no_cust_ref_match_goes_to_unmatched():
    plan = _plan(["random-doc.pdf"], index={})
    a = plan.actions[0]
    assert a.bucket == "Unmatched"
    assert a.dest == Path("dest/Unmatched/random-doc.pdf")


def test_cust_ref_not_in_index_goes_to_unmatched():
    plan = _plan(["16-01-19-2602-B.pdf"], index={})
    assert plan.actions[0].bucket == "Unmatched"


def test_rows_without_file_reported():
    index = {"16-01-19-2602": Classification("drawing", "x"),
             "16-01-19-2999": Classification("document", "y")}
    plan = _plan(["16-01-19-2602-B.pdf"], index)
    assert plan.rows_without_file == ("16-01-19-2999",)


def test_skipped_no_preferred_format():
    index = {"16-01-19-2602": Classification("drawing", "x")}
    plan = _plan(["16-01-19-2602-B.dwg"], index)
    assert plan.actions == ()
    assert "16-01-19-2602" in plan.skipped_no_preferred_format


def test_unknown_doc_type_routes_unmatched_not_double_counted():
    index = {"16-01-19-2602": Classification("widget", "x")}
    plan = _plan(["16-01-19-2602-B.pdf"], index)
    assert plan.actions[0].bucket == "Unmatched"
    assert plan.actions[0].doc_type == "widget"
    assert plan.rows_without_file == ()   # had a file -> not "without file"


def test_same_name_different_dirs_merge_into_one_group():
    # Two files with the same name (hence same group_key) merge into one
    # group: one winner, the other becomes a sibling. This is why dest
    # basenames are unique per bucket and no collision handling is needed.
    plan = _plan(["sub1/doc.pdf", "sub2/doc.pdf"], index={})
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.dest == Path("dest/Unmatched/doc.pdf")
    assert len(a.related) == 1
