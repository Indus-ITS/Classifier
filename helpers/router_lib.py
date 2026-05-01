"""Pure file-routing logic - no I/O prompts, no print(), no color.

Match files in a source directory against a schedule's cust_ref column,
build a copy/move plan that splits files by predicted class
(Drawings / Documents / Undefined / Unmatched), and execute it.

All functions are pure data transformations except `execute_plan` which
performs the actual filesystem operations. The CLI in sort_files.py
handles all user interaction (prompts, color, progress).
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from config import BUCKET_TO_CLASS, REF_PATTERN
from helpers.classifier_lib import (
    extract_ref,
    fold_to_class,
    pick_bucket,
    score_buckets,
)


# -----------------------------------------------------------------------
# Data types
# -----------------------------------------------------------------------
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


# -----------------------------------------------------------------------
# Discipline -> filesystem-safe folder name
# -----------------------------------------------------------------------
_DISCIPLINE_UNKNOWN = "_UNKNOWN"


def safe_discipline(raw: str) -> str:
    """Map a raw discipline value (from the schedule's Discip column) to a
    filesystem-safe folder name. Empty / NaN -> ``_UNKNOWN``.

    Rules: uppercase, replace any non-alphanumeric with underscore,
    collapse runs of underscores, strip leading/trailing underscores.
    Examples:
        'CIVIL'        -> 'CIVIL'
        'ENGG QA/QC'   -> 'ENGG_QA_QC'
        'ENGG HSE'     -> 'ENGG_HSE'
        ''             -> '_UNKNOWN'
    """
    if not raw or not raw.strip():
        return _DISCIPLINE_UNKNOWN
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", raw.upper()).strip("_")
    return cleaned or _DISCIPLINE_UNKNOWN


def safe_title(raw: str, max_len: int = 100) -> str:
    """Sanitize a schedule title for use as a filename component.

    Rules:
      - Replace path-unsafe chars (``<>:"/\\|?*`` and control chars) with ``_``
      - Collapse runs of whitespace to a single space
      - Strip leading/trailing whitespace
      - Truncate to max_len chars (defaults to 100; full title kept if shorter)
      - Strip trailing dots and spaces (Windows refuses these in filenames)

    Returns '' for empty/whitespace-only input. Callers should treat ''
    as 'no title available' and fall back to the original filename.
    """
    if not raw:
        return ""
    # Collapse all whitespace (incl. tab/newline) to single space first,
    # so '\t' and '\n' don't get replaced with underscores below.
    cleaned = re.sub(r"\s+", " ", raw).strip()
    # Replace path-unsafe + remaining control chars
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)
    if not cleaned:
        return ""
    # Truncate then re-strip trailing space/dot
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    cleaned = cleaned.rstrip(". ")
    return cleaned


@dataclass(frozen=True)
class RoutePlan:
    """List of (source path, destination path) pairs to execute."""
    operations: list[tuple[Path, Path]]


# -----------------------------------------------------------------------
# Step 1 - load schedule
# -----------------------------------------------------------------------
def load_schedule_refs(xls_path: Path) -> dict[str, tuple[str, str]]:
    """Read the schedule (Sheet1) and return ``{cust_ref: (title, discipline)}``
    for rows where Cust Ref # matches the canonical
    ``\\d{2}-\\d{2}-\\d{2}-\\d{4}`` pattern. Rows with placeholder refs
    like '30-99-97-XXXX' are dropped. On duplicate refs (multiple
    revisions), the first row's values win. Missing discipline becomes ''.
    """
    df = pd.read_excel(xls_path, sheet_name="Sheet1")
    needed = {"Title", "Cust Ref #"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"{xls_path.name}: missing columns {missing}")

    out: dict[str, tuple[str, str]] = {}
    ref_re = re.compile(REF_PATTERN)
    for _, r in df.iterrows():
        if pd.isna(r.get("Title")) or pd.isna(r.get("Cust Ref #")):
            continue
        title = str(r["Title"]).strip()
        ref = str(r["Cust Ref #"]).strip()
        if not ref_re.fullmatch(ref):
            continue
        discip = "" if pd.isna(r.get("Discip")) else str(r.get("Discip", "")).strip()
        out.setdefault(ref, (title, discip))
    return out


# -----------------------------------------------------------------------
# Step 2 - classify a title via the existing pipeline
# -----------------------------------------------------------------------
def classify_title(title: str) -> str:
    """Run the bucket classifier and return the user-facing class label
    (Drawings / Documents / Undefined). Uses the same code path as
    classifier.py and helpers/evaluate_corpus.py.
    """
    pick = pick_bucket(score_buckets(title, ""))
    return fold_to_class(pick, BUCKET_TO_CLASS)


# -----------------------------------------------------------------------
# Step 3 - match files in a directory against the schedule
# -----------------------------------------------------------------------
# -----------------------------------------------------------------------
# Class folder names (top-level folders under dest_dir). Defined here
# (before _iter_source_files) so the recursive walk can skip them on
# in-place re-runs.
# -----------------------------------------------------------------------
CLASS_FOLDERS: tuple[str, ...] = ("Drawings", "Documents", "Undefined")
UNMATCHED_FOLDER: str = "Unmatched"
_CLASS_DIR_NAMES = frozenset((*CLASS_FOLDERS, UNMATCHED_FOLDER))


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
            # Skip files whose relative path contains any class folder name.
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


# -----------------------------------------------------------------------
# Step 4 - build a route plan
# -----------------------------------------------------------------------
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


def plan_summary(plan: RoutePlan) -> dict[str, int]:
    """Count files per top-level class folder (Drawings / Documents /
    Undefined / Unmatched).
    """
    counts: dict[str, int] = {}
    for _, dst in plan.operations:
        # Top-level folder under dest_dir is the class name (or 'Unmatched').
        # Walk parents to find it: ops are dest/<class>/<discipline>/file
        # for matched, or dest/Unmatched/file for unmatched.
        parts = dst.parts
        # Find which part is one of our class folder names.
        class_name = next(
            (p for p in parts if p in CLASS_FOLDERS or p == UNMATCHED_FOLDER),
            dst.parent.name,
        )
        counts[class_name] = counts.get(class_name, 0) + 1
    return counts


def plan_summary_by_class_discipline(plan: RoutePlan) -> dict[str, dict[str, int]]:
    """Returns ``{class: {discipline: count}}`` for the matched-file ops.
    Unmatched files (no discipline level in path) are reported under
    ``Unmatched -> {'-': count}``.
    """
    out: dict[str, dict[str, int]] = {}
    for _, dst in plan.operations:
        parts = dst.parts
        class_idx = next(
            (i for i, p in enumerate(parts)
             if p in CLASS_FOLDERS or p == UNMATCHED_FOLDER),
            None,
        )
        if class_idx is None:
            continue
        cls = parts[class_idx]
        if cls == UNMATCHED_FOLDER:
            disc = "-"
        else:
            disc = parts[class_idx + 1] if class_idx + 1 < len(parts) - 1 else "_UNKNOWN"
        out.setdefault(cls, {})
        out[cls][disc] = out[cls].get(disc, 0) + 1
    return out


def find_collisions(plan: RoutePlan) -> list[Path]:
    """Return destination paths that already exist (would be overwritten).
    Detects same-source same-destination (in-place re-runs) and same-name
    collisions from different sources.
    """
    collisions: list[Path] = []
    seen_dsts: set[Path] = set()
    for src, dst in plan.operations:
        # Skip a no-op: file already lives at its target (in-place re-run)
        if src.resolve() == dst.resolve():
            continue
        if dst.exists() or dst in seen_dsts:
            collisions.append(dst)
        seen_dsts.add(dst)
    return collisions


# -----------------------------------------------------------------------
# Duplicate resolution
# -----------------------------------------------------------------------
def resolve_duplicates(
    plan: RoutePlan,
    strategy: str,
) -> tuple[RoutePlan, int, int]:
    """Resolve cases where two source files would land at the same
    destination, or a destination already exists on disk.

    strategy:
      'error'  - leave the plan untouched; find_collisions() will flag
                 these and the CLI will abort. Safe default.
      'skip'   - keep the first occurrence by source-path order, drop
                 the rest from the plan. Use when duplicates are most
                 likely identical re-sends across transmittals.
      'rename' - keep all by appending a numeric suffix to the destination
                 name (foo.pdf, foo-2.pdf, foo-3.pdf, ...). Use when
                 you want to preserve every file even at the cost of
                 cluttered names.

    Returns (resolved_plan, dropped_count, renamed_count).

    No-op operations (src == dst, in-place re-run safety) are passed
    through regardless of strategy.
    """
    if strategy not in ("error", "skip", "rename"):
        raise ValueError(f"on_duplicate must be 'error', 'skip', or 'rename', got {strategy!r}")
    if strategy == "error":
        return plan, 0, 0

    # Pre-seed the seen set with destinations that already exist on disk
    # so we treat existing files the same as in-plan duplicates.
    seen_dsts: set[Path] = set()
    for _, dst in plan.operations:
        if dst.exists():
            seen_dsts.add(dst)

    new_ops: list[tuple[Path, Path]] = []
    dropped = 0
    renamed = 0

    for src, dst in plan.operations:
        # No-op: file already at its target (in-place re-run safety).
        if src.resolve() == dst.resolve():
            new_ops.append((src, dst))
            continue

        if dst in seen_dsts:
            if strategy == "skip":
                dropped += 1
                continue
            else:  # rename
                base = dst.stem
                ext = dst.suffix
                parent = dst.parent
                i = 2
                candidate = parent / f"{base}-{i}{ext}"
                while candidate in seen_dsts or candidate.exists():
                    i += 1
                    candidate = parent / f"{base}-{i}{ext}"
                seen_dsts.add(candidate)
                new_ops.append((src, candidate))
                renamed += 1
                continue

        seen_dsts.add(dst)
        new_ops.append((src, dst))

    return RoutePlan(operations=new_ops), dropped, renamed


# -----------------------------------------------------------------------
# Step 5 - execute
# -----------------------------------------------------------------------
ProgressCallback = Callable[[int, int, Path], None]


def _class_folder_for(dst: Path) -> str:
    """Find which class folder (Drawings / Documents / Undefined / Unmatched)
    a destination path falls under. Walks the path parts and returns the
    first one that matches. Falls back to dst.parent.name.
    """
    for p in dst.parts:
        if p in CLASS_FOLDERS or p == UNMATCHED_FOLDER:
            return p
    return dst.parent.name


def clean_empty_dirs(root: Path) -> int:
    """Remove empty directories under root, recursively (deepest first).
    Returns the count of removed directories. Never removes root itself.
    """
    if not root.is_dir():
        return 0
    removed = 0
    # Walk bottom-up so child dirs are removed before their parents.
    all_dirs = sorted(
        (p for p in root.rglob("*") if p.is_dir()),
        key=lambda p: -len(p.parts),
    )
    for d in all_dirs:
        try:
            # rmdir only succeeds if empty
            d.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def execute_plan(
    plan: RoutePlan,
    mode: str,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, int]:
    """Perform the copy or move. Returns counts per top-level class folder
    (Drawings / Documents / Undefined / Unmatched).

    mode: 'copy' or 'move'.
    on_progress: optional callable(done, total, src) called after each op.
    """
    if mode not in ("copy", "move"):
        raise ValueError(f"mode must be 'copy' or 'move', got {mode!r}")

    counts: dict[str, int] = {}
    total = len(plan.operations)
    for i, (src, dst) in enumerate(plan.operations, start=1):
        cls = _class_folder_for(dst)
        # No-op: file is already at its target (in-place re-run safety)
        if src.resolve() == dst.resolve():
            counts[cls] = counts.get(cls, 0) + 1
            if on_progress:
                on_progress(i, total, src)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            shutil.copy2(src, dst)
        else:  # move
            shutil.move(str(src), str(dst))
        counts[cls] = counts.get(cls, 0) + 1
        if on_progress:
            on_progress(i, total, src)
    return counts
