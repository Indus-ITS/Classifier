"""Bucket taxonomy: the 10 internal buckets and their fold to user-facing classes.

The 10 buckets are the fine-grained classification; BUCKET_TO_CLASS folds
them down to the 3-class user output (Drawings / Documents / Sheets). TYPE_TO_BUCKET
maps dossier 3-letter Type codes to buckets.
"""
from __future__ import annotations

# -------------------------------------------------------------------------
# Buckets - the 10 content classifications
# -------------------------------------------------------------------------
BUCKETS = (
    "Drawings",
    "Isometrics",
    "Datasheets",
    "Specifications",
    "Calculations",
    "Reports",
    "Lists_MTOs_BOMs",
    "Procedures_Plans",
    "Documents",
)

# -------------------------------------------------------------------------
# 10-bucket -> 2-class fold. Used by classifier.py to derive the user-
# facing 'class' column. See docs/specs/2026-05-01-two-class-fold-design.md.
# Single source of truth - every consumer reads from here.
# -------------------------------------------------------------------------
BUCKET_TO_CLASS: dict = {
    "Drawings":         "Drawings",
    "Isometrics":       "Drawings",
    "Datasheets":       "Documents",
    "Specifications":   "Documents",
    "Calculations":     "Documents",
    "Reports":          "Documents",
    "Lists_MTOs_BOMs":  "Sheets",
    "Procedures_Plans": "Documents",
    "Documents":        "Documents",
}

# Primary short code for each bucket (used for display / reporting).
BUCKET_PRIMARY_CODE: dict = {
    "Drawings":         "DWG",
    "Isometrics":       "ISO",
    "Datasheets":       "DAS",
    "Specifications":   "SPC",
    "Calculations":     "CAL",
    "Reports":          "REP",
    "Lists_MTOs_BOMs":  "LST",
    "Procedures_Plans": "PRO",
    "Documents":        "DOC",
}

# -------------------------------------------------------------------------
# Dossier "Type" code -> bucket. Used when a file's cust_ref happens to
# match a dossier doc_no (rare on this project, but the mapping is also
# the source of truth for the self-test).
# -------------------------------------------------------------------------
TYPE_TO_BUCKET: dict = {
    "PID": "Drawings", "PFD": "Drawings", "PSF": "Drawings", "DGA": "Drawings",
    "DSD": "Drawings", "DWG": "Drawings", "DAL": "Drawings", "DWD": "Drawings",
    "DSL": "Drawings", "DBD": "Drawings", "DCE": "Drawings", "DHZ": "Drawings",
    "DPP": "Drawings", "MSD": "Drawings",
    "DAS": "Datasheets",
    "SPC": "Specifications", "STD": "Specifications",
    "CAL": "Calculations",
    "REP": "Reports", "BOD": "Reports", "SOW": "Reports",
    "LST": "Lists_MTOs_BOMs", "MTO": "Lists_MTOs_BOMs", "BOM": "Lists_MTOs_BOMs",
    "IDX": "Lists_MTOs_BOMs", "REG": "Documents", "SCH": "Lists_MTOs_BOMs",
    "PRO": "Procedures_Plans", "PLN": "Procedures_Plans", "PHL": "Procedures_Plans",
    "REQ": "Documents",
    "TBE": "Documents",     # Technical Bid Evaluation
    "ISO": "Isometrics",    # Isometric drawings (bucket exists)
    "DDT": "Drawings",      # Detail drawings (foundation/structural/roof)
}