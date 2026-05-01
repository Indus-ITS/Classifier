from helpers.classifier_lib import normalise_filename


def test_strip_whitespace():
    assert normalise_filename("   foo.pdf   ") == "foo.pdf"


def test_em_dash_becomes_ascii_hyphen():
    assert normalise_filename("16–01–19–2602.pdf") == "16-01-19-2602.pdf"


def test_en_dash_becomes_ascii_hyphen():
    assert normalise_filename("a–b.pdf") == "a-b.pdf"


def test_nbsp_becomes_space():
    assert normalise_filename("foo bar.pdf") == "foo bar.pdf"


def test_collapse_whitespace():
    assert normalise_filename("foo   bar.pdf") == "foo bar.pdf"


def test_nfkc_fullwidth_digit():
    assert normalise_filename("１.pdf") == "1.pdf"
