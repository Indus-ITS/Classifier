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
    # An ISOMETRIC is a drawing even without the DRAWING token. (Plural
    # ISOMETRICS routes via the ISO type override; this covers the singular.)
    ("ISOMETRIC",),
)
# NOTE: PLAN is deliberately excluded above (protects HSE/EXECUTION PLAN), so
# plot-plan *drawings* rely solely on the DPP->Drawings type mapping. "SCHEME"
# is likewise not a bare marker (would catch COLOR/CLASSIFICATION/NUMBERING
# SCHEME prose); only "VENDOR SCHEME" routes to a drawing, via the DWG type
# override in type_overrides.py.

# An INDEX title is a tabular sheet (INSTRUMENT INDEX, ISO INDEX, ...).
INDEX_MARKERS: tuple[tuple[str, ...], ...] = (
    ("INDEX",),
)

# Order-aware index/list-vs-drawing collision. Class markers match position-
# blind, so they cannot tell "INDEX DRAWING" (a drawing) from "DRAWING INDEX"
# (a sheet listing drawings). When a title carries BOTH a tabular word and a
# drawing word, the *trailing* head noun decides the class -- except an
# "X OF DRAWINGS" construction keeps the tabular word X as the head.
SHEET_HEAD_WORDS: frozenset[str] = frozenset({"INDEX", "LIST", "SCHEDULE"})
DOCUMENT_HEAD_WORDS: frozenset[str] = frozenset({"REGISTER"})
DRAWING_HEAD_WORDS: frozenset[str] = frozenset(
    {"DRAWING", "DIAGRAM", "SKETCH", "LAYOUT", "ISOMETRIC"})
