from pathlib import Path

from classifier.routing.dedup import parse_stem


def test_parse_stem_dash_letter_rev():
    assert parse_stem("16-01-39-2602-B") == ("16-01-39-2602", "B")


def test_parse_stem_underscore_rev_dot_letter():
    assert parse_stem("16-01-27-2604_Rev.A") == ("16-01-27-2604", "A")


def test_parse_stem_dash_digit_rev():
    assert parse_stem("16-99-90-2601-1") == ("16-99-90-2601", "1")


def test_parse_stem_rev_with_trailing_text():
    assert parse_stem("16-01-52-2609_B-MR for MPFM") == ("16-01-52-2609", "B")


def test_parse_stem_no_rev():
    assert parse_stem("16-99-91-2620") == ("16-99-91-2620", None)


def test_parse_stem_does_not_strip_cust_ref_tail():
    assert parse_stem("16-99-91-2602") == ("16-99-91-2602", None)


def test_parse_stem_prefix_text_kept():
    assert parse_stem("CRS 16-99-90-2601-B") == ("crs 16-99-90-2601", "B")


def test_parse_stem_no_cust_ref_fallback():
    assert parse_stem("Drawing-A") == ("drawing", "A")


def test_parse_stem_no_cust_ref_no_rev():
    assert parse_stem("Some Random File") == ("some random file", None)


from classifier.routing.dedup import group_and_pick, FileEntry, DedupResult


def _p(name: str) -> Path:
    return Path("/src") / name


def test_group_and_pick_pdf_beats_docx_same_rev():
    files = [_p("16-01-39-2602-B.pdf"), _p("16-01-39-2602-B.docx")]
    result = group_and_pick(files)
    assert len(result) == 1
    [(_, r)] = result.items()
    assert r.primary == _p("16-01-39-2602-B.pdf")
    assert list(r.related) == [_p("16-01-39-2602-B.docx")]


def test_group_and_pick_digit_rev_beats_letter_rev():
    files = [_p("16-99-90-2601-B.docx"), _p("16-99-90-2601-1.pdf")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("16-99-90-2601-1.pdf")
    assert _p("16-99-90-2601-B.docx") in r.related


def test_group_and_pick_higher_letter_wins():
    files = [_p("16-99-90-2601-A.pdf"), _p("16-99-90-2601-B.pdf")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("16-99-90-2601-B.pdf")


def test_group_and_pick_doc_beats_xls():
    files = [_p("16-01-27-2604_Rev.A.xlsx"), _p("16-01-27-2604-A.doc")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("16-01-27-2604-A.doc")


def test_group_and_pick_skips_non_candidate_extensions_as_winners():
    files = [
        _p("16-99-91-2620-A.dwg"),
        _p("16-99-91-2620-A.pdf"),
    ]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("16-99-91-2620-A.pdf")
    assert _p("16-99-91-2620-A.dwg") in r.related


def test_group_and_pick_group_with_only_non_candidate_has_no_winner():
    files = [_p("16-99-91-2620-A.dwg"), _p("16-99-91-2620-A.rar")]
    result = group_and_pick(files)
    assert result == {}


def test_group_and_pick_xlsx_only_group_still_wins():
    files = [_p("CRS 16-99-90-2601-B.xlsx")]
    result = group_and_pick(files)
    [(_, r)] = result.items()
    assert r.primary == _p("CRS 16-99-90-2601-B.xlsx")
    assert r.related == ()


def test_group_and_pick_deterministic_lexical_tiebreak():
    files = [_p("a.pdf"), _p("b.pdf")]
    result = group_and_pick(files)
    assert len(result) == 2
