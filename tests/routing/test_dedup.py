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
