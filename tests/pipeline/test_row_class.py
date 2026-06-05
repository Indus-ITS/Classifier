from classifier.pipeline._row import normalize_doc_type


def test_list_title_classifies_as_sheet():
    cls, reason = normalize_doc_type("NULL", "VALVE LIST")
    assert cls == "sheet"


def test_mto_title_classifies_as_sheet():
    cls, _ = normalize_doc_type("Documents/Drawings", "MTO FOR PIPES AND FITTINGS")
    assert cls == "sheet"


def test_pid_title_still_drawing():
    cls, _ = normalize_doc_type("NULL", "PIPING AND INSTRUMENT DIAGRAM")
    assert cls == "drawing"


def test_spec_title_still_document():
    cls, _ = normalize_doc_type("NULL", "SPECIFICATION FOR PIPING MATERIAL")
    assert cls == "document"


def test_existing_sheet_value_preserved():
    cls, reason = normalize_doc_type("sheet", "ANYTHING AT ALL")
    assert cls == "sheet"
    assert reason == "existing"
