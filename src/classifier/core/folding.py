"""Single source of truth for bucket -> user-facing doc_type folding."""
from __future__ import annotations

from classifier.config.buckets import BUCKET_TO_CLASS


def doc_type_for_bucket(bucket: str) -> str:
    """Return the lowercase doc_type ("drawing"/"sheet"/"document") for a bucket."""
    folded = BUCKET_TO_CLASS[bucket]
    return {"Drawings": "drawing", "Sheets": "sheet"}.get(folded, "document")
