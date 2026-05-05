"""Build a route plan: ordered (source, destination) pairs, given match results."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier.routing.folders import CLASS_FOLDERS, UNMATCHED_FOLDER
from classifier.routing.matching import MatchResult
from classifier.routing.schedule_refs import safe_discipline, safe_title


@dataclass(frozen=True)
class RoutePlan:
    """List of (source path, destination path) pairs to execute."""
    operations: list[tuple[Path, Path]]


def build_plan(
    result: MatchResult,
    dest_dir: Path,
    include_title: bool = False,
    title_max_len: int = 100,
) -> RoutePlan:
    """Build (src, dst) pairs for matched + unmatched files.

    Layout under dest_dir is two-level **class / discipline / file**:

      Drawings/<DISCIPLINE>/...   matched, class==Drawings
      Documents/<DISCIPLINE>/...  matched, class==Documents
      Undefined/<DISCIPLINE>/...  matched, class==Undefined
      Unmatched/                  files with no cust_ref or ref not in schedule
                                  (no schedule discipline available - kept flat)

    Discipline values are sanitized via ``safe_discipline()`` so the path
    is filesystem-safe (e.g. 'ENGG QA/QC' -> 'ENGG_QA_QC'). Missing or
    empty discipline becomes '_UNKNOWN'.

    include_title: when True, the schedule's title is appended to the
    destination filename: '<original_stem> - <safe_title><ext>'. The
    title is sanitized for filesystem safety and truncated to
    title_max_len chars. Files with no title (Unmatched, or rows with
    blank Title) keep their original filename.
    """
    ops: list[tuple[Path, Path]] = []
    for fm in result.matched:
        disc = safe_discipline(fm.discipline)
        new_name = _name_with_title(fm.path, fm.title, include_title, title_max_len)
        ops.append((fm.path, dest_dir / fm.class_label / disc / new_name))
    for f in result.unmatched:
        ops.append((f, dest_dir / UNMATCHED_FOLDER / f.name))
    return RoutePlan(operations=ops)


def _name_with_title(src: Path, title: str, include_title: bool, max_len: int) -> str:
    """Compose the destination filename. Returns the original src.name
    when include_title is False or no title is available; otherwise
    '<stem> - <safe_title><ext>'.
    """
    if not include_title:
        return src.name
    safe = safe_title(title, max_len)
    if not safe:
        return src.name
    return f"{src.stem} - {safe}{src.suffix}"


def _class_folder_for(dst: Path) -> str:
    """Find which class folder (Drawings / Documents / Undefined / Unmatched)
    a destination path falls under. Walks the path parts and returns the
    first one that matches. Falls back to dst.parent.name.
    """
    for p in dst.parts:
        if p in CLASS_FOLDERS or p == UNMATCHED_FOLDER:
            return p
    return dst.parent.name
