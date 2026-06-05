import csv
import classifier.tools.learn_discipline_keywords as L


def _write(path, rows):
    cols = ["discipline_id", "title"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def test_no_fold_symbols():
    # The fold is gone entirely.
    assert not hasattr(L, "_load_fold")
    assert not hasattr(L, "DISCIPLINE_FOLD_CSV")


def test_collect_rows_uses_raw_id_no_remap(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [{"discipline_id": "8", "title": "VALVE LIST"},
                         {"discipline_id": "8", "title": "MTO FOR PIPES"}])
    monkeypatch.setattr(L, "CSV_ROOT", d)
    rows, orphans = L._collect_rows(frozenset({1, 8}))
    assert sorted(rows_d := [dd for dd, _, _ in rows]) == [8, 8]
    assert orphans == {}


def test_collect_rows_drops_id_not_in_disciplines(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [{"discipline_id": "999", "title": "X"},
                         {"discipline_id": "8", "title": "VALVE"}])
    monkeypatch.setattr(L, "CSV_ROOT", d)
    rows, orphans = L._collect_rows(frozenset({8}))
    assert [dd for dd, _, _ in rows] == [8]
    assert orphans[999] == 1


def test_valid_discipline_ids_loaded_from_disciplines_csv():
    ids = L._load_valid_discipline_ids()
    # disciplines.csv contains these (sanity)
    assert {1, 3, 6, 7, 8, 11}.issubset(ids)
