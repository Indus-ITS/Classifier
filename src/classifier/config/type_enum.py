"""Hand-maintained classifier config (was generated; training retired). Edit directly."""
from __future__ import annotations

# Generated 2026-05-17 from 2 CSV(s) under input/classified_csv/.

KNOWN_TYPES: frozenset[str] = frozenset({
    'BOD',
    'BOM',
    'CAL',
    'DAL',
    'DAS',
    'DBD',
    'DCE',
    'DDT',
    'DGA',
    'DHZ',
    'DPP',
    'DSD',
    'DSL',
    'DWD',
    'DWG',
    'IDX',
    'ISO',
    'LST',
    'MSD',
    'MTO',
    'PFD',
    'PHL',
    'PID',
    'PLN',
    'PRO',
    'PSF',
    'REG',
    'REP',
    'REQ',
    'SCH',
    'SOW',
    'SPC',
    'STD',
    'TBE',
})

OBSERVED_OUTLIERS: dict[str, int] = {
    'ITB': 1,
    'PROPOSAL': 8,
}

ALL_OBSERVED_TYPES: frozenset[str] = KNOWN_TYPES | frozenset(OBSERVED_OUTLIERS)
