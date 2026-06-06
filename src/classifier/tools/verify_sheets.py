"""Offline verifier: does the title-derived class agree with file content?

For each documents-CSV row, locate its file(s), compute the prose
text-ratio, derive a content class, and report rows where the
title-derived class says "sheet" but the content says "document" (and
the inverse). VERIFICATION ONLY — changes no classification and moves no
files. The threshold is a tunable parameter, calibrated against known
files; it is not a hardcoded business rule.

Usage:
    verify-sheets --csv output/documents_updated.csv \
        --root "D:/Sahil_input" --threshold 0.4 --out output/sheet_verify.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re

from classifier.core.record import Record
from classifier.core.classify import classify_record
from classifier.core.text_ratio import text_ratio

csv.field_size_limit(10 ** 7)

DOCNUM_RE = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")
DEFAULT_THRESHOLD: float = 0.35
SPREADSHEET_EXTS = (".xlsx", ".xlsm", ".xls")


def _pdf_lines(path: str) -> list[str]:
    import pdfplumber
    out: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            out.extend(txt.splitlines())
    return out


def _xlsx_lines(path: str) -> list[str]:
    lower = path.lower()
    out: list[str] = []
    if lower.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                out.append(" ".join("" if c is None else str(c) for c in row))
        wb.close()
    elif lower.endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(path)
        for sh in book.sheets():
            for r in range(sh.nrows):
                out.append(" ".join(str(c) for c in sh.row_values(r)))
    return out


def file_text_ratio(path: str) -> float | None:
    """Prose text-ratio of a file, or None if it can't be read."""
    lower = path.lower()
    try:
        if lower.endswith(".pdf"):
            lines = _pdf_lines(path)
        elif lower.endswith((".xlsx", ".xlsm", ".xls")):
            lines = _xlsx_lines(path)
        else:
            return None
    except Exception:
        return None
    return text_ratio(lines)


def content_class(ratio: float, threshold: float) -> str:
    return "document" if ratio >= threshold else "sheet"


def _index_files(root: str) -> dict[str, list[str]]:
    """Map each embedded doc-number -> list of file paths under root."""
    idx: dict[str, list[str]] = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            m = DOCNUM_RE.search(f)
            if m:
                idx.setdefault(m.group(0), []).append(os.path.join(dirpath, f))
    return idx


def run(csv_path: str, root: str, threshold: float, out_path: str) -> None:
    file_idx = _index_files(root)
    rows_out = []
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ref = (row.get("customer_ref") or "").strip()
            title = row.get("title", "")
            title_class = classify_record(Record(title=title)).doc_type.value
            for path in file_idx.get(ref, []):
                fname = os.path.basename(path)
                if re.match(r"\s*(crs|cta)", fname, re.I):
                    continue  # CRS/CTA never count
                # Spreadsheets are tabular by construction; the prose-ratio
                # gate is PDF-only (verbose MTO description cells read as
                # prose and would false-positive). Only PDFs are gated.
                if fname.lower().endswith(SPREADSHEET_EXTS):
                    ratio = None
                    cclass = "sheet"
                else:
                    ratio = file_text_ratio(path)
                    cclass = "unknown" if ratio is None else content_class(ratio, threshold)
                rows_out.append({
                    "docnum": ref, "title": title, "file": fname,
                    "title_class": title_class,
                    "text_ratio": "" if ratio is None else f"{ratio:.3f}",
                    "content_class": cclass,
                    "mismatch": "1" if (title_class == "sheet"
                                        and cclass == "document") else "",
                })

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    _report(rows_out, threshold)


def _report(rows: list[dict], threshold: float) -> None:
    mism = [r for r in rows if r["mismatch"]]
    inv = [r for r in rows if r["title_class"] == "document"
           and r["content_class"] == "sheet"]
    print(f"\nthreshold              : {threshold}")
    print(f"files checked          : {len(rows)}")
    print(f"sheet->document misses : {len(mism)}")
    print(f"document->sheet misses : {len(inv)}")
    print("\nsheet->document mismatches (title says sheet, content says document):")
    for r in mism:
        print(f"  ratio={r['text_ratio']:>6}  {r['title'][:45]:45}  {r['file'][:30]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify sheet class vs file content.")
    ap.add_argument("--csv", default="output/documents_updated.csv")
    ap.add_argument("--root", default=r"D:/Sahil_input")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--out", default="output/sheet_verify.csv")
    args = ap.parse_args()
    run(args.csv, args.root, args.threshold, args.out)


if __name__ == "__main__":
    main()
