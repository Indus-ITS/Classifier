"""Regression tests for keyword-bank fixes across v4 (schedule rows)
and v5 (73k labelled corpus). Each test pins a real failing case so an
"innocent" config tweak can't silently re-break the bucket.
"""
from helpers.classifier_lib import pick_bucket, score_buckets


def _bucket(title: str, filename: str = "") -> str:
    return pick_bucket(score_buckets(title, filename))["bucket"]


# -----------------------------------------------------------------------
# v4: word-boundary regexes were too tight on plural forms - DRAWINGS,
# DIAGRAMS, LAYOUTS - so titles using the plural fell through to Documents.
# -----------------------------------------------------------------------
def test_plural_drawings_matches_drawings():
    # 'INSTRUMENT LOOP DRAWINGS' fell through to Documents pre-fix.
    assert _bucket("INSTRUMENT LOOP DRAWINGS - SB-159 WELL") == "Drawings"


def test_plural_diagrams_matches_drawings():
    assert _bucket("INSTRUMENT TERMINATION DIAGRAMS ASAB AREA") == "Drawings"


def test_plural_layouts_matches_drawings():
    assert _bucket("PIPING LAYOUTS WELLHEAD FOR GAS LIFT") == "Drawings"


def test_plural_lists_matches_lists():
    # 'lists' plural - was bare \blist\b before.
    assert _bucket("EQUIPMENT LISTS FOR SHAH CDS") == "Lists_MTOs_BOMs"


def test_plural_datasheets_matches_datasheets():
    assert _bucket("DATA SHEETS FOR ANGLE VALVES") == "Datasheets"


# -----------------------------------------------------------------------
# v4: typos seen in real data
# -----------------------------------------------------------------------
def test_arrangment_typo_matches_drawings():
    # 'ARRANGMENT' instead of 'ARRANGEMENT' - real data typo (missing 'e').
    assert _bucket("GENERAL ARRANGMENT PIPING SECTION A") == "Drawings"


def test_arragement_typo_matches_drawings():
    # 'ARRAGEMENT' instead of 'ARRANGEMENT' - real data typo (missing 'n').
    assert _bucket("GENERAL ARRAGEMENT WELLHEAD SB-159") == "Drawings"


def test_method_statment_typo_matches_procedures():
    # 'STATMENT' typo for 'STATEMENT'.
    assert _bucket("METHOD STATMENT FOR SHAH MSM") == "Procedures_Plans"


# -----------------------------------------------------------------------
# v4: abbreviations / additions
# -----------------------------------------------------------------------
def test_boq_matches_lists():
    assert _bucket("BOQ ASAB FIELD") == "Lists_MTOs_BOMs"


def test_take_off_matches_lists():
    assert _bucket("PIPING MATERIAL TAKE-OFFS FOR SHAH FIELD") == "Lists_MTOs_BOMs"
    assert _bucket("PIPING MATERIALS TAKE OFF FOR ASAB FIELD") == "Lists_MTOs_BOMs"


def test_engineering_sheet_matches_datasheets():
    # 'INSTRUMENT ENGINEERING SHEET' - was falling through.
    assert _bucket("INSTRUMENT ENGINEERING SHEET FOR PRESSURE") == "Datasheets"


def test_itp_matches_procedures():
    # 'ITP' = Inspection Test Plan.
    assert _bucket("ITP for Threaded Lines - Qusahwira") == "Procedures_Plans"


def test_standard_drawing_beats_specifications():
    # 'STANDARD DRAWING GENERAL NOTES' previously won by Specifications
    # (general notes 3 + standards 3 = 6 vs Drawings drawing 4). Fix added
    # 'standard drawings?' weight 5 to Drawings.
    assert _bucket("STANDARD DRAWING GENERAL NOTES, ABBREVIATION AND LEGEND") == "Drawings"


# -----------------------------------------------------------------------
# v5: corpus-driven additions - flow-diagram abbreviations
# -----------------------------------------------------------------------
def test_pfd_abbrev_matches_drawings():
    assert _bucket("PFD - HP Gas Injection Compression Sahil CDS") == "Drawings"


def test_bfd_abbrev_matches_drawings():
    assert _bucket("BFD-Sahil CDS - Gas Compressor") == "Drawings"


def test_ufd_abbrev_matches_drawings():
    assert _bucket("UFD - Cooling Water Distribution") == "Drawings"


def test_msd_abbrev_matches_drawings():
    assert _bucket("MSD - INLET MANIFOLDS AND TEST METERING") == "Drawings"


# -----------------------------------------------------------------------
# v5: drawing-context 'plan' must beat Procedures_Plans bare 'plan' rule
# -----------------------------------------------------------------------
def test_floor_plan_matches_drawings():
    assert _bucket("HVAC System Ground Floor Plan C/B Sahil CDS") == "Drawings"


def test_roof_plan_matches_drawings():
    assert _bucket("Roof Plan") == "Drawings"


def test_grading_plan_matches_drawings():
    assert _bucket("Block Valve Station Grading Plan For Sahil Asab MOL") == "Drawings"


def test_marking_plan_matches_drawings():
    assert _bucket("Architectural Drawings Flooring Plan And Marking Plan C/B Sahil CDS") == "Drawings"


def test_approach_plan_matches_drawings():
    assert _bucket("Pipeline approach plan to manifold M-0111 Sahil CDS") == "Drawings"


def test_plan_with_sections_matches_drawings():
    # 'X Plan & Sections' / 'Plan, Sections, Reinforcements' - explicit
    # drawing-thing co-occurrence overrides bare 'plan' Procedures match.
    assert _bucket("Evaporation Pond Stair. Plan, Sections & Reinforcements") == "Drawings"


# -----------------------------------------------------------------------
# v5: equipment-tag pattern '(NN-NN-V-NNNN)' classifies vessel/tank
# datasheet titles where 'data sheet' isn't in the title text
# -----------------------------------------------------------------------
def test_equipment_tag_prefix_matches_datasheets():
    assert _bucket("(16-01-V-3115) Gas Injection Compressor 1st Stage Suction Drum") == "Datasheets"


def test_equipment_tag_suffix_matches_datasheets():
    assert _bucket("Tundish Drain Sump (16-01-V-6703)") == "Datasheets"


# -----------------------------------------------------------------------
# v5: 'basis of design' (reversed word order) was missing from Reports
# -----------------------------------------------------------------------
def test_basis_of_design_matches_reports():
    assert _bucket("Process Basis Of Design - Sahil") == "Reports"


def test_design_basis_still_matches_reports():
    # The original 'design basis' rule must still work.
    assert _bucket("PROCESS DESIGN BASIS") == "Reports"


# -----------------------------------------------------------------------
# v5: hook-ups (with hyphen + plural) was previously only matching 'hook up'
# -----------------------------------------------------------------------
def test_hook_ups_plural_matches_drawings():
    assert _bucket("INSTRUMENT PROCESS & INSTRUMENT AIR SUB-HEADER HOOK-UPS") == "Drawings"


# -----------------------------------------------------------------------
# v5: door/window/finishing 'schedule' columns are architectural drawings,
# must not be miscaptured by Lists_MTOs_BOMs '\bschedule\b' rule.
# -----------------------------------------------------------------------
def test_door_schedule_matches_drawings():
    assert _bucket("Door Schedule - 1/2 - C/B Shah CDS") == "Drawings"


def test_window_schedule_matches_drawings():
    assert _bucket("Window Schedule - C/B Shah CDS") == "Drawings"


def test_finishing_schedule_matches_drawings():
    assert _bucket("Finishing Schedule - Control Building Shah CDS") == "Drawings"


# -----------------------------------------------------------------------
# v6: 'profile' (Pipeline Profiles & Details, code 22) was missing from
# Drawings keywords - real titles like 'Pipeline Long Profile' fell
# through to Documents.
# -----------------------------------------------------------------------
def test_pipeline_profile_matches_drawings():
    assert _bucket("Pipeline Approach Profile - Sahil CDS") == "Drawings"


def test_pipeline_long_profile_matches_drawings():
    assert _bucket("Pipeline Long Profile - 16 inch CDS South") == "Drawings"


# -----------------------------------------------------------------------
# v7: GA FOR (General Arrangement) and SKETCH - common drawing patterns
# that fell into Undefined in the schedule output (140 of 142 rows).
# -----------------------------------------------------------------------
def test_ga_for_matches_drawings():
    # Real Undefined examples from output/undefined_for_review.csv
    assert _bucket("CIVIL GA FOR CDS, SHAH FIELD") == "Drawings"
    assert _bucket("CIVIL GA FOR RDS-1, FOR QUSAHWIRA FIELD.") == "Drawings"


def test_ga_of_matches_drawings():
    assert _bucket("Detailed GA of Wellhead Platform") == "Drawings"


def test_sketch_matches_drawings():
    assert _bucket("Engineering Sketch for Pipe Support") == "Drawings"


# -----------------------------------------------------------------------
# v7: 'documents' / 'manuals' / 'vendor data' / 'catalogue' - explicit
# textual-document signals were missing from the Documents bucket.
# -----------------------------------------------------------------------
def test_manual_matches_documents():
    assert _bucket("Operating Manual for Compressor Package") == "Documents"


def test_manuals_plural_matches_documents():
    assert _bucket("Vendor Manuals - Pumps") == "Documents"


def test_document_in_title_matches_documents():
    # Real Undefined examples from output/undefined_for_review.csv
    assert _bucket("ASAB CONSTRUCTION DOCUMENT") == "Documents"
    assert _bucket("Construction QA Documents") == "Documents"


def test_vendor_data_matches_documents():
    assert _bucket("Vendor Data Book - Heat Exchanger E-3201") == "Documents"


def test_catalogue_matches_documents():
    assert _bucket("Equipment Catalogue") == "Documents"


# -----------------------------------------------------------------------
# v8: review of output/undefined_for_review.csv surfaced more real patterns
# -----------------------------------------------------------------------

# --- Pipeline alignment (plural + typos) ---
def test_pipeline_alignments_plural_matches_drawings():
    assert _bucket("PIPELINE ALIGNMENTS SHEET FOR GAS INJECTION WELL QW-83") == "Drawings"


def test_pipeline_alignment_typo_alingment_matches_drawings():
    assert _bucket("PIPELINE ALINGMENT SHEET NEW 3 GAS INJECTION FLOWLINE") == "Drawings"


def test_pipeline_alignment_typo_alignemnt_matches_drawings():
    assert _bucket("PIPELINE ALIGNEMNT SHEET NEW 6 OIL FLOWLINE") == "Drawings"


# --- Wellhead / structural / paving / typical drawings ---
def test_manifold_extension_matches_drawings():
    assert _bucket("MANIFOLD EXTENSION FOR QUSAHWIRA") == "Drawings"


def test_steel_platform_matches_drawings():
    assert _bucket("STEEL PLATFORM STUCTURE AT GAS INJECTION HEADER") == "Drawings"


def test_steel_shed_matches_drawings():
    assert _bucket("STEEL SHED FOR MSM FOR CDS, SHAH FIELD.") == "Drawings"


def test_typical_pulls_out_of_undefined():
    """'TYPICAL X' titles are drawings in this domain. Weight 2 means low
    confidence but still classifies as Drawings instead of Undefined."""
    assert _bucket("TYPICAL PIPE SLEEPERS") == "Drawings"
    assert _bucket("TYPICAL PIPELINE MARKER & WARNING NOTICE") == "Drawings"


def test_paving_matches_drawings():
    assert _bucket("PAVING AND DRAINAGE FOR MSM AREA FOR CDS, SHAH FIELD.") == "Drawings"


# --- Diagram / layout typos ---
def test_diagam_typo_matches_drawings():
    """DIAGAMS - missing 'r'."""
    assert _bucket("INSTRUMENT TERMINATION DIAGAMS (ASAB AREA SB-403 WELL)") == "Drawings"


def test_digrams_typo_matches_drawings():
    """DIGRAMS - missing 'a'."""
    assert _bucket("INSTRUMENT TERMINATION DIGRAMS (QUSAHWIRA AREA SB-087 WELL)") == "Drawings"


def test_layou_truncated_typo_matches_drawings():
    """'LAYOU' - truncated LAYOUT."""
    assert _bucket("INSTRUMENT LOCATION LAYOU SB-098 WELL") == "Drawings"


# --- Documents additions ---
def test_residual_engineering_matches_documents():
    """'Residual Engineering Activity for...' = scope/work package = Documents."""
    assert _bucket("Residual Engineering Activity for GL wells Construction Only") == "Documents"


def test_residulal_typo_matches_documents():
    """'RESIDULAL' - extra 'l' typo."""
    assert _bucket("Residulal Engineering GL") == "Documents"


def test_rfq_matches_documents():
    """RFQ = Request For Quotation = procurement document."""
    assert _bucket("RFQ FOR SAFETY EQUIPMENT") == "Documents"


def test_dossier_matches_documents():
    assert _bucket("CONSTRUCTION MATERIAL DOSSIER") == "Documents"


# --- Requisition typos (REQUISTATION, REQUISTION) ---
def test_requistation_typo_matches_documents():
    """REQUISTATION = REQUISITION with extra letters - relaxed pattern."""
    assert _bucket("MATERIAL REQUISTATION FOR CHAIN HOIST") == "Documents"


def test_requistion_typo_matches_documents():
    """REQUISTION = REQUISITION with letters dropped - relaxed pattern."""
    assert _bucket("MATERIAL REQUISTION FOR PIPELINE ISOLATING JOINT") == "Documents"


# --- Buckling analysis (Calculations) ---
def test_buckling_analysis_matches_calculations():
    assert _bucket("PIPELINE UPHEAVAL BUCKLING ANALYSIS FOR ASAB FIELD") == "Calculations"


# --- Matrix (Lists) ---
def test_crossing_matrix_matches_lists():
    assert _bucket("PIPELINE CROSSING MATRIX FOR QUASAHWIRA FIELD") == "Lists_MTOs_BOMs"


# --- Tie-in space tolerance ---
def test_tie_in_with_space_matches_lists():
    """'TIE IN' with space (not hyphen) used to fall through."""
    assert _bucket("EARLY TIE IN PACKAGE FOR CDS SHAH") == "Lists_MTOs_BOMs"


# --- Last-pass typos ---
def test_detais_typo_matches_drawings():
    """DETAIS - missing 'l' in DETAILS."""
    assert _bucket("MISCELLANOUS PLATFORM DETAIS IN WELLHEADS FOR SHAH FIELD") == "Drawings"


def test_extensiton_typo_matches_drawings():
    """MANIFOLD EXTENSITON - typo for EXTENSION."""
    assert _bucket("MANIFOLD EXTENSITON FOR QUSAHWIRA") == "Drawings"


def test_piping_plans_matches_drawings():
    assert _bucket("UPDATION OF EXISTING PIPING PLANS AT QUSAHWIRA CDS") == "Drawings"


def test_wing_valve_matches_drawings():
    assert _bucket("WING VALVE ORIENTATION FOR ESP WELLS IN SHAH FIELD") == "Drawings"
