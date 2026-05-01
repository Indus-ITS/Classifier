"""Tests for helpers/router_lib.py - file matching, plan building, execution."""
from pathlib import Path

import pytest

from helpers.router_lib import (
    FileMatch,
    MatchResult,
    RoutePlan,
    build_plan,
    classify_title,
    clean_empty_dirs,
    execute_plan,
    find_collisions,
    match_files,
    plan_summary,
    plan_summary_by_class_discipline,
    resolve_duplicates,
    safe_discipline,
    safe_title,
)


# -----------------------------------------------------------------------
# classify_title
# -----------------------------------------------------------------------
def test_classify_title_drawings():
    assert classify_title("P&ID - Production Header") == "Drawings"


def test_classify_title_documents():
    assert classify_title("Process Basis Of Design - Sahil") == "Documents"


def test_classify_title_undefined_for_zero_score():
    """Title with no keyword hits returns Undefined, not Documents."""
    assert classify_title("Water Disposal Well SA 075 Sahil") == "Undefined"


# -----------------------------------------------------------------------
# match_files
# -----------------------------------------------------------------------
def _touch(d: Path, name: str) -> Path:
    p = d / name
    p.write_bytes(b"x")
    return p


def test_match_files_basic(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _touch(src, "16-01-19-2602.pdf")           # in schedule -> matched
    _touch(src, "no-ref-here.pdf")             # no cust_ref -> unmatched_unrecognized
    _touch(src, "99-99-99-9999.pdf")           # ref not in schedule -> unmatched_not_in_schedule

    refs = {
        "16-01-19-2602": ("VALVE LIST", "PIPNG"),       # -> Lists -> Documents class
        "16-01-19-2700": ("Roof Plan", "CIVIL"),        # in schedule, no file on disk
    }
    result = match_files(refs, src)

    assert len(result.matched) == 1
    fm = result.matched[0]
    assert fm.cust_ref == "16-01-19-2602"
    assert fm.title == "VALVE LIST"
    assert fm.class_label == "Documents"
    assert fm.discipline == "PIPNG"
    assert len(result.unmatched_unrecognized) == 1
    assert len(result.unmatched_not_in_schedule) == 1
    assert result.refs_without_files == ["16-01-19-2700"]


def test_match_files_skips_subdirectories(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Drawings").mkdir()  # pre-existing class folder must be skipped
    _touch(src / "Drawings", "16-01-19-2602.pdf")  # nested file, not picked up
    _touch(src, "16-01-19-2603.pdf")

    refs = {
        "16-01-19-2602": ("Roof Plan", "CIVIL"),
        "16-01-19-2603": ("Roof Plan", "CIVIL"),
    }
    result = match_files(refs, src)

    assert len(result.matched) == 1
    assert result.matched[0].cust_ref == "16-01-19-2603"


def test_match_files_handles_filename_with_extra_text(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _touch(src, "CTA-X-16-01-19-2602.pdf")
    _touch(src, "16-01-19-2602-A.docx")

    refs = {"16-01-19-2602": ("Roof Plan", "CIVIL")}
    result = match_files(refs, src)

    assert len(result.matched) == 2
    assert all(fm.cust_ref == "16-01-19-2602" for fm in result.matched)


def test_match_files_unmatched_property_combines_lists(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _touch(src, "no-ref-here.pdf")
    _touch(src, "99-99-99-9999.pdf")

    result = match_files({}, src)
    assert len(result.unmatched) == 2
    assert set(p.name for p in result.unmatched) == {"no-ref-here.pdf", "99-99-99-9999.pdf"}


# -----------------------------------------------------------------------
# Recursive scanning
# -----------------------------------------------------------------------
def test_match_files_recursive_finds_nested_files(tmp_path: Path):
    """recursive=True walks subdirectories; recursive=False does not."""
    src = tmp_path / "src"; src.mkdir()
    sub1 = src / "C-A-ED-SA-15760.01-0068"; sub1.mkdir()
    sub2 = src / "C-A-ED-SA-15760.01-0069"; sub2.mkdir()
    _touch(sub1, "16-01-19-2602.pdf")
    _touch(sub2, "16-01-19-2603.pdf")
    _touch(src, "16-01-19-2604.pdf")  # also at top level

    refs = {
        "16-01-19-2602": ("Roof Plan", "CIVIL"),
        "16-01-19-2603": ("Project Report", "PIPNG"),
        "16-01-19-2604": ("VALVE LIST", "PIPNG"),
    }

    # Default: top-level only finds 1
    top = match_files(refs, src, recursive=False)
    assert len(top.matched) == 1
    assert top.matched[0].cust_ref == "16-01-19-2604"

    # Recursive finds all 3
    rec = match_files(refs, src, recursive=True)
    assert len(rec.matched) == 3
    assert {fm.cust_ref for fm in rec.matched} == {
        "16-01-19-2602", "16-01-19-2603", "16-01-19-2604",
    }


def test_match_files_recursive_skips_existing_class_folders(tmp_path: Path):
    """Recursive re-runs must NOT re-route files already inside class
    folders (Drawings/Documents/Undefined/Unmatched), to keep in-place
    re-runs safe.
    """
    src = tmp_path / "src"; src.mkdir()
    sub = src / "raw"; sub.mkdir()
    drawings = src / "Drawings" / "CIVIL"; drawings.mkdir(parents=True)
    docs = src / "Documents" / "PIPNG"; docs.mkdir(parents=True)
    unmatched = src / "Unmatched"; unmatched.mkdir()
    _touch(sub, "16-01-19-2602.pdf")           # not yet sorted - should be picked up
    _touch(drawings, "16-01-19-2603.pdf")      # already in Drawings - skip
    _touch(docs, "16-01-19-2604.pdf")          # already in Documents - skip
    _touch(unmatched, "stranger.pdf")          # already in Unmatched - skip

    refs = {
        "16-01-19-2602": ("Roof Plan", "CIVIL"),
        "16-01-19-2603": ("Roof Plan", "CIVIL"),
        "16-01-19-2604": ("Project Report", "PIPNG"),
    }
    rec = match_files(refs, src, recursive=True)
    matched_names = [fm.path.name for fm in rec.matched]
    assert matched_names == ["16-01-19-2602.pdf"]
    assert all("Drawings" not in str(fm.path) for fm in rec.matched)
    assert all("Documents" not in str(fm.path) for fm in rec.matched)


# -----------------------------------------------------------------------
# clean_empty_dirs
# -----------------------------------------------------------------------
def test_clean_empty_dirs_removes_empty_subdirs(tmp_path: Path):
    (tmp_path / "empty1").mkdir()
    (tmp_path / "empty2" / "nested").mkdir(parents=True)
    (tmp_path / "non_empty").mkdir()
    _touch(tmp_path / "non_empty", "a.pdf")

    removed = clean_empty_dirs(tmp_path)

    assert removed == 3   # empty1, empty2/nested, empty2 (after nested goes)
    assert not (tmp_path / "empty1").exists()
    assert not (tmp_path / "empty2").exists()
    assert (tmp_path / "non_empty").exists()
    # The root is never deleted
    assert tmp_path.exists()


def test_clean_empty_dirs_handles_missing_root(tmp_path: Path):
    assert clean_empty_dirs(tmp_path / "does-not-exist") == 0


# -----------------------------------------------------------------------
# resolve_duplicates
# -----------------------------------------------------------------------
def test_resolve_duplicates_error_strategy_is_passthrough(tmp_path: Path):
    src1 = _touch(tmp_path, "a.pdf")
    src2 = _touch(tmp_path, "b.pdf")
    dst = tmp_path / "dest" / "Drawings" / "CIVIL" / "x.pdf"
    plan = RoutePlan(operations=[(src1, dst), (src2, dst)])
    out, dropped, renamed = resolve_duplicates(plan, "error")
    assert out == plan
    assert dropped == 0
    assert renamed == 0


def test_resolve_duplicates_skip_keeps_first_drops_rest(tmp_path: Path):
    src1 = _touch(tmp_path, "a.pdf")
    src2 = _touch(tmp_path, "b.pdf")
    src3 = _touch(tmp_path, "c.pdf")
    dst = tmp_path / "dest" / "Drawings" / "CIVIL" / "x.pdf"
    plan = RoutePlan(operations=[(src1, dst), (src2, dst), (src3, dst)])
    out, dropped, renamed = resolve_duplicates(plan, "skip")
    assert len(out.operations) == 1
    assert out.operations[0] == (src1, dst)
    assert dropped == 2
    assert renamed == 0


def test_resolve_duplicates_rename_appends_numeric_suffix(tmp_path: Path):
    src1 = _touch(tmp_path, "a.pdf")
    src2 = _touch(tmp_path, "b.pdf")
    src3 = _touch(tmp_path, "c.pdf")
    dst = tmp_path / "dest" / "Drawings" / "CIVIL" / "x.pdf"
    plan = RoutePlan(operations=[(src1, dst), (src2, dst), (src3, dst)])
    out, dropped, renamed = resolve_duplicates(plan, "rename")
    dsts = [op[1] for op in out.operations]
    assert dsts[0] == dst
    assert dsts[1] == tmp_path / "dest" / "Drawings" / "CIVIL" / "x-2.pdf"
    assert dsts[2] == tmp_path / "dest" / "Drawings" / "CIVIL" / "x-3.pdf"
    assert dropped == 0
    assert renamed == 2


def test_resolve_duplicates_skip_treats_existing_disk_file_as_collision(tmp_path: Path):
    src = _touch(tmp_path, "a.pdf")
    dst_dir = tmp_path / "dest" / "Drawings" / "CIVIL"
    dst_dir.mkdir(parents=True)
    dst = dst_dir / "x.pdf"
    dst.write_bytes(b"existing")  # already on disk
    plan = RoutePlan(operations=[(src, dst)])
    out, dropped, renamed = resolve_duplicates(plan, "skip")
    assert len(out.operations) == 0
    assert dropped == 1


def test_resolve_duplicates_rename_avoids_existing_disk_file(tmp_path: Path):
    src = _touch(tmp_path, "a.pdf")
    dst_dir = tmp_path / "dest" / "Drawings" / "CIVIL"
    dst_dir.mkdir(parents=True)
    dst = dst_dir / "x.pdf"
    dst.write_bytes(b"existing")
    plan = RoutePlan(operations=[(src, dst)])
    out, dropped, renamed = resolve_duplicates(plan, "rename")
    assert out.operations[0][1] == dst_dir / "x-2.pdf"
    assert renamed == 1


def test_resolve_duplicates_passes_through_inplace_no_op(tmp_path: Path):
    """A no-op (src == dst, in-place re-run) is preserved as-is regardless
    of strategy."""
    f = _touch(tmp_path, "a.pdf")
    plan = RoutePlan(operations=[(f, f)])
    out, dropped, renamed = resolve_duplicates(plan, "skip")
    assert len(out.operations) == 1
    assert dropped == 0


def test_resolve_duplicates_rejects_invalid_strategy(tmp_path: Path):
    plan = RoutePlan(operations=[])
    with pytest.raises(ValueError, match="on_duplicate must be"):
        resolve_duplicates(plan, "merge")


# -----------------------------------------------------------------------
# build_plan + plan_summary
# -----------------------------------------------------------------------
def test_build_plan_routes_each_class_and_discipline(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    f1 = _touch(src, "drawing1.pdf")
    f2 = _touch(src, "doc1.pdf")
    f3 = _touch(src, "undef1.pdf")
    f4 = _touch(src, "qaqc.pdf")
    unmatched = _touch(src, "unmatched1.pdf")

    result = MatchResult(
        matched=[
            FileMatch(f1, "16-01-19-2602", "Roof Plan", "Drawings", "CIVIL"),
            FileMatch(f2, "16-01-19-2603", "Project Report", "Documents", "PIPNG"),
            FileMatch(f3, "16-01-19-2604", "Generic Item", "Undefined", "INST"),
            FileMatch(f4, "16-01-19-2605", "ITP Plan", "Documents", "ENGG QA/QC"),
        ],
        unmatched_unrecognized=[unmatched],
        unmatched_not_in_schedule=[],
        refs_without_files=[],
    )
    dest = tmp_path / "dest"
    plan = build_plan(result, dest)

    by_dst = {dst.name: dst for _, dst in plan.operations}
    assert by_dst["drawing1.pdf"] == dest / "Drawings" / "CIVIL" / "drawing1.pdf"
    assert by_dst["doc1.pdf"] == dest / "Documents" / "PIPNG" / "doc1.pdf"
    assert by_dst["undef1.pdf"] == dest / "Undefined" / "INST" / "undef1.pdf"
    # 'ENGG QA/QC' is sanitized to 'ENGG_QA_QC' (slashes are path separators)
    assert by_dst["qaqc.pdf"] == dest / "Documents" / "ENGG_QA_QC" / "qaqc.pdf"
    # Unmatched is kept flat (no schedule discipline available)
    assert by_dst["unmatched1.pdf"] == dest / "Unmatched" / "unmatched1.pdf"


def test_build_plan_routes_unknown_discipline_to_unknown_folder(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    f = _touch(src, "x.pdf")
    result = MatchResult(
        matched=[FileMatch(f, "16-01-19-2602", "Roof Plan", "Drawings", "")],
        unmatched_unrecognized=[],
        unmatched_not_in_schedule=[],
        refs_without_files=[],
    )
    plan = build_plan(result, tmp_path / "dest")
    assert plan.operations[0][1] == tmp_path / "dest" / "Drawings" / "_UNKNOWN" / "x.pdf"


def test_plan_summary_counts_per_class_folder(tmp_path: Path):
    plan = RoutePlan(operations=[
        (tmp_path / "a.pdf", tmp_path / "dest" / "Drawings" / "CIVIL" / "a.pdf"),
        (tmp_path / "b.pdf", tmp_path / "dest" / "Drawings" / "PIPNG" / "b.pdf"),
        (tmp_path / "c.pdf", tmp_path / "dest" / "Documents" / "PIPNG" / "c.pdf"),
        (tmp_path / "d.pdf", tmp_path / "dest" / "Unmatched" / "d.pdf"),
    ])
    counts = plan_summary(plan)
    assert counts == {"Drawings": 2, "Documents": 1, "Unmatched": 1}


def test_plan_summary_by_class_discipline(tmp_path: Path):
    plan = RoutePlan(operations=[
        (tmp_path / "a.pdf", tmp_path / "dest" / "Drawings" / "CIVIL" / "a.pdf"),
        (tmp_path / "b.pdf", tmp_path / "dest" / "Drawings" / "CIVIL" / "b.pdf"),
        (tmp_path / "c.pdf", tmp_path / "dest" / "Drawings" / "PIPNG" / "c.pdf"),
        (tmp_path / "d.pdf", tmp_path / "dest" / "Documents" / "INST" / "d.pdf"),
        (tmp_path / "e.pdf", tmp_path / "dest" / "Unmatched" / "e.pdf"),
    ])
    grid = plan_summary_by_class_discipline(plan)
    assert grid == {
        "Drawings": {"CIVIL": 2, "PIPNG": 1},
        "Documents": {"INST": 1},
        "Unmatched": {"-": 1},
    }


# -----------------------------------------------------------------------
# safe_discipline
# -----------------------------------------------------------------------
def test_safe_discipline_uppercases_alnum():
    assert safe_discipline("CIVIL") == "CIVIL"
    assert safe_discipline("civil") == "CIVIL"


def test_safe_discipline_replaces_path_unsafe_chars():
    assert safe_discipline("ENGG QA/QC") == "ENGG_QA_QC"
    assert safe_discipline("ENGG HSE") == "ENGG_HSE"
    assert safe_discipline("PACKAGE EQUIP") == "PACKAGE_EQUIP"


def test_safe_discipline_collapses_underscores():
    assert safe_discipline("A   B") == "A_B"
    assert safe_discipline("A//B") == "A_B"


def test_safe_discipline_strips_leading_trailing():
    assert safe_discipline("  CIVIL  ") == "CIVIL"
    assert safe_discipline("/CIVIL/") == "CIVIL"


def test_safe_discipline_empty_returns_unknown():
    assert safe_discipline("") == "_UNKNOWN"
    assert safe_discipline("   ") == "_UNKNOWN"
    assert safe_discipline("///") == "_UNKNOWN"


# -----------------------------------------------------------------------
# safe_title
# -----------------------------------------------------------------------
def test_safe_title_simple():
    assert safe_title("VALVE LIST") == "VALVE LIST"


def test_safe_title_replaces_path_unsafe_chars():
    assert safe_title("MTO FOR PIPES & FITTINGS / SAHIL") == "MTO FOR PIPES & FITTINGS _ SAHIL"
    assert safe_title('Title: "Quoted"') == "Title_ _Quoted_"
    assert safe_title("a*b?c|d<e>f") == "a_b_c_d_e_f"


def test_safe_title_collapses_whitespace():
    assert safe_title("A    B\tC\nD") == "A B C D"


def test_safe_title_strips_leading_trailing():
    assert safe_title("   VALVE LIST   ") == "VALVE LIST"


def test_safe_title_strips_trailing_dots_and_spaces():
    """Windows refuses filenames ending with dots or spaces."""
    assert safe_title("Title with trailing dots...") == "Title with trailing dots"
    assert safe_title("Title with trailing space ") == "Title with trailing space"


def test_safe_title_truncates_to_max_len():
    long = "A" * 200
    assert len(safe_title(long, max_len=100)) == 100
    assert safe_title(long, max_len=100) == "A" * 100


def test_safe_title_truncate_re_strips_trailing_space():
    """If truncation lands on a space, strip it so the filename doesn't
    end with a space."""
    s = "X" * 95 + " word that gets cut"
    assert not safe_title(s, max_len=98).endswith(" ")


def test_safe_title_empty_returns_empty():
    assert safe_title("") == ""
    assert safe_title("   ") == ""


# -----------------------------------------------------------------------
# build_plan with include_title
# -----------------------------------------------------------------------
def test_build_plan_include_title_appends_safe_title(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    f1 = _touch(src, "16-01-19-2602-B.pdf")
    f2 = _touch(src, "16-01-19-2603.pdf")
    result = MatchResult(
        matched=[
            FileMatch(f1, "16-01-19-2602", "VALVE LIST", "Documents", "PIPNG"),
            FileMatch(f2, "16-01-19-2603", "MTO FOR PIPES & FITTINGS", "Documents", "PIPNG"),
        ],
        unmatched_unrecognized=[],
        unmatched_not_in_schedule=[],
        refs_without_files=[],
    )
    plan = build_plan(result, tmp_path / "dest", include_title=True)
    dsts = sorted(op[1].name for op in plan.operations)
    assert dsts == [
        "16-01-19-2602-B - VALVE LIST.pdf",
        "16-01-19-2603 - MTO FOR PIPES & FITTINGS.pdf",
    ]


def test_build_plan_include_title_false_keeps_original_name(tmp_path: Path):
    """Default (include_title=False) is unchanged - backward compat."""
    src = tmp_path / "src"; src.mkdir()
    f = _touch(src, "16-01-19-2602.pdf")
    result = MatchResult(
        matched=[FileMatch(f, "16-01-19-2602", "VALVE LIST", "Documents", "PIPNG")],
        unmatched_unrecognized=[],
        unmatched_not_in_schedule=[],
        refs_without_files=[],
    )
    plan = build_plan(result, tmp_path / "dest")
    assert plan.operations[0][1].name == "16-01-19-2602.pdf"


def test_build_plan_include_title_unmatched_keeps_original_name(tmp_path: Path):
    """Unmatched files have no title - original name regardless of flag."""
    src = tmp_path / "src"; src.mkdir()
    f = _touch(src, "weird_name.pdf")
    result = MatchResult(
        matched=[],
        unmatched_unrecognized=[f],
        unmatched_not_in_schedule=[],
        refs_without_files=[],
    )
    plan = build_plan(result, tmp_path / "dest", include_title=True)
    assert plan.operations[0][1].name == "weird_name.pdf"


def test_build_plan_include_title_with_unsafe_chars(tmp_path: Path):
    """Title with path-unsafe chars gets sanitized before joining."""
    src = tmp_path / "src"; src.mkdir()
    f = _touch(src, "16-01-19-2602.pdf")
    result = MatchResult(
        matched=[FileMatch(f, "16-01-19-2602", 'Bad "Title" / Has* Bad? Chars', "Documents", "PIPNG")],
        unmatched_unrecognized=[],
        unmatched_not_in_schedule=[],
        refs_without_files=[],
    )
    plan = build_plan(result, tmp_path / "dest", include_title=True)
    name = plan.operations[0][1].name
    # Sanitized: " < > : " / \ | ? * become _
    assert ":" not in name
    assert '"' not in name
    assert "/" not in name
    assert "*" not in name
    assert "?" not in name
    assert name.endswith(".pdf")
    assert name.startswith("16-01-19-2602 - ")


def test_build_plan_include_title_respects_max_len(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    f = _touch(src, "16-01-19-2602.pdf")
    long_title = "A" * 200
    result = MatchResult(
        matched=[FileMatch(f, "16-01-19-2602", long_title, "Documents", "PIPNG")],
        unmatched_unrecognized=[],
        unmatched_not_in_schedule=[],
        refs_without_files=[],
    )
    plan = build_plan(result, tmp_path / "dest", include_title=True, title_max_len=20)
    name = plan.operations[0][1].name
    assert name == f"16-01-19-2602 - {'A' * 20}.pdf"


# -----------------------------------------------------------------------
# find_collisions
# -----------------------------------------------------------------------
def test_find_collisions_detects_existing_dest(tmp_path: Path):
    src = _touch(tmp_path, "a.pdf")
    dst = tmp_path / "Drawings" / "a.pdf"
    dst.parent.mkdir()
    dst.write_bytes(b"existing")
    plan = RoutePlan(operations=[(src, dst)])
    assert find_collisions(plan) == [dst]


def test_find_collisions_detects_duplicate_destinations(tmp_path: Path):
    """Two source files routed to the same destination is a collision."""
    src1 = _touch(tmp_path, "a.pdf")
    src2 = _touch(tmp_path, "a_copy.pdf")
    dst = tmp_path / "Drawings" / "a.pdf"
    plan = RoutePlan(operations=[(src1, dst), (src2, dst)])
    assert find_collisions(plan) == [dst]


def test_find_collisions_skips_inplace_no_op(tmp_path: Path):
    """A file already at its destination (in-place re-run) is not a collision."""
    f = _touch(tmp_path, "a.pdf")
    plan = RoutePlan(operations=[(f, f)])
    assert find_collisions(plan) == []


# -----------------------------------------------------------------------
# execute_plan
# -----------------------------------------------------------------------
def test_execute_plan_copy_keeps_source(tmp_path: Path):
    src = _touch(tmp_path, "a.pdf")
    dst = tmp_path / "Drawings" / "a.pdf"
    plan = RoutePlan(operations=[(src, dst)])

    counts = execute_plan(plan, mode="copy")

    assert src.exists()
    assert dst.exists()
    assert counts == {"Drawings": 1}


def test_execute_plan_move_removes_source(tmp_path: Path):
    src = _touch(tmp_path, "a.pdf")
    dst = tmp_path / "Documents" / "a.pdf"
    plan = RoutePlan(operations=[(src, dst)])

    counts = execute_plan(plan, mode="move")

    assert not src.exists()
    assert dst.exists()
    assert counts == {"Documents": 1}


def test_execute_plan_invokes_progress_callback(tmp_path: Path):
    f1 = _touch(tmp_path, "a.pdf")
    f2 = _touch(tmp_path, "b.pdf")
    plan = RoutePlan(operations=[
        (f1, tmp_path / "Drawings" / "a.pdf"),
        (f2, tmp_path / "Drawings" / "b.pdf"),
    ])
    seen: list[tuple[int, int]] = []
    execute_plan(plan, mode="copy", on_progress=lambda done, total, src: seen.append((done, total)))
    assert seen == [(1, 2), (2, 2)]


def test_execute_plan_rejects_invalid_mode(tmp_path: Path):
    plan = RoutePlan(operations=[])
    with pytest.raises(ValueError, match="mode must be"):
        execute_plan(plan, mode="symlink")


def test_execute_plan_creates_missing_destination_dirs(tmp_path: Path):
    src = _touch(tmp_path, "a.pdf")
    dst = tmp_path / "deep" / "nested" / "path" / "Drawings" / "a.pdf"
    plan = RoutePlan(operations=[(src, dst)])
    execute_plan(plan, mode="copy")
    assert dst.exists()
