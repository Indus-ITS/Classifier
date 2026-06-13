import pytest
from classifier.core.discipline_scoring import (
    score_disciplines, pick_discipline,
)


def _id(title):
    return pick_discipline(score_disciplines(title))["discipline_id"]


@pytest.mark.parametrize("title, expected", [
    ("SINGLE LINE DIAGRAM SUBSTATION", 3),     # Electrical
    ("ELECTRICAL LIGHTING LAYOUT", 3),
    ("PIPING LAYOUT DRAWING AREA 01", 8),       # Piping
    ("PIPING ISOMETRIC", 8),
    ("PIPING & INSTRUMENT DIAGRAM WATER", 11),  # Process (P&ID)
    ("PROCESS FLOW DIAGRAM", 11),
    ("FOUNDATION DETAILS STEEL STRUCTURE", 1),  # Civil
    ("CIVIL GENERAL ARRANGEMENT", 1),
    ("WATER DISPOSAL TANK", 7),                 # Mechanical
    ("ACTING REGULATORS DATA SHEET", 6),        # I&C
    ("TRANSMITTERS DATA SHEET", 6),
    # --- second tuning pass (still-null recovery) ---
    ("EARTHING INSTALLATION STANDARDS", 3),     # near-floor weight bump
    ("CABLE SIZING CALCULATION", 3),
    ("HSE PLAN", 5),                            # HSE bucket
    ("FIRE FIGHTING & SAFETY EQUIPMENT LAYOUT", 5),
    ("HAZOP REPORT", 5),
    ("F&G DETECTORS LOCATION LAYOUT", 6),       # Fire & Gas DETECTION -> I&C
    ("FIRE & GAS INPUT/OUTPUT LIST", 6),
    ("INSTRUMENT INDEX", 6),
    ("DCS I/O LIST", 6),
    ("PROCESS DATA SHEET FOR WATER DISPOSAL TANK", 7),  # PROCESS-collision resolved
    ("PROCESS DATA SHEET FOR MULTI-PHASE FLOW METER", 6),
    ("PIPING MTO", 8),                          # bare PIPING support
    ("MATERIAL REQUISITION FOR GATE VALVES", 8),
    ("STANDARD PIPE SUPPORTS DRAWINGS", 8),
    ("TOPOGRAPHICAL SURVEY REPORT", 1),         # Civil bump
    ("3D MODEL EXECUTION PHILOSOPHY", 11),      # CAD/model -> Process
    # --- third pass (taxonomy decisions on remaining nulls) ---
    ("OVERALL PLOT PLAN", 8),                   # PLOT PLAN -> Piping
    ("HAZARDOUS AREA CLASSIFICATION SCHEDULE", 3),  # HAC -> Electrical
    ("SCOPE OF WORK FOR CATHODIC PROTECTION", 3),   # cathodic -> Electrical
    ("CORROSION CONTROL AND MATERIAL SELECTION REPORT", 11),  # -> Process
    ("PROCESS DESIGN BASIS", 11),               # span-order fix
    ("PROCESS AND UTILITIES DESCRIPTION", 11),
    ("PROJECT DESIGN BASIS", 4),                # Engineering/Project Mgmt
    ("EPC OF SAHIL FIELD DEVELOPMENT PROJECT SCOPE OF WORK", 4),
    ("DATA SHEET FOR CONTROL VALVES AND SELF ACTING REGULATORS", 6),
    ("VALVE LIST", 8),
    ("FOUNDATION FOR PRODUCED WATER TANK", 1),  # FOUNDATION beats WATER TANK
    # --- real-world doc-number title vocabulary (test snapshot) ---
    ("Vendor Scheme Existing J11 Motor Feeder", 3),     # FEEDER -> Electrical
    ("Existing 415V Swbd SS-N Details", 3),             # SWBD -> Electrical
    ("415V Switchgear Single Line Diagram", 3),
])
def test_titles_resolve_to_canonical_discipline(title, expected):
    assert _id(title) == expected


def test_keys_are_all_valid_discipline_ids():
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
    from classifier.io.disciplines import load_valid_discipline_ids
    assert set(DISCIPLINE_KEYWORDS).issubset(load_valid_discipline_ids())
