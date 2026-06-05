from classifier.routing.cust_ref import extract_cust_ref, parse_group_and_revision


def test_extract_present_and_absent():
    assert extract_cust_ref("16-01-39-2602-B") == "16-01-39-2602"
    assert extract_cust_ref("CRS 16-99-90-2601-B") == "16-99-90-2601"
    assert extract_cust_ref("random_file_name") is None


def test_group_and_revision_with_cust_ref():
    assert parse_group_and_revision("16-01-39-2602-B") == ("16-01-39-2602", "B")
    assert parse_group_and_revision("16-01-27-2604_Rev.A") == ("16-01-27-2604", "A")
    assert parse_group_and_revision("16-99-90-2601-1") == ("16-99-90-2601", "1")
    # cust_ref with no revision tail keeps the whole (lowercased) stem as key
    assert parse_group_and_revision("16-01-19-2602") == ("16-01-19-2602", None)
    # prefix is preserved in the group key, lowercased
    gk, rev = parse_group_and_revision("CRS 16-99-90-2601-B")
    assert gk == "crs 16-99-90-2601" and rev == "B"
    # extra descriptive tail after the revision is dropped
    gk, rev = parse_group_and_revision("16-01-52-2609_B-MR for MPFM")
    assert gk == "16-01-52-2609" and rev == "B"


def test_group_and_revision_without_cust_ref():
    assert parse_group_and_revision("design note rev B") == ("design note", "B")
    assert parse_group_and_revision("plainfile") == ("plainfile", None)
