"""Extract the project cust_ref from a filename stem and parse a logical
group key + revision. Pure string logic; no I/O.
"""
from __future__ import annotations

import re

CUST_REF = re.compile(r"\d{2}-\d{2}-\d{2}-\d{4}")
# Revision tail: a single letter OR single digit, optionally "Rev"-prefixed,
# optionally followed by more descriptive text. Single-char value so a
# 4-digit cust_ref tail is never misread as a revision.
_REV_TAIL = re.compile(
    r"^[\s_-]+(?:REV\.?)?([A-Z]|\d)(?:[\s_.\-].*)?$", re.IGNORECASE
)
_REV_WHOLE = re.compile(
    r"[\s_-]+(?:REV[\s_.]*)?([A-Z]|\d)(?:[\s_.\-].*)?$", re.IGNORECASE
)


def extract_cust_ref(stem: str) -> str | None:
    m = CUST_REF.search(stem)
    return m.group(0) if m else None


def parse_group_and_revision(stem: str) -> tuple[str, str | None]:
    """Return (group_key, revision).

    With a cust_ref: anchor on it, strip a revision only from the tail that
    follows it; group_key = the rest (lowercased, stripped). Without a
    cust_ref: strip a trailing revision from the whole stem.
    """
    m = CUST_REF.search(stem)
    if m:
        prefix, suffix = stem[: m.end()], stem[m.end():]
        rev = _REV_TAIL.match(suffix)
        if rev:
            return prefix.strip().lower(), rev.group(1).upper()
        return (prefix + suffix).strip().lower(), None
    rev = _REV_WHOLE.search(stem)
    if rev:
        return stem[: rev.start()].strip().lower(), rev.group(1).upper()
    return stem.strip().lower(), None
