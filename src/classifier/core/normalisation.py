"""Filename normalisation: NFKC, dash variants, NBSP, whitespace collapse."""
from __future__ import annotations

import re
import unicodedata

_DASH_VARIANTS = "–—−‒"  # en-dash em-dash minus figure-dash
_DASH_TRANSLATE = str.maketrans({c: "-" for c in _DASH_VARIANTS})
_NBSP_TRANSLATE = str.maketrans({" ": " "})
_WS_RE = re.compile(r"\s+")


def normalise_filename(name: str) -> str:
    """Strip, NFKC-normalise, replace dash variants and NBSP, collapse whitespace."""
    s = name.strip()
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_DASH_TRANSLATE)
    s = s.translate(_NBSP_TRANSLATE)
    s = _WS_RE.sub(" ", s)
    return s
