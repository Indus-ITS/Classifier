"""Parse a Windows ``tree`` listing under TO CLIENT into file records."""
from __future__ import annotations

import re
from pathlib import Path

_FOLDER_MARK_RE = re.compile(r"(?:\+|\\)---")
_FILE_LINE_RE = re.compile(r"^([\s|]+)(\S.*)$")


def parse_transmittals(path) -> list:
    """Parse a Windows ``tree`` listing; return file records under TO CLIENT only."""
    text = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    start = None
    for i, ln in enumerate(text):
        if "TO CLIENT" in ln and "---" in ln:
            start = i
            break
    if start is None:
        return []

    records: list = []
    stack: list = []  # [(depth, name), ...]

    for raw in text[start + 1:]:
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _FOLDER_MARK_RE.search(line)
        if m:
            depth = m.start() // 4
            name = line[m.end():].strip()
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, name))
        else:
            mf = _FILE_LINE_RE.match(line)
            if not mf or not stack:
                continue
            fname = mf.group(2).strip()
            if fname == "|" or "---" in fname:
                continue
            submission = stack[0][1]
            nested = "/".join(n for _, n in stack[1:])
            full = submission + (("/" + nested) if nested else "") + "/" + fname
            records.append({
                "full_rel_path": full,
                "filename": fname,
                "submission_folder": submission,
                "subfolder": nested,
            })
    return records
