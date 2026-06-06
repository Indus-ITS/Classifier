import openpyxl
from classifier.tools.verify_sheets import file_text_ratio, content_class


def test_xlsx_grid_has_low_ratio(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ITEM", "DESC", "QTY"])
    for i in range(1, 8):
        ws.append([i, "VALVE", i * 2])
    p = tmp_path / "grid.xlsx"
    wb.save(p)
    assert file_text_ratio(str(p)) < 0.2


def test_content_class_threshold():
    assert content_class(0.9, 0.4) == "document"
    assert content_class(0.05, 0.4) == "sheet"
