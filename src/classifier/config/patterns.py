"""Named regex patterns for ref / CRS / cover-sheet detection.

Empirically validated on the real TO CLIENT corpus (98% CRS match rate).
"""
from __future__ import annotations

REF_PATTERN = r"(\d{2}-\d{2}-\d{2}-\d{4})"

CRS_PATTERN = (
    r"(?ix)("
    r"^crs[\s_\-]"
    r"|^crs(?=\d{2}-)"
    r"|^crsheet[\s_\-]"
    r"|^comment[\s_]response"
    r"|^copy[\s_]of[\s_]comment"
    r"|[\s_\-]crs(?=[\s_\-]|\.)"
    r")"
)

COVER_PATTERN = r"(?i)^(cta|c-a-ed-sa)"
