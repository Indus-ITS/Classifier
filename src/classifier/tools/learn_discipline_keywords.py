"""Generate ``classifier.config.discipline_keywords`` from labeled CSVs.

The labelled CSVs in ``input/classified_csv/`` use the CLIENT's
discipline taxonomy. DEST has 7 internal disciplines (Civil, Electrical,
EMT, I&C, Mechanical, Piping, Process) that the client taxonomy folds
into via ``input/discipline_fold.csv``.

Flow:
  1. Read every (client_discipline_id, title) pair from the labelled CSVs.
  2. Look up client_discipline_id in the fold table -> dest_discipline_id.
  3. Rows whose client_id has no fold entry are dropped as orphans.
  4. Train keyword rules per DEST discipline_id.
  5. Emit ``{dest_id: ((phrase, weight), ...)}`` to
     ``src/classifier/config/discipline_keywords.py``.

The RDS pipeline writes the trained dest_id directly into
``documents.discipline_id``, which is FK-safe by construction (every
dest_id in the fold is validated against ``input/disciplines.csv``).

Scoring, eligibility, auto-stopword rules mirror
``learn_type_keywords`` exactly so the two learners stay aligned.

Run from project root::

    learn-discipline-keywords
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from classifier.core.type_scoring import (
    STOP_TOKENS,
    candidate_phrases,
    canonicalize_title,
)
from classifier.io.normalize import is_empty

CSV_ROOT = Path("input/classified_csv")
DISCIPLINES_TABLE_CSV = Path("input/disciplines.csv")
DISCIPLINE_FOLD_CSV = Path("input/discipline_fold.csv")
OUT_PATH = Path("src/classifier/config/discipline_keywords.py")

MIN_CLASS_DOCS: int = 4
MIN_PHRASE_OCCURRENCES: int = 2
PRECISION_FLOOR: float = 0.6
AUTO_STOP_FREQ: float = 0.40
SPREAD_STOP_MIN_DOCS: int = 20
SPREAD_STOP_MAX_CLASS_SHARE: float = 0.30
TOP_PHRASES_PER_TYPE: int = 10


def _parse_discipline(raw: str) -> int | None:
    """Parse the labelled discipline_id column. CSV stores floats like
    ``13.0``; return the int. Empty / non-numeric values yield None."""
    if is_empty(raw):
        return None
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def _load_valid_dest_ids() -> frozenset[int]:
    """Load the canonical DEST discipline_id set from disciplines.csv.

    Used only to validate the RHS of the fold table -- every dest_id in
    the fold MUST exist in this set, otherwise the pipeline would write
    FK-invalid values into documents.discipline_id.
    """
    if not DISCIPLINES_TABLE_CSV.exists():
        raise SystemExit(
            f"disciplines table not found at {DISCIPLINES_TABLE_CSV}. "
            "Export the disciplines table to that path and re-run."
        )
    df = pd.read_csv(DISCIPLINES_TABLE_CSV, dtype=str, keep_default_na=False, na_values=[])
    if "id" not in df.columns:
        raise SystemExit(f"{DISCIPLINES_TABLE_CSV}: missing required 'id' column")
    ids: set[int] = set()
    for raw in df["id"]:
        if is_empty(raw):
            continue
        try:
            ids.add(int(float(str(raw).strip())))
        except (TypeError, ValueError):
            continue
    return frozenset(ids)


def _load_fold(valid_dest_ids: frozenset[int]) -> dict[int, int]:
    """Load the client -> DEST discipline fold table.

    The labelled training CSVs use the client's discipline taxonomy
    (e.g. Telecom, HVAC, Mechanical Static, project-management buckets).
    DEST has 7 disciplines that those fold into. The fold table makes
    that explicit: each row maps a client_id to one of DEST's 7 ids.

    Client ids that have no fold entry are treated as orphans in
    ``_collect_rows`` and dropped from training. This is the only
    whitelist mechanism -- discipline_ids reach training only through
    the fold table, which guarantees the learned rules emit DEST ids.
    """
    if not DISCIPLINE_FOLD_CSV.exists():
        raise SystemExit(
            f"discipline fold not found at {DISCIPLINE_FOLD_CSV}. "
            "Create it with (client_id, dest_id) columns."
        )
    df = pd.read_csv(DISCIPLINE_FOLD_CSV, dtype=str, keep_default_na=False, na_values=[])
    if not {"client_id", "dest_id"}.issubset(df.columns):
        raise SystemExit(f"{DISCIPLINE_FOLD_CSV}: need columns 'client_id' and 'dest_id'")
    fold: dict[int, int] = {}
    for _, row in df.iterrows():
        c = _parse_discipline(row["client_id"])
        d = _parse_discipline(row["dest_id"])
        if c is None or d is None:
            continue
        if d not in valid_dest_ids:
            raise SystemExit(
                f"{DISCIPLINE_FOLD_CSV}: dest_id={d} (folded from client_id={c}) "
                f"is not in {DISCIPLINES_TABLE_CSV}. Fix the fold or the disciplines table."
            )
        fold[c] = d
    if not fold:
        raise SystemExit(f"{DISCIPLINE_FOLD_CSV}: no valid (client_id, dest_id) rows found")
    return fold


def _collect_rows(fold: dict[int, int]
                  ) -> tuple[list[tuple[int, str, Path]], Counter[int]]:
    """Yield ``(dest_discipline_id, title, source_path)`` for every
    eligible row, applying the client -> DEST fold.

    Returns ``(rows, orphan_counts)`` where ``orphan_counts`` is a
    Counter of client discipline_ids seen in the training CSVs that
    have no entry in the fold table (and are therefore dropped).
    """
    rows: list[tuple[int, str, Path]] = []
    orphans: Counter[int] = Counter()
    csv_paths = sorted(CSV_ROOT.rglob("*.csv"), key=lambda p: str(p).lower())
    for p in csv_paths:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[])
        if not {"discipline_id", "title"}.issubset(df.columns):
            print(f"  [skip] {p}: missing 'discipline_id' or 'title' column")
            continue
        for _, row in df.iterrows():
            if is_empty(row["title"]):
                continue
            client_disc = _parse_discipline(row["discipline_id"])
            if client_disc is None:
                continue
            dest_disc = fold.get(client_disc)
            if dest_disc is None:
                orphans[client_disc] += 1
                continue
            rows.append((dest_disc, str(row["title"]), p))
    return rows, orphans


_DIGIT_RE = re.compile(r"\d")


def _phrase_is_publishable(ngram: tuple[str, ...]) -> bool:
    for tok in ngram:
        if _DIGIT_RE.search(tok):
            return False
    if not any(ch.isalpha() for ch in ngram[0]):
        return False
    if not any(ch.isalpha() for ch in ngram[-1]):
        return False
    return True


def _auto_stopwords(tokenized: list[tuple[int, list[str]]]) -> frozenset[str]:
    if not tokenized:
        return frozenset()
    doc_count_for: Counter[str] = Counter()
    class_count_for: defaultdict[str, Counter[int]] = defaultdict(Counter)
    for disc, toks in tokenized:
        for tok in set(toks):
            doc_count_for[tok] += 1
            class_count_for[tok][disc] += 1
    n = len(tokenized)
    freq_threshold = AUTO_STOP_FREQ * n
    stops: set[str] = set()
    for tok, count in doc_count_for.items():
        if count > freq_threshold:
            stops.add(tok)
            continue
        if count >= SPREAD_STOP_MIN_DOCS:
            max_share = max(class_count_for[tok].values()) / count
            if max_share < SPREAD_STOP_MAX_CLASS_SHARE:
                stops.add(tok)
    return frozenset(stops)


def learn(rows: Iterable[tuple[int, str, Path]]
          ) -> tuple[dict[int, tuple[tuple[str, float], ...]],
                      Counter[int],
                      frozenset[int]]:
    rows = list(rows)
    class_counts: Counter[int] = Counter(d for d, _, _ in rows)
    tokenized: list[tuple[int, list[str]]] = [
        (d, canonicalize_title(title)) for d, title, _ in rows
    ]
    auto_stop = _auto_stopwords(tokenized)
    row_phrases: list[tuple[int, set[tuple[str, ...]]]] = []
    for d, toks in tokenized:
        phrases = {ph for ph in candidate_phrases(toks, extra_stop=auto_stop)
                   if _phrase_is_publishable(ph)}
        row_phrases.append((d, phrases))
    phrase_in_class: defaultdict[tuple[int, tuple[str, ...]], int] = defaultdict(int)
    phrase_total: defaultdict[tuple[str, ...], int] = defaultdict(int)
    for d, phrases in row_phrases:
        for ph in phrases:
            phrase_in_class[(d, ph)] += 1
            phrase_total[ph] += 1
    eligible: set[int] = {d for d, n in class_counts.items() if n >= MIN_CLASS_DOCS}
    rules: dict[int, tuple[tuple[str, float], ...]] = {}
    for d in sorted(eligible):
        bag: list[tuple[float, str]] = []
        for (cd, ph), in_class in phrase_in_class.items():
            if cd != d:
                continue
            if in_class < MIN_PHRASE_OCCURRENCES:
                continue
            outside = phrase_total[ph] - in_class
            if outside >= in_class:
                continue
            precision = in_class / (in_class + outside)
            if precision < PRECISION_FLOOR:
                continue
            score = precision * math.log1p(in_class)
            bag.append((score, " ".join(ph)))
        bag.sort(key=lambda x: (-x[0], x[1]))
        rules[d] = tuple((phrase, round(score, 4)) for score, phrase in bag[:TOP_PHRASES_PER_TYPE])
    untrained = frozenset(class_counts) - eligible
    return rules, class_counts, untrained


def render(rules: dict[int, tuple[tuple[str, float], ...]],
           class_counts: Counter[int],
           untrained: frozenset[int],
           n_rows: int,
           source_root: Path) -> str:
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    untrained_list = ", ".join(
        f"{d} ({class_counts.get(d, 0)})" for d in sorted(untrained)
    )
    lines: list[str] = []
    lines.append('"""Generated by ``learn-discipline-keywords``. Do not edit by hand.')
    lines.append("")
    lines.append(f"Source: {source_root.as_posix()}/**/*.csv")
    lines.append(f"Generated: {now}")
    lines.append(f"Training rows used: {n_rows}")
    if untrained_list:
        lines.append("")
        lines.append(f"Untrained disciplines (< {MIN_CLASS_DOCS} examples, no rules emitted):")
        lines.append(f"  {untrained_list}")
    lines.append('"""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("UNTRAINED_DISCIPLINES: frozenset[int] = frozenset({")
    for d in sorted(untrained):
        lines.append(f"    {d},")
    lines.append("})")
    lines.append("")
    lines.append("DISCIPLINE_KEYWORDS: dict[int, tuple[tuple[str, float], ...]] = {")
    for d in sorted(rules):
        lines.append(f"    {d}: (")
        for phrase, score in rules[d]:
            lines.append(f"        ({phrase!r}, {score}),")
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not CSV_ROOT.exists():
        raise SystemExit(f"csv dir not found: {CSV_ROOT}")
    valid_dest_ids = _load_valid_dest_ids()
    fold = _load_fold(valid_dest_ids)
    rows, orphans = _collect_rows(fold)
    if not rows:
        raise SystemExit(f"no eligible (discipline_id, title) rows found under {CSV_ROOT}")
    rules, class_counts, untrained = learn(rows)
    text = render(rules, class_counts, untrained, len(rows), CSV_ROOT)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    dest_buckets = sorted(set(fold.values()))
    print(f"Wrote {OUT_PATH}")
    print(f"  fold table:            {len(fold)} client_id -> dest_id entries")
    print(f"  DEST buckets in fold:  {dest_buckets}")
    print(f"  training rows kept:    {len(rows)}")
    print(f"  DEST disciplines trained: {sorted(rules)}")
    print(f"  DEST disciplines untrained (< {MIN_CLASS_DOCS} training rows): {sorted(untrained)}")
    if orphans:
        orphan_summary = ", ".join(f"{d} ({n})" for d, n in orphans.most_common())
        print(f"  client IDs dropped (no fold entry):")
        print(f"    {orphan_summary}")
    for d in sorted(rules)[:3]:
        sample = ", ".join(f"{p!r}" for p, _ in rules[d][:3])
        print(f"    dest_id={d}: {sample}")


if __name__ == "__main__":
    main()
