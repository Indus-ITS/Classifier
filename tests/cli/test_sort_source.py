import csv
from pathlib import Path
from classifier.cli import sort_source as ss


def _docs(path, rows):
    cols = ["customer_ref", "document_no", "doc_source", "title"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(cols)
        for r in rows:
            w.writerow(r)


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x")


def test_cli_buckets_with_class_subfolders(tmp_path):
    deliv = tmp_path / "DELIV"; prop = tmp_path / "PROP"
    _touch(deliv / "C1" / "16-01-19-2602-B.pdf")
    _touch(deliv / "C1" / "16-01-19-2602-B.docx")          # collapsed (not copied)
    _touch(deliv / "C2" / "16-01-19-2605-A.xlsx")          # a sheet -> xlsx
    _touch(deliv / "C3" / "99-99-99-9999-A.pdf")           # unmatched stranger
    _touch(prop / "Write up Inst 240414.doc")              # proposal by filename
    docs = tmp_path / "docs.csv"
    _docs(docs, [
        ("16-01-19-2602", "d1", "deliverable", "SPECIFICATION FOR PIPING MATERIAL"),
        ("16-01-19-2605", "d2", "deliverable", "VALVE LIST"),
        ("PROPOSAL-WRITE-UP-INST-240414", "Write up Inst 240414.doc", "proposal",
         "INSTRUMENT WRITE UP"),
    ])
    dest = tmp_path / "out"
    rc = ss.main(["--documents", str(docs), "--dest", str(dest),
                  "--source", str(deliv), "--source", str(prop)])
    assert rc == 0
    assert (dest / "deliverable" / "document" / "16-01-19-2602-B.pdf").exists()
    assert not (dest / "deliverable" / "document" / "16-01-19-2602-B.docx").exists()
    assert (dest / "deliverable" / "sheet" / "16-01-19-2605-A.xlsx").exists()
    # proposal file lands under proposal/<class>/ (class depends on the classifier)
    assert list((dest / "proposal").rglob("Write up Inst 240414.doc"))
    assert (dest / "unmatched" / "99-99-99-9999-A.pdf").exists()   # flat, no class
    assert (dest / "route-by-source-report.csv").exists()


def test_dry_run_copies_nothing(tmp_path):
    d = tmp_path / "D"; _touch(d / "16-01-19-2602-B.pdf")
    docs = tmp_path / "docs.csv"
    _docs(docs, [("16-01-19-2602", "x", "deliverable", "SPECIFICATION FOR PIPING")])
    dest = tmp_path / "out"
    rc = ss.main(["--documents", str(docs), "--dest", str(dest),
                  "--source", str(d), "--dry-run"])
    assert rc == 0
    assert not dest.exists()
