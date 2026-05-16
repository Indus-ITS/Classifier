"""Generate ``classifier.config.type_keywords`` from labeled CSVs.

Walks ``input/classified_csv/**/*.csv`` (sorted), collects
``(type, title)`` pairs for rows where ``type`` is in the canonical
``KNOWN_TYPES`` enum, and emits a deterministic mapping of
``{type: ((phrase, weight), ...)}`` to
``src/classifier/config/type_keywords.py``.

Scoring per (type, phrase):

    in_class    = rows of this type containing the phrase
    outside     = rows of other types containing the phrase
    precision   = in_class / (in_class + outside)
    support     = log1p(in_class)
    final_score = precision * support

Filters (all must pass):
  * in_class >= MIN_PHRASE_OCCURRENCES
  * outside < in_class
  * precision >= PRECISION_FLOOR

Class eligibility:
  * type has >= MIN_CLASS_DOCS training rows. Classes below the
    threshold appear in UNTRAINED_TYPES with their actual count.

Auto-stopword:
  * Any token appearing in > AUTO_STOP_FREQ of training titles is
    treated as a stop token (in addition to the curated STOP_TOKENS
    in ``classifier.core.type_scoring``).

Run from project root::

    learn-type-keywords
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from classifier.config.type_enum import KNOWN_TYPES
from classifier.core.type_scoring import (
    STOP_TOKENS,
    candidate_phrases,
    canonicalize_title,
)
from classifier.io.normalize import is_empty

CSV_ROOT = Path("input/classified_csv")
OUT_PATH = Path("src/classifier/config/type_keywords.py")

MIN_CLASS_DOCS: int = 4
MIN_PHRASE_OCCURRENCES: int = 2
PRECISION_FLOOR: float = 0.6
AUTO_STOP_FREQ: float = 0.40    # token in > 40% of titles -> stop
SPREAD_STOP_MIN_DOCS: int = 20  # need this many appearances to judge spread
SPREAD_STOP_MAX_CLASS_SHARE: float = 0.30  # if dominant class is <30% of a
                                # token's appearances, the token is
                                # class-agnostic noise (project / site names
                                # like SAHIL spread evenly across all types).
TOP_PHRASES_PER_TYPE: int = 10


def _collect_rows() -> list[tuple[str, str, Path]]:
    """Yield ``(type, title, source_path)`` for every eligible row."""
    rows: list[tuple[str, str, Path]] = []
    csv_paths = sorted(CSV_ROOT.rglob("*.csv"), key=lambda p: str(p).lower())
    for p in csv_paths:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[])
        if not {"type", "title"}.issubset(df.columns):
            print(f"  [skip] {p}: missing 'type' or 'title' column")
            continue
        for _, row in df.iterrows():
            if is_empty(row["title"]) or is_empty(row["type"]):
                continue
            t = str(row["type"]).strip().upper()
            if t not in KNOWN_TYPES:
                continue
            rows.append((t, str(row["title"]), p))
    return rows


def _auto_stopwords(tokenized: list[tuple[str, list[str]]]) -> frozenset[str]:
    """Identify noise tokens algorithmically. A token is stopped if EITHER:

    * It appears in > AUTO_STOP_FREQ of all titles (overwhelming common
      across the corpus -- this catches generic English/site words that
      escape the curated STOP_TOKENS), OR
    * It appears in >= SPREAD_STOP_MIN_DOCS titles AND its single most
      common class accounts for < SPREAD_STOP_MAX_CLASS_SHARE of those
      appearances. A token whose appearances spread roughly uniformly
      across many classes carries no classification signal -- typically
      a project name, site name, or generic descriptor (SAHIL, CDS,
      WATER, AREA). This catches project names without an explicit list.

    Real signature tokens (DATA->DAS, REPORT->REP, SPECIFICATION->SPC)
    concentrate sharply in one class and stay safe.
    """
    if not tokenized:
        return frozenset()
    doc_count_for: Counter[str] = Counter()
    class_count_for: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for type_code, toks in tokenized:
        for tok in set(toks):
            doc_count_for[tok] += 1
            class_count_for[tok][type_code] += 1
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


_DIGIT_RE = re.compile(r"\d")


def _phrase_is_publishable(ngram: tuple[str, ...]) -> bool:
    """Reject n-grams that won't transfer across datasets.

    Rejects:
      * Any n-gram containing a digit-bearing token (project IDs,
        tag numbers, area suffixes).
      * Any n-gram whose first or last token has no alphabetic
        character (lone &, /, or other edge punctuation).

    Middle tokens may be punctuation-only - preserves
    'PIPING & INSTRUMENT' (middle '&') while rejecting '& INSTRUMENT'
    and 'PIPING &'.
    """
    for tok in ngram:
        if _DIGIT_RE.search(tok):
            return False
    if not any(ch.isalpha() for ch in ngram[0]):
        return False
    if not any(ch.isalpha() for ch in ngram[-1]):
        return False
    return True


def learn(rows: Iterable[tuple[str, str, Path]]
          ) -> tuple[dict[str, tuple[tuple[str, float], ...]],
                      Counter[str],
                      frozenset[str]]:
    """Return ``(rules, class_counts, untrained_types)``.

    rules:           {type_code: ((phrase_text, weight), ...)} sorted within type
    class_counts:    Counter of training-row counts per type code seen
    untrained_types: KNOWN_TYPES minus the rule-eligible classes
    """
    rows = list(rows)
    class_counts: Counter[str] = Counter(t for t, _, _ in rows)

    # Per-row canonical tokens.
    tokenized: list[tuple[str, list[str]]] = [
        (t, canonicalize_title(title)) for t, title, _ in rows
    ]
    auto_stop = _auto_stopwords(tokenized)

    # Per-row candidate phrase set (de-duped within row).
    row_phrases: list[tuple[str, set[tuple[str, ...]]]] = []
    for t, toks in tokenized:
        phrases = {ph for ph in candidate_phrases(toks, extra_stop=auto_stop)
                   if _phrase_is_publishable(ph)}
        row_phrases.append((t, phrases))

    # phrase_in_class[(type, phrase)] = count
    phrase_in_class: defaultdict[tuple[str, tuple[str, ...]], int] = defaultdict(int)
    # phrase_total[phrase] = count across all rows
    phrase_total: defaultdict[tuple[str, ...], int] = defaultdict(int)
    for t, phrases in row_phrases:
        for ph in phrases:
            phrase_in_class[(t, ph)] += 1
            phrase_total[ph] += 1

    eligible: set[str] = {t for t, n in class_counts.items() if n >= MIN_CLASS_DOCS}

    rules: dict[str, tuple[tuple[str, float], ...]] = {}
    for t in sorted(eligible):
        bag: list[tuple[float, str]] = []
        for (ct, ph), in_class in phrase_in_class.items():
            if ct != t:
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
        rules[t] = tuple((phrase, round(score, 4)) for score, phrase in bag[:TOP_PHRASES_PER_TYPE])

    untrained = frozenset(KNOWN_TYPES) - eligible
    return rules, class_counts, untrained


def render(rules: dict[str, tuple[tuple[str, float], ...]],
           class_counts: Counter[str],
           untrained: frozenset[str],
           n_rows: int,
           source_root: Path) -> str:
    """Render the generated module text."""
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    untrained_list = ", ".join(
        f"{t} ({class_counts.get(t, 0)})" for t in sorted(untrained)
    )

    lines: list[str] = []
    lines.append('"""Generated by ``learn-type-keywords``. Do not edit by hand.')
    lines.append("")
    lines.append(f"Source: {source_root.as_posix()}/**/*.csv")
    lines.append(f"Generated: {now}")
    lines.append(f"Training rows used: {n_rows}")
    if untrained_list:
        lines.append("")
        lines.append(f"Untrained types (< {MIN_CLASS_DOCS} examples, no rules emitted):")
        lines.append(f"  {untrained_list}")
    lines.append('"""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("UNTRAINED_TYPES: frozenset[str] = frozenset({")
    for t in sorted(untrained):
        lines.append(f"    {t!r},")
    lines.append("})")
    lines.append("")
    lines.append("TYPE_KEYWORD_RULES: dict[str, tuple[tuple[str, float], ...]] = {")
    for t in sorted(rules):
        lines.append(f"    {t!r}: (")
        for phrase, score in rules[t]:
            lines.append(f"        ({phrase!r}, {score}),")
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not CSV_ROOT.exists():
        raise SystemExit(f"csv dir not found: {CSV_ROOT}")

    rows = _collect_rows()
    if not rows:
        raise SystemExit(f"no eligible (type, title) rows found under {CSV_ROOT}")

    rules, class_counts, untrained = learn(rows)
    text = render(rules, class_counts, untrained, len(rows), CSV_ROOT)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8", newline="\n")

    print(f"Wrote {OUT_PATH}")
    print(f"  training rows:    {len(rows)}")
    print(f"  classes eligible: {len(rules)}")
    print(f"  classes untrained: {len(untrained)}")
    print(f"  top phrases per class (sample):")
    for t in sorted(rules)[:3]:
        sample = ", ".join(f"{p!r}" for p, _ in rules[t][:3])
        print(f"    {t}: {sample}")


if __name__ == "__main__":
    main()
