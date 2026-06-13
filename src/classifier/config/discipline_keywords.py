"""Hand-maintained per-discipline title scoring.

Keys are canonical discipline ids (input/disciplines.csv). Authored from the
learn/*.xlsx dossiers (see docs/superpowers/specs/2026-06-13-learn-dossier-
disciplines-design.md). Project/doc-no noise and cross-discipline type words
are deliberately excluded. Weights follow core.scoring thresholds: a lone
distinctive phrase weighs >= 2.5 so it classifies at "high" alone.
"""
from __future__ import annotations

UNTRAINED_DISCIPLINES: frozenset[int] = frozenset()

DISCIPLINE_KEYWORDS: dict[int, tuple[tuple[str, float], ...]] = {
    1: (  # Civil
        ('FOUNDATION', 3.2),
        ('FOUNDATION DETAILS', 2.6),
        ('STEEL STRUCTURE', 3.0),
        ('STEEL', 2.5),
        ('STRUCTURE', 2.5),
        ('CIVIL GENERAL ARRANGEMENT', 2.8),
        ('GENERAL ARRANGEMENT LAYOUT', 2.6),
        ('CIVIL', 2.4),
        ('TOPOGRAPHICAL', 2.3),
        ('PIPE RACK', 2.0),
    ),
    3: (  # Electrical
        ('SINGLE LINE DIAGRAM', 3.5),
        ('SINGLE LINE', 3.2),
        ('LINE DIAGRAM', 2.8),
        ('SUBSTATION', 3.0),
        ('SUBSTATION NO', 2.6),
        ('ELECTRICAL', 2.8),
        ('LIGHTING', 2.4),
        ('EARTHING', 2.4),
    ),
    6: (  # I&C
        ('TRANSMITTERS', 2.8),
        ('ELECTRONIC TRANSMITTERS', 2.8),
        ('ACTING REGULATORS', 2.6),
        ('PRESSURE GAUGES', 2.5),
        ('ROTAMETER', 2.5),
        ('MULTIPHASE FLOW METER', 2.6),
        ('AREA FLOWMETER', 2.4),
        ('ICSS', 2.4),
    ),
    7: (  # Mechanical (incl. tanks/vessels, ex-id-10)
        ('WATER DISPOSAL TANK', 3.2),
        ('DISPOSAL TANK', 2.8),
        ('WATER PUMPS', 2.6),
        ('MECHANICAL DATA SHEET', 2.6),
        ('MECHANICAL', 2.5),
        ('EOT CRANE', 2.4),
        ('NOZZLES DETAILS', 2.2),
        ('SHELL', 2.0),
    ),
    8: (  # Piping
        ('PIPING LAYOUT DRAWING', 3.4),
        ('PIPING LAYOUT', 3.0),
        ('PIPING ISOMETRIC', 3.0),
        ('ISOMETRIC', 2.6),
        ('PIPING GA', 2.8),
        ('PIPING GA CONSTRUCTION', 2.8),
        ('VALVES', 2.4),
        ('FITTINGS', 2.4),
    ),
    11: (  # Process
        ('PIPING & INSTRUMENT', 3.5),
        ('INSTRUMENT DIAGRAM', 3.2),
        ('PROCESS FLOW DIAGRAM', 3.2),
        ('FLOW DIAGRAM', 2.6),
        ('PROCESS', 2.4),
        ('MATERIAL SELECTION DIAGRAM', 2.8),
        ('SAFEGUARDING', 2.4),
    ),
}
