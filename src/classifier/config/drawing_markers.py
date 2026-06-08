"""Title markers for class-level precedence guards.

Matched as contiguous token subsequences against the canonicalized title
(same canonicalizer the scorer uses). Data only — the ordering/precedence
logic lives in classify.normalize_doc_type.
"""
from __future__ import annotations

# A title naming a DRAWING (or SKETCH) is a drawing, even when it also
# carries a LIST/INDEX/REGISTER word. Canonicalization depluralizes
# DRAWINGS->DRAWING and SKETCHES->SKETCH, so the singular forms suffice.
DRAWING_TITLE_MARKERS: tuple[tuple[str, ...], ...] = (
    ("DRAWING",),
    ("SKETCH",),
)

# An INDEX title is a tabular sheet (INSTRUMENT INDEX, ISO INDEX, ...).
INDEX_MARKERS: tuple[tuple[str, ...], ...] = (
    ("INDEX",),
)
