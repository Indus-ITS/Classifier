"""Hand-maintained: type -> discipline_id fallback.

Only "pure" dossier types (100% concentrated in one discipline, support >= 3 in
learn/*.xlsx) are listed, so an ambiguous type never forces a discipline.
Used two ways: a +2 score bonus in discipline_scoring, and the gated
write-time fallback in core.classify.fill_discipline. Ids are canonical
(input/disciplines.csv). Comments record dossier support.
"""
from __future__ import annotations

TYPE_TO_DISCIPLINE: dict[str, int] = {
    "PID": 11,  # Process — 24/24 (P&ID filed under Process in both dossiers)
    "PFD": 11,  # Process — 6/6
    "MSD": 11,  # Process — 5/5
    "PSF": 11,  # Process — 3/3
    "DSL": 3,   # Electrical — 14/14 (single line diagram)
    "DSD": 3,   # Electrical — 3/3
    "DGA": 8,   # Piping — 12/12 (piping GA)
}
