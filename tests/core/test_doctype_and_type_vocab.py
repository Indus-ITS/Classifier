"""Real-world document-number title vocabulary + the doc_type override policy.

Driven by the test/document_202606140012.csv snapshot, whose rows arrive with a
generic doc_type="document" default and ADNOC/AGES-style titles.
"""
import pytest
from classifier.core.classify import normalize_doc_type, fill_type
from classifier.core.record import Record
from classifier.core.classify import classify_record


# --- type vocabulary (HARD_OVERRIDES) ---------------------------------------
@pytest.mark.parametrize("title, expected_type", [
    ("AC1A3B-FA_Valve DS.pdf", "DAS"),                         # DS -> data sheet
    ("AD-16.0-M-42810 - GADs Construction", "DGA"),            # GADs -> GA drawing
    ("App 3.2 PMS Panel-4 GA & Wiring Diagram", "DWG"),        # wiring diagram
    ("AD41-16.0-I-61943 - Instrument Loop Diagram", "DWG"),    # loop diagram
    ("Protection and Metering Diagram 415V", "DWG"),
    ("App 3.1 Existing PMS Arch Diagram", "DBD"),              # arch diagram
    ("AD41-16.0-I-50117 - Instrument Cable Routing", "DAL"),
    ("Trench and Duct Bank Sectional Details", "DDT"),
    ("C0366-Civil BOQ-Rev.2", "MTO"),                          # bill of quantities
    ("AGES-SP-01-001 Rev.1-June 2020-CONCRETE", "SPC"),        # AGES spec series
    ("Instruction to Bidders_A", "ITB"),
    ("ADNOC Corporate Risk Matrix", "REG"),
    ("Energy Monitoring and Reporting Plan", "PLN"),
    ("constructability Review worksheet", "STD"),       # worksheet -> standard
    ("AD200-16.0-E-40885_IFD (SS-N LV SLD Mod)", "DSL"),  # SLD recovered from parens
])
def test_type_vocabulary(title, expected_type):
    assert fill_type("", title)[0] == expected_type


def test_meaningful_parens_kept_noise_parens_stripped():
    from classifier.core.scoring import canonicalize_title
    # noise parens dropped
    assert "REV" not in canonicalize_title("Foo Bar (Rev Rev-2)")
    assert canonicalize_title("Foo (11 SHEETS)") == ["FOO"]
    assert "NEW" not in canonicalize_title("Utility Flow Diagram (NEW) LP")
    # meaningful parens unwrapped and kept
    assert "SLD" in canonicalize_title("AD200-E-40885 (SS-N LV SLD Mod)")
    assert "SWBD" in canonicalize_title("App 2.1 (Existing 415V Swbd SS-N Details)")


# --- doc_type override of a generic "document" ------------------------------
@pytest.mark.parametrize("title, expected_class", [
    ("AD41-16.0-I-61943 - Instrument Loop Diagram", "drawing"),  # via DIAGRAM marker
    ("Single Line Diagram 415V Switchgear", "drawing"),
    ("Trench and Duct Bank Sectional Details", "drawing"),       # DDT
    ("AD-16.0-M-42810 - GADs Construction", "drawing"),          # DGA
    ("Electrical Cable Schedule", "sheet"),                      # SCH -> sheet
    ("DCS I/O List", "sheet"),                                   # LST -> sheet
    ("Instrument Index", "sheet"),                               # INDEX marker
    ("C0366-Civil BOQ-Rev.2", "sheet"),                         # MTO -> sheet
])
def test_document_overridden_by_confident_drawing_or_sheet(title, expected_class):
    # arrives as a generic "document"; confident detection wins
    assert normalize_doc_type("document", title)[0] == expected_class


def test_explicit_drawing_sheet_preserved():
    assert normalize_doc_type("drawing", "Some Report") == ("drawing", "existing")
    assert normalize_doc_type("sheet", "Some Diagram") == ("sheet", "existing")


def test_document_kept_when_no_confident_signal():
    # a genuine document with no drawing/sheet signal stays a document
    assert normalize_doc_type("document", "Operation and control philosophy") == (
        "document", "existing")
    assert normalize_doc_type("document", "ZZZ NONSENSE")[0] == "document"


def test_datasheet_and_spec_remain_documents():
    # DAS/SPC fold to the Documents class even though they are clearly typed
    assert normalize_doc_type("document", "Data Sheet for 415V Switchgear")[0] == "document"
    assert normalize_doc_type("document", "AGES-SP-01-002 Rev.1-STEEL")[0] == "document"


def test_vendor_scheme_is_drawing_bare_scheme_is_not():
    assert normalize_doc_type("document", "App-1.2 Vendor Scheme Motor Feeder")[0] == "drawing"
    # bare SCHEME is not a drawing marker (prose schemes stay documents)
    assert normalize_doc_type("document", "Document Numbering Scheme")[0] == "document"


def test_isometric_singular_is_drawing():
    assert normalize_doc_type("document", "Piping Isometric SH-01")[0] == "drawing"


def test_full_record_loop_diagram_is_drawing():
    res = classify_record(Record(
        title="AD41-16.0-I-61943 - Instrument Loop Diagram", doc_type="document"))
    assert res.doc_type.value == "drawing"
    assert res.type.value == "DWG"
