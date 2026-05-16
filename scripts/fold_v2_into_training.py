"""Filter classified_updated_v2.csv to exclude known-WRONG rows and
write the result as a training CSV under input/classified_csv/.

Drops only the `type` value for rows matching the wrong-pattern table
(see plan); leaves everything else intact. Run from project root::

    .venv/Scripts/python scripts/fold_v2_into_training.py
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from classifier.io.schema import TARGET_COLUMNS, validate_schema

SRC = Path("output/classified_updated_v2.csv")
DST = Path("input/classified_csv/document_user_audited.csv")

# (title-substring-uppercase-match, type-to-drop) tuples for the 19 known WRONG rows.
WRONG_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("PIPE RACK PLAN",), "PLN"),
    (("CABLE ROUTING PLAN",), "PLN"),
    (("STEEL STRUCTURE", "PLAN"), "PLN"),
    (("FOUNDATION", "PLAN"), "PLN"),
    (("SUPPORT", "PLAN"), "PLN"),
    (("ARCHITECTURE DIAGRAM",), "DWG"),
    (("INTERCONNECTION", "DRAWING"), "DWG"),
    (("HEAT AND MATERIAL",), "DWG"),
    (("MATERIALS BALANCE",), "DWG"),
    (("PIPING & INSTRUMENTATION DIAGRAM",), "DWG"),
    (("CAUSE & EFFE",), "DWG"),
    (("GENERAL ARRANGMENT",), "DWG"),
    (("GENERAL ARRANGEMENT",), "DWG"),
    (("HAZARDOUS AREA CLASSIFICATION",), "DAL"),
    (("PLANNING & SCHEDULING PROCEDURE",), "PLN"),
    (("PROGRESS REPORTING PROCEDURE",), "REP"),
    (("TIE-IN SKETCH",), "SCH"),
    (("MR FOR",), "SOW"),
]


def _row_is_wrong(title: str, t: str) -> bool:
    title_u = title.upper()
    for needles, bad_type in WRONG_PATTERNS:
        if t == bad_type and all(n in title_u for n in needles):
            return True
    return False


def main() -> None:
    df = pd.read_csv(SRC, dtype=str, keep_default_na=False, na_values=[])
    validate_schema(df.columns)
    n_blanked = 0
    for i in range(len(df)):
        if _row_is_wrong(df.at[i, "title"], df.at[i, "type"]):
            df.at[i, "type"] = ""
            n_blanked += 1
    DST.parent.mkdir(parents=True, exist_ok=True)
    with DST.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(TARGET_COLUMNS)
        for _, row in df.iterrows():
            w.writerow([row[c] for c in TARGET_COLUMNS])
    n_typed = (df["type"].str.strip() != "").sum()
    print(f"Wrote {DST}")
    print(f"  total rows:      {len(df)}")
    print(f"  rows with type:  {n_typed}")
    print(f"  WRONG blanked:   {n_blanked}")


if __name__ == "__main__":
    main()
