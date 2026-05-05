"""Match files in a source directory to schedule rows by cust_ref."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from classifier.config.buckets import BUCKET_TO_CLASS
from classifier.core.extraction import extract_ref
from classifier.core.scoring import fold_to_class, pick_bucket, score_buckets
from classifier.routing.folders import _CLASS_DIR_NAMES


@dataclass(frozen=True)
class FileMatch:
    """A source file that matched a schedule row, with its predicted class
    and the discipline as recorded in the schedule.
    """
    path: Path
    cust_ref: str
    title: str
    class_label: str   # 'Drawings' | 'Documents' | 'Undefined'
    discipline: str    # raw schedule discipline (e.g. 'CIVIL', 'ENGG QA/QC')


@dataclass
class MatchResult:
    matched: list[FileMatch]
    unmatched_unrecognized: list[Path]   # filename has no recognizable cust_ref
    unmatched_not_in_schedule: list[Path]  # cust_ref present but not in schedule
    refs_without_files: list[str]         # schedule rows with no file on disk

    @property
    def unmatched(self) -> list[Path]:
        return self.unmatched_unrecognized + self.unmatched_not_in_schedule


def classify_title(title: str) -> str:
    """Run the bucket classifier and return the user-facing class label
    (Drawings / Documents / Undefined). Uses the same code path as
    classify (cli) and evaluate (tools).
    """
    pick = pick_bucket(score_buckets(title, ""))
    return fold_to_class(pick, BUCKET_TO_CLASS)


def _iter_source_files(source_dir: Path) -> list[Path]:
    """Yield files under source_dir recursively. Files already inside a
    class folder (Drawings/Documents/Undefined/Unmatched) are skipped so
    re-runs are safe.
    """
    out: list[Path] = []
    for f in source_dir.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(source_dir)
        except ValueError:
            continue
        if any(part in _CLASS_DIR_NAMES for part in rel.parts[:-1]):
            continue
        out.append(f)
    return sorted(out)


def match_files(
    schedule_refs: dict[str, tuple[str, str]],
    source_dir: Path,
    files: list[Path] | None = None,
) -> MatchResult:
    """Match files against the schedule by cust_ref.

    If ``files`` is provided, match those exact paths (used after dedup).
    Otherwise walk ``source_dir`` recursively, skipping class folders.
    """
    if not source_dir.is_dir():
        raise ValueError(f"source_dir is not a directory: {source_dir}")

    matched: list[FileMatch] = []
    unmatched_unrecognized: list[Path] = []
    unmatched_not_in_schedule: list[Path] = []
    refs_seen: set[str] = set()

    iter_files = files if files is not None else _iter_source_files(source_dir)
    for f in iter_files:
        ref = extract_ref(f.name)
        if not ref:
            unmatched_unrecognized.append(f)
            continue
        if ref not in schedule_refs:
            unmatched_not_in_schedule.append(f)
            continue
        title, discipline = schedule_refs[ref]
        matched.append(FileMatch(
            path=f,
            cust_ref=ref,
            title=title,
            class_label=classify_title(title),
            discipline=discipline,
        ))
        refs_seen.add(ref)

    refs_without_files = sorted(set(schedule_refs.keys()) - refs_seen)
    return MatchResult(
        matched=matched,
        unmatched_unrecognized=unmatched_unrecognized,
        unmatched_not_in_schedule=unmatched_not_in_schedule,
        refs_without_files=refs_without_files,
    )
