from classifier.core.table_detect import _header_span, MIN_HEADER_COLS


def test_header_span_finds_three_adjacent_text_cells():
    row = [None, "Sr No", "Area", "Line Number", None]
    start, width = _header_span(row)
    assert (start, width) == (1, 3)


def test_header_span_rejects_too_few_columns():
    row = [None, "Title", None, None]
    assert _header_span(row) is None


def test_header_span_ignores_pure_numbers_as_header():
    # a row of numbers is data, not a header
    row = [1, 2, 3, 4]
    assert _header_span(row) is None


def test_min_header_cols_is_three():
    assert MIN_HEADER_COLS == 3
