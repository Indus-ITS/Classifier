"""Revision logic: bundle id, is_latest per axis, drift classification."""
from __future__ import annotations


def assign_bundle_id(cust_ref: str, letter_rev: str, numeric_rev: str,
                     submission_folder: str) -> str:
    """Per spec section 8."""
    if cust_ref:
        if letter_rev and numeric_rev:
            return f"{cust_ref}__N{numeric_rev}L{letter_rev}"
        if numeric_rev:
            return f"{cust_ref}__N{numeric_rev}"
        if letter_rev:
            return f"{cust_ref}__L{letter_rev}"
        return f"{cust_ref}__R0"
    return f"unmatched__{submission_folder}"


def compute_is_latest_for_group(rows: list) -> list:
    """Set is_latest_letter, is_latest_numeric, is_latest on each row in place.

    Numeric supersedes letter (per spec section 7.2): when any numeric_rev exists in the
    group, suppress is_latest_letter on every row (otherwise a stale letter-rev file
    would be reported as latest_letter even though it's been superseded by a numeric
    issue). When NO row has any rev (all-empty group), mark the lexicographically
    first source_path as is_latest=True so downstream "latest of each ref" filters
    don't silently drop the doc.
    """
    letters = [(i, r.get("letter_rev", "")) for i, r in enumerate(rows) if r.get("letter_rev")]
    letter_winner = max(letters, key=lambda x: x[1])[0] if letters else None
    numerics = [(i, int(r["numeric_rev"])) for i, r in enumerate(rows) if r.get("numeric_rev")]
    numeric_winner = max(numerics, key=lambda x: x[1])[0] if numerics else None
    has_any_numeric = numeric_winner is not None
    has_any_letter = letter_winner is not None

    if has_any_numeric:
        effective_letter_winner = None
    else:
        effective_letter_winner = letter_winner

    if not has_any_numeric and not has_any_letter:
        sorted_idx = sorted(range(len(rows)),
                            key=lambda i: rows[i].get("source_path", ""))
        all_empty_winner = sorted_idx[0] if sorted_idx else None
    else:
        all_empty_winner = None

    for i, r in enumerate(rows):
        r["is_latest_letter"] = (i == effective_letter_winner)
        r["is_latest_numeric"] = (i == numeric_winner)
        if has_any_numeric:
            r["is_latest"] = r["is_latest_numeric"]
        elif has_any_letter:
            r["is_latest"] = r["is_latest_letter"]
        else:
            r["is_latest"] = (i == all_empty_winner)
    return rows


def classify_revision_drift(*, file_letter: str, file_numeric: str,
                            schedule_rev: str) -> str:
    """Per spec section 7.3 (v4 - pre_issue split out from cross_axis).

    States:
      aligned         - the relevant axis matches schedule
      disk_newer      - disk has higher rev on the schedule's axis
      schedule_newer  - schedule has higher rev on its axis (file is stale)
      pre_issue       - schedule says numeric (post-issue) but disk has only a
                        letter rev. This is the NORMAL state during the IFA review
                        cycle: the file is the active letter revision being
                        commented on, and the schedule has already recorded the
                        promoted numeric issue. Not actionable.
      cross_axis      - genuine inversion: schedule says letter, disk has only
                        numeric. Rare; means file was promoted but schedule wasn't
                        updated.
      unknown         - no schedule rev or both axes empty.
    """
    sched = schedule_rev.strip()
    if not sched:
        return "unknown"
    if not file_letter and not file_numeric:
        return "unknown"
    if sched.isdigit():
        if file_numeric:
            f, s = int(file_numeric), int(sched)
            if f == s:
                return "aligned"
            return "disk_newer" if f > s else "schedule_newer"
        return "pre_issue"
    if len(sched) == 1 and sched.isalpha():
        sched_u = sched.upper()
        if file_letter:
            if file_letter == sched_u:
                return "aligned"
            return "disk_newer" if file_letter > sched_u else "schedule_newer"
        return "cross_axis"
    return "unknown"
