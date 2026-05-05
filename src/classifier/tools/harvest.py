"""Harvest (title, expected_bucket, source) triples from input/classified/.

Sources handled:
  1. sahild Phase 2 feed.xlsx          (Type column -> TYPE_TO_BUCKET)
  2. Sahil/Shah PROJECT DRAWING INDEX  (drawings file: discipline-named tabs ->
                                        bucket via numeric Document Code mapping)
  3. Sahil/Shah PROJECT TECHNICAL DOCS INDEX (subjects file: bucket via numeric code)
  4. Shah FFD Project Index            (sheet name + DOC. CODE)
  5. Qusahwira VBC drawings/documents  (Title column; drawings file -> Drawings,
                                        documents file -> bucket via Title prefix)
  6. ENGG DOSSIER INDEX FINAL_10-10-2010 (per-tab; uses Description; multiple tabs)

Writes a single CSV: output/helpers/labelled_corpus.csv with cols
  (source, expected_bucket, doc_code, title)

Run from the project root::

    harvest
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pandas as pd

from classifier.config.buckets import TYPE_TO_BUCKET

CLASSIFIED_DIR = Path("input/classified")
OUT_PATH = Path("output/helpers/labelled_corpus.csv")

# ---------------------------------------------------------------------------
# Numeric Document Code -> bucket. Built from the Document_Type sheet in the
# Sahil/Shah PROJECT DRAWING INDEX. None means ambiguous (skip for ground truth).
# ---------------------------------------------------------------------------
NUMERIC_CODE_TO_BUCKET: dict = {
    0:  "Specifications",
    1:  "Drawings",          # Hazardous Area Classification
    2:  "Drawings", 3: "Drawings", 4: "Drawings", 5: "Drawings", 7: "Drawings",
    8:  "Drawings",          # PFD & P&ID
    9:  None,
    11: None,                # Miscellaneous
    12: "Specifications",
    13: "Drawings", 14: "Drawings",
    15: "Isometrics",
    16: "Drawings",          # Pipe Supports
    17: "Lists_MTOs_BOMs",
    18: "Datasheets",
    19: "Lists_MTOs_BOMs",
    20: "Drawings",
    21: "Drawings",          # General Arrangement - Piping
    22: "Drawings",
    23: None,                # Misc / Stress Analysis Reports - mixed
    24: "Specifications",
    25: "Drawings",
    26: "Lists_MTOs_BOMs",
    27: "Datasheets",
    28: "Drawings",
    31: None, 36: None, 38: None,
    32: "Specifications",
    33: "Drawings",
    34: "Datasheets",
    37: "Specifications",
    39: "Specifications",
    40: "Datasheets",
    41: "Drawings",          # Loop Diagrams
    42: "Drawings",          # Cause & Effect, Logic, Ladder
    43: "Drawings",
    44: "Drawings",
    45: "Drawings",
    46: "Drawings",
    47: "Drawings",
    48: "Lists_MTOs_BOMs",
    49: "Drawings",
    50: "Drawings",
    51: "Datasheets",        # Instrumentation Engineering Sheets
    52: None,
    53: "Specifications",
    54: "Datasheets",
    55: "Lists_MTOs_BOMs",
    56: "Drawings", 57: "Drawings", 58: "Drawings", 59: "Drawings", 60: "Drawings",
    61: "Drawings", 62: "Drawings",
    63: "Lists_MTOs_BOMs",
    64: "Drawings", 65: "Drawings",
    67: None,
    68: "Specifications",
    69: "Datasheets",
    70: "Drawings", 71: "Drawings", 72: "Drawings",
    73: "Lists_MTOs_BOMs",
    74: None,
    75: "Specifications",
    76: "Drawings",          # All Structural and Civil Drawings
    77: "Lists_MTOs_BOMs",
    78: "Drawings", 79: "Drawings",
    82: "Drawings",          # Maps, topographic, plot
    83: None,
    84: "Specifications",
    85: "Datasheets",
    86: "Drawings", 87: "Drawings", 88: "Drawings",
    89: None,
    90: "Procedures_Plans",
    91: "Reports",
    92: "Documents",         # ToR / Contract / Tender / WO Documents
    93: "Reports",
    94: "Documents",         # Engineering Dossiers / Technical Proposal
    95: "Documents",         # Manuals (Engg, Operating, Maintenance, Safety)
    96: "Documents",         # Vendor Data Books
    97: "Reports",           # HAZOP / HAZAN / Audits
    98: "Documents",         # Finance Documents
    99: "Documents",         # Catalogue
}

DISCIPLINE_TABS = {
    "I.GENERAL-MISCELLANEOUS",
    "II.PROCESS",
    "III.PIPING-MTO-STRESS",
    "IV.PIPELINE",
    "V.MECHANICAL",
    "VI.MATERIALS-CORROSION",
    "VII.INSTRUMENTATION",
    "VIII.ELECTRICAL",
    "IX.TELECOMMUNICATION",
    "X.CIVIL-Architecture",
    "XI.HSE",
}


def _to_int(v) -> int | None:
    try:
        if pd.isna(v):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def harvest_dossier(rows: list, path: Path, source: str) -> None:
    """sahild Phase 2 feed.xlsx style: Type column -> TYPE_TO_BUCKET."""
    df = pd.read_excel(path, sheet_name="PDF", header=5)
    for _, r in df.iterrows():
        title = str(r.get("Title", "") or "").strip()
        type_code = str(r.get("Type", "") or "").strip().upper()
        if not title or title.lower() == "nan" or not type_code:
            continue
        bucket = TYPE_TO_BUCKET.get(type_code)
        if bucket is None:
            continue
        rows.append((source, bucket, type_code, title))


def harvest_drawing_index(rows: list, path: Path, source: str) -> None:
    """Sahil/Shah *PROJECT DRAWING INDEX* - per-discipline tabs, header on row 3.
    Title column is 'Drawing Description -Title'.
    """
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        if sheet not in DISCIPLINE_TABS:
            continue
        df = pd.read_excel(path, sheet_name=sheet, header=3)
        title_col = next((c for c in df.columns if "Drawing Description" in str(c) or c == "Subject"), None)
        if title_col is None:
            continue
        code_col = next((c for c in df.columns if str(c).strip() == "Document Code"), None)
        for _, r in df.iterrows():
            title = str(r.get(title_col, "") or "").strip()
            if not title or title.lower() == "nan":
                continue
            code = _to_int(r.get(code_col)) if code_col else None
            bucket = NUMERIC_CODE_TO_BUCKET.get(code) if code is not None else "Drawings"
            if bucket is None:
                continue
            rows.append((source, bucket, str(code) if code is not None else "", title))


def harvest_tech_docs_index(rows: list, path: Path, source: str) -> None:
    """Sahil/Shah *PROJECT TECHNICAL DOCS INDEX* - per-discipline tabs, header on row 3.
    Title column is 'Subject'.
    """
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        if sheet not in DISCIPLINE_TABS:
            continue
        df = pd.read_excel(path, sheet_name=sheet, header=3)
        if "Subject" not in df.columns:
            continue
        code_col = next((c for c in df.columns if str(c).strip() == "Document Code"), None)
        for _, r in df.iterrows():
            title = str(r.get("Subject", "") or "").strip()
            if not title or title.lower() == "nan":
                continue
            code = _to_int(r.get(code_col)) if code_col else None
            bucket = NUMERIC_CODE_TO_BUCKET.get(code) if code is not None else None
            if bucket is None:
                continue
            rows.append((source, bucket, str(code), title))


def harvest_shah_ffd(rows: list, path: Path, source: str) -> None:
    """Shah FFD Project Index.xlsx - sheets carry the bucket name in the title."""
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, header=1)
        title_col = next((c for c in df.columns if str(c).strip().upper() in {"DESCRIPTIONS", "DESCRIPTION", "TITLE"}), None)
        code_col = next((c for c in df.columns if "DOC. CODE" in str(c).upper() or str(c).strip().upper() == "DOC CODE"), None)
        if title_col is None:
            continue
        if "DWG" in sheet.upper():
            default_bucket = "Drawings"
        elif "ISOMETRIC" in sheet.upper():
            default_bucket = "Isometrics"
        elif "DOC" in sheet.upper():
            default_bucket = None
        else:
            continue
        for _, r in df.iterrows():
            title = str(r.get(title_col, "") or "").strip()
            if not title or title.lower() == "nan":
                continue
            code = _to_int(r.get(code_col)) if code_col else None
            bucket = NUMERIC_CODE_TO_BUCKET.get(code) if code is not None else default_bucket
            if bucket is None:
                bucket = default_bucket
            if bucket is None:
                continue
            rows.append((source, bucket, str(code) if code is not None else "", title))


def _override_from_title(default_bucket: str, title: str) -> str:
    """When a source uses a file-level default bucket but the title strongly
    signals otherwise, override. Only applied to file-default sources
    (qusahwira_drawings, asab_void_*) - never to numeric-code-derived labels.
    """
    t = title.lower()
    if "isometric" in t:
        return "Isometrics"
    if "data sheet" in t or "datasheet" in t:
        return "Datasheets"
    return default_bucket


def harvest_qusahwira(rows: list, path: Path, source: str, default_bucket: str | None) -> None:
    """VBC_24Mar2014_drawings/documents.xlsx - flat sheet with Title column."""
    xl = pd.ExcelFile(path)
    sheet = xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, header=0)
    if "Title" not in df.columns:
        return
    for _, r in df.iterrows():
        title = str(r.get("Title", "") or "").strip()
        if not title or title.lower() == "nan":
            continue
        bucket = _override_from_title(default_bucket, title) if default_bucket else default_bucket
        rows.append((source, bucket, "", title))


def harvest_asab_void(rows: list, path: Path, source: str) -> None:
    """input/classified/Asab.../void/*.xls - flat 'Subject'-keyed drawing lists.
    Each file is a drawing-list per area, so default = Drawings.
    """
    xl = pd.ExcelFile(path)
    sheet = xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, header=0)
    title_col = next((c for c in df.columns if str(c).strip() == "Subject"), None)
    if title_col is None:
        return
    for _, r in df.iterrows():
        title = str(r.get(title_col, "") or "").strip()
        if not title or title.lower() == "nan":
            continue
        bucket = _override_from_title("Drawings", title)
        rows.append((source, bucket, "", title))


def main() -> None:
    rows: list[tuple[str, str, str, str]] = []

    p = CLASSIFIED_DIR / "sahild Phase 2 feed.xlsx"
    if p.exists():
        harvest_dossier(rows, p, "sahild_phase2_feed")

    sahil_dir = CLASSIFIED_DIR / "Sahil Drawings & Documents Index"
    if sahil_dir.exists():
        for f in sahil_dir.glob("*"):
            name = f.name
            if "DRAWING  INDEX" in name or "DRAWING INDEX" in name:
                harvest_drawing_index(rows, f, "sahil_drawing_index")
            elif "TECHNICAL DOCS  INDEX" in name or "TECHNICAL DOCS INDEX" in name:
                harvest_tech_docs_index(rows, f, "sahil_tech_docs_index")

    shah_dir = CLASSIFIED_DIR / "Shah Drrawings & Documents Index"
    if shah_dir.exists():
        for f in shah_dir.glob("*"):
            name = f.name
            if "FFD Project Index" in name:
                harvest_shah_ffd(rows, f, "shah_ffd_project_index")
            elif "DRAWING  INDEX" in name or "DRAWING INDEX" in name:
                harvest_drawing_index(rows, f, "shah_drawing_index")
            elif "TECHNICAL DOCS  INDEX" in name or "TECHNICAL DOCS INDEX" in name:
                harvest_tech_docs_index(rows, f, "shah_tech_docs_index")

    q_dir = CLASSIFIED_DIR / "Qusahwira Drawings & Documents Index"
    if q_dir.exists():
        for f in q_dir.glob("*"):
            if "drawings" in f.name.lower():
                harvest_qusahwira(rows, f, "qusahwira_drawings", "Drawings")

    asab_void = CLASSIFIED_DIR / "Asab Drawings & Documents Index" / "void"
    if asab_void.exists():
        for f in asab_void.glob("*.xls"):
            harvest_asab_void(rows, f, f"asab_void_{f.stem}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(("source", "expected_bucket", "doc_code", "title"))
        for r in rows:
            w.writerow(r)

    print(f"wrote {OUT_PATH} with {len(rows)} rows")
    print()
    print("By source:")
    for s, n in Counter(r[0] for r in rows).most_common():
        print(f"  {s:35s} {n:>5}")
    print()
    print("By expected_bucket:")
    for b, n in Counter(r[1] for r in rows).most_common():
        print(f"  {b:18s} {n:>5}")


if __name__ == "__main__":
    main()
