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


def _iter_source_files(source_dir: Path, recursive: bool) -> list[Path]:
    """Yield files under source_dir.

    - recursive=False: top-level only (skips subdirs).
    - recursive=True: walks all subdirs but skips any file whose path
      passes through a class folder (Drawings/Documents/Undefined/
      Unmatched). This makes recursive in-place re-runs safe: files
      already sorted into class folders are not re-processed.
    """
    if recursive:
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
    return sorted(f for f in source_dir.iterdir() if f.is_file())


def match_files(
    schedule_refs: dict[str, tuple[str, str]],
    source_dir: Path,
    recursive: bool = False,
) -> MatchResult:
    """For every file in source_dir, extract the cust_ref from the filename
    and look it up in schedule_refs. Files where no cust_ref is
    recognizable, or the cust_ref isn't in the schedule, end up in the
    unmatched lists.

    recursive: if True, walks subdirectories. Files already inside
    class folders (Drawings/Documents/Undefined/Unmatched) are skipped
    so recursive re-runs don't re-route already-sorted files.
    """
    if not source_dir.is_dir():
        raise ValueError(f"source_dir is not a directory: {source_dir}")

    matched: list[FileMatch] = []
    unmatched_unrecognized: list[Path] = []
    unmatched_not_in_schedule: list[Path] = []
    refs_seen: set[str] = set()

    for f in _iter_source_files(source_dir, recursive):
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
