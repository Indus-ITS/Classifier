from classifier.core.classify import normalize_doc_type


def _cls(title):
    return normalize_doc_type("NULL", title)[0]


def test_known_prose_docs_classify_as_document():
    for title in [
        "HAZARD & EFFECT REGISTER",
        "HSE ACTION TRACKING REGISTER",
        "HAZARDOUS AREA CLASSIFICATION SCHEDULE",
        "LIST OF PIPING SPECIALTY ITEMS",
        "SPECIALITY ITEMS LIST",
        "RELAY SETTING SCHEDULE SUBSTATION 4-SAHIL CDS",
        "LIST OF ENGINEERING DELIVERABLES",
    ]:
        assert _cls(title) == "document", title


def test_genuine_sheets_stay_sheet():
    for title in [
        "VALVE LIST",
        "MTO FOR PIPES AND FITTINGS",
        "INSTRUMENT CABLE SCHEDULE",
        "TIE-IN LIST",
        "ELECTRICAL LOAD LIST - SAHIL CDS",
        "DCS I/O LIST",
    ]:
        assert _cls(title) == "sheet", title
