"""Extract cust_ref, letter rev, and numeric rev from filenames."""
from __future__ import annotations

import re

from classifier.config.patterns import REF_PATTERN

_REF_RE = re.compile(REF_PATTERN)


def _esc_ref(ref: str) -> str:
    return re.escape(ref)


def extract_ref(filename: str) -> "str | None":
    """Return the first \\d{2}-\\d{2}-\\d{2}-\\d{4} ref, or None."""
    m = _REF_RE.search(filename)
    return m.group(1) if m else None


def extract_letter_rev(filename: str, ref: "str | None") -> str:
    """Return parsed letter rev (single uppercase A-Z) or empty string."""
    if ref:
        m = re.search(rf"{_esc_ref(ref)}[ _\-]([A-Z])(?:[ _.\-]|$)", filename)
        if m:
            return m.group(1).upper()
    m = re.search(r"(?i)(?<![A-Za-z])IF[ARDCU][ _\-]?([A-Z])(?![A-Za-z])", filename)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?i)(?<![A-Za-z])REV[._ \-]?([A-Z])(?![A-Za-z])", filename)
    if m:
        return m.group(1).upper()
    return ""


def extract_numeric_rev(filename: str, ref: "str | None") -> str:
    """Return parsed numeric rev (1-99 as decimal string) or empty string."""
    if ref:
        m = re.search(rf"{_esc_ref(ref)}[ _\-](\d{{1,2}})(?:[ _.\-]|$)", filename)
        if m:
            return m.group(1)
    m = re.search(r"(?i)(?<![A-Za-z])IF[ARDCU][ _\-]?(\d{1,2})(?!\d)", filename)
    if m:
        return m.group(1)
    m = re.search(r"(?i)(?<![A-Za-z])REV[._ \-]?(\d{1,2})(?!\d)", filename)
    if m:
        return m.group(1)
    return ""


def extract_revs(filename: str, ref: "str | None") -> tuple:
    """Return (letter_rev, numeric_rev). Either may be empty."""
    return extract_letter_rev(filename, ref), extract_numeric_rev(filename, ref)


def inherit_rev_from_siblings(target: dict, siblings: list) -> tuple:
    """Tier-5 sibling rev inheritance.

    If target already has either rev, return target's existing pair unchanged.
    Otherwise look at siblings sharing submission_folder + subfolder + cust_ref.
    Numeric supersedes letter (per spec section 7.2). Within numeric, highest int.
    Within letter, lexicographic max.
    """
    if target.get("letter_rev") or target.get("numeric_rev"):
        return target.get("letter_rev", ""), target.get("numeric_rev", "")
    if not target.get("cust_ref"):
        return "", ""
    matches = [
        s for s in siblings
        if s is not target
        and s.get("cust_ref") == target.get("cust_ref")
        and s.get("submission_folder") == target.get("submission_folder")
        and s.get("subfolder", "") == target.get("subfolder", "")
        and (s.get("letter_rev") or s.get("numeric_rev"))
    ]
    if not matches:
        return "", ""
    numeric = [int(s["numeric_rev"]) for s in matches if s.get("numeric_rev")]
    if numeric:
        return "", str(max(numeric))
    letters = [s["letter_rev"] for s in matches if s.get("letter_rev")]
    if letters:
        return max(letters), ""
    return "", ""
