# RDS Classifier Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a callable `classify_from_rds(conn, ...)` pipeline that reads unclassified rows from a PostgreSQL `documents` table, classifies `doc_type` / `type` / `discipline_id` from the row `title`, and UPDATEs them in place. Keeps the existing CSV CLI working.

**Architecture:** New `io/rds.py` owns all psycopg2 calls. New `pipeline/_row.py` holds the shared per-row classifier logic (lifted from `cli/classify.py`). New `pipeline/classify_rds.py` orchestrates the cursor loop + dynamic UPDATE. New `core/discipline_scoring.py` + generated `config/discipline_keywords.py` provide title→discipline_id inference. A `classify-rds` console script exposes the pipeline via env-var DSN.

**Tech Stack:** Python 3.10+, psycopg2-binary, pandas (already a dep), existing classifier core modules.

**Spec:** [docs/superpowers/specs/2026-05-25-rds-pipeline-design.md](../specs/2026-05-25-rds-pipeline-design.md)

**Testing policy:** The user has explicitly opted out of automated tests for this iteration. Each task ends with a manual smoke check (importability, dry-run, or print-stats) plus a commit.

---

## Task 1: Add psycopg2 dependency and pipeline package init

**Files:**
- Modify: `pyproject.toml`
- Create: `src/classifier/pipeline/__init__.py`

- [ ] **Step 1: Add psycopg2-binary to dependencies**

Modify [pyproject.toml](../../../pyproject.toml). Add `"psycopg2-binary>=2.9"` to the `dependencies` list:

```toml
[project]
name = "classifier"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pandas>=2.0",
    "openpyxl>=3.1",
    "xlrd>=2.0",
    "psycopg2-binary>=2.9",
]
```

- [ ] **Step 2: Create the pipeline package**

Create `src/classifier/pipeline/__init__.py` with a single docstring line:

```python
"""Orchestration layer: enrich / audit / RDS classification flows."""
```

- [ ] **Step 3: Reinstall the package so the new dep is available**

Run from project root: `pip install -e .`
Expected: succeeds; `python -c "import psycopg2"` exits 0.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/classifier/pipeline/__init__.py
git commit -m "deps: add psycopg2-binary; create pipeline package"
```

---

## Task 2: Extract shared per-row logic to pipeline/_row.py

**Files:**
- Create: `src/classifier/pipeline/_row.py`
- Modify: `src/classifier/cli/classify.py`

- [ ] **Step 1: Create `pipeline/_row.py`**

Create `src/classifier/pipeline/_row.py` with the existing per-row helpers from [src/classifier/cli/classify.py](../../../src/classifier/cli/classify.py), renamed to drop the leading underscore. Copy verbatim except for the rename.

```python
"""Shared per-row classifier logic.

Pure functions reused by:
  * ``classifier.cli.classify``        (CSV input/output)
  * ``classifier.pipeline.classify_rds`` (PostgreSQL input/output)

Each function takes ``(existing_value, title)`` and returns
``(new_value, reason_tag)`` so callers can build aggregate stats.
"""
from __future__ import annotations

from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.core.type_scoring import pick_type_with_overrides
from classifier.io.normalize import is_empty

DRAWING_ALIASES = {"drawing", "drawings", "dwg"}
DOCUMENT_ALIASES = {"document", "documents", "doc", "docs"}


def normalize_doc_type(value: str, title: str) -> tuple[str, str]:
    """Return ``(normalized, reason)``. reason: existing / via_keyword / via_override / defaulted."""
    if not is_empty(value):
        v = str(value).strip().lower()
        if v in DRAWING_ALIASES:
            return "drawing", "existing"
        if v in DOCUMENT_ALIASES:
            return "document", "existing"
    pick = pick_type_with_overrides(title)
    if pick["confidence"] == "high":
        bucket = TYPE_TO_BUCKET.get(pick["type"])
        if bucket is not None:
            folded = BUCKET_TO_CLASS[bucket]
            reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
            return ("drawing" if folded == "Drawings" else "document"), reason_tag
    return "document", "defaulted"


def fill_type(row_type: str, title: str) -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / via_override / miss."""
    if not is_empty(row_type):
        return str(row_type).strip(), "preserved"
    pick = pick_type_with_overrides(title)
    if pick["confidence"] == "high":
        reason_tag = "via_override" if pick["reason"] == "override" else "via_keyword"
        return pick["type"], reason_tag
    return "", "miss"
```

- [ ] **Step 2: Update `cli/classify.py` to import from `_row`**

Modify [src/classifier/cli/classify.py](../../../src/classifier/cli/classify.py). Replace the local `_normalize_doc_type` and `_fill_type` function definitions (currently lines 48-88) with an import. Update both call sites (currently at lines 122 and 127) to use the new names. The `DRAWING_ALIASES` / `DOCUMENT_ALIASES` constants at lines 44-45 become unused — remove them too.

Specifically:
- Delete `DRAWING_ALIASES` and `DOCUMENT_ALIASES` constants (lines 44-45).
- Delete the `_normalize_doc_type` function (lines 48-71).
- Delete the `_fill_type` function (lines 74-88).
- Below the existing imports near the top, add:
  ```python
  from classifier.pipeline._row import normalize_doc_type, fill_type
  ```
- Change the call site `_normalize_doc_type(out["doc_type"], out["title"])` to `normalize_doc_type(out["doc_type"], out["title"])`.
- Change the call site `_fill_type(out["type"], out["title"])` to `fill_type(out["type"], out["title"])`.
- Also remove the now-unused imports `BUCKET_TO_CLASS, TYPE_TO_BUCKET` and `pick_type_with_overrides, score_types, pick_type` — keep only what `cli/classify.py` still uses (`from classifier.io.normalize import is_empty` and `from classifier.io.schema import TARGET_COLUMNS, validate_schema` remain).

Reason output strings change in one place: the old `_fill_type` returned `"empty"` on miss; the new `fill_type` returns `"miss"`. Update the CSV CLI's reporting loop near the end of `main()` (currently iterates `("preserved", "via_override", "via_keyword", "empty")`) to use `("preserved", "via_override", "via_keyword", "miss")` to match.

- [ ] **Step 3: Verify CSV CLI still works**

Run from project root: `classify`
Expected: prints `Wrote output/classified.csv (N rows)` and the stats blocks. `type fill outcomes:` lists `miss` instead of `empty`; numbers otherwise match the previous run.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/pipeline/_row.py src/classifier/cli/classify.py
git commit -m "refactor: lift per-row classifier helpers to pipeline/_row"
```

---

## Task 3: Build the discipline-keyword learner tool

**Files:**
- Create: `src/classifier/tools/learn_discipline_keywords.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the learner**

Create `src/classifier/tools/learn_discipline_keywords.py`. This is structurally identical to [src/classifier/tools/learn_type_keywords.py](../../../src/classifier/tools/learn_type_keywords.py), but the training column is `discipline_id` (parsed via `int(float(x))` because labelled CSVs store it as `13.0`), and the output is a `dict[int, list[tuple[str, int]]]` named `DISCIPLINE_KEYWORDS`.

```python
"""Generate ``classifier.config.discipline_keywords`` from labeled CSVs.

Walks ``input/classified_csv/**/*.csv`` (sorted), collects
``(discipline_id, title)`` pairs for rows where ``discipline_id`` is a
non-empty integer, and emits a deterministic
``{discipline_id: ((phrase, weight), ...)}`` mapping to
``src/classifier/config/discipline_keywords.py``.

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


def _collect_rows() -> list[tuple[int, str, Path]]:
    """Yield ``(discipline_id, title, source_path)`` for every eligible row."""
    rows: list[tuple[int, str, Path]] = []
    csv_paths = sorted(CSV_ROOT.rglob("*.csv"), key=lambda p: str(p).lower())
    for p in csv_paths:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[])
        if not {"discipline_id", "title"}.issubset(df.columns):
            print(f"  [skip] {p}: missing 'discipline_id' or 'title' column")
            continue
        for _, row in df.iterrows():
            if is_empty(row["title"]):
                continue
            disc = _parse_discipline(row["discipline_id"])
            if disc is None:
                continue
            rows.append((disc, str(row["title"]), p))
    return rows


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
    rows = _collect_rows()
    if not rows:
        raise SystemExit(f"no eligible (discipline_id, title) rows found under {CSV_ROOT}")
    rules, class_counts, untrained = learn(rows)
    text = render(rules, class_counts, untrained, len(rows), CSV_ROOT)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT_PATH}")
    print(f"  training rows:    {len(rows)}")
    print(f"  disciplines eligible: {len(rules)}")
    print(f"  disciplines untrained: {len(untrained)}")
    for d in sorted(rules)[:3]:
        sample = ", ".join(f"{p!r}" for p, _ in rules[d][:3])
        print(f"    discipline_id={d}: {sample}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Register the console script**

Modify [pyproject.toml](../../../pyproject.toml). Under `[project.scripts]` add:

```toml
learn-discipline-keywords = "classifier.tools.learn_discipline_keywords:main"
```

- [ ] **Step 3: Reinstall and run the learner to generate the config**

Run from project root:
```bash
pip install -e .
learn-discipline-keywords
```
Expected: writes `src/classifier/config/discipline_keywords.py`; prints training counts and a sample of phrases per discipline.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/tools/learn_discipline_keywords.py pyproject.toml src/classifier/config/discipline_keywords.py
git commit -m "feat(tools): learn-discipline-keywords learner + generated config"
```

---

## Task 4: Discipline scoring + fill_discipline helper

**Files:**
- Create: `src/classifier/core/discipline_scoring.py`
- Modify: `src/classifier/pipeline/_row.py`

- [ ] **Step 1: Create the scorer**

Create `src/classifier/core/discipline_scoring.py`. Mirrors the structure of `pick_type` but operates on the generated `DISCIPLINE_KEYWORDS` dict and uses the existing `canonicalize_title` + `_index_phrases_in` infrastructure from `type_scoring`.

```python
"""Discipline-level keyword scoring.

Public API:
  * ``score_disciplines(title)``  - {discipline_id: (score, n_phrases)}
  * ``pick_discipline(scores)``   - confidence-gated single choice
  * ``pick_discipline_with_overrides(title)`` - convenience wrapper
    returning the standard
    ``{discipline_id, confidence, reason}`` shape.

No overrides table in this iteration. ``reason`` is always
``"keyword"`` or ``"miss"``.
"""
from __future__ import annotations

from classifier.core.type_scoring import (
    MIN_MARGIN, MIN_SCORE, SINGLE_PHRASE_FLOOR,
    _index_phrases_in, canonicalize_title,
)


def score_disciplines(title: str) -> dict[int, tuple[float, int]]:
    """Cumulative ``(score, n_phrases)`` per discipline."""
    from classifier.config.discipline_keywords import DISCIPLINE_KEYWORDS

    tokens = canonicalize_title(title)
    if not tokens:
        return {}

    scores: dict[int, tuple[float, int]] = {}
    for disc_id, rules in DISCIPLINE_KEYWORDS.items():
        consumed: list[tuple[int, int]] = []
        total = 0.0
        n_phrases = 0
        for phrase_text, weight in rules:
            phrase = phrase_text.split(" ")
            start = _index_phrases_in(tokens, phrase)
            if start < 0:
                continue
            end = start + len(phrase)
            if any(not (end <= cs or start >= ce) for cs, ce in consumed):
                continue
            consumed.append((start, end))
            total += weight
            n_phrases += 1
        if total > 0:
            scores[disc_id] = (total, n_phrases)
    return scores


def pick_discipline(scores: dict[int, tuple[float, int]]) -> dict:
    """Return ``{discipline_id, confidence}``. Same gates as pick_type."""
    if not scores:
        return {"discipline_id": None, "confidence": "none"}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    top_id, (top_score, top_n) = ranked[0]
    rup_score = ranked[1][1][0] if len(ranked) > 1 else 0.0
    if top_score < MIN_SCORE:
        confidence = "none"
    elif (top_score - rup_score) < MIN_MARGIN:
        confidence = "low"
    elif top_n < 2 and top_score < SINGLE_PHRASE_FLOOR:
        confidence = "low"
    else:
        confidence = "high"
    return {
        "discipline_id": top_id if confidence != "none" else None,
        "confidence": confidence,
    }


def pick_discipline_with_overrides(title: str) -> dict:
    """No overrides yet; thin wrapper for API symmetry with type scoring."""
    pick = pick_discipline(score_disciplines(title))
    pick["reason"] = "keyword" if pick["confidence"] != "none" else "miss"
    return pick
```

- [ ] **Step 2: Add `fill_discipline` to `_row.py`**

Append to `src/classifier/pipeline/_row.py`:

```python
from classifier.core.discipline_scoring import pick_discipline_with_overrides


def fill_discipline(row_disc: str, title: str) -> tuple[str, str]:
    """Return ``(value, reason)``. reason: preserved / via_keyword / miss.

    ``value`` is the discipline_id as a decimal string when found, else
    ``""``. The RDS layer converts ``""`` to "omit from SET clause" and
    a non-empty string to ``int(...)`` before parameterising. The CSV
    CLI does not currently call this function.
    """
    if not is_empty(row_disc):
        return str(row_disc).strip(), "preserved"
    pick = pick_discipline_with_overrides(title)
    if pick["confidence"] == "high" and pick["discipline_id"] is not None:
        return str(pick["discipline_id"]), "via_keyword"
    return "", "miss"
```

- [ ] **Step 3: Smoke-test imports**

Run: `python -c "from classifier.pipeline._row import fill_discipline; print(fill_discipline('', 'VALVE LIST'))"`
Expected: prints a 2-tuple like `('13', 'via_keyword')` or `('', 'miss')` depending on training data — exits 0.

- [ ] **Step 4: Commit**

```bash
git add src/classifier/core/discipline_scoring.py src/classifier/pipeline/_row.py
git commit -m "feat(core): discipline scoring + fill_discipline helper"
```

---

## Task 5: RDS I/O layer

**Files:**
- Create: `src/classifier/io/rds.py`

- [ ] **Step 1: Create `io/rds.py`**

Create `src/classifier/io/rds.py`. This module owns every psycopg2 call. The public API is two functions: `iter_unclassified(conn, table, pk, fetch_size)` (a generator) and `update_row(cur, table, pk, pk_value, writes)`. The dynamic SET clause and `psycopg2.sql.Identifier` usage live entirely here.

```python
"""PostgreSQL read/write helpers for the RDS classifier pipeline.

Identifier safety
-----------------
The ``table`` and ``pk`` arguments are SQL identifiers and CANNOT be
parameterised with %s. They are always wrapped in
``psycopg2.sql.Identifier`` before composition. Callers MUST NOT
build statements outside this module.

Write policy
------------
``update_row`` builds the SET clause from only the columns present in
the ``writes`` dict. A column whose value is None or empty string is
omitted upstream by the pipeline -- if it reaches this layer, it WILL
be written. This is intentional: this module trusts its caller and
does not second-guess the value type. The NULL-vs-empty policy lives
in ``classify_rds``.
"""
from __future__ import annotations

from typing import Iterator

from psycopg2 import sql


def iter_unclassified(conn, table: str, pk: str, fetch_size: int
                      ) -> Iterator[tuple]:
    """Yield ``(pk_value, doc_type, type, discipline_id, title)`` for
    every row where any classification target is NULL or empty.

    Uses a named (server-side) cursor so the result set streams instead
    of loading entirely into client memory. ``itersize`` controls the
    per-round-trip fetch volume.

    The generator must be fully consumed (or its `.close()` called)
    before another statement is issued on the same connection. Callers
    typically iterate it inline.
    """
    select_q = sql.SQL(
        "SELECT {pk}, doc_type, type, discipline_id, title "
        "FROM {tbl} "
        "WHERE doc_type IS NULL OR doc_type = '' "
        "   OR type     IS NULL OR type     = '' "
        "   OR discipline_id IS NULL"
    ).format(
        pk=sql.Identifier(pk),
        tbl=sql.Identifier(table),
    )
    cur = conn.cursor(name="classify_cur")
    try:
        cur.itersize = fetch_size
        cur.execute(select_q)
        for row in cur:
            yield row
    finally:
        cur.close()


def update_row(cur, table: str, pk: str, pk_value, writes: dict) -> bool:
    """Issue an UPDATE for the listed columns. Returns True if a
    statement was sent (i.e. ``writes`` was non-empty), False otherwise.

    The cursor is the caller's regular (non-server-side) cursor.
    """
    if not writes:
        return False
    cols = list(writes.keys())
    set_clause = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in cols
    )
    stmt = sql.SQL("UPDATE {tbl} SET {sets} WHERE {pk} = %s").format(
        tbl=sql.Identifier(table),
        sets=set_clause,
        pk=sql.Identifier(pk),
    )
    cur.execute(stmt, [*writes.values(), pk_value])
    return True
```

- [ ] **Step 2: Smoke-test importability**

Run: `python -c "from classifier.io.rds import iter_unclassified, update_row; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/classifier/io/rds.py
git commit -m "feat(io): psycopg2 read/write helpers with sql.Identifier safety"
```

---

## Task 6: Pipeline orchestrator — classify_from_rds

**Files:**
- Create: `src/classifier/pipeline/classify_rds.py`

- [ ] **Step 1: Create the orchestrator**

Create `src/classifier/pipeline/classify_rds.py`. This is the public API the calling pipeline will use.

```python
"""Classify and update unclassified rows in a PostgreSQL ``documents`` table.

Public API: ``classify_from_rds(conn, ...) -> stats``. See
``docs/superpowers/specs/2026-05-25-rds-pipeline-design.md`` §4.
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from pathlib import Path
from typing import Callable

from classifier.io.rds import iter_unclassified, update_row
from classifier.pipeline._row import (
    fill_discipline, fill_type, normalize_doc_type,
)

log = logging.getLogger("classifier.rds")

TYPE_KEYWORDS_PATH = Path("src/classifier/config/type_keywords.py")
DISCIPLINE_KEYWORDS_PATH = Path("src/classifier/config/discipline_keywords.py")
CLASSIFIED_CSV_DIR = Path("input/classified_csv")


def _stale_rule_warnings() -> list[str]:
    """Return a list of human-readable warnings for stale generated configs."""
    warnings: list[str] = []
    if not CLASSIFIED_CSV_DIR.exists():
        return warnings
    csv_mtimes = [p.stat().st_mtime for p in CLASSIFIED_CSV_DIR.rglob("*.csv")]
    if not csv_mtimes:
        return warnings
    newest_csv = max(csv_mtimes)
    if TYPE_KEYWORDS_PATH.exists() and newest_csv > TYPE_KEYWORDS_PATH.stat().st_mtime:
        warnings.append("type_keywords.py is older than training data; run learn-type-keywords")
    if DISCIPLINE_KEYWORDS_PATH.exists() and newest_csv > DISCIPLINE_KEYWORDS_PATH.stat().st_mtime:
        warnings.append("discipline_keywords.py is older than training data; run learn-discipline-keywords")
    return warnings


def _empty_stats() -> dict:
    return {
        "rows_scanned": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "doc_type":      Counter(),
        "type":          Counter(),
        "discipline_id": Counter(),
        "callback_error": None,
    }


def _finalize_stats(stats: dict) -> dict:
    """Convert internal Counters to plain dicts for caller convenience."""
    for k in ("doc_type", "type", "discipline_id"):
        stats[k] = dict(stats[k])
    return stats


def classify_from_rds(
    conn,
    *,
    table: str = "documents",
    pk: str = "document_id",
    commit_every: int = 500,
    fetch_size: int = 1000,
    on_done: Callable[[dict], None] | None = None,
) -> dict:
    """See spec §4. Caller owns the connection lifecycle."""
    for w in _stale_rule_warnings():
        log.warning(w)

    stats = _empty_stats()
    log.info("classify_from_rds start: table=%s pk=%s", table, pk)
    start = time.monotonic()

    write_cur = conn.cursor()
    try:
        for processed, row in enumerate(
            iter_unclassified(conn, table=table, pk=pk, fetch_size=fetch_size),
            start=1,
        ):
            pk_value, cur_doc_type, cur_type, cur_disc, title = row
            stats["rows_scanned"] += 1

            # Normalise None to "" so the pure helpers always see strings.
            cur_doc_type_s = "" if cur_doc_type is None else str(cur_doc_type)
            cur_type_s     = "" if cur_type     is None else str(cur_type)
            cur_disc_s     = "" if cur_disc     is None else str(cur_disc)
            title_s        = "" if title        is None else str(title)

            new_doc_type, dt_reason = normalize_doc_type(cur_doc_type_s, title_s)
            new_type,     t_reason  = fill_type(cur_type_s, title_s)
            new_disc,     d_reason  = fill_discipline(cur_disc_s, title_s)

            stats["doc_type"][dt_reason]      += 1
            stats["type"][t_reason]           += 1
            stats["discipline_id"][d_reason]  += 1

            writes: dict = {}

            # doc_type: write whenever the normalised value differs from
            # what's currently stored (handles both empty and alias cases).
            if new_doc_type != cur_doc_type_s.strip().lower():
                writes["doc_type"] = new_doc_type

            # type: only when existing was empty AND inference produced a value.
            if cur_type_s == "" and new_type != "":
                writes["type"] = new_type

            # discipline_id: only when existing was NULL AND inference hit.
            if cur_disc is None and new_disc != "":
                writes["discipline_id"] = int(new_disc)

            if update_row(write_cur, table=table, pk=pk, pk_value=pk_value, writes=writes):
                stats["rows_updated"] += 1
            else:
                stats["rows_skipped"] += 1

            if processed % commit_every == 0:
                conn.commit()
                elapsed = time.monotonic() - start
                rate = processed / elapsed if elapsed > 0 else 0.0
                log.info(
                    "progress: scanned=%d updated=%d elapsed=%.1fs rate=%.1f rows/s",
                    stats["rows_scanned"], stats["rows_updated"], elapsed, rate,
                )

        conn.commit()
    finally:
        write_cur.close()

    elapsed = time.monotonic() - start
    log.info(
        "done: scanned=%d updated=%d skipped=%d elapsed=%.1fs",
        stats["rows_scanned"], stats["rows_updated"], stats["rows_skipped"], elapsed,
    )

    stats = _finalize_stats(stats)

    if on_done is not None:
        try:
            on_done(stats)
        except Exception as e:  # callback isolation -- never propagate
            log.warning("on_done callback raised: %r", e)
            stats["callback_error"] = repr(e)

    return stats
```

- [ ] **Step 2: Smoke-test importability**

Run: `python -c "from classifier.pipeline.classify_rds import classify_from_rds; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/classifier/pipeline/classify_rds.py
git commit -m "feat(pipeline): classify_from_rds orchestrator"
```

---

## Task 7: CLI wrapper — classify-rds entry point

**Files:**
- Create: `src/classifier/cli/classify_rds.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the CLI wrapper**

Create `src/classifier/cli/classify_rds.py`:

```python
"""Console entry point: run classify_from_rds against env-var DSN.

Reads PGHOST / PGDATABASE / PGUSER / PGPASSWORD / PGPORT (optional)
from the environment, opens a connection, runs the pipeline, prints
the stats summary on completion. Real callers pass their own
connection -- this script is a convenience for ops / smoke runs.
"""
from __future__ import annotations

import logging
import os
import sys

import psycopg2

from classifier.pipeline.classify_rds import classify_from_rds


def _print_stats(stats: dict) -> None:
    print()
    print(f"scanned: {stats['rows_scanned']}")
    print(f"updated: {stats['rows_updated']}")
    print(f"skipped: {stats['rows_skipped']}")
    print(f"doc_type:      {stats['doc_type']}")
    print(f"type:          {stats['type']}")
    print(f"discipline_id: {stats['discipline_id']}")
    if stats.get("callback_error"):
        print(f"callback_error: {stats['callback_error']}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        conn = psycopg2.connect(
            host=os.environ["PGHOST"],
            dbname=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            port=os.environ.get("PGPORT", "5432"),
        )
    except KeyError as e:
        sys.exit(f"missing required env var: {e.args[0]}")

    try:
        classify_from_rds(conn, on_done=_print_stats)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Register the console script**

Modify [pyproject.toml](../../../pyproject.toml). Add to `[project.scripts]`:

```toml
classify-rds = "classifier.cli.classify_rds:main"
```

- [ ] **Step 3: Reinstall and smoke-test**

Run from project root:
```bash
pip install -e .
classify-rds
```
Expected with no `PGHOST` etc set: exits with `missing required env var: PGHOST`. (We are not testing against a real DB in this iteration; the smoke test confirms the entry point is wired correctly.)

- [ ] **Step 4: Commit**

```bash
git add src/classifier/cli/classify_rds.py pyproject.toml
git commit -m "feat(cli): classify-rds console script wired to classify_from_rds"
```

---

## Self-review checklist

Run through this once after all tasks are complete:

1. **Spec coverage:**
   - §3 architecture (modules created): Tasks 1, 2, 3, 4, 5, 6, 7 ✓
   - §4 public API + stats shape: Task 6 ✓
   - §4.2 commit_every counts processed rows: Task 6 step 1 ✓
   - §4.3 on_done exception isolation + callback_error: Task 6 step 1 ✓
   - §5 NULL-only at DB boundary: Task 6 step 1 ✓
   - §6.1 sql.Identifier safety: Task 5 ✓
   - §6.2 cursor.itersize: Task 5 ✓
   - §6.3 dynamic SET clause: Task 5 ✓
   - §6.5 indexing operational note: documented in spec only; no code task (correctly out-of-scope).
   - §7 shared per-row logic: Tasks 2 + 4 ✓
   - §8 discipline learner + scorer: Tasks 3 + 4 ✓
   - §9 CLI wrapper: Task 7 ✓
   - §10 logging: Task 6 ✓
   - §11 stale-rules warning: Task 6 ✓

2. **No placeholders:** No "TBD" / "implement later" / "similar to" references; all code blocks present.

3. **Type consistency:** `normalize_doc_type` / `fill_type` / `fill_discipline` all return `(str, str)`. `classify_from_rds` signature matches spec §4. `pick_discipline_with_overrides` returns the documented `{discipline_id, confidence, reason}` shape, consistent with how `fill_discipline` consumes it.
