"""Convert every ``input/classified/**/*.xls*`` into a 28-column CSV.

Output mirrors the source tree under ``input/classified_csv/`` with one
CSV per sheet. Filenames: ``<workbook-stem>__<sheet-slug>.csv``.
Section-header rows and column mapping are documented in the spec
``docs/superpowers/specs/2026-05-13-uniform-csv-and-classifier-design.md``.

Run from project root::

    convert-classified
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.io.normalize import is_empty, normalize_header_token, slugify_sheet
from classifier.io.schema import TARGET_COLUMNS, validate_schema

SRC_ROOT = Path("input/classified")
DST_ROOT = Path("input/classified_csv")

# Source-header -> target-column map. Keys are normalized header tokens
# (see normalize_header_token). One target may have several source
# aliases; first match wins per row.
HEADER_ALIASES: dict[str, str] = {
    "document no": "document_no",
    "doc no": "document_no",
    "pcs doc no": "document_no",
    "title": "title",
    "rev": "rev",
    "revision": "rev",
    "status": "status",
    "type": "type",
    "volume": "volume",
    "book": "book",
    "cust ref": "customer_ref",
    "cust ref #": "customer_ref",
    "customer ref": "customer_ref",
    "customer reference": "customer_ref",
}

# Section labels that map cleanly to the ``category`` target column.
KNOWN_CATEGORIES: frozenset[str] = frozenset({
    "project management", "process", "mechanical", "electrical",
    "instrumentation", "piping", "civil", "structural", "safety",
    "telecom", "hvac",
})

# Section labels that resolve doc_type when row.type is absent.
DOC_TYPE_FROM_SECTION: dict[str, str] = {
    "document": "document", "documents": "document",
    "drawing": "drawing", "drawings": "drawing",
}


def _find_header_row(df: pd.DataFrame) -> int | None:
    """Return the 0-indexed row that contains both 'document no' and 'type'.

    Scans the first 50 rows. Returns None on miss.
    """
    for i in range(min(50, len(df))):
        tokens = {normalize_header_token(c) for c in df.iloc[i].tolist()}
        if "document no" in tokens and "type" in tokens:
            return i
    return None


def _build_column_index(header_row: Sequence[object]) -> dict[str, int]:
    """Map target-column name -> source column index."""
    mapping: dict[str, int] = {}
    for idx, raw in enumerate(header_row):
        target = HEADER_ALIASES.get(normalize_header_token(raw))
        if target and target not in mapping:
            mapping[target] = idx
    return mapping


def _is_section_label(row: Sequence[object], col_idx: dict[str, int]) -> bool:
    """A row is a section label if column A is short alpha-ish and the
    primary data columns are blank.
    """
    if is_empty(row[0]):
        return False
    label = str(row[0]).strip()
    if len(label) > 40:
        return False
    if any(ch.isdigit() or ch == ":" for ch in label):
        return False
    if not all(ch.isalpha() or ch in " /&-" for ch in label):
        return False
    # Skip document_no: section labels often sit in the doc_no column
    # itself (e.g. row=["Project Management","","",...]).
    for key in ("type", "title", "rev"):
        col = col_idx.get(key)
        if col is not None and not is_empty(row[col]):
            return False
    return True


def _doc_type_for(section_label: str, type_code: str) -> str:
    """Derive ``doc_type`` from a row's section label and Type code."""
    norm = section_label.strip().lower()
    if norm in DOC_TYPE_FROM_SECTION:
        return DOC_TYPE_FROM_SECTION[norm]
    code = type_code.strip().upper()
    bucket = TYPE_TO_BUCKET.get(code)
    if bucket is None:
        return ""
    folded = BUCKET_TO_CLASS[bucket]
    return "drawing" if folded == "Drawings" else "document"


def xlsx_to_rows(workbook_path: Path) -> Iterable[tuple[str, list[dict[str, str]]]]:
    """Yield ``(sheet_name, list_of_28-col_dicts)`` per readable sheet."""
    xl = pd.ExcelFile(workbook_path)
    for sheet in xl.sheet_names:
        df = pd.read_excel(
            workbook_path, sheet_name=sheet,
            header=None, dtype=str, keep_default_na=False, na_values=[],
        )
        header_idx = _find_header_row(df)
        if header_idx is None:
            print(f"  [skip] {workbook_path.name}::{sheet}: no header row found")
            continue
        col_idx = _build_column_index(df.iloc[header_idx].tolist())

        rows: list[dict[str, str]] = []
        section_label = ""
        unknown_sections: Counter[str] = Counter()
        for i in range(header_idx + 1, len(df)):
            row = df.iloc[i].tolist()
            if _is_section_label(row, col_idx):
                section_label = str(row[0]).strip()
                if section_label.lower() not in KNOWN_CATEGORIES and \
                   section_label.lower() not in DOC_TYPE_FROM_SECTION:
                    unknown_sections[section_label] += 1
                continue

            doc_no_col = col_idx.get("document_no")
            if doc_no_col is None or is_empty(row[doc_no_col]):
                continue

            target: dict[str, str] = {c: "" for c in TARGET_COLUMNS}
            for key, idx in col_idx.items():
                v = row[idx]
                target[key] = "" if is_empty(v) else str(v).strip()

            type_code = target.get("type", "")
            target["doc_type"] = _doc_type_for(section_label, type_code)
            lower_label = section_label.lower()
            if lower_label in KNOWN_CATEGORIES:
                target["category"] = section_label
            target["doc_source"] = workbook_path.name

            rows.append(target)

        if unknown_sections:
            top = ", ".join(f"{k!r}({n})" for k, n in unknown_sections.most_common(5))
            print(f"  unknown section labels in {workbook_path.name}::{sheet}: {top}")
        yield sheet, rows


def _write_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    validate_schema(TARGET_COLUMNS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(TARGET_COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in TARGET_COLUMNS])


def _walk_workbooks() -> list[Path]:
    paths = [p for p in SRC_ROOT.rglob("*.xls*")
             if "void" not in {part.lower() for part in p.parts}]
    return sorted(paths, key=lambda p: str(p).lower())


def main() -> None:
    if not SRC_ROOT.exists():
        raise SystemExit(f"source dir not found: {SRC_ROOT}")

    workbooks = _walk_workbooks()
    print(f"Found {len(workbooks)} workbook(s) under {SRC_ROOT} (excluding void/).\n")

    per_file: list[tuple[str, str, int]] = []
    for wb in workbooks:
        rel = wb.relative_to(SRC_ROOT)
        print(f"[{wb.name}]")
        seen_slugs: defaultdict[str, int] = defaultdict(int)
        for sheet, rows in xlsx_to_rows(wb):
            slug = slugify_sheet(sheet)
            seen_slugs[slug] += 1
            if seen_slugs[slug] > 1:
                slug = f"{slug}_{seen_slugs[slug]}"
            out_name = f"{wb.stem}__{slug}.csv"
            out_path = DST_ROOT / rel.parent / out_name
            _write_csv(rows, out_path)
            per_file.append((wb.name, sheet, len(rows)))
            print(f"  -> {out_path}  ({len(rows)} rows)")

    print()
    print(f"Wrote {len(per_file)} CSV file(s).")
    total_rows = sum(n for _, _, n in per_file)
    print(f"Total rows: {total_rows}")


if __name__ == "__main__":
    main()
