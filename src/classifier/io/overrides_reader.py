"""Load ``overrides/ref_to_bucket.csv``: project-specific bucket pinning."""
from __future__ import annotations

import csv
from pathlib import Path


def load_overrides(path) -> dict:
    """Load overrides/ref_to_bucket.csv. Missing file -> empty dict."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict = {}
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = (row.get("cust_ref") or "").strip()
            bucket = (row.get("bucket") or "").strip()
            if ref and bucket:
                out[ref] = bucket
    return out
