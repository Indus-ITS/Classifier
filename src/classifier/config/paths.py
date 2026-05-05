"""I/O paths and the dossier self-test gate threshold."""
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
