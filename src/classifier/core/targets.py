"""Build proposed target paths and detect target collisions."""
from __future__ import annotations

import re
from collections import defaultdict


_TITLE_SANITISE_RE = re.compile(r"[^A-Za-z0-9]+")


def _sanitise_title(title: str, max_len: int = 60) -> str:
    s = _TITLE_SANITISE_RE.sub("_", title.upper()).strip("_")
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


def _rev_token(letter_rev: str, numeric_rev: str) -> str:
    if letter_rev and numeric_rev:
        return f"N{numeric_rev}L{letter_rev}"
    if numeric_rev:
        return f"N{numeric_rev}"
    if letter_rev:
        return f"L{letter_rev}"
    return "R0"


def build_target_paths(*, cust_ref: str, letter_rev: str, numeric_rev: str,
                       type_code: str, form: str, bucket: str, discipline: str,
                       title: str, extension: str,
                       submission_folder: str, source_filename: str) -> dict:
    """Per spec section 9."""
    folder = f"{form}/{bucket}/{discipline}/"
    if not cust_ref:
        return {
            "proposed_target_folder": folder,
            "proposed_target_filename": f"{submission_folder}__{source_filename}",
        }
    rev = _rev_token(letter_rev, numeric_rev)
    short = _sanitise_title(title)
    base = f"{cust_ref}_{rev}_{type_code}_{short}" if short else f"{cust_ref}_{rev}_{type_code}"
    return {
        "proposed_target_folder": folder,
        "proposed_target_filename": base + extension,
    }


def detect_target_collisions(rows: list) -> None:
    """Sets `target_collision` on every row; appends colliding peers to `notes`."""
    buckets: dict = defaultdict(list)
    for r in rows:
        key = (r.get("proposed_target_folder", ""), r.get("proposed_target_filename", ""))
        buckets[key].append(r)
    for key, group in buckets.items():
        if len(group) > 1:
            ids = [g.get("bundle_id", "") for g in group]
            for r in group:
                r["target_collision"] = True
                peers = [b for b in ids if b != r.get("bundle_id")]
                note = "collision_with=" + ",".join(peers)
                r["notes"] = (r.get("notes", "") + (" | " if r.get("notes") else "") + note).strip()
        else:
            for r in group:
                r["target_collision"] = False
