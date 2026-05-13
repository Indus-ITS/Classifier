"""String normalization helpers shared by every pipeline stage.

Centralized so doc_no/customer_ref lookup keys and header tokens are
folded the same way wherever they're touched. No ad-hoc ``.strip().upper()``
chains anywhere else in the codebase.
"""
from __future__ import annotations

import re
import unicodedata

_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-",
                          "–": "-", "—": "-", "―": "-",
                          "−": "-"})
_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s:.\-_#]+$")
_SLUG_REPLACE_RE = re.compile(r"[^a-z0-9_-]+")
_SLUG_COLLAPSE_RE = re.compile(r"_+")


def is_empty(value: object) -> bool:
    """True for None, NaN, empty/whitespace strings, and literal 'NULL'."""
    if value is None:
        return True
    s = str(value).strip()
    if s == "" or s.upper() == "NULL" or s.lower() == "nan":
        return True
    return False


def normalize_lookup_key(value: object) -> str:
    """Canonical key form for document_no / customer_ref lookups.

    Empty inputs map to ``""``. Otherwise: NFKC, dash-folded, internal
    whitespace collapsed to one space, stripped, uppercased.
    """
    if is_empty(value):
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = s.translate(_DASHES)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s.upper()


def normalize_header_token(value: object) -> str:
    """Canonical form for an xlsx header cell.

    ``"Document No."``, ``"Document No"``, ``"Document No :"`` all fold to
    ``"document no"``. Used by Sub-project A's header auto-detection.
    """
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = s.translate(_DASHES)
    s = s.lower().strip()
    s = _TRAILING_PUNCT_RE.sub("", s)
    s = _WHITESPACE_RE.sub(" ", s)
    return s


def slugify_sheet(name: str) -> str:
    """Filesystem-safe sheet-name slug for output CSV filenames.

    Lowercase, NFKC; non ``[a-z0-9_-]`` runs become a single ``_``; leading
    and trailing ``_`` stripped. Empty result falls back to ``"sheet"``.
    """
    s = unicodedata.normalize("NFKC", name).lower()
    s = _SLUG_REPLACE_RE.sub("_", s)
    s = _SLUG_COLLAPSE_RE.sub("_", s).strip("_-")
    return s or "sheet"
