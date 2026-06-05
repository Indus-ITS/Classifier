from classifier.core.type_scoring import canonicalize_title, pick_type_with_overrides
from classifier.pipeline._row import normalize_doc_type


def test_sketches_depluralizes_to_sketch():
    assert "SKETCH" in canonicalize_title("PIPING TIE-IN SKETCHES (25 SHEETS)")


def test_plural_sketch_title_is_drawing_type():
    pick = pick_type_with_overrides("PIPING TIE-IN SKETCHES (25 SHEETS)")
    assert pick["type"] == "DWG"


def test_sketch_title_class_is_drawing_not_sheet():
    cls, _ = normalize_doc_type("Documents/Drawings", "PIPING TIE-IN SKETCHES (25 SHEETS)")
    assert cls == "drawing"
    cls2, _ = normalize_doc_type("NULL", "TIE-IN SKETCHES")
    assert cls2 == "drawing"
