"""Titles that name a prose engineering document despite carrying a
sheet-ish keyword (LIST / SCHEDULE / REGISTER). Verified by reading the
actual files: each has a Table of Contents + Introduction narrative.

Matched as contiguous token subsequences against the canonicalized title
(same canonicalizer the scorer uses). Kept here as data so the list can
grow from verifier evidence without touching logic.
"""
from __future__ import annotations

PROSE_DOC_PHRASES: tuple[tuple[str, ...], ...] = (
    ("HAZARDOUS", "AREA"),                       # HAZARDOUS AREA CLASSIFICATION SCHEDULE
    ("RELAY", "SETTING"),                        # RELAY SETTING SCHEDULE
    ("SPECIALITY", "ITEMS"),                     # SPECIALITY ITEMS LIST
    ("SPECIALTY", "ITEMS"),                      # LIST OF PIPING SPECIALTY ITEMS
    ("LIST", "OF", "ENGINEERING", "DELIVERABLES"),
    ("HAZARD", "&", "EFFECT"),                   # HAZARD & EFFECT REGISTER ('&' kept as token)
    ("HSE",),                                    # HSE ACTION TRACKING REGISTER / HSE plans
)
