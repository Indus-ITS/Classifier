from pathlib import Path
from classifier.routing.dedup import (
    parse_entry, group_files, pick_winner, format_priority, CANDIDATE_EXTS,
)


def test_format_first_prefers_pdf_over_higher_rev_docx():
    # A lower/no-rev pdf still wins over a higher-rev docx when format_first=True.
    entries = [
        parse_entry(Path("16-01-67-2602-001.pdf")),   # no parsed rev
        parse_entry(Path("16-01-67-2602-1.docx")),     # spurious numeric "rev 1"
    ]
    g = pick_winner(entries, "document", format_first=True)
    assert g.winner.name == "16-01-67-2602-001.pdf"
    # Default (rev-first) would instead pick the docx:
    g2 = pick_winner(entries, "document")
    assert g2.winner.name == "16-01-67-2602-1.docx"


def test_format_first_latest_rev_among_pdfs():
    entries = [parse_entry(Path("16-01-19-2602-A.pdf")),
               parse_entry(Path("16-01-19-2602-B.pdf"))]
    g = pick_winner(entries, "document", format_first=True)
    assert g.winner.name == "16-01-19-2602-B.pdf"   # latest revision within pdf


def test_parse_entry_fields():
    e = parse_entry(Path("a/16-01-39-2602-B.pdf"))
    assert e.cust_ref == "16-01-39-2602"
    assert e.group_key == "16-01-39-2602"
    assert e.revision == "B"
    assert e.ext == "pdf"
    assert e.rev_rank == (0, "B")


def test_rev_rank_ordering():
    digit2 = parse_entry(Path("16-01-39-2602-2.pdf")).rev_rank
    digit1 = parse_entry(Path("16-01-39-2602-1.pdf")).rev_rank
    letterB = parse_entry(Path("16-01-39-2602-B.pdf")).rev_rank
    letterA = parse_entry(Path("16-01-39-2602-A.pdf")).rev_rank
    none = parse_entry(Path("16-01-39-2602.pdf")).rev_rank
    assert digit2 > digit1 > letterB > letterA > none


def test_format_priority_class_aware():
    # drawing/document: pdf preferred
    assert format_priority("pdf", "document") < format_priority("xlsx", "document")
    assert format_priority("pdf", "drawing") < format_priority("xls", "drawing")
    # sheet: xlsx preferred over pdf
    assert format_priority("xlsx", "sheet") < format_priority("pdf", "sheet")
    assert format_priority("xls", "sheet") < format_priority("pdf", "sheet")
    # unknown class behaves like doc (pdf-first)
    assert format_priority("pdf", None) < format_priority("xlsx", None)


def test_pick_winner_prefers_latest_rev_then_format():
    entries = [
        parse_entry(Path("16-01-39-2602-A.pdf")),
        parse_entry(Path("16-01-39-2602-B.pdf")),
        parse_entry(Path("16-01-39-2602-B.docx")),
    ]
    g = pick_winner(entries, "document")
    assert g.winner == Path("16-01-39-2602-B.pdf")
    assert Path("16-01-39-2602-B.docx") in g.related
    assert Path("16-01-39-2602-A.pdf") in g.related


def test_pick_winner_sheet_prefers_xlsx():
    entries = [
        parse_entry(Path("16-01-39-2602-B.pdf")),
        parse_entry(Path("16-01-39-2602-B.xlsx")),
    ]
    g = pick_winner(entries, "sheet")
    assert g.winner == Path("16-01-39-2602-B.xlsx")


def test_non_candidate_never_wins_but_is_related():
    entries = [
        parse_entry(Path("16-01-39-2602-B.dwg")),
        parse_entry(Path("16-01-39-2602-B.pdf")),
    ]
    g = pick_winner(entries, "drawing")
    assert g.winner == Path("16-01-39-2602-B.pdf")
    assert Path("16-01-39-2602-B.dwg") in g.related


def test_group_with_only_non_candidates_has_no_winner():
    entries = [parse_entry(Path("16-01-39-2602-B.dwg"))]
    g = pick_winner(entries, "drawing")
    assert g.winner is None
    assert Path("16-01-39-2602-B.dwg") in g.related


def test_group_files_groups_by_group_key():
    paths = [Path("16-01-39-2602-A.pdf"), Path("16-01-39-2602-B.pdf"),
             Path("16-01-39-2700-A.pdf")]
    groups = group_files(paths)
    assert set(groups) == {"16-01-39-2602", "16-01-39-2700"}
    assert len(groups["16-01-39-2602"]) == 2
