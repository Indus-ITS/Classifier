"""Backward-compatible shim. The per-row helpers moved to
``classifier.core.classify``; this module re-exports them so existing imports
(and tests) keep working.
"""
from __future__ import annotations

from classifier.core.classify import (  # noqa: F401
    DRAWING_ALIASES, DOCUMENT_ALIASES, SHEET_ALIASES,
    normalize_doc_type, fill_type, fill_discipline,
)
