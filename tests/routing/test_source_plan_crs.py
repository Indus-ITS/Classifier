from classifier.routing.source_plan import build_plan, DocRow


def test_crs_file_is_skipped(tmp_path):
    f = tmp_path / "CRS_16-01-55-2601 REV-B.xlsx"
    f.write_text("x")
    rows = [DocRow(customer_ref="16-01-55-2601", document_no="",
                   doc_source="deliverable", title="ELECTRICAL LOAD LIST")]
    plan = build_plan(rows, [f])
    assert plan.actions == ()
    assert "CRS_16-01-55-2601 REV-B.xlsx" in plan.skipped_crs


def test_cta_file_is_skipped(tmp_path):
    f = tmp_path / "CTA-ED-SA-15760 16-01-19-2602.pdf"
    f.write_text("x")
    rows = [DocRow(customer_ref="16-01-19-2602", document_no="",
                   doc_source="deliverable", title="VALVE LIST")]
    plan = build_plan(rows, [f])
    assert plan.actions == ()
    assert any(p.startswith("CTA") for p in plan.skipped_crs)
