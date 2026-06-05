from classifier.core.table_detect import (
    _header_cols,
    MIN_HEADER_COLS,
    find_table,
    MIN_DATA_ROWS,
)


def test_header_cols_finds_three_adjacent_text_cells():
    row = [None, "Sr No", "Area", "Line Number", None]
    assert _header_cols(row) == [1, 2, 3]


def test_header_cols_rejects_too_few_columns():
    row = [None, "Title", None, None]
    assert _header_cols(row) is None


def test_header_cols_ignores_pure_numbers_as_header():
    row = [1, 2, 3, 4]
    assert _header_cols(row) is None


def test_header_cols_tolerates_gaps_from_merged_cells():
    row = ["ITEM", "MATERIAL DESCRIPTION", None, None, None, "UNIT", "QTY"]
    assert _header_cols(row) == [0, 1, 5, 6]


def test_min_header_cols_is_three():
    assert MIN_HEADER_COLS == 3


def _mto_grid():
    header = [None, "Sr No", "Tag", "Description", "Qty"]
    rows = [[None, i, f"T-{i}", "VALVE", i * 2] for i in range(1, 9)]
    return [[None] * 5, header, *rows]


def test_find_table_accepts_real_table():
    hit = find_table(_mto_grid())
    assert hit is not None
    assert hit.n_data_rows >= MIN_DATA_ROWS
    assert hit.header_row == 1


def test_find_table_rejects_label_value_form():
    # CRS-style: each "data" row only fills 1-2 scattered cells
    grid = [
        ["DESCON TRANSMITTAL", "ADCO PDR", "DATE", "REVIEW CODE"],
        ["CTA-ED-SA-1576", None, None, None],
        ["REVIEWED BY", None, None, None],
        ["NAME", "Ahmed", None, None],
        ["POSITION", "CE", None, None],
    ]
    assert find_table(grid) is None


def test_find_table_rejects_short_table():
    header = ["A", "B", "C"]
    grid = [header, [1, 2, 3], [4, 5, 6]]  # only 2 data rows < MIN_DATA_ROWS
    assert find_table(grid) is None


def test_find_table_scans_past_leading_blank_rows():
    grid = [[None, None, None, None]] * 4 + _mto_grid()
    assert find_table(grid) is not None



def test_find_table_skips_blank_row_within_data():
    header = ["A", "B", "C"]
    data = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    blank = [None, None, None]
    # blank row in the middle must NOT stop the count
    grid = [header, *data, blank, [10, 11, 12], [13, 14, 15]]
    hit = find_table(grid)
    assert hit is not None
    assert hit.n_data_rows == 5


def test_find_table_accepts_gapped_header_mto():
    header = ["ITEM", "DESCRIPTION", None, None, "UNIT", "QTY"]
    rows = [[str(i), "Pipe", None, None, "m", i * 10] for i in range(1, 7)]
    grid = [header, *rows]
    hit = find_table(grid)
    assert hit is not None
    assert hit.n_data_rows == 6
