"""Form classification: Archive / CoverSheet / CRS / Drawing / Sheet / Document."""
from __future__ import annotations

import re

from classifier.config.patterns import COVER_PATTERN, CRS_PATTERN

_CRS_RE = re.compile(CRS_PATTERN)
_COVER_RE = re.compile(COVER_PATTERN)


def is_crs_filename(filename: str) -> bool:
    """True if filename matches the empirically-tuned CRS pattern (spec section 6.1a)."""
    return _CRS_RE.search(filename) is not None


def is_cover_filename(filename: str) -> bool:
    """True if filename starts with a transmittal cover prefix.
    Caller is responsible for the 'lacks ref' check."""
    return _COVER_RE.search(filename) is not None


def resolve_form_pre(filename: str, has_ref: bool):
    """Pass-1 form: Archive or CoverSheet, else None."""
    lower = filename.lower()
    if lower.endswith(".rar") or lower.endswith(".zip"):
        return "Archive"
    if (not has_ref) and is_cover_filename(filename):
        return "CoverSheet"
    return None


_DRAWING_EXTS = {".dwg", ".dgn"}
_SHEET_EXTS = {".xlsx", ".xls", ".xlsm"}
_DOC_EXTS = {".docx", ".doc"}


def resolve_form_post(filename: str, bucket: str) -> str:
    """Pass-2 form: extension-driven, with PDF disambiguated by bucket."""
    lower = filename.lower()
    ext = "." + lower.rsplit(".", 1)[1] if "." in lower else ""
    if ext in _DRAWING_EXTS:
        return "Drawing"
    if ext in _SHEET_EXTS:
        return "Sheet"
    if ext in _DOC_EXTS:
        return "Document"
    if ext == ".pdf":
        if bucket in {"Drawings", "Isometrics"}:
            return "Drawing"
        if bucket in {"Datasheets", "Lists_MTOs_BOMs"}:
            return "Sheet"
        return "Document"
    return "Document"
