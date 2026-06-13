from classifier.config.type_to_discipline import TYPE_TO_DISCIPLINE
from classifier.io.disciplines import load_valid_discipline_ids


def test_pure_type_mappings_canonical_ids():
    assert TYPE_TO_DISCIPLINE == {
        "PID": 11, "PFD": 11, "MSD": 11, "PSF": 11,
        "DSL": 3, "DSD": 3,
        "DGA": 8,
    }


def test_values_are_valid_discipline_ids():
    valid = load_valid_discipline_ids()
    assert set(TYPE_TO_DISCIPLINE.values()).issubset(valid)


def test_ambiguous_types_absent():
    for t in ("DAS", "REP", "SPC", "LST", "DAL", "CAL", "DWG", "REQ", "SCH"):
        assert t not in TYPE_TO_DISCIPLINE
