"""CSV column order for the audit/enrich output.

Don't reorder unless you also update downstream consumers that depend on
column position.
"""
from __future__ import annotations

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
