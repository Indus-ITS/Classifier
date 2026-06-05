"""Load the classified CSV into a customer_ref -> classification map for the
sort-files router. Read-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from classifier.io.normalize import is_empty, normalize_lookup_key
from classifier.io.schema import validate_schema


@dataclass(frozen=True)
class Classification:
    doc_type: str
    title: str


def load_classified_index(csv_path: Path) -> dict[str, Classification]:
    """Map normalize_lookup_key(customer_ref) -> Classification. First row
    wins on a duplicate normalized key; rows with empty customer_ref are
    skipped; doc_type is lowercased."""
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[])
    validate_schema(df.columns)
    index: dict[str, Classification] = {}
    for _, row in df.iterrows():
        key = normalize_lookup_key(row["customer_ref"])
        if not key:
            continue
        if key in index:
            continue  # first wins
        doc_type = "" if is_empty(row["doc_type"]) else str(row["doc_type"]).strip().lower()
        title = "" if is_empty(row["title"]) else str(row["title"]).strip()
        index[key] = Classification(doc_type=doc_type, title=title)
    return index
