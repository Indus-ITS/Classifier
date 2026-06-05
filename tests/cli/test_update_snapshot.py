import csv
from pathlib import Path
import pandas as pd
from classifier.cli import update_snapshot as us
from classifier.io.disciplines import load_valid_discipline_ids


def _snapshot(path, rows):
    cols = ["document_id", "title", "doc_type", "type", "discipline_id", "doc_source"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def test_process_rules(tmp_path):
    valid = load_valid_discipline_ids()  # real table
    snap = tmp_path / "snap.csv"
    _snapshot(snap, [
        # feed: type preserved; doc_type recomputed
        {"document_id": "1", "title": "VALVE LIST", "doc_type": "document",
         "type": "FEEDTYPE", "discipline_id": "", "doc_source": "feed"},
        # non-feed: type overwritten; missing discipline filled if rule hits
        {"document_id": "2", "title": "PIPING AND INSTRUMENT DIAGRAM",
         "doc_type": "document", "type": "", "discipline_id": "", "doc_source": "deliverable"},
        # invalid discipline 17 -> treated as missing (never stays 17)
        {"document_id": "3", "title": "FOUNDATION LAYOUT", "doc_type": "drawing",
         "type": "DWG", "discipline_id": "17", "doc_source": "deliverable"},
    ])
    df = pd.read_csv(snap, dtype=str, keep_default_na=False)
    out, changes, summary = us.process(df, valid)

    rows = {r["document_id"]: r for _, r in out.iterrows()}
    # feed type preserved
    assert rows["1"]["type"] == "FEEDTYPE"
    # doc_type recomputed for all (VALVE LIST -> sheet)
    assert rows["1"]["doc_type"] == "sheet"
    # non-feed type overwritten (no longer empty -> a code or blank, but not the
    # literal old empty stays empty only if classifier misses)
    # every written discipline id is valid or empty
    for r in rows.values():
        d = r["discipline_id"]
        assert d == "" or int(d) in valid
    # doc 3 never keeps the invalid 17
    assert rows["3"]["discipline_id"] != "17"
    # changes only lists changed docs
    changed_ids = {c["document_id"] for c in changes}
    assert "1" in changed_ids  # doc_type document->sheet


def test_main_writes_outputs(tmp_path):
    snap = tmp_path / "snap.csv"
    _snapshot(snap, [
        {"document_id": "1", "title": "VALVE LIST", "doc_type": "document",
         "type": "X", "discipline_id": "", "doc_source": "feed"},
    ])
    out_dir = tmp_path / "out"
    rc = us.main(["--input", str(snap), "--out-dir", str(out_dir)])
    assert rc == 0
    assert (out_dir / "documents_updated.csv").exists()
    assert (out_dir / "documents_changes.csv").exists()
    upd = pd.read_csv(out_dir / "documents_updated.csv", dtype=str, keep_default_na=False)
    assert list(upd["document_id"]) == ["1"]
    assert upd.iloc[0]["doc_type"] == "sheet"   # recomputed
    assert upd.iloc[0]["type"] == "X"           # feed preserved
