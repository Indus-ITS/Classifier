import csv
from pathlib import Path
from classifier.cli import sort as sort_cli
from classifier.io.schema import TARGET_COLUMNS


def _write_classified(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(TARGET_COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in TARGET_COLUMNS])


def test_cli_end_to_end(tmp_path, capsys):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    for n in ["16-01-19-2602-B.pdf", "16-01-19-2602-A.pdf",
              "16-01-19-2602-B.dwg", "16-01-19-2605-B.xlsx",
              "16-01-19-2605-B.pdf", "sub/random.pdf"]:
        (src / n).write_text("x")

    csv_path = tmp_path / "classified.csv"
    _write_classified(csv_path, [
        {"customer_ref": "16-01-19-2602", "doc_type": "drawing", "title": "P&ID"},
        {"customer_ref": "16-01-19-2605", "doc_type": "sheet", "title": "VALVE LIST"},
        {"customer_ref": "16-01-19-2700", "doc_type": "document", "title": "SPEC"},  # no file
    ])
    dest = tmp_path / "dest"

    rc = sort_cli.main([
        "--classified-csv", str(csv_path),
        "--source-dir", str(src),
        "--dest-dir", str(dest),
    ])
    assert rc == 0
    # drawing winner = pdf (latest rev B); sheet winner = xlsx
    assert (dest / "Drawings" / "16-01-19-2602-B.pdf").exists()
    assert (dest / "Sheets" / "16-01-19-2605-B.xlsx").exists()
    # random.pdf -> Unmatched
    assert (dest / "Unmatched" / "random.pdf").exists()
    # sidecar exists and names the no-file row
    report = dest / "route-report.csv"
    assert report.exists()
    with report.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert any(r["customer_ref"] == "16-01-19-2700" and r["status"] == "no-file-for-row"
               for r in rows)


def test_cli_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "src"; src.mkdir()
    (src / "16-01-19-2602-B.pdf").write_text("x")
    csv_path = tmp_path / "classified.csv"
    _write_classified(csv_path, [
        {"customer_ref": "16-01-19-2602", "doc_type": "drawing", "title": "x"}])
    dest = tmp_path / "dest"
    rc = sort_cli.main([
        "--classified-csv", str(csv_path), "--source-dir", str(src),
        "--dest-dir", str(dest), "--dry-run"])
    assert rc == 0
    assert not dest.exists()
