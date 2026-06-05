import csv
from pathlib import Path
from classifier.io.classified_index import load_classified_index
from classifier.io.schema import TARGET_COLUMNS


def _write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(TARGET_COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in TARGET_COLUMNS])


def test_maps_cust_ref_to_classification(tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, [
        {"customer_ref": "16-01-19-2602", "doc_type": "sheet", "title": "VALVE LIST"},
        {"customer_ref": "16-01-19-2605", "doc_type": "drawing", "title": "P&ID"},
    ])
    idx = load_classified_index(p)
    assert idx["16-01-19-2602"].doc_type == "sheet"
    assert idx["16-01-19-2602"].title == "VALVE LIST"
    assert idx["16-01-19-2605"].doc_type == "drawing"


def test_empty_cust_ref_skipped_and_first_wins_on_dup(tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, [
        {"customer_ref": "", "doc_type": "document", "title": "no ref"},
        {"customer_ref": "16-01-19-2602", "doc_type": "drawing", "title": "first"},
        {"customer_ref": "16-01-19-2602", "doc_type": "sheet", "title": "second"},
    ])
    idx = load_classified_index(p)
    assert "" not in idx
    assert idx["16-01-19-2602"].title == "first"   # first wins
    assert idx["16-01-19-2602"].doc_type == "drawing"


def test_doc_type_lowercased(tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, [{"customer_ref": "16-01-19-2602", "doc_type": "Drawing", "title": "x"}])
    idx = load_classified_index(p)
    assert idx["16-01-19-2602"].doc_type == "drawing"
