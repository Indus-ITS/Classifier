import csv
import classifier.tools.learn_type_discipline as T
from classifier.config.type_enum import KNOWN_TYPES

_T = "ISO" if "ISO" in KNOWN_TYPES else sorted(KNOWN_TYPES)[0]


def _write(path, rows):
    cols = ["type", "discipline_id"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for t, d in rows:
            w.writerow([t, d])


def test_no_fold_import():
    assert not hasattr(T, "_load_fold")


def test_collect_pairs_uses_raw_id(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [(_T, "8")] * 5)
    monkeypatch.setattr(T, "CSV_ROOT", d)
    per_type, orphans = T._collect_pairs(frozenset({8}))
    assert per_type[_T][8] == 5
    assert orphans == {}


def test_collect_pairs_drops_id_not_in_disciplines(tmp_path, monkeypatch):
    d = tmp_path / "csv"; d.mkdir()
    _write(d / "a.csv", [(_T, "999")] * 3)
    monkeypatch.setattr(T, "CSV_ROOT", d)
    per_type, orphans = T._collect_pairs(frozenset({8}))
    assert per_type == {} or per_type.get(_T, {}) == {}
    assert orphans[999] == 3
