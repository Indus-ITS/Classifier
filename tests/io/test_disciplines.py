from classifier.io.disciplines import load_valid_discipline_ids


def test_loads_new_table_ids():
    ids = load_valid_discipline_ids()
    # new table has these; and NOT the removed provisional ids
    assert {1, 3, 6, 7, 8, 11, 13, 39}.issubset(ids)
    assert 17 not in ids and 25 not in ids and 26 not in ids


def test_config_ids_are_all_valid():
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS
    from classifier.config.type_to_discipline import TYPE_TO_DISCIPLINE
    ids = load_valid_discipline_ids()
    assert set(DISCIPLINE_KEYWORDS).issubset(ids)
    assert set(TYPE_TO_DISCIPLINE.values()).issubset(ids)
