"""update-snapshot: fill doc_type/type/discipline_id on a documents-table
snapshot export using the frozen classifier.

Rules (see spec 2026-06-05-sync-db-state-and-snapshot-update-design.md):
  * doc_type  — recomputed for ALL rows.
  * type      — feed rows kept; non-feed rows recomputed (kept on a miss).
  * discipline_id — filled where missing OR currently invalid (valid kept);
                    every written id validated against input/disciplines.csv.
Outputs documents_updated.csv (+ documents_changes.csv) under --out-dir.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from classifier.core.record import Record
from classifier.core.classify import classify_record
from classifier.io.disciplines import load_valid_discipline_ids
from classifier.io.normalize import is_empty

REQUIRED_COLS = ("document_id", "title", "doc_type", "type",
                 "discipline_id", "doc_source")
CHANGE_COLS = ("document_id",
               "doc_type_old", "doc_type_new",
               "type_old", "type_new",
               "discipline_id_old", "discipline_id_new")


def _disc_int(v) -> int | None:
    if is_empty(v):
        return None
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def process(df: pd.DataFrame, valid_ids: frozenset[int]):
    """Return (updated_df, changes_list, summary_dict). Pure: no I/O."""
    out = df.copy()
    changes: list[dict] = []
    summary = {"rows": 0, "doc_type_changed": 0, "type_changed_nonfeed": 0,
               "disc_filled_missing": 0, "disc_reclassified_invalid": 0,
               "disc_left_null": 0}
    for i, row in df.iterrows():
        summary["rows"] += 1
        title = "" if is_empty(row["title"]) else str(row["title"])
        cur_doc = "" if is_empty(row["doc_type"]) else str(row["doc_type"]).strip()
        cur_type = "" if is_empty(row["type"]) else str(row["type"]).strip()
        cur_disc_i = _disc_int(row["discipline_id"])
        disc_valid = cur_disc_i is not None and cur_disc_i in valid_ids
        is_feed = (not is_empty(row["doc_source"])
                   and str(row["doc_source"]).strip().lower() == "feed")

        rec = Record(
            title=title,
            doc_type="",                                   # overwrite all
            type=(cur_type if is_feed else ""),            # feed kept; else recompute
            discipline_id=(str(cur_disc_i) if disc_valid else ""),
        )
        res = classify_record(rec)

        new_doc = res.doc_type.value
        new_type = cur_type if is_feed else (res.type.value or cur_type)
        new_disc = res.discipline_id.value  # "" or a valid id string
        if new_disc and int(new_disc) not in valid_ids:
            raise SystemExit(f"BUG: produced invalid discipline {new_disc!r}")

        out.at[i, "doc_type"] = new_doc
        out.at[i, "type"] = new_type
        out.at[i, "discipline_id"] = new_disc

        old_disc_str = "" if cur_disc_i is None else str(cur_disc_i)
        ch: dict[str, tuple[str, str]] = {}
        if new_doc != cur_doc:
            summary["doc_type_changed"] += 1
            ch["doc_type"] = (cur_doc, new_doc)
        if not is_feed and new_type != cur_type:
            summary["type_changed_nonfeed"] += 1
            ch["type"] = (cur_type, new_type)
        if new_disc != old_disc_str:
            ch["discipline_id"] = (old_disc_str, new_disc)
            if cur_disc_i is None and new_disc:
                summary["disc_filled_missing"] += 1
            elif cur_disc_i is not None and not disc_valid and new_disc:
                summary["disc_reclassified_invalid"] += 1
        if (cur_disc_i is None or not disc_valid) and not new_disc:
            summary["disc_left_null"] += 1

        if ch:
            entry = {"document_id": row["document_id"]}
            for f in ("doc_type", "type", "discipline_id"):
                o, n = ch.get(f, ("", ""))
                entry[f"{f}_old"], entry[f"{f}_new"] = o, n
            changes.append(entry)
    return out, changes, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="update-snapshot")
    ap.add_argument("--input", type=Path, required=True,
                    help="documents snapshot CSV (DB export)")
    ap.add_argument("--disciplines", type=Path, default=Path("input/disciplines.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("output"))
    args = ap.parse_args(argv)

    if not args.input.exists():
        raise SystemExit(f"input not found: {args.input}")
    df = pd.read_csv(args.input, dtype=str, keep_default_na=False, na_values=[])
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise SystemExit(f"snapshot missing required columns: {missing}")

    valid_ids = load_valid_discipline_ids(args.disciplines)
    out, changes, summary = process(df, valid_ids)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    updated_path = args.out_dir / "documents_updated.csv"
    changes_path = args.out_dir / "documents_changes.csv"
    out.to_csv(updated_path, index=False, lineterminator="\n")
    with changes_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CHANGE_COLS, lineterminator="\n")
        w.writeheader()
        for c in changes:
            w.writerow(c)

    print(f"\nWrote {updated_path}  ({summary['rows']} rows)")
    print(f"Wrote {changes_path}  ({len(changes)} changed rows)")
    for k, v in summary.items():
        print(f"  {k:28s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
