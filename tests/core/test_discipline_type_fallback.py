from classifier.core.classify import fill_discipline


def test_pure_type_rescues_blank_title():
    # title scores no discipline; PID is a pure type -> Process (11)
    assert fill_discipline("", "ZZZ NONSENSE", type_hint="PID") == ("11", "via_type")


def test_pure_type_rescues_when_keyword_low():
    # garbage title, DSL pure type -> Electrical (3)
    assert fill_discipline("", "QWERTY", type_hint="DSL") == ("3", "via_type")


def test_ambiguous_type_does_not_rescue():
    assert fill_discipline("", "ZZZ NONSENSE", type_hint="DAS") == ("", "miss")


def test_no_type_still_misses():
    assert fill_discipline("", "ZZZ NONSENSE")[1] == "miss"


def test_keyword_high_beats_type_fallback():
    # title clearly Electrical via keywords; even with a Process type hint,
    # the high-confidence keyword discipline (3) wins and reason is via_keyword.
    val, reason = fill_discipline("", "SINGLE LINE DIAGRAM SUBSTATION", type_hint="PID")
    assert val == "3" and reason == "via_keyword"


def test_existing_discipline_preserved():
    assert fill_discipline("8", "anything", type_hint="PID") == ("8", "preserved")


def test_type_hint_does_not_demote_high_keyword_discipline():
    # Civil title scores "high" on its own; a PID type code must not erode its
    # margin and flip it to the type's discipline (Process). Regression for the
    # +2 bonus / via_type fallback double-counting bug.
    assert fill_discipline(
        "", "CIVIL GENERAL ARRANGEMENT LAYOUT", type_hint="PID"
    ) == ("1", "via_keyword")
