import csv
from pathlib import Path
from classifier.cli import sort_source as ss


def _docs(path, rows):
    cols = ["customer_ref", "doc_type"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(cols)
        for r in rows: w.writerow(r)


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x")


def test_cli_copies_into_buckets(tmp_path):
    feed = tmp_path / "FEED"; deliv = tmp_path / "DELIV"
    _touch(feed / "16-01-19-2602-B.pdf")
    _touch(feed / "16-01-19-2602-B.docx")        # sibling, not copied
    _touch(deliv / "sub" / "16-01-19-2605-A.pdf")
    _touch(deliv / "sub" / "99-99-99-9999-A.pdf")  # unmatched
    docs = tmp_path / "docs.csv"
    _docs(docs, [("16-01-19-2602", "document"), ("16-01-19-2605", "sheet")])
    dest = tmp_path / "out"

    rc = ss.main(["--documents", str(docs), "--dest", str(dest),
                  "--source", f"feed={feed}", "--source", f"deliverable={deliv}"])
    assert rc == 0
    assert (dest / "feed" / "16-01-19-2602-B.pdf").exists()
    assert not (dest / "feed" / "16-01-19-2602-B.docx").exists()  # deduped
    assert (dest / "deliverable" / "16-01-19-2605-A.pdf").exists()
    assert (dest / "unmatched" / "99-99-99-9999-A.pdf").exists()
    assert (dest / "route-by-source-report.csv").exists()


def test_dry_run_copies_nothing(tmp_path):
    feed = tmp_path / "FEED"; _touch(feed / "16-01-19-2602-B.pdf")
    docs = tmp_path / "docs.csv"; _docs(docs, [("16-01-19-2602", "document")])
    dest = tmp_path / "out"
    rc = ss.main(["--documents", str(docs), "--dest", str(dest),
                  "--source", f"feed={feed}", "--dry-run"])
    assert rc == 0
    assert not dest.exists()
