"""Title markers for class-level precedence guards.

Matched as contiguous token subsequences against the canonicalized title
(same canonicalizer the scorer uses). Data only — the ordering/precedence
logic lives in classify.normalize_doc_type.
"""
from __future__ import annotations

# A title naming a DRAWING / SKETCH / LAYOUT is a drawing, even when it
# also carries a prose or LIST/INDEX/REGISTER word (e.g. "HAZARDOUS AREA
# CLASSIFICATION LAYOUT" is a layout drawing, not the prose schedule).
# Canonicalization depluralizes DRAWINGS->DRAWING etc., so singular forms
# suffice. NOTE: PLAN is deliberately NOT a marker — "HSE PLAN" /
# "EXECUTION PLAN" are management documents, while plan-view *drawings*
# already classify via the type scorer (DAL/DPP/...).
DRAWING_TITLE_MARKERS: tuple[tuple[str, ...], ...] = (
    ("DRAWING",),
    ("SKETCH",),
    ("LAYOUT",),
    # A titled DIAGRAM is a drawing (P&ID, SLD, loop / block / wiring /
    # protection & metering / cause-&-effect diagrams all fold to Drawings).
    ("DIAGRAM",),
)

# An INDEX title is a tabular sheet (INSTRUMENT INDEX, ISO INDEX, ...).
INDEX_MARKERS: tuple[tuple[str, ...], ...] = (
    ("INDEX",),
)
