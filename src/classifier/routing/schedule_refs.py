"""Schedule reading and helpers for filesystem-safe discipline / title strings."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from classifier.config.patterns import REF_PATTERN

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
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)
    if not cleaned:
        return ""
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    cleaned = cleaned.rstrip(". ")
    return cleaned


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
