"""Load the valid discipline id set from the disciplines table CSV."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from classifier.io.normalize import is_empty


def load_valid_discipline_ids(path: Path = Path("input/disciplines.csv")
                              ) -> frozenset[int]:
    if not path.exists():
        raise SystemExit(f"disciplines table not found at {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
    if "id" not in df.columns:
        raise SystemExit(f"{path}: missing required 'id' column")
    ids: set[int] = set()
    for raw in df["id"]:
        if is_empty(raw):
            continue
        try:
            ids.add(int(float(str(raw).strip())))
        except (TypeError, ValueError):
            continue
    return frozenset(ids)
