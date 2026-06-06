"""Pure prose-vs-grid text metric.

A genuine sheet is a grid of short cell tokens; a document carries
narrative paragraphs. text_ratio(lines) returns the fraction of
non-whitespace characters that live in "prose" lines — high for
documents, near zero for spreadsheets. No file I/O lives here.
"""
from __future__ import annotations

import re
from typing import Sequence

MIN_PROSE_WORDS: int = 6   # tunable: words needed before a line counts as prose

_WORD = re.compile(r"\S+")
_ALPHA = re.compile(r"[A-Za-z]")


def _is_wordy(token: str) -> bool:
    """A token that looks like a real word: >= 2 letters, not a pure code/number."""
    letters = len(_ALPHA.findall(token))
    return letters >= 2 and letters >= len(token) / 2


def is_prose_line(line: str) -> bool:
    """True iff the line reads like a sentence: enough wordy tokens, mostly words."""
    tokens = _WORD.findall(line)
    if len(tokens) < MIN_PROSE_WORDS:
        return False
    wordy = sum(1 for t in tokens if _is_wordy(t))
    return wordy >= len(tokens) / 2


def _nonws_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def text_ratio(lines: Sequence[str]) -> float:
    """Fraction of non-whitespace characters that belong to prose lines.

    Returns 0.0 when there is no non-whitespace content.
    """
    total = prose = 0
    for ln in lines:
        n = _nonws_len(ln)
        total += n
        if is_prose_line(ln):
            prose += n
    return (prose / total) if total else 0.0
