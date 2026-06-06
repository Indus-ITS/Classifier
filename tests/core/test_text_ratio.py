from classifier.core.text_ratio import is_prose_line, text_ratio, MIN_PROSE_WORDS


def test_min_prose_words_default():
    assert MIN_PROSE_WORDS == 6


def test_sentence_is_prose():
    assert is_prose_line(
        "South East Group of Fields of Abu Dhabi Company consists of Sahil and Asab")


def test_table_row_is_not_prose():
    assert not is_prose_line("1 01001P 3\"-D-2501 16-01-15 01 / 03")


def test_short_label_is_not_prose():
    assert not is_prose_line("VALVE LIST")


def test_numeric_row_is_not_prose():
    assert not is_prose_line("1 2 3 4 5 6 7 8")


def test_text_ratio_high_for_paragraphs():
    lines = [
        "This document describes the hazardous area classification for the plant.",
        "The introduction sets out the scope and purpose of the study in detail.",
        "Each area is assessed against the relevant standards and guidelines here.",
    ]
    assert text_ratio(lines) > 0.8


def test_text_ratio_low_for_grid():
    lines = ["ITEM DESC QTY", "1 PUMP 4", "2 VALVE 8", "3 PIPE 12", "4 FLANGE 6"]
    assert text_ratio(lines) < 0.2


def test_text_ratio_empty_is_zero():
    assert text_ratio([]) == 0.0
