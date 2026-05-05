"""Discipline inference: keyword tier and the 5-tier derive_discipline chain."""
from __future__ import annotations

import re

import pandas as pd

from classifier.config.keywords import DISCIPLINE_KEYWORD_RULES


def discipline_from_keywords(text: str) -> str:
    t = text.lower().replace("_", " ")
    for pattern, disc in DISCIPLINE_KEYWORD_RULES:
        if re.search(pattern, t):
            return disc
    return ""


def build_seg2_discipline_map(schedule_df: pd.DataFrame) -> dict:
    out: dict = {}
    for seg2, grp in schedule_df.groupby("seg2"):
        out[seg2] = grp["discipline"].value_counts().idxmax()
    return out


def derive_discipline(*, cust_ref: str, title: str, filename: str,
                      schedule_lookup: dict, seg2_map: dict,
                      submission_majority: str,
                      multi_disc_submission: bool) -> str:
    """5-tier discipline chain (spec section 6.3)."""
    if cust_ref and cust_ref in schedule_lookup:
        return schedule_lookup[cust_ref]
    if cust_ref:
        seg2 = cust_ref.split("-")[2] if "-" in cust_ref else ""
        if seg2 in seg2_map:
            return seg2_map[seg2]
    kw = discipline_from_keywords(title + " " + filename)
    if kw:
        return kw
    if submission_majority and not multi_disc_submission:
        return submission_majority
    return "UNK"
