"""MODEL INDEX DRAWING titles are CAD drawings (.dwg), not tabular
indexes. The IDX type must be suppressed when the title also names a
DRAWING, so these route to the Drawings class -- while a plain
INSTRUMENT INDEX (no DRAWING) stays a Sheet.
"""
from classifier.core.type_scoring import pick_type_with_overrides
from classifier.pipeline._row import normalize_doc_type


def test_model_index_drawing_is_drawing_class():
    cls, _ = normalize_doc_type(
        "NULL", "3D MODEL DESIGN AREA/MODEL INDEX DRAWING AREA-2 SAHIL CDS")
    assert cls == "drawing"


def test_index_with_drawing_token_not_idx():
    pick = pick_type_with_overrides(
        "3D MODEL DESIGN AREA/MODEL INDEX DRAWING AREA-2 SAHIL CDS")
    assert pick["type"] != "IDX"


def test_instrument_index_without_drawing_not_routed_to_drawing():
    # The DRAWING guard must not catch a plain index (no DRAWING token);
    # its class is unchanged by this guard.
    cls, _ = normalize_doc_type("NULL", "INSTRUMENT INDEX - SAHIL CDS")
    assert cls != "drawing"
