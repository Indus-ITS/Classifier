from helpers.classifier_lib import extract_ref, is_crs_filename, is_cover_filename


# extract_ref
def test_extract_ref_clean():
    assert extract_ref("16-01-19-2602-A.pdf") == "16-01-19-2602"


def test_extract_ref_underscore_rev():
    assert extract_ref("16-01-19-2602_A.docx") == "16-01-19-2602"


def test_extract_ref_no_rev():
    assert extract_ref("16-01-08-2606.pdf") == "16-01-08-2606"


def test_extract_ref_with_freetext():
    assert extract_ref("16-99-91-2650-B Invoicing Procedure.docx") == "16-99-91-2650"


def test_extract_ref_in_crs():
    assert extract_ref("CRS-16-01-39-2602 REV-A.xlsx") == "16-01-39-2602"


def test_extract_ref_none():
    assert extract_ref("CAD Files.rar") is None


# is_crs_filename
def test_crs_dash_form():
    assert is_crs_filename("CRS-16-01-39-2602 REV-A.xlsx") is True


def test_crs_space_form():
    assert is_crs_filename("CRS 16-01-31-2604 REV-A.xlsx") is True


def test_crs_no_separator():
    assert is_crs_filename("CRS16-99-91-2650_A.xlsx") is True


def test_crs_sheet_form():
    assert is_crs_filename("CRSheet-16-01-33-2625 REV-B.xlsx") is True


def test_crs_comment_response():
    assert is_crs_filename("Comment Response Sheet-16-01-40-2607.xlsx") is True


def test_crs_copy_of_comment():
    assert is_crs_filename("Copy of Comment Response Sheet-16-01-40-2605.xlsx") is True


def test_crs_mid_string():
    assert is_crs_filename("16-01-12-2603-CRS_Specification.xlsx") is True


def test_crs_at_end():
    assert is_crs_filename("16-01-89-2607 CRS.xlsx") is True


def test_crs_negative():
    assert is_crs_filename("16-01-19-2602-A.pdf") is False


# is_cover_filename
def test_cover_cta():
    assert is_cover_filename("CTA-ED-SA-15760.01-008.pdf") is True


def test_cover_c_a_ed_sa():
    assert is_cover_filename("C-A-ED-SA-15760.01-0068.pdf") is True


def test_cover_negative():
    assert is_cover_filename("16-01-19-2602-A.pdf") is False


from helpers.classifier_lib import extract_letter_rev, extract_numeric_rev, extract_revs


# Letter
def test_letter_rev_dash():
    assert extract_letter_rev("16-01-19-2602-A.pdf", "16-01-19-2602") == "A"


def test_letter_rev_underscore():
    assert extract_letter_rev("16-01-19-2602_B.docx", "16-01-19-2602") == "B"


def test_letter_rev_space():
    assert extract_letter_rev("16-99-91-2650 C.docx", "16-99-91-2650") == "C"


def test_letter_rev_freetext_after():
    assert extract_letter_rev("16-99-91-2650-B Invoicing Procedure.docx", "16-99-91-2650") == "B"


def test_letter_rev_explicit_rev_word():
    assert extract_letter_rev("CRS-16-01-39-2602 REV-A.xlsx", "16-01-39-2602") == "A"


def test_letter_rev_revdot():
    assert extract_letter_rev("foo_Rev.A.pdf", "16-01-19-2602") == "A"


def test_letter_rev_ifa_form():
    assert extract_letter_rev("CRS-16-01-36-2602 IFA-D.xlsx", "16-01-36-2602") == "D"


def test_letter_rev_none():
    assert extract_letter_rev("16-01-19-2602.pdf", "16-01-19-2602") == ""


# Numeric
def test_numeric_rev_dash():
    assert extract_numeric_rev("16-01-08-2606-1.pdf", "16-01-08-2606") == "1"


def test_numeric_rev_underscore():
    assert extract_numeric_rev("16-01-08-2606_2.pdf", "16-01-08-2606") == "2"


def test_numeric_rev_two_digits():
    assert extract_numeric_rev("16-01-08-2606_12.pdf", "16-01-08-2606") == "12"


def test_numeric_rev_explicit():
    assert extract_numeric_rev("CRS-16-01-33-2611 REV-3.xlsx", "16-01-33-2611") == "3"


def test_numeric_rev_ifc_form():
    assert extract_numeric_rev("CRS-16-01-33-2616 - IFC-2.xlsx", "16-01-33-2616") == "2"


def test_numeric_rev_none():
    assert extract_numeric_rev("16-01-19-2602-A.pdf", "16-01-19-2602") == ""


# Combined
def test_extract_revs_both():
    assert extract_revs("16-01-19-2602-A REV-1.pdf", "16-01-19-2602") == ("A", "1")


def test_extract_revs_neither():
    assert extract_revs("16-01-19-2602.pdf", "16-01-19-2602") == ("", "")


from helpers.classifier_lib import inherit_rev_from_siblings


def test_inherit_picks_unique_sibling():
    target = {"filename": "CRS-16-01-39-2602.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "16-01-39-2602-A.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("A", "")


def test_inherit_picks_highest_among_matching_siblings():
    target = {"filename": "CRS.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "x-A.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
        {"filename": "x-B.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "B", "numeric_rev": ""},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("B", "")


def test_inherit_numeric_supersedes_letter():
    target = {"filename": "CRS.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "x-A.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
        {"filename": "x-1.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": "1"},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("", "1")


def test_inherit_no_matching_ref():
    target = {"filename": "CRS.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "y-A.pdf", "cust_ref": "16-01-99-9999",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("", "")


def test_inherit_only_when_target_has_neither_rev():
    target = {"filename": "x-A.pdf", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""}
    siblings = [
        {"filename": "y-B.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "B", "numeric_rev": ""},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("A", "")
