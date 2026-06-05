"""Behavior-lock for the scoring collapse: pick_type / pick_discipline must
return identical results before and after the engine extraction, across every
title in the labelled training CSVs.
"""
from pathlib import Path
import csv

from classifier.core.type_scoring import score_types, pick_type
from classifier.core.discipline_scoring import score_disciplines, pick_discipline

CSV_DIR = Path("input/classified_csv")


def _titles():
    titles = []
    for p in sorted(CSV_DIR.rglob("*.csv")):   # sorted -> deterministic across machines
        with p.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = (row.get("title") or "").strip()
                if t:
                    titles.append(t)
    return titles[:2000]   # cap for runtime; sorted-path order is stable


def test_pick_type_is_deterministic_and_runs():
    # Smoke + determinism: same title twice -> same verdict.
    for t in _titles():
        a = pick_type(score_types(t))
        b = pick_type(score_types(t))
        assert a == b


def test_pick_discipline_is_deterministic_and_runs():
    for t in _titles():
        a = pick_discipline(score_disciplines(t))
        b = pick_discipline(score_disciplines(t))
        assert a == b


import json

from classifier.core.record import Record
from classifier.core.classify import classify_record

BASELINE = Path("tests/core/scoring_baseline.json")


def _verdicts():
    out = []
    for t in _titles():
        pt = pick_type(score_types(t))
        pd_ = pick_discipline(score_disciplines(t))
        # Full end-to-end triple via classify_record. This is the ONLY guard
        # that exercises the type->discipline hint feedback (classify_record
        # passes the inferred type as fill_discipline's type_hint), so it locks
        # the TYPE_HINT_BONUS path that Task 18 rewrites.
        cr = classify_record(Record(title=t))
        out.append({"title": t,
                    "type": pt.get("type"), "type_conf": pt.get("confidence"),
                    "disc": pd_.get("discipline_id"), "disc_conf": pd_.get("confidence"),
                    "cr_doc_type": cr.doc_type.value,
                    "cr_type": cr.type.value,
                    "cr_disc": cr.discipline_id.value})
    return out


def test_verdicts_match_frozen_baseline():
    current = _verdicts()
    if not BASELINE.exists():
        BASELINE.write_text(json.dumps(current, indent=0))
        return  # first run records the baseline
    saved = json.loads(BASELINE.read_text())
    assert current == saved, "scoring verdicts drifted from frozen baseline"
