"""Hand-curated overrides for the type classifier.

Two tables, hand-edited not generated. Consulted by
``classifier.core.type_scoring.pick_type_with_overrides`` before
(``HARD_OVERRIDES``) and after (``NEGATIVE_KEYWORDS``) the learned
keyword scorer.

Phrases are tuples of canonicalized tokens — i.e., what
``canonicalize_title`` returns. Match is "all phrase tokens appear in
the title token list as a contiguous subsequence". The phrase
``("PIPING", "&", "INSTRUMENT")`` matches the canonicalized form of
"PIPING & INSTRUMENT DIAGRAM" because the tokenizer preserves ``&``.

These are deterministic semantic truths, separate from the
probabilistic learned rules in ``type_keywords.py``. The two systems
must not be merged: a learner that "discovers" garbage should never
overwrite engineering convention.
"""
from __future__ import annotations

HARD_OVERRIDES: dict[str, tuple[tuple[str, ...], ...]] = {
    "PID": (
        ("P&ID",),
        ("PIPING", "&", "INSTRUMENT"),
        ("PIPING", "AND", "INSTRUMENT"),
        ("PIPING", "&", "INSTRUMENTATION"),
        ("PIPING", "AND", "INSTRUMENTATION"),
        ("PIPING", "&", "INSTRUMENTATION", "DIAGRAM"),
        ("PIPING", "AND", "INSTRUMENT", "DIAGRAM"),
    ),
    "PFD": (
        ("PROCESS", "FLOW", "DIAGRAM"),
        ("UTILITY", "FLOW", "DIAGRAM"),
        ("HEAT", "AND", "MATERIAL", "BALANCE"),
        ("HEAT", "AND", "MATERIALS", "BALANCE"),
    ),
    "DCE": (
        ("CAUSE", "&", "EFFECT"),
        ("CAUSE", "&", "EFFET"),
        ("CAUSE", "AND", "EFFECT"),
    ),
    "PSF": (
        ("SAFEGUARDING", "DIAGRAM"),
        ("SAFEGUARDING", "MEMORANDUM"),
    ),
    "MSD": (
        ("MATERIAL", "SELECTION", "DIAGRAM"),
    ),
    "DGA": (
        ("GENERAL", "ARRANGEMENT"),
        ("GENERAL", "ARRANGMENT"),
        ("GENERAL", "ARRANGEMENT", "DRAWING"),
        ("PIPING", "GENERAL", "ARRANGEMENT"),
    ),
    "PRO": (
        ("PROCEDURE",),
        ("METHOD", "STATEMENT"),
        ("WORK", "INSTRUCTION"),
    ),
    "TBE": (
        ("TBE",),
        ("TECHNICAL", "BID", "EVALUATION"),
        ("TECHNICAL", "BID", "EVALATION"),
        ("TECHNICAL", "BID", "EVALATUION"),
    ),
    "ISO": (
        ("ISOMETRIC",),
        ("ISOMETRICS",),
    ),
    "MTO": (
        ("MTO",),
    ),
    "DAS": (
        ("DATASHEET",),
        ("DATA", "SHEET"),
        ("MECHANICAL", "DATASHEET"),
        ("INSTRUMENT", "DATASHEET"),
        ("ELECTRICAL", "DATASHEET"),
    ),
    "PHL": (
        ("PHILOSOPHY",),
    ),
    "REG": (
        ("REGISTER",),
    ),
    "SCH": (
        ("SCHEDULE",),
    ),
    # ARCHITECTURE DIAGRAM -> DBD is a temporary operational mapping
    # (audit included ICSS SYSTEM ARCHITECTURE DIAGRAM). Revisit if a
    # network-architecture variant lands.
    "DBD": (
        ("BLOCK", "DIAGRAM"),
        ("SCHEMATIC", "BLOCK", "DIAGRAM"),
        ("ARCHITECTURE", "DIAGRAM"),
    ),
    # Detail drawings — tank/structural fabrication-detail family.
    # Activated per user direction after the override pass found 28
    # unclassified rows all matching "X DETAILS FOR Y" / "X DETAIL FOR Y"
    # structural pattern. Conservative coverage: specific 2/3-grams
    # only, no bare ("DETAILS",) 1-gram (would catch documents).
    "DDT": (
        ("DETAILS", "FOR"),
        ("DETAIL", "FOR"),
        ("FOUNDATION", "DETAILS"),
        ("FOUNDATION", "DETAIL"),
        ("STRUCTURAL", "DETAILS"),
        ("STRUCTURAL", "DETAIL"),
        ("MODIFICATION", "DETAILS"),
        ("NOZZLES", "DETAILS"),
        ("BRACKET", "DETAILS"),
        ("CLEATS", "DETAILS"),
        ("HANDRAIL", "DETAILS"),
    ),
    # Generic construction drawings - "CONSTRUCTION DRAWING (TYP)..." titles.
    "DWG": (
        ("CONSTRUCTION", "DRAWING"),
    ),
    "DPP": (
        ("PLOT", "PLAN"),
    ),
    "DAL": (
        ("ELECTRICAL", "EQUIPMENT", "LAYOUT"),
        ("ELECTRICAL", "CABLE", "ROUTING"),
    ),
}

# A title containing any of these phrases blocks the listed type even
# if the scorer would have picked it. Targeted suppression of proven
# semantic contamination only. All entries today target PID, where
# "INSTRUMENT" reads as a PID signal in non-P&ID contexts.
NEGATIVE_KEYWORDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "PID": (
        ("MTO",),
        ("SCHEDULE",),
        ("LAYOUT",),
        ("LIST",),
        ("BULK",),
        ("LOCATION",),
    ),
}
