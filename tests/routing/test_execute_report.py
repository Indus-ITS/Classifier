import csv
from pathlib import Path
from classifier.io.classified_index import Classification
from classifier.routing.dedup import group_files
from classifier.routing.plan import build_plan
from classifier.routing.execute import execute
from classifier.routing.report import report_rows, write_report_csv


def _make(tmp_path, names):
    src = tmp_path / "src"
    src.mkdir()
    for n in names:
        p = src / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    return src


def test_execute_copies_winner_and_creates_buckets(tmp_path):
    src = _make(tmp_path, ["16-01-19-2602-B.pdf", "16-01-19-2602-A.pdf"])
    index = {"16-01-19-2602": Classification("drawing", "P&ID")}
    dest = tmp_path / "dest"
    plan = build_plan(group_files(sorted(src.rglob("*"))), index, dest)
    done = execute(plan, dry_run=False)
    assert (dest / "Drawings" / "16-01-19-2602-B.pdf").exists()
    assert not (dest / "Drawings" / "16-01-19-2602-A.pdf").exists()  # sibling not copied
    assert len(done) == 1
    # source untouched (copy, not move)
    assert (src / "16-01-19-2602-A.pdf").exists()


def test_dry_run_copies_nothing(tmp_path):
    src = _make(tmp_path, ["16-01-19-2602-B.pdf"])
    index = {"16-01-19-2602": Classification("drawing", "x")}
    dest = tmp_path / "dest"
    plan = build_plan(group_files(sorted(src.rglob("*"))), index, dest)
    execute(plan, dry_run=True)
    assert not dest.exists()


def test_report_rows_and_csv(tmp_path):
    src = _make(tmp_path, ["16-01-19-2602-B.pdf", "16-01-19-2602-B.dwg",
                           "16-01-19-2999-A.pdf", "random.pdf"])
    index = {"16-01-19-2602": Classification("drawing", "P&ID"),
             "16-01-19-2999": Classification("document", "SPEC"),
             "16-01-19-3000": Classification("sheet", "LIST")}  # no file
    dest = tmp_path / "dest"
    plan = build_plan(group_files(sorted(src.rglob("*"))), index, dest)
    rows = report_rows(plan, index)
    statuses = {r["status"] for r in rows}
    assert "copied" in statuses
    assert "no-file-for-row" in statuses          # 16-01-19-3000
    # the random.pdf has no cust_ref -> routed Unmatched -> status unmatched-file
    assert "unmatched-file" in statuses
    out = write_report_csv(rows, dest)
    assert out.exists()
    with out.open(encoding="utf-8") as f:
        got = list(csv.DictReader(f))
    assert any(r["customer_ref"] == "16-01-19-3000" and r["status"] == "no-file-for-row"
               for r in got)


def test_report_class_column_is_lowercase_doctype(tmp_path):
    src = _make(tmp_path, ["16-01-19-2602-B.pdf"])
    index = {"16-01-19-2602": Classification("drawing", "P&ID"),
             "16-01-19-3000": Classification("sheet", "LIST")}  # no file
    dest = tmp_path / "dest"
    plan = build_plan(group_files(sorted(src.rglob("*"))), index, dest)
    rows = {r["customer_ref"]: r for r in report_rows(plan, index)}
    assert rows["16-01-19-2602"]["class"] == "drawing"   # copied row, lowercase
    assert rows["16-01-19-3000"]["class"] == "sheet"     # no-file row, lowercase
