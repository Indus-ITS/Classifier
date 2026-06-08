from classifier.core.classify import normalize_doc_type


def _cls(title):
    return normalize_doc_type("NULL", title)[0]


def test_standard_drawing_titles_are_drawing():
    assert _cls("STANDARD DRAWING REBAR ARRANGEMENT") == "drawing"
    assert _cls("STANDARD DRAWING ANCHOR BOLT DETAILS") == "drawing"


def test_drawing_wins_over_index_and_list():
    assert _cls("3D MODEL DESIGN AREA/MODEL INDEX DRAWING AREA-2") == "drawing"
    assert _cls("STANDARD DRAWING MEMBER LIST") == "drawing"


def test_sketch_title_is_drawing():
    assert _cls("PIPING TIE-IN SKETCHES (25 SHEETS)") == "drawing"


def test_index_titles_are_sheet():
    assert _cls("INSTRUMENT INDEX") == "sheet"
    assert _cls("INSTRUMENT INDEX - SAHIL CDS") == "sheet"
    assert _cls("ISO INDEX") == "sheet"
    assert _cls("ISOMETRIC INDEX") == "sheet"


def test_prose_guard_still_wins_over_new_rules():
    assert _cls("HAZARDOUS AREA CLASSIFICATION SCHEDULE") == "document"
    assert _cls("RELAY SETTING SCHEDULE SUBSTATION 4-SAHIL CDS") == "document"


def test_plain_isometrics_stay_drawing():
    assert _cls("PIPING ISOMETRICS FOR SAHIL CDS") == "drawing"


def test_line_list_prefers_sheet():
    assert _cls("LINE LIST") == "sheet"


def test_low_confidence_sheet_type_prefers_sheet():
    assert normalize_doc_type("NULL", "LINE LIST")[1] == "prefer_sheet"


def test_low_confidence_nonsheet_stays_document():
    assert _cls("MISCELLANEOUS NOTE") == "document"


def test_genuine_documents_unchanged():
    assert _cls("CABLE SIZING CALCULATION") == "document"
    assert _cls("MATERIAL REQUISITION FOR CS & LTCS") == "document"
    assert _cls("SPECIFICATION FOR LV POWER, CONTROL") == "document"


def test_genuine_sheets_unchanged():
    assert _cls("VALVE LIST") == "sheet"
    assert _cls("MTO FOR PIPES AND FITTINGS") == "sheet"


from classifier.core.classify import classify_record
from classifier.core.record import Record


def _rec_cls(title):
    return classify_record(Record(title=title)).doc_type.value


def test_classify_record_end_to_end():
    assert _rec_cls("STANDARD DRAWING REBAR ARRANGEMENT") == "drawing"
    assert _rec_cls("INSTRUMENT INDEX") == "sheet"
    assert _rec_cls("LINE LIST") == "sheet"
    assert _rec_cls("PIPING & INSTRUMENT DIAGRAM") == "drawing"
    assert _rec_cls("CABLE SIZING CALCULATION") == "document"
    assert _rec_cls("VALVE LIST") == "sheet"
    assert _rec_cls("HAZARDOUS AREA CLASSIFICATION SCHEDULE") == "document"


# --- Hardening: LAYOUT is a drawing word and wins over the prose guard,
#     but PLAN is NOT a drawing word (HSE/EXECUTION PLANs are documents). ---

def test_layout_wins_over_prose_guard():
    # "HAZARDOUS AREA" prose phrase must NOT capture a layout DRAWING.
    assert _cls("HAZARDOUS AREA CLASSIFICATION LAYOUT - SAHIL CDS") == "drawing"
    assert _cls("HAZARDOUS AREA CLASSIFICATION LAYOUT  - SAHIL CDS (2 SHEETS)") == "drawing"


def test_hazardous_area_schedule_stays_document():
    # Same prose subject, but a SCHEDULE (no drawing word) is a document.
    assert _cls("HAZARDOUS AREA CLASSIFICATION SCHEDULE") == "document"


def test_site_layout_is_drawing_not_defaulted():
    assert _cls('SITE LAYOUT - 6" PROPOSED WATER DISPOSAL FLOW LINE FROM SAHIL') == "drawing"


def test_representative_layout_titles_are_drawing():
    for t in [
        "F&G DETECTORS LOCATION LAYOUT - SAHIL CDS",
        "ELECTRICAL EQUIPMENT LAYOUT -SUBSTATION NO. 4 SAHIL CDS",
        "PIPING LAYOUT FOR CDS AREA",
        "EARTHING LAYOUT PLANT AREA-2 - SAHIL CDS",
        "ESCAPE ROUTES LAYOUT",
    ]:
        assert _cls(t) == "drawing", t


def test_plan_is_not_a_drawing_word():
    # PLAN is ambiguous; HSE / management plans are documents (prose guard).
    assert _cls("HSE PLAN") == "document"
    assert _cls("DESIGN HSE PLAN") == "document"
    assert _cls("SITE HSE PLAN") == "document"


def test_prose_docs_unaffected_by_reorder():
    for t in [
        "HAZARD & EFFECT REGISTER",
        "HSE ACTION TRACKING REGISTER",
        "RELAY SETTING SCHEDULE SUBSTATION 4-SAHIL CDS",
        "SPECIALITY ITEMS LIST",
        "LIST OF ENGINEERING DELIVERABLES",
        "LIST OF PIPING SPECIALTY ITEMS",
    ]:
        assert _cls(t) == "document", t
