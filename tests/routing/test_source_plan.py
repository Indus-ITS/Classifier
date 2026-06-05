from pathlib import Path
from classifier.routing.source_plan import DocRow, build_plan

# Titles chosen to classify deterministically:
DOC = "SPECIFICATION FOR PIPING MATERIAL"   # -> document
DRW = "PIPING AND INSTRUMENT DIAGRAM"       # -> drawing
SHEET = "VALVE LIST"                         # -> sheet


def _row(cref="", docno="", src="deliverable", title=DOC):
    return DocRow(customer_ref=cref, document_no=docno, doc_source=src, title=title)


def test_cust_ref_row_bucketed_by_doc_source_and_class():
    rows = [_row(cref="16-01-19-2602", src="deliverable", title=DOC)]
    files = [Path("d/16-01-19-2602-B.pdf"), Path("d/16-01-19-2602-B.docx")]
    plan = build_plan(rows, files)
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.bucket == "deliverable" and a.doc_class == "document" and a.matched is True
    assert a.src.name == "16-01-19-2602-B.pdf"   # pdf preferred (format-first)


def test_bucket_is_csv_doc_source_not_folder():
    rows = [_row(cref="16-01-76-0602", src="feed", title=DRW)]
    files = [Path("deliverable_dir/16-01-76-0602_2.pdf")]
    plan = build_plan(rows, files)
    a = plan.actions[0]
    assert a.bucket == "feed" and a.doc_class == "drawing"


def test_proposal_matched_by_document_no_filename():
    rows = [_row(cref="PROPOSAL-WRITE-UP-INST-240414",
                 docno="Write up Inst 240414.doc", src="proposal", title=DOC)]
    files = [Path("p/Write up Inst 240414.doc")]
    plan = build_plan(rows, files)
    assert len(plan.actions) == 1
    a = plan.actions[0]
    assert a.bucket == "proposal" and a.doc_class == "document"
    assert a.src.name == "Write up Inst 240414.doc"


def test_one_winner_collapses_crs_and_formats():
    rows = [_row(cref="16-01-39-2602", src="deliverable", title=DOC)]
    files = [Path("16-01-39-2602-B.pdf"), Path("16-01-39-2602-B.docx"),
             Path("Comment Response Sheet-16-01-39-2602.xlsx")]
    plan = build_plan(rows, files)
    acts = [a for a in plan.actions if a.bucket == "deliverable"]
    assert len(acts) == 1
    assert acts[0].src.name == "16-01-39-2602-B.pdf"
    assert len(acts[0].related) == 2


def test_sheet_title_prefers_xlsx_and_sheet_class():
    rows = [_row(cref="16-01-19-2602", src="deliverable", title=SHEET)]
    files = [Path("16-01-19-2602-B.pdf"), Path("16-01-19-2602-B.xlsx")]
    plan = build_plan(rows, files)
    a = plan.actions[0]
    assert a.doc_class == "sheet"
    assert a.src.name == "16-01-19-2602-B.xlsx"


def test_row_without_file_recorded():
    plan = build_plan([_row(cref="16-01-19-9999")], [])
    assert plan.actions == ()
    assert plan.rows_without_file


def test_leftover_unknown_cust_ref_goes_unmatched_flat():
    rows = [_row(cref="16-01-19-2602", src="deliverable")]
    files = [Path("16-01-19-2602-A.pdf"), Path("99-99-99-9999-A.pdf")]
    plan = build_plan(rows, files)
    um = next(a for a in plan.actions if a.bucket == "unmatched")
    assert um.key == "99-99-99-9999" and um.matched is False
    assert um.doc_class == ""          # flat: no title to classify


def test_junk_without_cust_ref_is_ignored():
    rows = [_row(cref="16-01-19-2602")]
    files = [Path("16-01-19-2602-A.pdf"), Path("Transmittal Form.pdf")]
    plan = build_plan(rows, files)
    names = {a.src.name for a in plan.actions}
    assert "Transmittal Form.pdf" not in names
