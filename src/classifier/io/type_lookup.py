"""Build deterministic ``document_no``/``customer_ref`` -> ``type`` maps
from the canonical CSVs produced by ``convert-classified``.

Keys with conflicting types across CSVs are dropped (never guessed).
Used by ``classifier.cli.classify`` to fill the ``type`` column when
the input row's ``type`` is empty.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from classifier.config.type_enum import ALL_OBSERVED_TYPES
from classifier.io.normalize import is_empty, normalize_lookup_key


@dataclass
class TypeLookup:
    by_doc_no: dict[str, str] = field(default_factory=dict)
    by_cust_ref: dict[str, str] = field(default_factory=dict)
    conflicts_doc_no: dict[str, set[str]] = field(default_factory=dict)
    conflicts_cust_ref: dict[str, set[str]] = field(default_factory=dict)
    n_csvs: int = 0


def build_lookup(csv_dir: Path) -> TypeLookup:
    """Walk ``csv_dir`` deterministically; return a TypeLookup."""
    paths = sorted(csv_dir.rglob("*.csv"), key=lambda p: str(p).lower())
    raw_doc: defaultdict[str, set[str]] = defaultdict(set)
    raw_cust: defaultdict[str, set[str]] = defaultdict(set)

    for p in paths:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[])
        if not {"document_no", "customer_ref", "type"}.issubset(df.columns):
            continue
        for _, row in df.iterrows():
            t = "" if is_empty(row["type"]) else str(row["type"]).strip().upper()
            if t == "" or t not in ALL_OBSERVED_TYPES:
                continue
            k_doc = normalize_lookup_key(row["document_no"])
            if k_doc:
                raw_doc[k_doc].add(t)
            k_cust = normalize_lookup_key(row["customer_ref"])
            if k_cust:
                raw_cust[k_cust].add(t)

    lookup = TypeLookup(n_csvs=len(paths))
    for k, ts in raw_doc.items():
        if len(ts) == 1:
            lookup.by_doc_no[k] = next(iter(ts))
        else:
            lookup.conflicts_doc_no[k] = ts
    for k, ts in raw_cust.items():
        if len(ts) == 1:
            lookup.by_cust_ref[k] = next(iter(ts))
        else:
            lookup.conflicts_cust_ref[k] = ts
    return lookup
