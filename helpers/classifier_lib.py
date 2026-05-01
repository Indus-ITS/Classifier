"""Document Classifier - Phase 1.

See docs/specs/2026-04-30-classifier-design.md for the design.
"""
from __future__ import annotations

# =========================================================================
# Section A - Project-agnostic core
# =========================================================================
# REFACTOR HINT: split here for core_classifier.py

import re
import unicodedata

import config

# Re-export tunables from config so the rest of this module stays clean.
BUCKETS = config.BUCKETS
KEYWORD_RULES = config.KEYWORD_RULES
TYPE_TO_BUCKET = config.TYPE_TO_BUCKET
BUCKET_PRIMARY_CODE = config.BUCKET_PRIMARY_CODE
CSV_COLUMNS = config.CSV_COLUMNS

_DASH_VARIANTS = "–—−‒"  # en-dash em-dash minus figure-dash
_DASH_TRANSLATE = str.maketrans({c: "-" for c in _DASH_VARIANTS})
_NBSP_TRANSLATE = str.maketrans({" ": " "})
_WS_RE = re.compile(r"\s+")


def normalise_filename(name: str) -> str:
    """Strip, NFKC-normalise, replace dash variants and NBSP, collapse whitespace."""
    s = name.strip()
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_DASH_TRANSLATE)
    s = s.translate(_NBSP_TRANSLATE)
    s = _WS_RE.sub(" ", s)
    return s


REF_RE = re.compile(config.REF_PATTERN)
CRS_RE = re.compile(config.CRS_PATTERN)
COVER_RE = re.compile(config.COVER_PATTERN)


def extract_ref(filename: str) -> "str | None":
    """Return the first \\d{2}-\\d{2}-\\d{2}-\\d{4} ref, or None."""
    m = REF_RE.search(filename)
    return m.group(1) if m else None


def is_crs_filename(filename: str) -> bool:
    """True if filename matches the empirically-tuned CRS pattern (spec section 6.1a)."""
    return CRS_RE.search(filename) is not None


def is_cover_filename(filename: str) -> bool:
    """True if filename starts with a transmittal cover prefix.
    Caller is responsible for the 'lacks ref' check."""
    return COVER_RE.search(filename) is not None


def _esc_ref(ref: str) -> str:
    return re.escape(ref)


def extract_letter_rev(filename: str, ref: "str | None") -> str:
    """Return parsed letter rev (single uppercase A-Z) or empty string."""
    if ref:
        m = re.search(rf"{_esc_ref(ref)}[ _\-]([A-Z])(?:[ _.\-]|$)", filename)
        if m:
            return m.group(1).upper()
    m = re.search(r"(?i)(?<![A-Za-z])IF[ARDCU][ _\-]?([A-Z])(?![A-Za-z])", filename)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?i)(?<![A-Za-z])REV[._ \-]?([A-Z])(?![A-Za-z])", filename)
    if m:
        return m.group(1).upper()
    return ""


def extract_numeric_rev(filename: str, ref: "str | None") -> str:
    """Return parsed numeric rev (1-99 as decimal string) or empty string."""
    if ref:
        m = re.search(rf"{_esc_ref(ref)}[ _\-](\d{{1,2}})(?:[ _.\-]|$)", filename)
        if m:
            return m.group(1)
    m = re.search(r"(?i)(?<![A-Za-z])IF[ARDCU][ _\-]?(\d{1,2})(?!\d)", filename)
    if m:
        return m.group(1)
    m = re.search(r"(?i)(?<![A-Za-z])REV[._ \-]?(\d{1,2})(?!\d)", filename)
    if m:
        return m.group(1)
    return ""


def extract_revs(filename: str, ref: "str | None") -> tuple:
    """Return (letter_rev, numeric_rev). Either may be empty."""
    return extract_letter_rev(filename, ref), extract_numeric_rev(filename, ref)


def inherit_rev_from_siblings(target: dict, siblings: list) -> tuple:
    """Tier-5 sibling rev inheritance.

    If target already has either rev, return target's existing pair unchanged.
    Otherwise look at siblings sharing submission_folder + subfolder + cust_ref.
    Numeric supersedes letter (per spec section 7.2). Within numeric, highest int.
    Within letter, lexicographic max.
    """
    if target.get("letter_rev") or target.get("numeric_rev"):
        return target.get("letter_rev", ""), target.get("numeric_rev", "")
    if not target.get("cust_ref"):
        return "", ""
    matches = [
        s for s in siblings
        if s is not target
        and s.get("cust_ref") == target.get("cust_ref")
        and s.get("submission_folder") == target.get("submission_folder")
        and s.get("subfolder", "") == target.get("subfolder", "")
        and (s.get("letter_rev") or s.get("numeric_rev"))
    ]
    if not matches:
        return "", ""
    numeric = [int(s["numeric_rev"]) for s in matches if s.get("numeric_rev")]
    if numeric:
        return "", str(max(numeric))
    letters = [s["letter_rev"] for s in matches if s.get("letter_rev")]
    if letters:
        return max(letters), ""
    return "", ""




# -----------------------------------------------------------------------
# Task 6 - bucket scoring
# -----------------------------------------------------------------------
def score_buckets(title: str, filename: str) -> dict:
    """For each bucket, return (score_sum, score_top).
    Underscores in the filename are treated as spaces so word-separator regex
    keywords match real-world `piping_and_instrument_diagram.pdf` style names.
    """
    text = (title + " " + filename).lower().replace("_", " ")
    out: dict = {}
    for bucket, rules in KEYWORD_RULES.items():
        s_sum = 0
        s_top = 0
        for pattern, weight in rules:
            for _ in re.finditer(pattern, text):
                s_sum += weight
                if weight > s_top:
                    s_top = weight
        out[bucket] = (s_sum, s_top)
    out.setdefault("CRS", (0, 0))
    out.setdefault("Documents", (0, 0))
    return out


# -----------------------------------------------------------------------
# Task 7 - pick bucket
# -----------------------------------------------------------------------
def pick_bucket(scores: dict) -> dict:
    """Pick winning bucket by score_sum (lex tiebreak), with runner-up + confidence."""
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    if not ranked:
        return {"bucket": "Documents", "score_sum": 0, "score_top": 0,
                "confidence": "low", "runner_up_bucket": "", "runner_up_score": 0}
    winner_name, (winner_sum, winner_top) = ranked[0]
    if winner_sum == 0:
        runner = next(((n, s) for n, s in ranked if n != "Documents"), ("", (0, 0)))
        return {"bucket": "Documents", "score_sum": 0, "score_top": 0,
                "confidence": "low",
                "runner_up_bucket": runner[0], "runner_up_score": runner[1][0]}
    if winner_top == 5:
        confidence = "high"
    elif winner_top in (3, 4):
        confidence = "medium"
    else:
        confidence = "low"
    runner = ranked[1] if len(ranked) > 1 else ("", (0, 0))
    return {
        "bucket": winner_name,
        "score_sum": winner_sum,
        "score_top": winner_top,
        "confidence": confidence,
        "runner_up_bucket": runner[0],
        "runner_up_score": runner[1][0],
    }


def fold_to_class(pick: dict, bucket_to_class: dict) -> str:
    """Fold a pick_bucket() result to the user-facing class label.

    Returns 'Undefined' when no keyword fired (score_sum == 0). Otherwise
    looks the picked bucket up in bucket_to_class. The Undefined branch
    keeps the fallthrough-to-Documents bucket from polluting the clean
    Drawings/Documents signal — those rows can be audited separately.
    """
    if pick["score_sum"] == 0:
        return "Undefined"
    return bucket_to_class[pick["bucket"]]


# -----------------------------------------------------------------------
# Task 8 - form resolution (two passes)
# -----------------------------------------------------------------------
def resolve_form_pre(filename: str, has_ref: bool):
    """Pass-1 form: Archive or CoverSheet, else None."""
    lower = filename.lower()
    if lower.endswith(".rar") or lower.endswith(".zip"):
        return "Archive"
    if (not has_ref) and is_cover_filename(filename):
        return "CoverSheet"
    return None


_DRAWING_EXTS = {".dwg", ".dgn"}
_SHEET_EXTS = {".xlsx", ".xls", ".xlsm"}
_DOC_EXTS = {".docx", ".doc"}


def resolve_form_post(filename: str, bucket: str) -> str:
    """Pass-2 form: extension-driven, with PDF disambiguated by bucket."""
    lower = filename.lower()
    ext = "." + lower.rsplit(".", 1)[1] if "." in lower else ""
    if ext in _DRAWING_EXTS:
        return "Drawing"
    if ext in _SHEET_EXTS:
        return "Sheet"
    if ext in _DOC_EXTS:
        return "Document"
    if ext == ".pdf":
        if bucket in {"Drawings", "Isometrics"}:
            return "Drawing"
        if bucket in {"Datasheets", "Lists_MTOs_BOMs"}:
            return "Sheet"
        return "Document"
    return "Document"


# -----------------------------------------------------------------------
# Task 13 - override loader (project-agnostic)
# -----------------------------------------------------------------------
import csv
from pathlib import Path


def load_overrides(path) -> dict:
    """Load overrides/ref_to_bucket.csv. Missing file -> empty dict."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict = {}
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = (row.get("cust_ref") or "").strip()
            bucket = (row.get("bucket") or "").strip()
            if ref and bucket:
                out[ref] = bucket
    return out


# -----------------------------------------------------------------------
# Task 14 - bundle id
# -----------------------------------------------------------------------
def assign_bundle_id(cust_ref: str, letter_rev: str, numeric_rev: str,
                     submission_folder: str) -> str:
    """Per spec section 8."""
    if cust_ref:
        if letter_rev and numeric_rev:
            return f"{cust_ref}__N{numeric_rev}L{letter_rev}"
        if numeric_rev:
            return f"{cust_ref}__N{numeric_rev}"
        if letter_rev:
            return f"{cust_ref}__L{letter_rev}"
        return f"{cust_ref}__R0"
    return f"unmatched__{submission_folder}"


# -----------------------------------------------------------------------
# Task 15 - is_latest per axis + combined precedence
# -----------------------------------------------------------------------
def compute_is_latest_for_group(rows: list) -> list:
    """Set is_latest_letter, is_latest_numeric, is_latest on each row in place.

    Numeric supersedes letter (per spec section 7.2): when any numeric_rev exists in the
    group, suppress is_latest_letter on every row (otherwise a stale letter-rev file
    would be reported as latest_letter even though it's been superseded by a numeric
    issue). When NO row has any rev (all-empty group), mark the lexicographically
    first source_path as is_latest=True so downstream "latest of each ref" filters
    don't silently drop the doc.
    """
    letters = [(i, r.get("letter_rev", "")) for i, r in enumerate(rows) if r.get("letter_rev")]
    letter_winner = max(letters, key=lambda x: x[1])[0] if letters else None
    numerics = [(i, int(r["numeric_rev"])) for i, r in enumerate(rows) if r.get("numeric_rev")]
    numeric_winner = max(numerics, key=lambda x: x[1])[0] if numerics else None
    has_any_numeric = numeric_winner is not None
    has_any_letter = letter_winner is not None

    if has_any_numeric:
        # Bug-2 fix: numeric supersedes letter. Suppress letter-axis flag on
        # everything, so a stale Rev C file isn't reported as is_latest_letter
        # when the doc has been promoted to Rev 1.
        effective_letter_winner = None
    else:
        effective_letter_winner = letter_winner

    if not has_any_numeric and not has_any_letter:
        # Bug-3 fix: zero parseable revs in this group. Mark the first row by
        # source_path as is_latest=True so the doc isn't dropped by downstream
        # filters. Tie-break is deterministic.
        sorted_idx = sorted(range(len(rows)),
                            key=lambda i: rows[i].get("source_path", ""))
        all_empty_winner = sorted_idx[0] if sorted_idx else None
    else:
        all_empty_winner = None

    for i, r in enumerate(rows):
        r["is_latest_letter"] = (i == effective_letter_winner)
        r["is_latest_numeric"] = (i == numeric_winner)
        if has_any_numeric:
            r["is_latest"] = r["is_latest_numeric"]
        elif has_any_letter:
            r["is_latest"] = r["is_latest_letter"]
        else:
            r["is_latest"] = (i == all_empty_winner)
    return rows


# -----------------------------------------------------------------------
# Task 16 - revision drift
# -----------------------------------------------------------------------
def classify_revision_drift(*, file_letter: str, file_numeric: str,
                            schedule_rev: str) -> str:
    """Per spec section 7.3 (v4 — pre_issue split out from cross_axis).

    States:
      aligned         - the relevant axis matches schedule
      disk_newer      - disk has higher rev on the schedule's axis
      schedule_newer  - schedule has higher rev on its axis (file is stale)
      pre_issue       - schedule says numeric (post-issue) but disk has only a
                        letter rev. This is the NORMAL state during the IFA review
                        cycle: the file is the active letter revision being
                        commented on, and the schedule has already recorded the
                        promoted numeric issue. Not actionable.
      cross_axis      - genuine inversion: schedule says letter, disk has only
                        numeric. Rare; means file was promoted but schedule wasn't
                        updated.
      unknown         - no schedule rev or both axes empty.
    """
    sched = schedule_rev.strip()
    if not sched:
        return "unknown"
    if not file_letter and not file_numeric:
        return "unknown"
    if sched.isdigit():
        if file_numeric:
            f, s = int(file_numeric), int(sched)
            if f == s:
                return "aligned"
            return "disk_newer" if f > s else "schedule_newer"
        # Schedule is post-issue numeric, disk has only letter -> normal pre-issue.
        return "pre_issue"
    if len(sched) == 1 and sched.isalpha():
        sched_u = sched.upper()
        if file_letter:
            if file_letter == sched_u:
                return "aligned"
            return "disk_newer" if file_letter > sched_u else "schedule_newer"
        # Schedule says letter but disk has numeric -> genuine inversion.
        return "cross_axis"
    return "unknown"


# -----------------------------------------------------------------------
# Task 17 - target paths + collisions
# -----------------------------------------------------------------------
_TITLE_SANITISE_RE = re.compile(r"[^A-Za-z0-9]+")


def _sanitise_title(title: str, max_len: int = 60) -> str:
    s = _TITLE_SANITISE_RE.sub("_", title.upper()).strip("_")
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


def _rev_token(letter_rev: str, numeric_rev: str) -> str:
    if letter_rev and numeric_rev:
        return f"N{numeric_rev}L{letter_rev}"
    if numeric_rev:
        return f"N{numeric_rev}"
    if letter_rev:
        return f"L{letter_rev}"
    return "R0"


def build_target_paths(*, cust_ref: str, letter_rev: str, numeric_rev: str,
                       type_code: str, form: str, bucket: str, discipline: str,
                       title: str, extension: str,
                       submission_folder: str, source_filename: str) -> dict:
    """Per spec section 9."""
    folder = f"{form}/{bucket}/{discipline}/"
    if not cust_ref:
        return {
            "proposed_target_folder": folder,
            "proposed_target_filename": f"{submission_folder}__{source_filename}",
        }
    rev = _rev_token(letter_rev, numeric_rev)
    short = _sanitise_title(title)
    base = f"{cust_ref}_{rev}_{type_code}_{short}" if short else f"{cust_ref}_{rev}_{type_code}"
    return {
        "proposed_target_folder": folder,
        "proposed_target_filename": base + extension,
    }


def detect_target_collisions(rows: list) -> None:
    """Sets `target_collision` on every row; appends colliding peers to `notes`."""
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for r in rows:
        key = (r.get("proposed_target_folder", ""), r.get("proposed_target_filename", ""))
        buckets[key].append(r)
    for key, group in buckets.items():
        if len(group) > 1:
            ids = [g.get("bundle_id", "") for g in group]
            for r in group:
                r["target_collision"] = True
                peers = [b for b in ids if b != r.get("bundle_id")]
                note = "collision_with=" + ",".join(peers)
                r["notes"] = (r.get("notes", "") + (" | " if r.get("notes") else "") + note).strip()
        else:
            for r in group:
                r["target_collision"] = False


# -----------------------------------------------------------------------
# Discipline keyword tier (rules in config.DISCIPLINE_KEYWORD_RULES)
# -----------------------------------------------------------------------
def discipline_from_keywords(text: str) -> str:
    t = text.lower().replace("_", " ")
    for pattern, disc in config.DISCIPLINE_KEYWORD_RULES:
        if re.search(pattern, t):
            return disc
    return ""


def _csv_value(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return ""
    return str(v)


def write_csv(rows: list, path) -> None:
    """Write classified rows to CSV (33 columns)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for r in rows:
            writer.writerow([_csv_value(r.get(col, "")) for col in CSV_COLUMNS])


# =========================================================================
# Section B - Project-specific enrichment (Sahil-CDS schedule + dossier)
# =========================================================================
# REFACTOR HINT: split here for sahil_enrichment.py

import pandas as pd
from collections import Counter, defaultdict


# Task 9 - schedule loader
def load_schedule(path) -> pd.DataFrame:
    """Load schedule xls Sheet1 -> DataFrame with normalised columns."""
    df = pd.read_excel(path, sheet_name="Sheet1")
    df = df.dropna(subset=["Cust Ref #", "Title", "Discip"]).copy()
    df["cust_ref"] = df["Cust Ref #"].astype(str).str.strip()
    df = df[df["cust_ref"].str.match(r"\d{2}-\d{2}-\d{2}-\d{4}")].copy()
    df["pcs_doc_no"] = df["PCS Doc No."].astype(str).str.strip()
    df["title"] = df["Title"].astype(str).str.strip()
    df["discipline"] = df["Discip"].astype(str).str.strip()
    df["schedule_rev"] = df["Rev."].fillna("").astype(str).str.strip()
    df["seg2"] = df["cust_ref"].str.split("-").str[2]
    return df[["cust_ref", "pcs_doc_no", "title", "discipline",
               "schedule_rev", "seg2"]].reset_index(drop=True)


# Task 10 - dossier loader
def load_dossier(path) -> pd.DataFrame:
    """Load dossier xlsx PDF sheet -> normalised DataFrame."""
    df = pd.read_excel(path, sheet_name="PDF", header=4)
    df.columns = ["doc_no", "title", "rev", "status", "type_code",
                  "pdf", "volume", "book"]
    df = df[df["title"].notna() & df["type_code"].notna()
            & (df["type_code"] != "Type")].copy()
    df["doc_no"] = df["doc_no"].astype(str).str.strip()
    df["title"] = df["title"].astype(str).str.strip()
    df["type_code"] = df["type_code"].astype(str).str.strip()
    df["rev"] = df["rev"].fillna("").astype(str).str.strip()
    df["status"] = df["status"].fillna("").astype(str).str.strip()
    return df[["doc_no", "title", "rev", "status", "type_code",
               "volume"]].reset_index(drop=True)


# Task 11 - tree parser
_FOLDER_MARK_RE = re.compile(r"(?:\+|\\)---")
_FILE_LINE_RE = re.compile(r"^([\s|]+)(\S.*)$")


def parse_transmittals(path) -> list:
    """Parse a Windows `tree` listing; return file records under TO CLIENT only."""
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


# Task 12 part 2 - seg2 map + discipline chain
def build_seg2_discipline_map(schedule_df: pd.DataFrame) -> dict:
    out: dict = {}
    for seg2, grp in schedule_df.groupby("seg2"):
        out[seg2] = grp["discipline"].value_counts().idxmax()
    return out


def derive_discipline(*, cust_ref: str, title: str, filename: str,
                      schedule_lookup: dict, seg2_map: dict,
                      submission_majority: str,
                      multi_disc_submission: bool) -> str:
    """5-tier discipline chain (spec section 6.3)."""
    if cust_ref and cust_ref in schedule_lookup:
        return schedule_lookup[cust_ref]
    if cust_ref:
        seg2 = cust_ref.split("-")[2] if "-" in cust_ref else ""
        if seg2 in seg2_map:
            return seg2_map[seg2]
    kw = discipline_from_keywords(title + " " + filename)
    if kw:
        return kw
    if submission_majority and not multi_disc_submission:
        return submission_majority
    return "UNK"


# =========================================================================
# Section C - Orchestration / CLI
# =========================================================================
import sys
import argparse


def enrich_files(*, schedule_path, dossier_path, tree_path,
                 overrides_path) -> list:
    """Run the full Phase-1 pipeline. Returns list of populated row dicts."""
    schedule_df = load_schedule(schedule_path)
    dossier_df = load_dossier(dossier_path)
    raw = parse_transmittals(tree_path)
    overrides = load_overrides(overrides_path)

    schedule_disc = {r["cust_ref"]: r["discipline"] for _, r in schedule_df.iterrows()}
    schedule_rev = {r["cust_ref"]: r["schedule_rev"] for _, r in schedule_df.iterrows()}
    schedule_title = {r["cust_ref"]: r["title"] for _, r in schedule_df.iterrows()}
    schedule_pcs = {r["cust_ref"]: r["pcs_doc_no"] for _, r in schedule_df.iterrows()}
    seg2_map = build_seg2_discipline_map(schedule_df)
    dossier_by_doc = {r["doc_no"]: r for _, r in dossier_df.iterrows()}

    # Pass 1: per-record extraction
    rows: list = []
    for r in raw:
        original = r["filename"]
        norm = normalise_filename(original)
        cust_ref = extract_ref(norm) or ""
        letter, numeric = extract_revs(norm, cust_ref or None)
        ext = ("." + norm.rsplit(".", 1)[1].lower()) if "." in norm else ""
        rows.append({
            "source_path": r["full_rel_path"],
            "source_filename": original,
            "_norm_filename": norm,
            "submission_folder": r["submission_folder"],
            "subfolder": r["subfolder"],
            "cust_ref": cust_ref,
            "is_crs": is_crs_filename(norm),
            "is_transmittal_cover": (not cust_ref) and is_cover_filename(norm),
            "is_archive": ext in {".rar", ".zip"},
            "letter_rev": letter,
            "numeric_rev": numeric,
            "extension": ext,
            "notes": "",
        })

    # Pass 2: sibling rev inheritance
    by_sub_sub = defaultdict(list)
    for r in rows:
        by_sub_sub[(r["submission_folder"], r["subfolder"])].append(r)
    for r in rows:
        if r["letter_rev"] or r["numeric_rev"] or not r["cust_ref"]:
            continue
        siblings = by_sub_sub[(r["submission_folder"], r["subfolder"])]
        l, n = inherit_rev_from_siblings(r, siblings)
        if l or n:
            r["letter_rev"] = l
            r["numeric_rev"] = n
            r["notes"] = (r["notes"] + (" | " if r["notes"] else "")
                          + "rev_inherited_from_sibling").strip()

    # Per-submission discipline majority
    sub_disciplines = defaultdict(list)
    for r in rows:
        if r["cust_ref"] and r["cust_ref"] in schedule_disc:
            sub_disciplines[r["submission_folder"]].append(schedule_disc[r["cust_ref"]])
    sub_majority: dict = {}
    multi_disc: dict = {}
    for sub, ds in sub_disciplines.items():
        c = Counter(ds)
        sub_majority[sub] = c.most_common(1)[0][0] if c else ""
        multi_disc[sub] = len(c) > 2

    # Pass 3: classify
    for r in rows:
        norm = r.pop("_norm_filename")
        cust_ref = r["cust_ref"]
        title = schedule_title.get(cust_ref, "")
        type_code_dossier = ""
        if cust_ref in dossier_by_doc:
            if not title:
                title = dossier_by_doc[cust_ref]["title"]
            type_code_dossier = dossier_by_doc[cust_ref]["type_code"]
        r["title"] = title
        r["pcs_doc_no"] = schedule_pcs.get(cust_ref, "")
        r["schedule_rev"] = schedule_rev.get(cust_ref, "")

        if cust_ref and cust_ref in overrides:
            bucket = overrides[cust_ref]
            bucket_source = "override"
            confidence = "high"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif r["is_archive"]:
            bucket = "Documents"
            bucket_source = "archive"
            confidence = "low"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif r["is_transmittal_cover"]:
            bucket = "Documents"
            bucket_source = "cover_sheet"
            confidence = "low"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif r["is_crs"]:
            bucket = "CRS"
            bucket_source = "crs_pin"
            confidence = "high"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif type_code_dossier and type_code_dossier in TYPE_TO_BUCKET:
            bucket = TYPE_TO_BUCKET[type_code_dossier]
            bucket_source = "dossier_type"
            confidence = "high"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        else:
            scores = score_buckets(title, norm)
            picked = pick_bucket(scores)
            bucket = picked["bucket"]
            bucket_source = "weighted" if picked["score_sum"] > 0 else "fallback"
            confidence = picked["confidence"]
            score_sum, score_top = picked["score_sum"], picked["score_top"]
            runner_up = picked["runner_up_bucket"]
            runner_score = picked["runner_up_score"]

        r["type_bucket"] = bucket
        r["bucket_source"] = bucket_source
        r["bucket_confidence"] = confidence
        r["bucket_score"] = score_sum
        r["runner_up_bucket"] = runner_up
        r["runner_up_score"] = runner_score

        pre = resolve_form_pre(norm, has_ref=bool(cust_ref))
        r["form"] = pre if pre else resolve_form_post(norm, bucket)

        r["type_code"] = type_code_dossier or BUCKET_PRIMARY_CODE[bucket]

        sub = r["submission_folder"]
        r["discipline"] = derive_discipline(
            cust_ref=cust_ref, title=title, filename=norm,
            schedule_lookup=schedule_disc, seg2_map=seg2_map,
            submission_majority=sub_majority.get(sub, ""),
            multi_disc_submission=multi_disc.get(sub, False),
        )

        r["bundle_id"] = assign_bundle_id(cust_ref, r["letter_rev"],
                                          r["numeric_rev"], sub)

        if cust_ref and cust_ref in schedule_disc:
            r["match_status"] = "matched"
        elif cust_ref and cust_ref in dossier_by_doc:
            r["match_status"] = "ref_in_dossier_only"
        elif cust_ref:
            r["match_status"] = "ref_unknown"
        elif r["is_transmittal_cover"]:
            r["match_status"] = "cover_sheet"
        elif r["is_archive"]:
            r["match_status"] = "archive"
        elif r["is_crs"]:
            r["match_status"] = "crs_orphan"
        else:
            r["match_status"] = "attachment"

    # Pass 4: is_latest per ref
    by_ref = defaultdict(list)
    for r in rows:
        if r["cust_ref"]:
            by_ref[r["cust_ref"]].append(r)
    for group in by_ref.values():
        compute_is_latest_for_group(group)
    for r in rows:
        if not r["cust_ref"]:
            r.setdefault("is_latest_letter", False)
            r.setdefault("is_latest_numeric", False)
            r.setdefault("is_latest", False)

    # Pass 5: revision drift
    for r in rows:
        r["revision_drift"] = classify_revision_drift(
            file_letter=r["letter_rev"], file_numeric=r["numeric_rev"],
            schedule_rev=r["schedule_rev"],
        )

    # Pass 6: target paths
    for r in rows:
        tp = build_target_paths(
            cust_ref=r["cust_ref"], letter_rev=r["letter_rev"],
            numeric_rev=r["numeric_rev"], type_code=r["type_code"],
            form=r["form"], bucket=r["type_bucket"], discipline=r["discipline"],
            title=r["title"], extension=r["extension"],
            submission_folder=r["submission_folder"],
            source_filename=r["source_filename"],
        )
        r.update(tp)

    # Pass 7: collisions
    detect_target_collisions(rows)

    # Pass 8: deterministic sort - by source_path. This makes CSV output stable
    # across runs regardless of upstream parse-order changes (idempotency).
    rows.sort(key=lambda r: r.get("source_path", ""))

    return rows


def write_audit(*, rows: list, schedule_df, override_count: int,
                override_unknown_refs: list, path) -> None:
    """Write audit text per spec section 10."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _count(field: str) -> Counter:
        return Counter(r.get(field, "") for r in rows)

    lines: list = []
    lines.append("=== Counts ===")
    lines.append(f"Total files: {len(rows)}")
    for field in ("match_status", "bucket_confidence", "bucket_source", "form",
                  "revision_drift"):
        lines.append(f"\nBy {field}:")
        counts = _count(field).most_common()
        total = sum(c for _, c in counts)
        for k, c in counts:
            pct = (c / total * 100) if total else 0
            lines.append(f"  {k or '(empty)'}: {c}  ({pct:.1f}%)")

    # Watch for revision_drift mix shifts across runs.
    drift = _count("revision_drift")
    pre_issue_pct = (drift.get("pre_issue", 0) / max(1, sum(drift.values()))) * 100
    actionable = drift.get("schedule_newer", 0) + drift.get("cross_axis", 0)
    lines.append(
        f"\nRevision drift summary: pre_issue dominates at {pre_issue_pct:.1f}% "
        f"(normal during IFA review); {actionable} actionable rows "
        f"(schedule_newer + cross_axis)."
    )

    lines.append("\n=== Bucket x discipline matrix ===")
    matrix = Counter((r.get("type_bucket", ""), r.get("discipline", "")) for r in rows)
    bs = sorted({b for (b, _) in matrix})
    ds = sorted({d for (_, d) in matrix})
    lines.append("bucket".ljust(20) + " | " + " | ".join(d.rjust(8) for d in ds))
    for b in bs:
        cells = [str(matrix.get((b, d), 0)).rjust(8) for d in ds]
        lines.append(b.ljust(20) + " | " + " | ".join(cells))

    lines.append("\n=== Schedule coverage ===")
    if schedule_df is not None and len(schedule_df):
        present = {r["cust_ref"] for r in rows if r.get("cust_ref")}
        missing = [ref for ref in schedule_df["cust_ref"] if ref not in present]
        lines.append(f"Schedule docs with files: "
                     f"{len(schedule_df) - len(missing)} / {len(schedule_df)}")
        lines.append(f"Schedule docs WITHOUT files: {len(missing)}")
        for ref in missing[:50]:
            lines.append(f"  - {ref}")
        if len(missing) > 50:
            lines.append(f"  ... and {len(missing) - 50} more")
    else:
        lines.append("(no schedule loaded)")

    lines.append("\n=== Refs not in schedule ===")
    if schedule_df is not None and len(schedule_df):
        sched_refs = set(schedule_df["cust_ref"])
        unknown = sorted({r["cust_ref"] for r in rows
                          if r.get("cust_ref") and r["cust_ref"] not in sched_refs})
        lines.append(f"Count: {len(unknown)}")
        for ref in unknown[:50]:
            lines.append(f"  - {ref}")
        if len(unknown) > 50:
            lines.append(f"  ... and {len(unknown) - 50} more")

    lines.append("\n=== Fallthrough (bucket_source=fallback, score=0) ===")
    fallthrough = [r for r in rows if r.get("bucket_source") == "fallback"]
    titled = [r for r in fallthrough if r.get("title", "").strip()]
    untitled = [r for r in fallthrough if not r.get("title", "").strip()]
    lines.append(f"Total: {len(fallthrough)}  "
                 f"(with title: {len(titled)} - regex-tunable; "
                 f"without title: {len(untitled)} - inherently unclassifiable from filename alone)")
    lines.append("\nTitled fallthroughs (improve KEYWORD_RULES to capture):")
    for r in titled[:80]:
        lines.append(f"  [{r.get('discipline','UNK')}] {r.get('title','')} :: "
                     f"{r.get('source_filename','')}")
    if len(titled) > 80:
        lines.append(f"  ... and {len(titled) - 80} more")
    lines.append("\nUntitled fallthroughs (attachments / appendices; need parent inheritance to classify):")
    for r in untitled[:30]:
        lines.append(f"  [{r.get('discipline','UNK')}] {r.get('source_filename','')} "
                     f"({r.get('submission_folder','')})")
    if len(untitled) > 30:
        lines.append(f"  ... and {len(untitled) - 30} more")

    lines.append("\n=== Ambiguous classifications (gap <= 1) ===")
    ambig = [r for r in rows
             if isinstance(r.get("bucket_score"), int)
             and isinstance(r.get("runner_up_score"), int)
             and r["bucket_score"] > 0
             and r["bucket_score"] - r["runner_up_score"] <= 1]
    lines.append(f"Count: {len(ambig)}")
    for r in ambig[:30]:
        lines.append(f"  {r.get('cust_ref','')} {r.get('type_bucket','')}"
                     f"({r['bucket_score']}) vs "
                     f"{r.get('runner_up_bucket','')}({r['runner_up_score']}): "
                     f"{r.get('title','')[:80]}")

    lines.append("\n=== Revision drift ===")
    drift_counts = _count("revision_drift")
    for k, c in drift_counts.most_common():
        lines.append(f"  {k}: {c}")
    actionable = [r for r in rows
                  if r.get("revision_drift") in ("schedule_newer", "cross_axis")]
    if actionable:
        lines.append("\nActionable (schedule_newer or cross_axis - investigate):")
        for r in actionable[:50]:
            lines.append(f"  {r.get('cust_ref','')}  drift={r.get('revision_drift','')}"
                         f"  file=L{r.get('letter_rev','')}/N{r.get('numeric_rev','')}"
                         f"  sched={r.get('schedule_rev','')}")
    else:
        lines.append("\nNo actionable drift (no schedule_newer or cross_axis rows).")
    lines.append("Note: pre_issue is NORMAL during IFA review cycles, not drift.")

    lines.append("\n=== Multi-discipline submissions ===")
    sd: dict = defaultdict(set)
    for r in rows:
        if r.get("discipline") and r["discipline"] != "UNK":
            sd[r["submission_folder"]].add(r["discipline"])
    multi = {s: ds_ for s, ds_ in sd.items() if len(ds_) > 2}
    lines.append(f"Count: {len(multi)}")
    for s, ds_ in list(multi.items())[:30]:
        lines.append(f"  {s}: {sorted(ds_)}")

    lines.append("\n=== Target collisions ===")
    coll = [r for r in rows if r.get("target_collision")]
    lines.append(f"Count: {len(coll)} rows in collision groups")
    seen: set = set()
    for r in coll[:30]:
        key = (r.get("proposed_target_folder", ""), r.get("proposed_target_filename", ""))
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  {key[0]}{key[1]}")

    lines.append("\n=== Override hits ===")
    lines.append(f"Overrides applied: {override_count}")
    if override_unknown_refs:
        lines.append("Overrides with unknown refs (no effect):")
        for ref in override_unknown_refs:
            lines.append(f"  override defined for unknown ref {ref} - no effect")

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_dossier_selftest(dossier_path, out_path) -> dict:
    """Classify each dossier row by title alone vs known Type. Writes report."""
    df = load_dossier(dossier_path)
    total = len(df)
    correct = 0
    mismatches: list = []
    confusion: dict = defaultdict(int)
    for _, r in df.iterrows():
        expected = TYPE_TO_BUCKET.get(r["type_code"], "Documents")
        scores = score_buckets(r["title"], "")
        picked = pick_bucket(scores)
        predicted = picked["bucket"]
        confusion[(expected, predicted)] += 1
        if predicted == expected:
            correct += 1
        else:
            mismatches.append({"type_code": r["type_code"], "expected": expected,
                               "predicted": predicted, "title": r["title"]})
    acc = correct / total if total else 1.0

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list = []
    lines.append("=== Dossier self-test ===")
    lines.append(f"Total: {total}")
    lines.append(f"Correct: {correct}")
    lines.append(f"Accuracy: {acc:.4f} ({correct}/{total})")
    lines.append("\n=== Confusion (expected -> predicted): count ===")
    for (e, p_), c in sorted(confusion.items(), key=lambda x: -x[1]):
        marker = " " if e == p_ else "*"
        lines.append(f"  {marker} {e:18} -> {p_:18} : {c}")
    lines.append("\n=== Mismatches ===")
    for m in mismatches:
        lines.append(f"  type={m['type_code']:5} expected={m['expected']:18} "
                     f"predicted={m['predicted']:18} title={m['title'][:90]}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"accuracy": acc, "total": total, "correct": correct,
            "mismatches": mismatches}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Document classifier (Phase 1). "
        "Defaults read from config.py; override on the command line as needed."
    )
    parser.add_argument("--schedule", default=config.SCHEDULE_PATH)
    parser.add_argument("--dossier", default=config.DOSSIER_PATH)
    parser.add_argument("--tree", default=config.TREE_PATH)
    parser.add_argument("--overrides", default=config.OVERRIDES_PATH)
    parser.add_argument("--output-dir", default=config.OUTPUT_DIR)
    parser.add_argument("--no-selftest", action="store_true",
                        help="Skip the dossier-selftest CI gate.")
    parser.add_argument("--gate-threshold", type=float,
                        default=config.GATE_THRESHOLD,
                        help=f"Min selftest accuracy (default {config.GATE_THRESHOLD}).")
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    overrides = load_overrides(args.overrides)
    schedule_df = load_schedule(args.schedule)
    sched_refs = set(schedule_df["cust_ref"])
    override_unknown = [ref for ref in overrides if ref not in sched_refs]

    rows = enrich_files(
        schedule_path=args.schedule, dossier_path=args.dossier,
        tree_path=args.tree, overrides_path=args.overrides,
    )

    write_csv(rows, out_dir / "classified_files.csv")
    write_audit(
        rows=rows, schedule_df=schedule_df,
        override_count=sum(1 for r in rows if r.get("bucket_source") == "override"),
        override_unknown_refs=override_unknown,
        path=out_dir / "classification_audit.txt",
    )

    if not args.no_selftest:
        result = run_dossier_selftest(args.dossier,
                                      out_dir / "dossier_selftest.txt")
        if result["accuracy"] < args.gate_threshold:
            print(f"FAIL: dossier-selftest accuracy {result['accuracy']:.4f} "
                  f"below gate {args.gate_threshold:.4f}", file=sys.stderr)
            return 1
        print(f"OK: dossier-selftest accuracy {result['accuracy']:.4f} "
              f">= gate {args.gate_threshold:.4f}")

    print(f"OK: {len(rows)} rows -> {out_dir / 'classified_files.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
