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
])
def test_titles_resolve_to_canonical_discipline(title, expected):
    assert _id(title) == expected


def test_keys_are_all_valid_discipline_ids():
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
    from classifier.io.disciplines import load_valid_discipline_ids
    assert set(DISCIPLINE_KEYWORDS).issubset(load_valid_discipline_ids())
