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
        ("GADS",),          # general arrangement drawings (GADs Construction)
        ("GAD",),
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
        ("BOQ",),
        ("BILL", "OF", "QUANTITIES"),
    ),
    "DAS": (
        ("DATASHEET",),
        ("DATA", "SHEET"),
        ("MECHANICAL", "DATASHEET"),
        ("INSTRUMENT", "DATASHEET"),
        ("ELECTRICAL", "DATASHEET"),
        ("VALVE", "DS"),        # "<tag>_Valve DS" filename style
        ("LEGEND", "SHEET"),    # legend sheets
    ),
    "PHL": (
        ("PHILOSOPHY",),
    ),
    "REG": (
        ("REGISTER",),
        ("RISK", "MATRIX"),
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
        ("ARCH", "DIAGRAM"),
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
        ("SECTIONAL", "DETAILS"),
        ("SECTIONAL", "DETAIL"),
    ),
    # Generic construction drawings - "CONSTRUCTION DRAWING (TYP)..." titles.
    "DWG": (
        ("CONSTRUCTION", "DRAWING"),
        ("WIRING", "DIAGRAM"),
        ("LOOP", "DIAGRAM"),
        ("PROTECTION", "AND", "METERING", "DIAGRAM"),
        ("METERING", "DIAGRAM"),
        ("DEMOLITION",),                # demolition drawings
    ),
    "DPP": (
        ("PLOT", "PLAN"),
    ),
    # Specifications issued under the ADNOC AGES-SP series whose title may
    # carry only the subject word (CONCRETE/STEEL/DB) not "specification".
    "SPC": (
        ("AGES", "SP"),
    ),
    # Instruction to Bidders (tender document).
    "ITB": (
        ("INSTRUCTION", "TO", "BIDDERS"),
        ("ITB",),
    ),
    # Plan documents (not plan-view drawings). Specific 2-grams only —
    # avoid bare ("PLAN",) so structural plan-view drawings like
    # "PIPE RACK PLANS AND DETAIL" are not swept up.
    "PLN": (
        ("EXECUTION", "PLAN"),
        ("QUALITY", "PLAN"),
        ("HSE", "PLAN"),
        ("INSPECTION", "PLAN"),
        ("MANAGEMENT", "PLAN"),
        ("PROJECT", "PLAN"),
        ("CONTINGENCY", "PLAN"),
        ("PROCUREMENT", "PLAN"),
        ("MOBILIZATION", "PLAN"),
        ("COMMISSIONING", "PLAN"),
        ("EMERGENCY", "RESPONSE", "PLAN"),
        ("REPORTING", "PLAN"),
    ),
    "DAL": (
        ("ELECTRICAL", "EQUIPMENT", "LAYOUT"),
        ("ELECTRICAL", "CABLE", "ROUTING"),
        ("CABLE", "ROUTING"),
        ("INSTRUMENT", "CABLE", "ROUTING"),
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
        # "INSTRUMENT X DRAWINGS" patterns where the X is not "DIAGRAM".
        # Real P&IDs land via HARD_OVERRIDES before this prune runs, so
        # these only suppress the learned scorer's "INSTRUMENT" signal
        # on instrumentation-discipline drawings that are not P&IDs.
        ("INSTRUMENT", "LOOP"),
        ("INSTRUMENT", "LOOP/SEGMENT"),
        ("INSTRUMENT", "INSTALLATION"),
        ("INSTRUMENT", "JB"),
        ("INSTRUMENT", "INDEX"),
        ("INSTRUMENT", "HOOK"),
        ("LOOP", "DRAWING"),
    ),
    # "MODEL INDEX DRAWING" and similar are CAD drawings (.dwg), not
    # tabular indexes. When a title names a DRAWING, suppress IDX so the
    # row routes to the Drawings class via the DRAWING/SKETCH fallback.
    # A plain index ("INSTRUMENT INDEX") has no DRAWING token and is
    # unaffected. Lists/registers of drawings ("DRAWING LIST",
    # "DRAWING REGISTER") are typed LST/REG, not IDX, so they stay Sheets.
    "IDX": (
        ("DRAWING",),
    ),
}
