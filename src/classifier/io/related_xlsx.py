"""Write the related-documents.xlsx sidecar listing winners + dropped siblings."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

OUTPUT_FILENAME = "related-documents.xlsx"

COLUMNS = [
    "cust_ref",
    "title",
    "class",
    "discipline",
    "revision",
    "chosen_file",
    "chosen_format",
    "related_files",
    "related_count",
    "source_group_dir",
]


@dataclass(frozen=True)
class RelatedRow:
    cust_ref: str
    title: str
    class_label: str
    discipline: str
    revision: str | None
    chosen_file: str
    chosen_format: str
    related_files: list[str] = field(default_factory=list)
    source_group_dir: str = ""


def write_related_xlsx(dest_dir: Path, rows: list[RelatedRow]) -> Path:
    """Write ``<dest_dir>/related-documents.xlsx`` and return the path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / OUTPUT_FILENAME
    records = [
        {
            "cust_ref": r.cust_ref,
            "title": r.title,
            "class": r.class_label,
            "discipline": r.discipline,
            "revision": r.revision or "",
            "chosen_file": r.chosen_file,
            "chosen_format": r.chosen_format,
            "related_files": "; ".join(r.related_files),
            "related_count": len(r.related_files),
            "source_group_dir": r.source_group_dir,
        }
        for r in rows
    ]
    df = pd.DataFrame(records, columns=COLUMNS)
    df.to_excel(out, engine="openpyxl", index=False)
    return out
