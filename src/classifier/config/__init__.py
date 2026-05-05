"""Backwards-compatible re-exports.

SUNSET: remove these re-exports after the next two changes that touch the
classifier package, or by 2026-08-01 - whichever comes first. New code MUST
import from the specific submodule (e.g. ``from classifier.config.keywords
import KEYWORD_RULES``).
"""
from classifier.config.paths import (
    SCHEDULE_PATH,
    DOSSIER_PATH,
    TREE_PATH,
    OUTPUT_DIR,
    GATE_THRESHOLD,
)
from classifier.config.buckets import (
    BUCKETS,
    BUCKET_TO_CLASS,
    TYPE_TO_BUCKET,
    BUCKET_PRIMARY_CODE,
)
from classifier.config.keywords import KEYWORD_RULES, DISCIPLINE_KEYWORD_RULES
from classifier.config.patterns import REF_PATTERN, CRS_PATTERN, COVER_PATTERN
from classifier.config.schema import CSV_COLUMNS

__all__ = [
    "SCHEDULE_PATH", "DOSSIER_PATH", "TREE_PATH",
    "OUTPUT_DIR", "GATE_THRESHOLD",
    "BUCKETS", "BUCKET_TO_CLASS", "TYPE_TO_BUCKET", "BUCKET_PRIMARY_CODE",
    "KEYWORD_RULES", "DISCIPLINE_KEYWORD_RULES",
    "REF_PATTERN", "CRS_PATTERN", "COVER_PATTERN",
    "CSV_COLUMNS",
]
