"""Classifier tunables - edit this file to change behaviour without touching classifier.py.

This file holds:
  * default I/O paths
  * gate threshold for the dossier self-test
  * the bucket taxonomy (BUCKETS, KEYWORD_RULES with weights, TYPE_TO_BUCKET, BUCKET_PRIMARY_CODE)
  * the discipline keyword tier (DISCIPLINE_KEYWORD_RULES)
  * the named regexes for ref / CRS / cover-sheet detection
  * the CSV column order

Re-run after edits:  python classifier.py
The dossier self-test will fail if your changes drop accuracy below GATE_THRESHOLD.
"""
from __future__ import annotations

# -------------------------------------------------------------------------
# I/O paths (relative to project root). Override on the command line if needed.
# -------------------------------------------------------------------------
SCHEDULE_PATH = "input/schedule.xls"
DOSSIER_PATH = "input/dossier.xlsx"
TREE_PATH = "input/transmittals.txt"
OVERRIDES_PATH = "overrides/ref_to_bucket.csv"
OUTPUT_DIR = "output"

# -------------------------------------------------------------------------
# Self-test gate. Set just below your last measured accuracy so legitimate
# keyword tweaks have headroom but real regressions still trip the gate.
# Last measured: 0.957 on 256 dossier rows.
# -------------------------------------------------------------------------
GATE_THRESHOLD = 0.935

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
    "CRS",
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
    "Lists_MTOs_BOMs":  "Documents",
    "Procedures_Plans": "Documents",
    "CRS":              "Documents",
    "Documents":        "Documents",
}

# -------------------------------------------------------------------------
# KEYWORD_RULES drives bucket scoring.
#
# Format:  { bucket_name: [(regex, weight), ...] }
#
# Weights 1-5. Confidence is set from the highest single weight that fired
# in the winning bucket:  5 -> high, 3-4 -> medium, 1-2 -> low.
#
# Regexes are matched case-insensitively against `title + " " + filename`
# with underscores replaced by spaces (so PIPING_AND_INSTRUMENT.pdf hits
# "piping (and|&) instrument").
#
# CRS is filename-pinned (see CRS_RE below) and bypasses scoring; its rule
# list here is intentionally empty.
# Documents is the fallback bucket and only fires its keywords explicitly.
#
# Typo tolerance policy: target real typos seen in the data with relaxed
# regex (e.g. arra?n?g(e)?ment for ARRANGMENT/ARRAGEMENT, requ[is]+ition
# for REQUSITION). Do NOT add generic fuzzy matching (Levenshtein/soundex)
# - false positives are expensive and hard to test. When a new typo
# surfaces in output/undefined_for_review.csv, relax the relevant pattern
# and pin it with a regression test in tests/test_keyword_bank.py.
# -------------------------------------------------------------------------
KEYWORD_RULES: dict = {
    "Drawings": [
        (r"p&id", 5),
        (r"piping (and|&) instrument", 5),
        (r"flow diagram", 4),
        (r"\bpfd\b", 5),  # Process Flow Diagram
        (r"\bbfd\b", 5),  # Block Flow Diagram
        (r"\bufd\b", 5),  # Utility Flow Diagram
        (r"\bmsd\b", 5),  # Mechanical Sketch Diagram
        (r"floor plan", 5),
        (r"approach plan", 5),
        (r"key plan", 4),
        (r"framing plan", 5),
        (r"roof plan", 5),
        (r"grading plan", 5),
        (r"marking plan", 5),
        (r"flooring plan", 5),
        # 'Plan, Sections', 'Plan & Details', 'Plan And Reinforcements' - the
        # 'X plan + drawing-thing' pattern is overwhelmingly architectural drawings.
        (r"plan\s*[,&]?\s*(sections?|details?|elevations?|reinforcements?)", 5),
        (r"approach (drawing|plan)", 5),
        (r"\bcable rout(e|ing)\b", 4),
        (r"cross[\s\-]?section", 3),
        (r"general arrangement", 5),
        (r"\bschematic\b", 3),
        (r"site preparation", 3),
        (r"material selection diagram", 5),
        (r"heat (and|&) materials? balance", 5),
        # Pipeline alignment - tolerate plural and ALINGMENT/ALIGNEMNT typos
        (r"\bpipeline\s+(?:alignment|alingment|alignemnt)s?\b", 5),
        (r"(?:alignment|alingment|alignemnt)s?\s+sheets?\b", 5),
        (r"3d model.*drawing", 5),
        (r"hook-up drawing", 5),
        (r"\bsteel\s+(?:platform|shed|structure|structures)\b", 4),
        (r"manifold (?:extension|extensiton|extention)", 4),  # tolerate EXTENSITON typo
        (r"\bpipe[\s\-]?sleepers?\b", 4),
        (r"\bpaving\b", 3),
        (r"\btypical\b", 2),  # weak signal, but pulls 'TYPICAL <X>' titles out of Undefined
        (r"\bpiping plans?\b", 4),  # 'UPDATION OF EXISTING PIPING PLANS'
        (r"\bwing valves?\b", 4),  # 'Wing Valve Orientation' = wellhead drawing
        (r"\b(?:layouts?|layou)\b", 5),  # tolerate LAYOU typo (truncated)
        (r"arra?n?g(e)?ment", 4),  # tolerate ARRANGMENT (no 'e') and ARRAGEMENT (no 'n') typos
        (r"plot plan", 4),
        (r"standard drawings?", 5),  # 'STANDARD DRAWING(S)' must beat Specifications
        (r"single line", 4),
        (r"block diagram", 4),
        (r"cause (and|&) effect", 5),
        (r"wiring diagram", 4),
        (r"loop /? segment", 4),
        (r"architecture", 3),
        (r"safeguarding", 4),
        (r"hazardous area", 3),
        (r"interconnection diagram", 4),
        (r"installation drawing", 3),
        (r"hook up", 3),
        (r"junction box", 3),
        (r"structural detail", 3),
        (r"foundation", 4),
        (r"pipe support", 4),
        (r"elevation", 3),
        (r"\bprofile\b", 4),  # Pipeline Profiles & Details (code 22)
        (r"\bsketch\b", 4),  # engineering sketch is always a drawing
        (r"\bga\b\s+(for|of)\b", 4),  # 'CIVIL GA FOR ...' = General Arrangement
        (r"\bdetai(?:ls?|s)?\b", 2),  # detail / details / detai / detais (typo)
        (r"\bdrawings?\b", 4),
        (r"\b(?:diagrams?|diagams?|digrams?)\b", 4),  # tolerate DIAGAMS / DIGRAMS typos
        (r"hook[- ]?ups?", 4),  # 'HOOK-UP' / 'HOOK-UPS' / 'HOOK UPS'
        (r"\bdptd\b", 4),  # Distribution Piping Terminal Diagram
        (r"\bhvac\b", 3),  # most HVAC entries in indices are drawings
        (r"rout(e|ing) cables?", 4),  # 'Re-Routing cables', 'Routing Cable'
        (r"(door|window|finishing|architectural) schedule", 4),
        (r"flare system", 3),
    ],
    "Isometrics": [
        (r"isometric", 5),
        (r"\biso\b", 2),
    ],
    "Datasheets": [
        (r"data ?sheets?", 5),
        (r"process data", 4),
        (r"engineering sheets?", 4),  # 'INSTRUMENT ENGINEERING SHEET' style
        # Equipment tag like '(16-01-V-3115)' is highly correlated with
        # vessel/tank datasheet titles (where the title is just the equipment
        # description without the words 'data sheet').
        (r"\(\d{2}-\d{2}-[a-z]+-\d{4}", 3),
    ],
    "Specifications": [
        (r"specification", 5),
        (r"standards?\b", 3),
        (r"general notes", 3),
    ],
    "Calculations": [
        (r"calculation", 5),
        (r"caculation", 5),  # common typo seen in real data
        (r"sizing", 3),
        (r"wall thickness", 4),
        (r"stress analysis", 4),
        (r"buckling analysis", 5),  # 'Pipeline Upheaval Buckling Analysis'
        (r"calc note", 4),
    ],
    "Reports": [
        (r"\breport\b", 5),
        (r"design basis", 5),
        (r"basis of design", 5),  # reversed word order
        (r"\bstudy\b", 3),
        (r"\breview\b", 2),
        (r"close out", 4),
        (r"topograph", 4),
        (r"scope of work", 4),
        (r"hazid", 5),
        (r"hazop", 5),
        (r"phser", 4),
        (r"process .*description", 3),
        (r"technical bid eval[uat]+ion", 5),  # tolerate EVALATION/EVALATUION typos
        (r"\btbe\b", 4),
        (r"geotechnical", 4),
        (r"hazard.*effect register", 5),
    ],
    "Lists_MTOs_BOMs": [
        (r"\bmto\b", 5),
        (r"\bboq\b", 5),  # bill of quantities abbreviation
        (r"bill of quantities", 5),
        (r"bill of material", 5),
        (r"\blists?\b", 3),
        (r"\bschedule\b", 2),
        (r"equipment list", 5),
        (r"line list", 5),
        (r"\bindex\b", 3),
        (r"register", 3),
        (r"tie[\s\-]?in", 4),  # 'tie-in', 'tie in', 'tiein'
        (r"crossing matrix", 5),  # pipeline crossing matrix - tabular register
        (r"\bmatrix\b", 2),  # weak generic - matrices are typically tabular registers in this domain
        (r"i/o list", 5),
        (r"load list", 4),
        (r"consumption summary", 4),
        (r"take[\s\-]?offs?", 4),  # 'PIPING MATERIAL TAKE-OFF' / 'TAKE OFFS'
        (r"materials? take", 4),
    ],
    "Procedures_Plans": [
        (r"procedure", 5),
        (r"\bplan(ning)?\b", 3),  # also matches PLANNING (PACKAGE)
        (r"philosophy", 5),
        (r"\bexecution\b", 3),
        (r"change over", 4),
        (r"work breakdown", 4),
        (r"invoicing", 4),
        (r"method stat(e)?ment", 5),  # tolerate STATMENT typo
        (r"look ahead", 4),
        (r"\btra-", 4),  # Task Risk Assessment - project-specific prefix
        (r"\bitp\b", 4),  # Inspection Test Plan
        (r"\bms\b for\b", 4),  # 'MS FOR ...' = Method Statement abbreviation
    ],
    "CRS": [],  # filename-pinned; see CRS_RE below
    "Documents": [
        # Requisition - tolerate REQUSITION, REQUISTION, REQUISTATION typos
        (r"\brequ[a-z]{2,5}tion\b", 5),
        (r"material requ[a-z]{2,5}tion", 5),
        (r"\bmr\b for", 4),             # 'MR FOR XYZ' = Material Requisition abbreviation
        (r"\brfq\b", 4),                # Request For Quotation
        (r"\bmanuals?\b", 5),           # operating / maintenance / engineering manual
        (r"\bdocuments?\b", 4),         # explicit 'Document' keyword in title
        (r"vendor data", 4),            # vendor data books (code 96)
        (r"\bcatalogue?s?\b", 4),       # catalogue / catalog (code 99)
        (r"\bdossiers?\b", 4),          # construction / engineering dossiers
        (r"residu(?:al|lal) engineering", 4),  # 'Residual Engineering Activity' scope packages (incl. RESIDULAL typo)
    ],
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
    "IDX": "Lists_MTOs_BOMs", "REG": "Lists_MTOs_BOMs", "SCH": "Lists_MTOs_BOMs",
    "PRO": "Procedures_Plans", "PLN": "Procedures_Plans", "PHL": "Procedures_Plans",
    "REQ": "Documents",
}

# Bucket -> primary 3-letter code used in the proposed target filename
# when no dossier Type matches.
BUCKET_PRIMARY_CODE: dict = {
    "Drawings": "DWG",
    "Isometrics": "ISO",
    "Datasheets": "DAS",
    "Specifications": "SPC",
    "Calculations": "CAL",
    "Reports": "REP",
    "Lists_MTOs_BOMs": "LST",
    "Procedures_Plans": "PRO",
    "CRS": "CRS",
    "Documents": "DOC",
}

# -------------------------------------------------------------------------
# Discipline keyword tier (fallback for files without a schedule match
# or seg2 lookup). First match wins; order matters.
# -------------------------------------------------------------------------
DISCIPLINE_KEYWORD_RULES: list = [
    (r"\bhazop\b|\bhazid\b|\bhse\b|\bfire\b|f&g|\bsafety\b", "HSE"),
    (r"foundation|structural|civil\b|rebar|concrete works|steel works", "CIVIL"),
    (r"\bsld\b|\bhv\b|\blv\b|earth(ing)?|substation|cathodic", "ELEC"),
    (r"instrument|\bdcs\b|\besd\b|junction box|\bloop\b|interconnection", "INST"),
    (r"\bpump\b|vessel|exchanger|mechanical|rotating|static equipment", "MECH"),
    (r"\bp&id\b|\bpfd\b|\bufd\b|process flow|safeguarding|cause.*effect", "PROC"),
    (r"stress|hydraulic|piping", "PIPNG"),
    (r"procedure|\bplan\b|invoicing|work breakdown|method statement|\btra-", "PROJECTS"),
]

# -------------------------------------------------------------------------
# Named regexes (used by classifier.py - keep here so they're tunable).
# Empirically validated on the real TO CLIENT corpus (98% CRS match rate).
# -------------------------------------------------------------------------
REF_PATTERN = r"(\d{2}-\d{2}-\d{2}-\d{4})"

CRS_PATTERN = (
    r"(?ix)("
    r"^crs[\s_\-]"
    r"|^crs(?=\d{2}-)"
    r"|^crsheet[\s_\-]"
    r"|^comment[\s_]response"
    r"|^copy[\s_]of[\s_]comment"
    r"|[\s_\-]crs(?=[\s_\-]|\.)"
    r")"
)

COVER_PATTERN = r"(?i)^(cta|c-a-ed-sa)"

# -------------------------------------------------------------------------
# CSV column order. Don't reorder unless you also update downstream
# consumers that depend on column position.
# -------------------------------------------------------------------------
CSV_COLUMNS: tuple = (
    "source_path", "source_filename", "submission_folder", "subfolder",
    "cust_ref", "is_crs", "is_transmittal_cover", "is_archive",
    "letter_rev", "numeric_rev", "extension",
    "pcs_doc_no", "title", "discipline", "schedule_rev",
    "type_code", "form", "type_bucket", "bucket_score",
    "runner_up_bucket", "runner_up_score", "bucket_source", "bucket_confidence",
    "bundle_id", "is_latest_letter", "is_latest_numeric", "is_latest",
    "revision_drift", "match_status",
    "proposed_target_folder", "proposed_target_filename",
    "target_collision", "notes",
)
