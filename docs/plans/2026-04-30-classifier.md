# Document Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 1 of the classifier (per `docs/specs/2026-04-30-classifier-design.md`): a Python script that reads `4. List of DOC + Schedule (Correct doc).xls`, `50703-EPC Dossier Index - PDF (Updated on 27-03-2014).xlsx`, and `Transmittals.txt`, and writes `output/classified_files.csv` (33 columns, one row per file under `TO CLIENT`), `output/classification_audit.txt`, and `output/dossier_selftest.txt` (with a CI gate). No file copying; no archive extraction; `FROM CLIENT` ignored.

**Architecture:** Single Python file `classifier.py`, sectioned A/B/C with `# REFACTOR HINT: split here` markers (Section A — project-agnostic core: filename normalisation, ref/rev extraction, form, weighted bucket scoring, bundles, collisions, output writers; Section B — project-specific enrichment: schedule + dossier loaders, seg2-discipline map, dossier CI self-test; Section C — orchestration: `main()`). Pytest test suite alongside in `tests/`. TDD discipline: each function gets a failing test before code. Frequent commits.

**Tech Stack:** Python 3.13 (existing `.venv/`), `pandas`, `openpyxl`, `xlrd`, `pytest`. Stdlib `re`, `pathlib`, `csv`, `collections`, `unicodedata`, `argparse`, `dataclasses`.

---

## File structure (locked in before tasks)

| Path | Responsibility | Created in |
|---|---|---|
| `classifier.py` | Main script: all pipeline functions + CLI | Task 1 onward |
| `tests/__init__.py` | Empty marker | Task 0 |
| `tests/conftest.py` | Pytest fixtures: tiny synthetic data + paths to real fixtures | Task 0 |
| `tests/fixtures/sample_schedule.xls` | 6-row excerpt of real schedule for integration tests | Task 0 |
| `tests/fixtures/sample_dossier.xlsx` | 6-row excerpt of real dossier | Task 0 |
| `tests/fixtures/sample_transmittals.txt` | Hand-crafted small tree covering matched/CRS/cover/archive/attachment/em-dash/REV-A cases | Task 0 |
| `tests/test_normalise.py` | Filename normalisation tests | Task 1 |
| `tests/test_extract.py` | Ref + CRS + cover + rev extraction tests | Tasks 2-4 |
| `tests/test_classify.py` | Bucket scoring/picking + form + discipline tests | Tasks 5-8, 12 |
| `tests/test_loaders.py` | Schedule, dossier, transmittals, overrides loaders | Tasks 9-11, 13 |
| `tests/test_pipeline.py` | bundle id, is_latest, drift, target paths, collisions | Tasks 14-17 |
| `tests/test_writers.py` | CSV + audit + self-test outputs | Tasks 19-21 |
| `tests/test_integration.py` | End-to-end run + acceptance criteria | Task 23 |
| `requirements.txt` | Pinned deps | Task 0 |
| `.gitignore` | Already exists; expanded in Task 0 | Task 0 |
| `overrides/ref_to_bucket.csv` | User-editable bucket overrides; created empty | Task 13 |
| `output/` | Created at runtime; ignored in git | Task 0 |

---

## Task 0: Bootstrap

**Files:**
- Create: `requirements.txt`
- Modify: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/sample_transmittals.txt`
- Generate: `tests/fixtures/sample_schedule.xls`
- Generate: `tests/fixtures/sample_dossier.xlsx`
- Create: `output/.gitkeep`
- Create: `overrides/.gitkeep`

- [ ] **Step 1: Init git repo (no remote)**

```bash
cd /c/Users/MrError/Desktop/classifier
git init
git config user.email "kamran@industechsol.com"
git config user.name "Kamran"
```

- [ ] **Step 2: Expand .gitignore**

```bash
cat > .gitignore <<'EOF'
.venv/
__pycache__/
*.pyc
.pytest_cache/
output/*
!output/.gitkeep
.idea/
.vscode/
*.tmp
sample_test.py
sample_test2.py
sample_test3.py
EOF
```

- [ ] **Step 3: Write requirements.txt**

```
pandas>=2.0
openpyxl>=3.1
xlrd>=2.0
pytest>=7.4
```

- [ ] **Step 4: Install deps**

```bash
.venv/Scripts/pip install -r requirements.txt
```

Expected: pytest installs alongside existing pandas/openpyxl/xlrd.

- [ ] **Step 5: Create directories and gitkeep files**

```bash
mkdir -p tests/fixtures output overrides
touch tests/__init__.py output/.gitkeep overrides/.gitkeep
```

- [ ] **Step 6: Hand-craft `tests/fixtures/sample_transmittals.txt`**

```
Folder PATH listing for volume Volume
Volume serial number is 0000-0000
D:.
|   Transmittals.txt
|
+---FROM CLIENT
|   +---APDRC-ED-SA-15760-01-001
|   |       APDRC-ED-SA-15760.01-001.pdf
|   |
\---TO CLIENT
    +---C-A-ED-SA-15760.01-0068
    |       16-01-39-2602-A.pdf
    |       16-01-39-2602_A.docx
    |       CRS-16-01-39-2602 REV-A.xlsx
    |
    +---C-A-ED-SA-15760.01-0069
    |       16-01-27-2604-B.pdf
    |       16-01-27-2604_B.docx
    |       16-01-27-2604_1.pdf
    |
    +---C-A-ED-SA-15760.01-0070
    |   |   16-01-23-2602-A.pdf
    |   |   CTA-ED-SA-15760.01.070.pdf
    |   |   CAD Files.rar
    |   |
    |   \---CAD FILES
    |           16-01-23-2602-A.dwg
    |
    +---C-A-ED-SA-15760.01-0071
    |       Comment Response Sheet-16-01-40-2607.xlsx
    |       Attachment-1.pdf
    |       16–01–84–2602-A.pdf
    |
```

(Note: line 4 from bottom uses em-dashes `–` to test normalisation. CRS pattern `CRS-...REV-A` covers the dominant CRS form. Cover sheet `CTA-...` and archive `CAD Files.rar` are present. Comment Response Sheet variant present. `Attachment-1.pdf` is a ref-less attachment.)

- [ ] **Step 7: Generate small Excel fixtures from real files**

Create script `tests/fixtures/_make_fixtures.py`:

```python
"""Generate small Excel fixtures by sampling the real input files."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

# Schedule: take 6 rows covering the disciplines we need in tests.
sched = pd.read_excel(ROOT / "4. List of DOC + Schedule (Correct doc).xls", sheet_name="Sheet1")
wanted_refs = ["16-01-39-2602", "16-01-27-2604", "16-01-23-2602", "16-01-19-2602",
               "16-01-84-2602", "16-99-91-2632"]
small = sched[sched["Cust Ref #"].astype(str).isin(wanted_refs)].copy()
small.to_excel(Path(__file__).parent / "sample_schedule.xls", sheet_name="Sheet1", index=False, engine="openpyxl")

# Dossier: take 6 rows covering several Type codes.
doss = pd.read_excel(ROOT / "50703-EPC Dossier Index - PDF (Updated on 27-03-2014).xlsx",
                     sheet_name="PDF", header=4)
doss.columns = ["DocNo", "Title", "Rev", "Status", "Type", "PDF", "VOLUME", "BOOK"]
doss = doss[doss["Type"].notna() & (doss["Type"] != "Type")]
small_d = doss.groupby("Type").head(1).head(8).copy()
# write back with same header position (4 blank rows then real header) so loader can be tested as-is
out = Path(__file__).parent / "sample_dossier.xlsx"
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "PDF"
for _ in range(4):
    ws.append([""] * 8)
ws.append(["Document No.", "Title", "Rev.", "Status", "Type", "PDF", "VOLUME", "BOOK"])
for _, r in small_d.iterrows():
    ws.append([r["DocNo"], r["Title"], r["Rev"], r["Status"], r["Type"], r["PDF"], r["VOLUME"], r["BOOK"]])
wb.save(out)
print("Wrote", out)
```

Run it:

```bash
.venv/Scripts/python tests/fixtures/_make_fixtures.py
```

Expected: `tests/fixtures/sample_schedule.xls` and `tests/fixtures/sample_dossier.xlsx` exist.

- [ ] **Step 8: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixtures_dir():
    return FIXTURES


@pytest.fixture
def sample_schedule_path():
    return FIXTURES / "sample_schedule.xls"


@pytest.fixture
def sample_dossier_path():
    return FIXTURES / "sample_dossier.xlsx"


@pytest.fixture
def sample_tree_path():
    return FIXTURES / "sample_transmittals.txt"


@pytest.fixture
def real_schedule_path():
    return PROJECT_ROOT / "4. List of DOC + Schedule (Correct doc).xls"


@pytest.fixture
def real_dossier_path():
    return PROJECT_ROOT / "50703-EPC Dossier Index - PDF (Updated on 27-03-2014).xlsx"


@pytest.fixture
def real_tree_path():
    return PROJECT_ROOT / "Transmittals.txt"
```

- [ ] **Step 9: Create empty classifier.py with section markers**

```python
"""Document Classifier — Phase 1.

See docs/specs/2026-04-30-classifier-design.md for the design.
"""
from __future__ import annotations

# =========================================================================
# Section A — Project-agnostic core
# =========================================================================
# REFACTOR HINT: split here for core_classifier.py


# =========================================================================
# Section B — Project-specific enrichment (Sahil-CDS schedule + dossier)
# =========================================================================
# REFACTOR HINT: split here for sahil_enrichment.py


# =========================================================================
# Section C — Orchestration / CLI
# =========================================================================


if __name__ == "__main__":
    raise SystemExit("CLI not yet implemented")
```

- [ ] **Step 10: Smoke-test pytest discovery**

```bash
.venv/Scripts/pytest -q
```

Expected: `no tests ran in 0.0Xs` (pytest finds zero tests, exits 0 or 5; either is fine for now).

- [ ] **Step 11: Initial commit**

```bash
git add .gitignore requirements.txt classifier.py tests/__init__.py tests/conftest.py tests/fixtures/_make_fixtures.py tests/fixtures/sample_schedule.xls tests/fixtures/sample_dossier.xlsx tests/fixtures/sample_transmittals.txt output/.gitkeep overrides/.gitkeep
git commit -m "chore: bootstrap classifier project skeleton"
```

---

## Task 1: Filename normalisation

**Files:**
- Create: `tests/test_normalise.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Write the failing test**

`tests/test_normalise.py`:

```python
from classifier import normalise_filename


def test_strip_whitespace():
    assert normalise_filename("   foo.pdf   ") == "foo.pdf"


def test_em_dash_becomes_ascii_hyphen():
    assert normalise_filename("16–01–19–2602.pdf") == "16-01-19-2602.pdf"


def test_en_dash_becomes_ascii_hyphen():
    assert normalise_filename("a–b.pdf") == "a-b.pdf"


def test_nbsp_becomes_space():
    assert normalise_filename("foo bar.pdf") == "foo bar.pdf"


def test_collapse_whitespace():
    assert normalise_filename("foo   bar.pdf") == "foo bar.pdf"


def test_nfkc_fullwidth_digit():
    # FULLWIDTH DIGIT ONE U+FF11 -> '1'
    assert normalise_filename("１.pdf") == "1.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/Scripts/pytest tests/test_normalise.py -v
```

Expected: all 6 tests fail with `ImportError: cannot import name 'normalise_filename'`.

- [ ] **Step 3: Implement `normalise_filename`**

In `classifier.py` Section A, append:

```python
import re
import unicodedata

_DASH_VARIANTS = "–—−‒"  # – — − ‒
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/Scripts/pytest tests/test_normalise.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_normalise.py
git commit -m "feat: filename normalisation (NFKC + dash/NBSP/whitespace)"
```

---

## Task 2: Reference, CRS and cover-sheet detection

**Files:**
- Create: `tests/test_extract.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Write the failing tests**

`tests/test_extract.py`:

```python
from classifier import extract_ref, is_crs_filename, is_cover_filename


# extract_ref
def test_extract_ref_clean():
    assert extract_ref("16-01-19-2602-A.pdf") == "16-01-19-2602"


def test_extract_ref_underscore_rev():
    assert extract_ref("16-01-19-2602_A.docx") == "16-01-19-2602"


def test_extract_ref_no_rev():
    assert extract_ref("16-01-08-2606.pdf") == "16-01-08-2606"


def test_extract_ref_with_freetext():
    assert extract_ref("16-99-91-2650-B Invoicing Procedure.docx") == "16-99-91-2650"


def test_extract_ref_in_crs():
    assert extract_ref("CRS-16-01-39-2602 REV-A.xlsx") == "16-01-39-2602"


def test_extract_ref_none():
    assert extract_ref("CAD Files.rar") is None


# is_crs_filename
def test_crs_dash_form():
    assert is_crs_filename("CRS-16-01-39-2602 REV-A.xlsx") is True


def test_crs_space_form():
    assert is_crs_filename("CRS 16-01-31-2604 REV-A.xlsx") is True


def test_crs_no_separator():
    assert is_crs_filename("CRS16-99-91-2650_A.xlsx") is True  # CRS<digit-digit-dash> branch


def test_crs_sheet_form():
    assert is_crs_filename("CRSheet-16-01-33-2625 REV-B.xlsx") is True


def test_crs_comment_response():
    assert is_crs_filename("Comment Response Sheet-16-01-40-2607.xlsx") is True


def test_crs_copy_of_comment():
    assert is_crs_filename("Copy of Comment Response Sheet-16-01-40-2605.xlsx") is True


def test_crs_mid_string():
    assert is_crs_filename("16-01-12-2603-CRS_Specification.xlsx") is True


def test_crs_at_end():
    assert is_crs_filename("16-01-89-2607 CRS.xlsx") is True


def test_crs_negative():
    assert is_crs_filename("16-01-19-2602-A.pdf") is False


# is_cover_filename
def test_cover_cta():
    assert is_cover_filename("CTA-ED-SA-15760.01-008.pdf") is True


def test_cover_c_a_ed_sa():
    assert is_cover_filename("C-A-ED-SA-15760.01-0068.pdf") is True


def test_cover_negative():
    assert is_cover_filename("16-01-19-2602-A.pdf") is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/Scripts/pytest tests/test_extract.py -v
```

Expected: all tests fail with ImportError.

- [ ] **Step 3: Implement the three functions**

Append to `classifier.py` Section A:

```python
REF_RE = re.compile(r"(\d{2}-\d{2}-\d{2}-\d{4})")

CRS_RE = re.compile(
    r"""(?ix)(
        ^crs[\s_\-]
      | ^crs(?=\d{2}-)
      | ^crsheet[\s_\-]
      | ^comment[\s_]response
      | ^copy[\s_]of[\s_]comment
      | [\s_\-]crs(?=[\s_\-]|\.)
    )"""
)

COVER_RE = re.compile(r"(?i)^(cta|c-a-ed-sa)")


def extract_ref(filename: str) -> str | None:
    """Return the first \\d{2}-\\d{2}-\\d{2}-\\d{4} ref, or None."""
    m = REF_RE.search(filename)
    return m.group(1) if m else None


def is_crs_filename(filename: str) -> bool:
    """True if filename matches the empirically-tuned CRS pattern (see spec §6.1a)."""
    return CRS_RE.search(filename) is not None


def is_cover_filename(filename: str) -> bool:
    """True if filename starts with a transmittal cover prefix (and lacks a Cust Ref #).
    Caller is responsible for the 'lacks ref' check; this only checks the prefix."""
    return COVER_RE.search(filename) is not None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/Scripts/pytest tests/test_extract.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_extract.py
git commit -m "feat: ref / CRS / cover-sheet detection regexes"
```

---

## Task 3: Letter-rev and numeric-rev extraction

**Files:**
- Modify: `tests/test_extract.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_extract.py`:

```python
from classifier import extract_letter_rev, extract_numeric_rev, extract_revs


# Letter
def test_letter_rev_dash():
    assert extract_letter_rev("16-01-19-2602-A.pdf", "16-01-19-2602") == "A"


def test_letter_rev_underscore():
    assert extract_letter_rev("16-01-19-2602_B.docx", "16-01-19-2602") == "B"


def test_letter_rev_space():
    assert extract_letter_rev("16-99-91-2650 C.docx", "16-99-91-2650") == "C"


def test_letter_rev_freetext_after():
    assert extract_letter_rev("16-99-91-2650-B Invoicing Procedure.docx", "16-99-91-2650") == "B"


def test_letter_rev_explicit_rev_word():
    assert extract_letter_rev("CRS-16-01-39-2602 REV-A.xlsx", "16-01-39-2602") == "A"


def test_letter_rev_revdot():
    assert extract_letter_rev("foo_Rev.A.pdf", "16-01-19-2602") == "A"


def test_letter_rev_ifa_form():
    assert extract_letter_rev("CRS-16-01-36-2602 IFA-D.xlsx", "16-01-36-2602") == "D"


def test_letter_rev_none():
    assert extract_letter_rev("16-01-19-2602.pdf", "16-01-19-2602") == ""


# Numeric
def test_numeric_rev_dash():
    assert extract_numeric_rev("16-01-08-2606-1.pdf", "16-01-08-2606") == "1"


def test_numeric_rev_underscore():
    assert extract_numeric_rev("16-01-08-2606_2.pdf", "16-01-08-2606") == "2"


def test_numeric_rev_two_digits():
    assert extract_numeric_rev("16-01-08-2606_12.pdf", "16-01-08-2606") == "12"


def test_numeric_rev_explicit():
    assert extract_numeric_rev("CRS-16-01-33-2611 REV-3.xlsx", "16-01-33-2611") == "3"


def test_numeric_rev_ifc_form():
    assert extract_numeric_rev("CRS-16-01-33-2616 - IFC-2.xlsx", "16-01-33-2616") == "2"


def test_numeric_rev_none():
    assert extract_numeric_rev("16-01-19-2602-A.pdf", "16-01-19-2602") == ""


# Combined
def test_extract_revs_both():
    assert extract_revs("16-01-19-2602-A REV-1.pdf", "16-01-19-2602") == ("A", "1")


def test_extract_revs_neither():
    assert extract_revs("16-01-19-2602.pdf", "16-01-19-2602") == ("", "")
```

- [ ] **Step 2: Run tests, expect failure**

```bash
.venv/Scripts/pytest tests/test_extract.py -v -k "rev"
```

Expected: 16 fail with ImportError.

- [ ] **Step 3: Implement extraction functions**

Append to `classifier.py` Section A:

```python
def _esc_ref(ref: str) -> str:
    """Escape a ref for use inside a regex (handles literal hyphens)."""
    return re.escape(ref)


def extract_letter_rev(filename: str, ref: str | None) -> str:
    """Return parsed letter rev (single uppercase A-Z) or empty string.

    Tier 1: <ref>[-_ ]([A-Z])(?:[ _.-]|$)   clean trailing or followed by separator
    Tier 3: (?i)REV[._ \\-]?([A-Z])         e.g. REV-A, REV.A
    Tier 3a: (?i)IF[ARDCU][ _\\-]?([A-Z])   e.g. IFA-D
    """
    if ref:
        m = re.search(rf"{_esc_ref(ref)}[ _\-]([A-Z])(?:[ _.\-]|$)", filename)
        if m:
            return m.group(1).upper()
    m = re.search(r"(?i)\bIF[ARDCU][ _\-]?([A-Z])\b", filename)
    if m:
        return m.group(1).upper()
    m = re.search(r"(?i)\bREV[._ \-]?([A-Z])\b", filename)
    if m:
        return m.group(1).upper()
    return ""


def extract_numeric_rev(filename: str, ref: str | None) -> str:
    """Return parsed numeric rev (1-99 as decimal string) or empty string.

    Tier 2: <ref>[-_ ](\\d{1,2})(?:[ _.-]|$)
    Tier 4: (?i)REV[._ \\-]?(\\d{1,2})
    Tier 4a: (?i)IF[ARDCU][ _\\-]?(\\d{1,2})  e.g. IFC-2
    """
    if ref:
        m = re.search(rf"{_esc_ref(ref)}[ _\-](\d{{1,2}})(?:[ _.\-]|$)", filename)
        if m:
            return m.group(1)
    m = re.search(r"(?i)\bIF[ARDCU][ _\-]?(\d{1,2})\b", filename)
    if m:
        return m.group(1)
    m = re.search(r"(?i)\bREV[._ \-]?(\d{1,2})\b", filename)
    if m:
        return m.group(1)
    return ""


def extract_revs(filename: str, ref: str | None) -> tuple[str, str]:
    """Return (letter_rev, numeric_rev). Either may be empty."""
    return extract_letter_rev(filename, ref), extract_numeric_rev(filename, ref)
```

- [ ] **Step 4: Run tests, expect pass**

```bash
.venv/Scripts/pytest tests/test_extract.py -v
```

Expected: all tests pass (Task 2 + Task 3 = ~32 tests).

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_extract.py
git commit -m "feat: letter-rev and numeric-rev extraction (4 tiers each)"
```

---

## Task 4: Sibling-rev inheritance (tier 5)

**Files:**
- Modify: `tests/test_extract.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_extract.py`:

```python
from classifier import inherit_rev_from_siblings


def test_inherit_picks_unique_sibling():
    target = {"filename": "CRS-16-01-39-2602.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "16-01-39-2602-A.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("A", "")


def test_inherit_picks_highest_among_matching_siblings():
    target = {"filename": "CRS.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "x-A.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
        {"filename": "x-B.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "B", "numeric_rev": ""},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("B", "")


def test_inherit_numeric_supersedes_letter():
    target = {"filename": "CRS.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "x-A.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
        {"filename": "x-1.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": "1"},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("", "1")


def test_inherit_no_matching_ref():
    target = {"filename": "CRS.xlsx", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "", "numeric_rev": ""}
    siblings = [
        {"filename": "y-A.pdf", "cust_ref": "16-01-99-9999",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""},
    ]
    assert inherit_rev_from_siblings(target, siblings) == ("", "")


def test_inherit_only_when_target_has_neither_rev():
    target = {"filename": "x-A.pdf", "cust_ref": "16-01-39-2602",
              "submission_folder": "S1", "subfolder": "", "letter_rev": "A", "numeric_rev": ""}
    siblings = [
        {"filename": "y-B.pdf", "cust_ref": "16-01-39-2602",
         "submission_folder": "S1", "subfolder": "", "letter_rev": "B", "numeric_rev": ""},
    ]
    # Should not overwrite target's existing rev.
    assert inherit_rev_from_siblings(target, siblings) == ("A", "")
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_extract.py -v -k "inherit"
```

Expected: 5 fail with ImportError.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
def inherit_rev_from_siblings(target: dict, siblings: list[dict]) -> tuple[str, str]:
    """Tier-5 sibling rev inheritance.

    Returns (letter_rev, numeric_rev) for `target`. If target already has either rev,
    returns target's existing pair unchanged. Otherwise looks at siblings sharing the
    same submission_folder + subfolder + cust_ref; among those with a parseable rev,
    inherits the highest under §7.2 ordering (numeric supersedes letter; within
    numeric, highest int; within letter, lexicographic max).
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
    # Numeric wins if any sibling has one.
    numeric = [int(s["numeric_rev"]) for s in matches if s.get("numeric_rev")]
    if numeric:
        return "", str(max(numeric))
    letters = [s["letter_rev"] for s in matches if s.get("letter_rev")]
    if letters:
        return max(letters), ""
    return "", ""
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_extract.py -v -k "inherit"
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_extract.py
git commit -m "feat: tier-5 sibling rev inheritance"
```

---

## Task 5: Bucket constants — keyword bank and type maps

**Files:**
- Create: `tests/test_classify.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Write failing test for the constant tables**

`tests/test_classify.py`:

```python
from classifier import KEYWORD_RULES, TYPE_TO_BUCKET, BUCKET_PRIMARY_CODE, BUCKETS


def test_buckets_count():
    assert len(BUCKETS) == 10


def test_required_buckets_present():
    expected = {"Drawings", "Isometrics", "Datasheets", "Specifications",
                "Calculations", "Reports", "Lists_MTOs_BOMs", "Procedures_Plans",
                "CRS", "Documents"}
    assert set(BUCKETS) == expected


def test_keyword_rules_keyed_by_bucket():
    for bucket in BUCKETS:
        if bucket in {"CRS", "Documents"}:
            # CRS is filename-pinned; Documents is the fallback. May have empty kw list.
            continue
        assert bucket in KEYWORD_RULES
        assert len(KEYWORD_RULES[bucket]) > 0


def test_keyword_weights_in_range():
    for bucket, rules in KEYWORD_RULES.items():
        for pattern, weight in rules:
            assert isinstance(pattern, str)
            assert 1 <= weight <= 5


def test_type_to_bucket_known_codes():
    assert TYPE_TO_BUCKET["PID"] == "Drawings"
    assert TYPE_TO_BUCKET["DAS"] == "Datasheets"
    assert TYPE_TO_BUCKET["CAL"] == "Calculations"
    assert TYPE_TO_BUCKET["REP"] == "Reports"
    assert TYPE_TO_BUCKET["MTO"] == "Lists_MTOs_BOMs"
    assert TYPE_TO_BUCKET["PRO"] == "Procedures_Plans"


def test_bucket_primary_code_for_each_bucket():
    for bucket in BUCKETS:
        assert bucket in BUCKET_PRIMARY_CODE
        assert len(BUCKET_PRIMARY_CODE[bucket]) >= 3
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_classify.py -v
```

Expected: 6 fail with ImportError.

- [ ] **Step 3: Implement constants**

Append to `classifier.py` Section A:

```python
BUCKETS = (
    "Drawings",
    "Isometrics",
    "Datasheets",
    "Specifications",
    "Calculations",
    "Reports",
    "Lists_MTOs_BOMs",
    "Procedures_Plans",
    "CRS",
    "Documents",
)

# (regex_pattern, weight 1-5). Patterns are searched case-insensitively against
# a normalised lowercased title+filename. Weights per spec §5.2.
KEYWORD_RULES: dict[str, list[tuple[str, int]]] = {
    "Drawings": [
        (r"p&id", 5),
        (r"piping (and|&) instrument", 5),
        (r"flow diagram", 4),
        (r"material selection diagram", 5),
        (r"\blayout\b", 2),
        (r"arrangement", 3),
        (r"plot plan", 4),
        (r"single line", 4),
        (r"block diagram", 4),
        (r"cause (and|&) effect", 5),
        (r"wiring diagram", 4),
        (r"loop /? segment", 4),
        (r"architecture", 3),
        (r"safeguarding", 4),
        (r"hazardous area", 3),
        (r"interconnection diagram", 4),
        (r"installation drawing", 3),
        (r"hook up", 3),
        (r"junction box", 3),
        (r"structural detail", 3),
        (r"foundation", 2),
        (r"pipe support", 2),
        (r"elevation", 2),
        (r"\bdetails\b", 1),
    ],
    "Isometrics": [
        (r"isometric", 5),
        (r"\biso\b", 2),
    ],
    "Datasheets": [
        (r"data ?sheet", 5),
        (r"process data", 4),
    ],
    "Specifications": [
        (r"specification", 5),
        (r"standards?\b", 3),
        (r"general notes", 3),
    ],
    "Calculations": [
        (r"calculation", 5),
        (r"caculation", 5),
        (r"sizing", 3),
        (r"wall thickness", 4),
        (r"stress analysis", 4),
        (r"calc note", 4),
    ],
    "Reports": [
        (r"\breport\b", 5),
        (r"design basis", 5),
        (r"\bstudy\b", 3),
        (r"\breview\b", 2),
        (r"close out", 4),
        (r"topograph", 4),
        (r"scope of work", 4),
        (r"hazid", 5),
        (r"hazop", 5),
        (r"phser", 4),
        (r"process .*description", 3),
    ],
    "Lists_MTOs_BOMs": [
        (r"\bmto\b", 5),
        (r"bill of quantities", 5),
        (r"bill of material", 5),
        (r"\blist\b", 3),
        (r"\bschedule\b", 2),
        (r"equipment list", 5),
        (r"line list", 5),
        (r"\bindex\b", 3),
        (r"register", 3),
        (r"tie-?in", 4),
        (r"i/o list", 5),
        (r"load list", 4),
        (r"consumption summary", 4),
    ],
    "Procedures_Plans": [
        (r"procedure", 5),
        (r"\bplan\b", 3),
        (r"philosophy", 5),
        (r"\bexecution\b", 3),
        (r"change over", 4),
        (r"work breakdown", 4),
        (r"invoicing", 4),
        (r"method statement", 5),
        (r"look ahead", 4),
        (r"\btra-", 4),  # Task Risk Assessment, project-specific prefix
    ],
    # CRS is filename-pinned (see §6.2 step 2); Documents is the fallback.
    "CRS": [],
    "Documents": [],
}

# Dossier Type code -> bucket (per spec §5.2)
TYPE_TO_BUCKET: dict[str, str] = {
    "PID": "Drawings", "PFD": "Drawings", "PSF": "Drawings", "DGA": "Drawings",
    "DSD": "Drawings", "DWG": "Drawings", "DAL": "Drawings", "DWD": "Drawings",
    "DSL": "Drawings", "DBD": "Drawings", "DCE": "Drawings", "DHZ": "Drawings",
    "DPP": "Drawings", "MSD": "Drawings",
    "DAS": "Datasheets",
    "SPC": "Specifications", "STD": "Specifications",
    "CAL": "Calculations",
    "REP": "Reports", "BOD": "Reports", "SOW": "Reports",
    "LST": "Lists_MTOs_BOMs", "MTO": "Lists_MTOs_BOMs", "BOM": "Lists_MTOs_BOMs",
    "IDX": "Lists_MTOs_BOMs", "REG": "Lists_MTOs_BOMs", "SCH": "Lists_MTOs_BOMs",
    "PRO": "Procedures_Plans", "PLN": "Procedures_Plans", "PHL": "Procedures_Plans",
    "REQ": "Documents",
}

# Bucket -> primary 3-letter code used in target filename when no dossier Type matches.
BUCKET_PRIMARY_CODE: dict[str, str] = {
    "Drawings": "DWG",
    "Isometrics": "ISO",
    "Datasheets": "DAS",
    "Specifications": "SPC",
    "Calculations": "CAL",
    "Reports": "REP",
    "Lists_MTOs_BOMs": "LST",
    "Procedures_Plans": "PRO",
    "CRS": "CRS",
    "Documents": "DOC",
}
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_classify.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_classify.py
git commit -m "feat: bucket constants — keyword rules, type map, primary codes"
```

---

## Task 6: Bucket scoring (`score_buckets`)

**Files:**
- Modify: `tests/test_classify.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_classify.py`:

```python
from classifier import score_buckets


def test_score_single_keyword():
    scores = score_buckets("VALVE LIST", "16-01-19-2602.pdf")
    # \blist\b weight 3 -> Lists score (3, 3)
    assert scores["Lists_MTOs_BOMs"] == (3, 3)


def test_score_two_keywords_same_bucket():
    scores = score_buckets("EQUIPMENT LIST AND LINE LIST", "")
    # equipment list (5) + line list (5) + \blist\b (3) twice
    s_sum, s_top = scores["Lists_MTOs_BOMs"]
    assert s_top == 5
    assert s_sum >= 10


def test_score_uses_score_top_for_signal_strength():
    # Title with one weight-5 hit and a title with three weight-5 hits both have score_top=5
    a_sum, a_top = score_buckets("DATA SHEET", "")["Datasheets"]
    b_sum, b_top = score_buckets("DATA SHEET DATA SHEET DATA SHEET", "")["Datasheets"]
    assert a_top == b_top == 5
    assert b_sum > a_sum


def test_score_zero_when_no_match():
    scores = score_buckets("RANDOM XYZ TEXT", "foo.pdf")
    assert scores["Lists_MTOs_BOMs"] == (0, 0)
    assert scores["Drawings"] == (0, 0)


def test_score_filename_contributes():
    # Title is empty, but filename contains a keyword
    scores = score_buckets("", "PIPING_AND_INSTRUMENT_DIAGRAM_FOO.pdf")
    s_sum, s_top = scores["Drawings"]
    assert s_top == 5
    assert s_sum >= 5
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k score
```

Expected: 5 fail with ImportError.

- [ ] **Step 3: Implement `score_buckets`**

Append to `classifier.py` Section A:

```python
def score_buckets(title: str, filename: str) -> dict[str, tuple[int, int]]:
    """For each bucket, return (score_sum, score_top).

    score_sum = total of weights of all keyword hits in title+filename.
    score_top = maximum single weight that fired (used for confidence).
    Both are 0 when no rule fires.
    """
    text = (title + " " + filename).lower()
    out: dict[str, tuple[int, int]] = {}
    for bucket, rules in KEYWORD_RULES.items():
        s_sum = 0
        s_top = 0
        for pattern, weight in rules:
            for _ in re.finditer(pattern, text):
                s_sum += weight
                if weight > s_top:
                    s_top = weight
        out[bucket] = (s_sum, s_top)
    # CRS and Documents always present, with zeros (CRS is filename-pinned upstream).
    out.setdefault("CRS", (0, 0))
    out.setdefault("Documents", (0, 0))
    return out
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k score
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_classify.py
git commit -m "feat: weighted bucket scoring (score_sum + score_top)"
```

---

## Task 7: Bucket picking (`pick_bucket`)

**Files:**
- Modify: `tests/test_classify.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_classify.py`:

```python
from classifier import pick_bucket


def test_pick_winner_high_confidence():
    scores = {"Drawings": (5, 5), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["bucket"] == "Drawings"
    assert res["score_sum"] == 5
    assert res["confidence"] == "high"
    assert res["runner_up_bucket"] == "Documents"
    assert res["runner_up_score"] == 0


def test_pick_medium_confidence():
    scores = {"Drawings": (3, 3), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["confidence"] == "medium"


def test_pick_low_confidence_weight1():
    scores = {"Drawings": (1, 1), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["confidence"] == "low"


def test_pick_fallback_to_documents_on_zero():
    scores = {b: (0, 0) for b in ("Drawings", "Reports", "Documents")}
    res = pick_bucket(scores)
    assert res["bucket"] == "Documents"
    assert res["confidence"] == "low"
    assert res["score_sum"] == 0


def test_pick_runner_up_with_three_buckets():
    scores = {"Drawings": (5, 5), "Reports": (3, 3), "Documents": (0, 0)}
    res = pick_bucket(scores)
    assert res["bucket"] == "Drawings"
    assert res["runner_up_bucket"] == "Reports"
    assert res["runner_up_score"] == 3


def test_pick_tiebreak_lexicographic():
    # Two buckets tied on score_sum
    scores = {"Reports": (5, 5), "Drawings": (5, 5), "Documents": (0, 0)}
    res = pick_bucket(scores)
    # Lexicographic: Drawings < Reports
    assert res["bucket"] == "Drawings"
    assert res["runner_up_bucket"] == "Reports"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k pick
```

Expected: 6 fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
def pick_bucket(scores: dict[str, tuple[int, int]]) -> dict:
    """Pick winning bucket by score_sum (lex tiebreak), with runner-up + confidence.

    Returns dict with keys: bucket, score_sum, score_top, confidence,
    runner_up_bucket, runner_up_score.
    """
    # Sort by (-score_sum, bucket_name) so the first item is the winner.
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    if not ranked:
        return {"bucket": "Documents", "score_sum": 0, "score_top": 0,
                "confidence": "low", "runner_up_bucket": "", "runner_up_score": 0}
    winner_name, (winner_sum, winner_top) = ranked[0]
    if winner_sum == 0:
        # No keyword fired anywhere — fall back to Documents, low confidence.
        runner = next(((n, s) for n, s in ranked if n != "Documents"), ("", (0, 0)))
        return {"bucket": "Documents", "score_sum": 0, "score_top": 0,
                "confidence": "low",
                "runner_up_bucket": runner[0], "runner_up_score": runner[1][0]}
    if winner_top == 5:
        confidence = "high"
    elif winner_top in (3, 4):
        confidence = "medium"
    else:  # 1 or 2
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
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k pick
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_classify.py
git commit -m "feat: bucket picker with score_top-based confidence + lex tiebreak"
```

---

## Task 8: Form resolution (two passes)

**Files:**
- Modify: `tests/test_classify.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_classify.py`:

```python
from classifier import resolve_form_pre, resolve_form_post


# Pass 1: structural
def test_form_pre_archive_rar():
    assert resolve_form_pre("foo.rar", has_ref=False) == "Archive"


def test_form_pre_archive_zip():
    assert resolve_form_pre("foo.zip", has_ref=False) == "Archive"


def test_form_pre_cover_no_ref():
    assert resolve_form_pre("CTA-ED-SA-15760.01-008.pdf", has_ref=False) == "CoverSheet"


def test_form_pre_cover_with_ref_is_not_cover():
    # When the filename has both CTA prefix and a ref, treat as content (rare edge)
    assert resolve_form_pre("CTA-X-16-01-19-2602.pdf", has_ref=True) is None


def test_form_pre_default_unset():
    assert resolve_form_pre("16-01-19-2602-A.pdf", has_ref=True) is None


# Pass 2: content-driven
def test_form_post_dwg():
    assert resolve_form_post("foo.dwg", "Drawings") == "Drawing"


def test_form_post_xlsx_lists():
    assert resolve_form_post("foo.xlsx", "Lists_MTOs_BOMs") == "Sheet"


def test_form_post_docx():
    assert resolve_form_post("foo.docx", "Reports") == "Document"


def test_form_post_pdf_in_drawings_bucket():
    assert resolve_form_post("foo.pdf", "Drawings") == "Drawing"


def test_form_post_pdf_in_isometrics_bucket():
    assert resolve_form_post("foo.pdf", "Isometrics") == "Drawing"


def test_form_post_pdf_in_datasheets_bucket():
    assert resolve_form_post("foo.pdf", "Datasheets") == "Sheet"


def test_form_post_pdf_in_lists_bucket():
    assert resolve_form_post("foo.pdf", "Lists_MTOs_BOMs") == "Sheet"


def test_form_post_pdf_in_reports_bucket():
    assert resolve_form_post("foo.pdf", "Reports") == "Document"


def test_form_post_unknown_extension():
    assert resolve_form_post("foo.xyz", "Documents") == "Document"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k form
```

Expected: 14 fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
def resolve_form_pre(filename: str, has_ref: bool) -> str | None:
    """Pass-1 form resolution (structural): Archive or CoverSheet, else None.

    has_ref is whether the filename contains a Cust Ref #; cover sheets only
    apply when there is no ref (a CTA-prefix filename that also contains a ref
    is content, not a cover sheet).
    """
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
    """Pass-2 form resolution (content-driven), called after the bucket is decided.

    For non-PDF: deterministic by extension. For .pdf: derived from bucket.
    Anything else: Document.
    """
    lower = filename.lower()
    # extract extension (last dot)
    if "." in lower:
        ext = "." + lower.rsplit(".", 1)[1]
    else:
        ext = ""
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
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k form
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_classify.py
git commit -m "feat: two-pass form resolution (structural + content-driven)"
```

---

## Task 9: Schedule loader

**Files:**
- Create: `tests/test_loaders.py`
- Modify: `classifier.py` (Section B)

- [ ] **Step 1: Write failing test**

`tests/test_loaders.py`:

```python
from classifier import load_schedule


def test_load_schedule_returns_dataframe(sample_schedule_path):
    df = load_schedule(sample_schedule_path)
    assert "cust_ref" in df.columns
    assert "title" in df.columns
    assert "discipline" in df.columns
    assert "schedule_rev" in df.columns
    assert "pcs_doc_no" in df.columns
    assert len(df) >= 1
    # cust_ref should be the digit pattern
    import re
    for ref in df["cust_ref"]:
        assert re.fullmatch(r"\d{2}-\d{2}-\d{2}-\d{4}", ref), f"bad ref: {ref!r}"


def test_load_schedule_drops_blank_rows(sample_schedule_path):
    df = load_schedule(sample_schedule_path)
    # No blanks in cust_ref
    assert df["cust_ref"].isna().sum() == 0
    assert (df["cust_ref"].astype(str).str.strip() == "").sum() == 0


def test_load_schedule_seg2_column(sample_schedule_path):
    df = load_schedule(sample_schedule_path)
    assert "seg2" in df.columns
    # seg2 is third hyphen segment
    for ref, seg2 in zip(df["cust_ref"], df["seg2"]):
        assert ref.split("-")[2] == seg2
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v
```

Expected: 3 fail with ImportError.

- [ ] **Step 3: Implement `load_schedule`**

In `classifier.py` Section B (under the section marker), append:

```python
import pandas as pd
from pathlib import Path


def load_schedule(path: Path | str) -> pd.DataFrame:
    """Load schedule xls Sheet1 and return a clean DataFrame.

    Columns returned: cust_ref, pcs_doc_no, title, discipline, schedule_rev, seg2.
    Rows with missing cust_ref are dropped. cust_ref values are stripped.
    """
    df = pd.read_excel(path, sheet_name="Sheet1")
    df = df.dropna(subset=["Cust Ref #", "Title", "Discip"]).copy()
    df["cust_ref"] = df["Cust Ref #"].astype(str).str.strip()
    df = df[df["cust_ref"].str.match(r"\d{2}-\d{2}-\d{2}-\d{4}")].copy()
    df["pcs_doc_no"] = df["PCS Doc No."].astype(str).str.strip()
    df["title"] = df["Title"].astype(str).str.strip()
    df["discipline"] = df["Discip"].astype(str).str.strip()
    df["schedule_rev"] = df["Rev."].fillna("").astype(str).str.strip()
    df["seg2"] = df["cust_ref"].str.split("-").str[2]
    return df[["cust_ref", "pcs_doc_no", "title", "discipline", "schedule_rev", "seg2"]].reset_index(drop=True)
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_loaders.py
git commit -m "feat: schedule loader (xls Sheet1 -> normalised DataFrame)"
```

---

## Task 10: Dossier loader

**Files:**
- Modify: `tests/test_loaders.py`
- Modify: `classifier.py` (Section B)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_loaders.py`:

```python
from classifier import load_dossier


def test_load_dossier(sample_dossier_path):
    df = load_dossier(sample_dossier_path)
    assert "doc_no" in df.columns
    assert "title" in df.columns
    assert "type_code" in df.columns
    assert "rev" in df.columns
    assert "status" in df.columns
    assert len(df) >= 1


def test_load_dossier_drops_section_headers(sample_dossier_path):
    df = load_dossier(sample_dossier_path)
    # type_code never empty / "Type" / NaN in returned rows
    assert (df["type_code"].astype(str) == "Type").sum() == 0
    assert df["type_code"].isna().sum() == 0
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v -k dossier
```

Expected: 2 fail.

- [ ] **Step 3: Implement `load_dossier`**

Append to `classifier.py` Section B:

```python
def load_dossier(path: Path | str) -> pd.DataFrame:
    """Load dossier xlsx PDF sheet and return a clean DataFrame.

    Columns returned: doc_no, title, rev, status, type_code, volume.
    """
    df = pd.read_excel(path, sheet_name="PDF", header=4)
    df.columns = ["doc_no", "title", "rev", "status", "type_code", "pdf", "volume", "book"]
    df = df[df["title"].notna() & df["type_code"].notna() & (df["type_code"] != "Type")].copy()
    df["doc_no"] = df["doc_no"].astype(str).str.strip()
    df["title"] = df["title"].astype(str).str.strip()
    df["type_code"] = df["type_code"].astype(str).str.strip()
    df["rev"] = df["rev"].fillna("").astype(str).str.strip()
    df["status"] = df["status"].fillna("").astype(str).str.strip()
    return df[["doc_no", "title", "rev", "status", "type_code", "volume"]].reset_index(drop=True)
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v -k dossier
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_loaders.py
git commit -m "feat: dossier loader"
```

---

## Task 11: Transmittals tree parser

**Files:**
- Modify: `tests/test_loaders.py`
- Modify: `classifier.py` (Section B)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_loaders.py`:

```python
from classifier import parse_transmittals


def test_parse_transmittals_skips_from_client(sample_tree_path):
    records = parse_transmittals(sample_tree_path)
    # No record should reference FROM CLIENT
    for r in records:
        assert "FROM CLIENT" not in r["submission_folder"]
        assert "APDRC" not in r["submission_folder"]


def test_parse_transmittals_finds_files(sample_tree_path):
    records = parse_transmittals(sample_tree_path)
    filenames = {r["filename"] for r in records}
    assert "16-01-39-2602-A.pdf" in filenames
    assert "16-01-39-2602_A.docx" in filenames
    assert "CRS-16-01-39-2602 REV-A.xlsx" in filenames
    assert "CTA-ED-SA-15760.01.070.pdf" in filenames
    assert "CAD Files.rar" in filenames
    assert "Comment Response Sheet-16-01-40-2607.xlsx" in filenames
    assert "Attachment-1.pdf" in filenames


def test_parse_transmittals_subfolder(sample_tree_path):
    records = parse_transmittals(sample_tree_path)
    rows = [r for r in records if r["filename"] == "16-01-23-2602-A.dwg"]
    assert len(rows) == 1
    assert rows[0]["submission_folder"] == "C-A-ED-SA-15760.01-0070"
    assert rows[0]["subfolder"] == "CAD FILES"


def test_parse_transmittals_em_dash_filename_preserved(sample_tree_path):
    records = parse_transmittals(sample_tree_path)
    # The em-dash variant must appear in records (we normalise downstream)
    em_dash_files = [r for r in records if "–" in r["filename"]]
    assert len(em_dash_files) == 1
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v -k transmittals
```

Expected: 4 fail.

- [ ] **Step 3: Implement `parse_transmittals`**

Append to `classifier.py` Section B:

```python
_FOLDER_MARK_RE = re.compile(r"(?:\+|\\)---")
_FILE_LINE_RE = re.compile(r"^([\s|]+)(\S.*)$")


def parse_transmittals(path: Path | str) -> list[dict]:
    """Parse a Windows `tree` listing and return file records under TO CLIENT.

    Each record: {full_rel_path, filename, submission_folder, subfolder}.
    Files inside FROM CLIENT are skipped. Filenames are returned as-is (the
    caller normalises them via normalise_filename).
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    # Find the TO CLIENT root line
    start = None
    for i, ln in enumerate(text):
        if "TO CLIENT" in ln and "---" in ln:
            start = i
            break
    if start is None:
        return []

    records: list[dict] = []
    stack: list[tuple[int, str]] = []  # [(depth, name), ...]

    for raw in text[start + 1:]:
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _FOLDER_MARK_RE.search(line)
        if m:
            # Folder entry. Depth = leading-prefix length / 4.
            depth = m.start() // 4
            name = line[m.end():].strip()
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, name))
        else:
            # File line.
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
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v -k transmittals
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_loaders.py
git commit -m "feat: TO CLIENT tree parser"
```

---

## Task 12: Discipline resolution (5-tier chain)

**Files:**
- Modify: `tests/test_classify.py`
- Modify: `classifier.py` (Section A for keyword tier; Section B for full chain)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_classify.py`:

```python
from classifier import build_seg2_discipline_map, derive_discipline


def test_seg2_map_from_dataframe():
    import pandas as pd
    df = pd.DataFrame({
        "cust_ref": ["16-01-23-2601", "16-01-23-2602", "16-01-67-2601", "16-01-67-2602"],
        "discipline": ["PIPNG", "PIPNG", "ELEC", "ELEC"],
        "seg2": ["23", "23", "67", "67"],
    })
    m = build_seg2_discipline_map(df)
    assert m["23"] == "PIPNG"
    assert m["67"] == "ELEC"


def test_seg2_map_majority_vote():
    import pandas as pd
    df = pd.DataFrame({
        "cust_ref": ["a", "b", "c"], "seg2": ["91", "91", "91"],
        "discipline": ["PROJECTS", "PROJECTS", "ENGG MGMT"],
    })
    m = build_seg2_discipline_map(df)
    assert m["91"] == "PROJECTS"


# Discipline chain
def test_discipline_tier1_schedule_match():
    schedule_lookup = {"16-01-19-2602": "PIPNG"}
    seg2 = {}
    out = derive_discipline(
        cust_ref="16-01-19-2602", title="VALVE LIST", filename="x.pdf",
        schedule_lookup=schedule_lookup, seg2_map=seg2,
        submission_majority="", multi_disc_submission=False)
    assert out == "PIPNG"


def test_discipline_tier2_seg2():
    out = derive_discipline(
        cust_ref="16-01-67-9999", title="", filename="x.pdf",
        schedule_lookup={}, seg2_map={"67": "ELEC"},
        submission_majority="", multi_disc_submission=False)
    assert out == "ELEC"


def test_discipline_tier3_filename_keyword():
    out = derive_discipline(
        cust_ref="", title="STRESS ANALYSIS REPORT", filename="x.pdf",
        schedule_lookup={}, seg2_map={},
        submission_majority="", multi_disc_submission=False)
    assert out == "PIPNG"


def test_discipline_tier4_submission_majority():
    out = derive_discipline(
        cust_ref="", title="", filename="x.pdf",
        schedule_lookup={}, seg2_map={},
        submission_majority="HSE", multi_disc_submission=False)
    assert out == "HSE"


def test_discipline_tier4_disabled_for_multi_disc():
    out = derive_discipline(
        cust_ref="", title="", filename="x.pdf",
        schedule_lookup={}, seg2_map={},
        submission_majority="HSE", multi_disc_submission=True)
    assert out == "UNK"


def test_discipline_unk_fallback():
    out = derive_discipline(
        cust_ref="", title="", filename="x.pdf",
        schedule_lookup={}, seg2_map={},
        submission_majority="", multi_disc_submission=False)
    assert out == "UNK"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k discipline
```

Expected: tests fail.

- [ ] **Step 3: Implement**

In `classifier.py` Section A, add discipline keyword tier:

```python
# Discipline keyword tier (spec §6.3 step 3). Order matters: first match wins.
_DISCIPLINE_KEYWORD_RULES: list[tuple[str, str]] = [
    (r"\bhazop\b|\bhazid\b|\bhse\b|\bfire\b|f&g|\bsafety\b", "HSE"),
    (r"foundation|structural|civil\b|rebar|concrete works|steel works", "CIVIL"),
    (r"\bsld\b|\bhv\b|\blv\b|earth(ing)?|substation|cathodic", "ELEC"),
    (r"instrument|\bdcs\b|\besd\b|junction box|\bloop\b|interconnection", "INST"),
    (r"\bpump\b|vessel|exchanger|mechanical|rotating|static equipment", "MECH"),
    (r"stress|hydraulic|piping", "PIPNG"),
    (r"procedure|\bplan\b|invoicing|work breakdown|method statement|\btra-", "PROJECTS"),
]


def discipline_from_keywords(text: str) -> str:
    """Return discipline guess from filename/title keyword, or empty string."""
    t = text.lower()
    for pattern, disc in _DISCIPLINE_KEYWORD_RULES:
        if re.search(pattern, t):
            return disc
    return ""
```

In `classifier.py` Section B, add the map builder and full chain:

```python
def build_seg2_discipline_map(schedule_df: pd.DataFrame) -> dict[str, str]:
    """Majority-vote per Cust Ref segment-2 -> discipline."""
    out: dict[str, str] = {}
    for seg2, grp in schedule_df.groupby("seg2"):
        out[seg2] = grp["discipline"].value_counts().idxmax()
    return out


def derive_discipline(
    *, cust_ref: str, title: str, filename: str,
    schedule_lookup: dict[str, str], seg2_map: dict[str, str],
    submission_majority: str, multi_disc_submission: bool,
) -> str:
    """5-tier discipline chain (spec §6.3)."""
    # Tier 1: schedule match
    if cust_ref and cust_ref in schedule_lookup:
        return schedule_lookup[cust_ref]
    # Tier 2: seg2 lookup
    if cust_ref:
        seg2 = cust_ref.split("-")[2] if "-" in cust_ref else ""
        if seg2 in seg2_map:
            return seg2_map[seg2]
    # Tier 3: filename/title keywords
    kw = discipline_from_keywords(title + " " + filename)
    if kw:
        return kw
    # Tier 4: submission majority (only when not multi-discipline)
    if submission_majority and not multi_disc_submission:
        return submission_majority
    # Tier 5: UNK
    return "UNK"
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_classify.py -v -k discipline
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_classify.py
git commit -m "feat: 5-tier discipline resolution"
```

---

## Task 13: Override loader

**Files:**
- Modify: `tests/test_loaders.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_loaders.py`:

```python
from classifier import load_overrides


def test_load_overrides_missing_file_returns_empty(tmp_path):
    out = load_overrides(tmp_path / "nope.csv")
    assert out == {}


def test_load_overrides_reads_csv(tmp_path):
    p = tmp_path / "ov.csv"
    p.write_text("cust_ref,bucket\n16-01-19-2602,Drawings\n16-99-91-2650,Reports\n", encoding="utf-8")
    out = load_overrides(p)
    assert out == {"16-01-19-2602": "Drawings", "16-99-91-2650": "Reports"}


def test_load_overrides_strips_whitespace(tmp_path):
    p = tmp_path / "ov.csv"
    p.write_text("cust_ref,bucket\n  16-01-19-2602  ,  Drawings  \n", encoding="utf-8")
    out = load_overrides(p)
    assert out == {"16-01-19-2602": "Drawings"}


def test_load_overrides_skips_blank_rows(tmp_path):
    p = tmp_path / "ov.csv"
    p.write_text("cust_ref,bucket\n\n16-01-19-2602,Drawings\n,\n", encoding="utf-8")
    out = load_overrides(p)
    assert out == {"16-01-19-2602": "Drawings"}
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v -k override
```

Expected: 4 fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
import csv


def load_overrides(path: Path | str) -> dict[str, str]:
    """Load overrides/ref_to_bucket.csv. Missing file -> empty dict.

    Returns {cust_ref: bucket}. Blank/incomplete rows are skipped.
    Caller is responsible for warning on overrides referencing unknown refs.
    """
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = (row.get("cust_ref") or "").strip()
            bucket = (row.get("bucket") or "").strip()
            if ref and bucket:
                out[ref] = bucket
    return out
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_loaders.py -v -k override
```

Expected: 4 passed.

- [ ] **Step 5: Create the empty overrides file**

```bash
echo "cust_ref,bucket" > overrides/ref_to_bucket.csv
```

- [ ] **Step 6: Commit**

```bash
git add classifier.py tests/test_loaders.py overrides/ref_to_bucket.csv
git commit -m "feat: override CSV loader (cust_ref -> bucket)"
```

---

## Task 14: Bundle id assignment

**Files:**
- Create: `tests/test_pipeline.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Write failing tests**

`tests/test_pipeline.py`:

```python
from classifier import assign_bundle_id


def test_bundle_both_revs():
    assert assign_bundle_id("16-01-19-2602", "A", "1", "S1") == "16-01-19-2602__N1LA"


def test_bundle_numeric_only():
    assert assign_bundle_id("16-01-19-2602", "", "2", "S1") == "16-01-19-2602__N2"


def test_bundle_letter_only():
    assert assign_bundle_id("16-01-19-2602", "B", "", "S1") == "16-01-19-2602__LB"


def test_bundle_neither():
    assert assign_bundle_id("16-01-19-2602", "", "", "S1") == "16-01-19-2602__R0"


def test_bundle_no_ref():
    assert assign_bundle_id("", "", "", "C-A-ED-SA-15760.01-0068") == "unmatched__C-A-ED-SA-15760.01-0068"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k bundle
```

Expected: 5 fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
def assign_bundle_id(cust_ref: str, letter_rev: str, numeric_rev: str,
                     submission_folder: str) -> str:
    """Per spec §8."""
    if cust_ref:
        if letter_rev and numeric_rev:
            return f"{cust_ref}__N{numeric_rev}L{letter_rev}"
        if numeric_rev:
            return f"{cust_ref}__N{numeric_rev}"
        if letter_rev:
            return f"{cust_ref}__L{letter_rev}"
        return f"{cust_ref}__R0"
    return f"unmatched__{submission_folder}"
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k bundle
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_pipeline.py
git commit -m "feat: bundle id assignment with rev encoding"
```

---

## Task 15: is_latest per axis + combined precedence

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline.py`:

```python
from classifier import compute_is_latest_for_group


def test_is_latest_letter_only():
    rows = [
        {"cust_ref": "x", "letter_rev": "A", "numeric_rev": ""},
        {"cust_ref": "x", "letter_rev": "B", "numeric_rev": ""},
        {"cust_ref": "x", "letter_rev": "", "numeric_rev": ""},
    ]
    out = compute_is_latest_for_group(rows)
    assert [r["is_latest_letter"] for r in out] == [False, True, False]
    assert [r["is_latest_numeric"] for r in out] == [False, False, False]
    # Combined: no numeric in group -> use letter axis
    assert [r["is_latest"] for r in out] == [False, True, False]


def test_is_latest_numeric_supersedes_letter():
    rows = [
        {"cust_ref": "x", "letter_rev": "A", "numeric_rev": ""},
        {"cust_ref": "x", "letter_rev": "B", "numeric_rev": ""},
        {"cust_ref": "x", "letter_rev": "", "numeric_rev": "1"},
    ]
    out = compute_is_latest_for_group(rows)
    # Group has numeric -> is_latest = is_latest_numeric only
    assert [r["is_latest"] for r in out] == [False, False, True]


def test_is_latest_numeric_compare_numerically():
    rows = [
        {"cust_ref": "x", "letter_rev": "", "numeric_rev": "2"},
        {"cust_ref": "x", "letter_rev": "", "numeric_rev": "12"},
    ]
    out = compute_is_latest_for_group(rows)
    assert [r["is_latest_numeric"] for r in out] == [False, True]


def test_is_latest_singleton():
    rows = [{"cust_ref": "x", "letter_rev": "A", "numeric_rev": ""}]
    out = compute_is_latest_for_group(rows)
    assert out[0]["is_latest_letter"] is True
    assert out[0]["is_latest"] is True


def test_is_latest_no_revs_in_group():
    rows = [
        {"cust_ref": "x", "letter_rev": "", "numeric_rev": ""},
        {"cust_ref": "x", "letter_rev": "", "numeric_rev": ""},
    ]
    out = compute_is_latest_for_group(rows)
    assert all(r["is_latest_letter"] is False for r in out)
    assert all(r["is_latest_numeric"] is False for r in out)
    assert all(r["is_latest"] is False for r in out)
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k latest
```

Expected: 5 fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
def compute_is_latest_for_group(rows: list[dict]) -> list[dict]:
    """Per spec §7.2/§7.3: set is_latest_letter, is_latest_numeric, is_latest on each row.

    Modifies rows in place AND returns them. Letter and numeric axes computed
    independently. Combined `is_latest`: numeric supersedes letter — if any row in
    the group has a numeric_rev, only is_latest_numeric counts; else is_latest_letter.
    """
    # Letter winner
    letters = [(i, r.get("letter_rev", "")) for i, r in enumerate(rows) if r.get("letter_rev")]
    letter_winner = max(letters, key=lambda x: x[1])[0] if letters else None
    # Numeric winner
    numerics = [(i, int(r["numeric_rev"])) for i, r in enumerate(rows) if r.get("numeric_rev")]
    numeric_winner = max(numerics, key=lambda x: x[1])[0] if numerics else None

    has_any_numeric = numeric_winner is not None

    for i, r in enumerate(rows):
        r["is_latest_letter"] = (i == letter_winner)
        r["is_latest_numeric"] = (i == numeric_winner)
        if has_any_numeric:
            r["is_latest"] = r["is_latest_numeric"]
        else:
            r["is_latest"] = r["is_latest_letter"]
    return rows
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k latest
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_pipeline.py
git commit -m "feat: per-axis is_latest with numeric-supersedes-letter precedence"
```

---

## Task 16: Revision drift

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline.py`:

```python
from classifier import classify_revision_drift


def test_drift_unknown_when_no_schedule():
    assert classify_revision_drift(file_letter="A", file_numeric="", schedule_rev="") == "unknown"
    assert classify_revision_drift(file_letter="", file_numeric="", schedule_rev="A") == "unknown"


def test_drift_aligned_letter():
    assert classify_revision_drift(file_letter="B", file_numeric="", schedule_rev="B") == "aligned"


def test_drift_aligned_numeric():
    assert classify_revision_drift(file_letter="", file_numeric="2", schedule_rev="2") == "aligned"


def test_drift_disk_newer_letter():
    assert classify_revision_drift(file_letter="C", file_numeric="", schedule_rev="A") == "disk_newer"


def test_drift_schedule_newer_letter():
    assert classify_revision_drift(file_letter="A", file_numeric="", schedule_rev="C") == "schedule_newer"


def test_drift_disk_newer_numeric():
    assert classify_revision_drift(file_letter="", file_numeric="3", schedule_rev="1") == "disk_newer"


def test_drift_schedule_newer_numeric():
    assert classify_revision_drift(file_letter="", file_numeric="1", schedule_rev="3") == "schedule_newer"


def test_drift_cross_axis_letter_to_numeric():
    # schedule says numeric, disk has only letter
    assert classify_revision_drift(file_letter="B", file_numeric="", schedule_rev="1") == "cross_axis"


def test_drift_cross_axis_numeric_to_letter():
    assert classify_revision_drift(file_letter="", file_numeric="2", schedule_rev="A") == "cross_axis"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k drift
```

Expected: 9 fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
def classify_revision_drift(*, file_letter: str, file_numeric: str, schedule_rev: str) -> str:
    """Per spec §7.3."""
    sched = schedule_rev.strip()
    if not sched:
        return "unknown"
    if not file_letter and not file_numeric:
        return "unknown"
    sched_is_numeric = sched.isdigit()
    sched_is_letter = len(sched) == 1 and sched.isalpha()
    if sched_is_numeric:
        if file_numeric:
            f, s = int(file_numeric), int(sched)
            if f == s:
                return "aligned"
            return "disk_newer" if f > s else "schedule_newer"
        # No numeric on disk -> cross axis
        return "cross_axis"
    if sched_is_letter:
        sched_u = sched.upper()
        if file_letter:
            if file_letter == sched_u:
                return "aligned"
            return "disk_newer" if file_letter > sched_u else "schedule_newer"
        return "cross_axis"
    return "unknown"
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k drift
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_pipeline.py
git commit -m "feat: revision_drift classifier (5 states)"
```

---

## Task 17: Target paths + collision detection

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_pipeline.py`:

```python
from classifier import build_target_paths, detect_target_collisions


def test_build_target_matched():
    out = build_target_paths(
        cust_ref="16-01-19-2602", letter_rev="A", numeric_rev="",
        type_code="DAS", form="Sheet", bucket="Datasheets", discipline="PIPNG",
        title="VALVE LIST", extension=".pdf",
        submission_folder="C-A-ED-SA-15760.01-0068", source_filename="x.pdf",
    )
    assert out["proposed_target_folder"] == "Sheet/Datasheets/PIPNG/"
    assert out["proposed_target_filename"] == "16-01-19-2602_LA_DAS_VALVE_LIST.pdf"


def test_build_target_both_revs():
    out = build_target_paths(
        cust_ref="16-01-19-2602", letter_rev="A", numeric_rev="1",
        type_code="DAS", form="Sheet", bucket="Datasheets", discipline="PIPNG",
        title="VALVE LIST", extension=".pdf",
        submission_folder="S1", source_filename="x.pdf",
    )
    assert out["proposed_target_filename"] == "16-01-19-2602_N1LA_DAS_VALVE_LIST.pdf"


def test_build_target_no_revs_uses_R0():
    out = build_target_paths(
        cust_ref="16-01-19-2602", letter_rev="", numeric_rev="",
        type_code="DOC", form="Document", bucket="Documents", discipline="UNK",
        title="some doc", extension=".pdf",
        submission_folder="S1", source_filename="x.pdf",
    )
    assert "_R0_" in out["proposed_target_filename"]


def test_build_target_unmatched():
    out = build_target_paths(
        cust_ref="", letter_rev="", numeric_rev="",
        type_code="DOC", form="Document", bucket="Documents", discipline="UNK",
        title="", extension=".pdf",
        submission_folder="S1", source_filename="Attachment-1.pdf",
    )
    # Unmatched: prefix submission folder
    assert out["proposed_target_filename"] == "S1__Attachment-1.pdf"


def test_build_target_short_title_truncated():
    long = "X" * 200
    out = build_target_paths(
        cust_ref="16-01-19-2602", letter_rev="A", numeric_rev="",
        type_code="DAS", form="Sheet", bucket="Datasheets", discipline="PIPNG",
        title=long, extension=".pdf",
        submission_folder="S1", source_filename="x.pdf",
    )
    # short_title segment is at most 60 chars
    parts = out["proposed_target_filename"].rsplit(".", 1)[0].split("_")
    short_title_seg = "_".join(parts[4:])
    assert len(short_title_seg) <= 60


def test_build_target_short_title_sanitised():
    out = build_target_paths(
        cust_ref="16-01-19-2602", letter_rev="A", numeric_rev="",
        type_code="DAS", form="Sheet", bucket="Datasheets", discipline="PIPNG",
        title="WATER & FUEL/GAS - SAHIL", extension=".pdf",
        submission_folder="S1", source_filename="x.pdf",
    )
    # alphanumerics + underscores only in short_title
    fn = out["proposed_target_filename"]
    short = fn.split("DAS_")[1].rsplit(".", 1)[0]
    assert all(c.isalnum() or c == "_" for c in short)


# Collision detection
def test_collisions_marks_duplicates():
    rows = [
        {"proposed_target_folder": "X/", "proposed_target_filename": "f.pdf",
         "bundle_id": "b1", "notes": ""},
        {"proposed_target_folder": "X/", "proposed_target_filename": "f.pdf",
         "bundle_id": "b2", "notes": ""},
        {"proposed_target_folder": "X/", "proposed_target_filename": "g.pdf",
         "bundle_id": "b3", "notes": ""},
    ]
    detect_target_collisions(rows)
    assert rows[0]["target_collision"] is True
    assert rows[1]["target_collision"] is True
    assert rows[2]["target_collision"] is False
    assert "b2" in rows[0]["notes"] or "b1" in rows[1]["notes"]
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k target
```

Expected: tests fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
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


def build_target_paths(
    *, cust_ref: str, letter_rev: str, numeric_rev: str,
    type_code: str, form: str, bucket: str, discipline: str,
    title: str, extension: str,
    submission_folder: str, source_filename: str,
) -> dict:
    """Per spec §9 / Proposed filename template."""
    folder = f"{form}/{bucket}/{discipline}/"
    if not cust_ref:
        # Unmatched: prefix submission folder
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


def detect_target_collisions(rows: list[dict]) -> None:
    """Modifies rows in place. Sets `target_collision` (bool) on every row,
    appends colliding peer's bundle_id to `notes`."""
    from collections import defaultdict
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
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
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k target
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_pipeline.py
git commit -m "feat: target path builder + collision detection"
```

---

## Task 18: Pipeline orchestration (`enrich_files`)

**Files:**
- Modify: `tests/test_pipeline.py`
- Modify: `classifier.py` (Section C)

- [ ] **Step 1: Add a failing integration test**

Append to `tests/test_pipeline.py`:

```python
from classifier import enrich_files


def test_enrich_files_end_to_end(sample_schedule_path, sample_dossier_path,
                                 sample_tree_path, tmp_path):
    overrides_path = tmp_path / "overrides.csv"
    overrides_path.write_text("cust_ref,bucket\n", encoding="utf-8")
    rows = enrich_files(
        schedule_path=sample_schedule_path,
        dossier_path=sample_dossier_path,
        tree_path=sample_tree_path,
        overrides_path=overrides_path,
    )
    # All TO CLIENT files turned into rows
    assert len(rows) >= 8

    # Every row has the full set of columns
    required = {
        "source_path", "source_filename", "submission_folder", "subfolder",
        "cust_ref", "is_crs", "is_transmittal_cover", "is_archive",
        "letter_rev", "numeric_rev", "extension",
        "pcs_doc_no", "title", "discipline", "schedule_rev",
        "type_code", "form", "type_bucket", "bucket_score",
        "runner_up_bucket", "runner_up_score", "bucket_source", "bucket_confidence",
        "bundle_id", "is_latest_letter", "is_latest_numeric", "is_latest",
        "revision_drift", "match_status",
        "proposed_target_folder", "proposed_target_filename",
        "target_collision", "notes",
    }
    for r in rows:
        missing = required - set(r.keys())
        assert not missing, f"missing columns: {missing}"

    # CRS file present and pinned to CRS bucket
    crs_rows = [r for r in rows if r["filename"] if r.get("is_crs")] if False else [r for r in rows if r["is_crs"]]
    assert len(crs_rows) >= 1
    assert all(r["type_bucket"] == "CRS" for r in crs_rows)

    # Cover sheet present
    cover = [r for r in rows if r["is_transmittal_cover"]]
    assert len(cover) >= 1
    assert cover[0]["form"] == "CoverSheet"

    # Archive present
    arc = [r for r in rows if r["is_archive"]]
    assert len(arc) >= 1
    assert arc[0]["form"] == "Archive"

    # Em-dash filename: ref correctly extracted after normalisation
    em = [r for r in rows if r["source_filename"].count("–") > 0
          or r.get("notes", "").startswith("normalised")]
    # At least one em-dash file's ref should resolve correctly
    em_resolved = [r for r in rows if r["cust_ref"] == "16-01-84-2602"]
    assert len(em_resolved) >= 1
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k enrich
```

Expected: fail with ImportError.

- [ ] **Step 3: Implement `enrich_files`**

Append to `classifier.py` Section C:

```python
from collections import Counter, defaultdict


def enrich_files(*, schedule_path, dossier_path, tree_path, overrides_path) -> list[dict]:
    """Run the full Phase-1 pipeline. Returns the list of fully-populated row dicts.

    Does NOT write outputs (CSV / audit / selftest). Caller does that.
    """
    schedule_df = load_schedule(schedule_path)
    dossier_df = load_dossier(dossier_path)
    raw = parse_transmittals(tree_path)
    overrides = load_overrides(overrides_path)

    # Schedule lookups by cust_ref
    schedule_lookup = {r["cust_ref"]: r for _, r in schedule_df.iterrows()}
    schedule_disc = {r["cust_ref"]: r["discipline"] for _, r in schedule_df.iterrows()}
    schedule_rev = {r["cust_ref"]: r["schedule_rev"] for _, r in schedule_df.iterrows()}
    schedule_title = {r["cust_ref"]: r["title"] for _, r in schedule_df.iterrows()}
    schedule_pcs = {r["cust_ref"]: r["pcs_doc_no"] for _, r in schedule_df.iterrows()}
    seg2_map = build_seg2_discipline_map(schedule_df)
    dossier_by_doc = {r["doc_no"]: r for _, r in dossier_df.iterrows()}

    # First pass: per-record extraction (without sibling rev or is_latest yet)
    rows: list[dict] = []
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

    # Second pass: sibling rev inheritance for ref-less revs
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
            r["notes"] = (r["notes"] + (" | " if r["notes"] else "") + "rev_inherited_from_sibling").strip()

    # Per-submission discipline majority + multi-disc detection (used by tier 4)
    sub_disciplines: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["cust_ref"] and r["cust_ref"] in schedule_disc:
            sub_disciplines[r["submission_folder"]].append(schedule_disc[r["cust_ref"]])
    sub_majority: dict[str, str] = {}
    multi_disc: dict[str, bool] = {}
    for sub, ds in sub_disciplines.items():
        c = Counter(ds)
        sub_majority[sub] = c.most_common(1)[0][0] if c else ""
        multi_disc[sub] = len(c) > 2

    # Third pass: classify each row (form, bucket, discipline, type_code, etc.)
    for r in rows:
        norm = r.pop("_norm_filename")
        cust_ref = r["cust_ref"]
        # Title from schedule (preferred) or dossier
        title = schedule_title.get(cust_ref, "")
        type_code_dossier = ""
        if cust_ref in dossier_by_doc:
            if not title:
                title = dossier_by_doc[cust_ref]["title"]
            type_code_dossier = dossier_by_doc[cust_ref]["type_code"]
        r["title"] = title
        r["pcs_doc_no"] = schedule_pcs.get(cust_ref, "")
        r["schedule_rev"] = schedule_rev.get(cust_ref, "")

        # Bucket resolution chain
        bucket_source = ""
        if cust_ref and cust_ref in overrides:
            bucket = overrides[cust_ref]
            bucket_source = "override"
            confidence = "high"
            score_sum, score_top = 0, 0
            runner_up, runner_score = "", 0
        elif r["is_archive"]:
            bucket = "Documents"
            bucket_source = "archive"
            confidence = "low"
            score_sum, score_top = 0, 0
            runner_up, runner_score = "", 0
        elif r["is_transmittal_cover"]:
            bucket = "Documents"
            bucket_source = "cover_sheet"
            confidence = "low"
            score_sum, score_top = 0, 0
            runner_up, runner_score = "", 0
        elif r["is_crs"]:
            bucket = "CRS"
            bucket_source = "crs_pin"
            confidence = "high"
            score_sum, score_top = 0, 0
            runner_up, runner_score = "", 0
        elif type_code_dossier and type_code_dossier in TYPE_TO_BUCKET:
            bucket = TYPE_TO_BUCKET[type_code_dossier]
            bucket_source = "dossier_type"
            confidence = "high"
            score_sum, score_top = 0, 0
            runner_up, runner_score = "", 0
        else:
            scores = score_buckets(title, norm)
            picked = pick_bucket(scores)
            bucket = picked["bucket"]
            bucket_source = "weighted" if picked["score_sum"] > 0 else "fallback"
            confidence = picked["confidence"]
            score_sum, score_top = picked["score_sum"], picked["score_top"]
            runner_up, runner_score = picked["runner_up_bucket"], picked["runner_up_score"]

        r["type_bucket"] = bucket
        r["bucket_source"] = bucket_source
        r["bucket_confidence"] = confidence
        r["bucket_score"] = score_sum
        r["runner_up_bucket"] = runner_up
        r["runner_up_score"] = runner_score

        # Form: pass 1 + pass 2
        pre = resolve_form_pre(norm, has_ref=bool(cust_ref))
        if pre:
            r["form"] = pre
        else:
            r["form"] = resolve_form_post(norm, bucket)

        # type_code
        r["type_code"] = type_code_dossier or BUCKET_PRIMARY_CODE[bucket]

        # discipline
        sub = r["submission_folder"]
        r["discipline"] = derive_discipline(
            cust_ref=cust_ref, title=title, filename=norm,
            schedule_lookup=schedule_disc, seg2_map=seg2_map,
            submission_majority=sub_majority.get(sub, ""),
            multi_disc_submission=multi_disc.get(sub, False),
        )

        # bundle id
        r["bundle_id"] = assign_bundle_id(cust_ref, r["letter_rev"], r["numeric_rev"], sub)

        # match_status
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

    # Fourth pass: is_latest per cust_ref group (only for matched files)
    by_ref = defaultdict(list)
    for r in rows:
        if r["cust_ref"]:
            by_ref[r["cust_ref"]].append(r)
    for group in by_ref.values():
        compute_is_latest_for_group(group)
    # Ref-less rows: all is_latest_* False
    for r in rows:
        if not r["cust_ref"]:
            r.setdefault("is_latest_letter", False)
            r.setdefault("is_latest_numeric", False)
            r.setdefault("is_latest", False)

    # Fifth pass: revision_drift
    for r in rows:
        r["revision_drift"] = classify_revision_drift(
            file_letter=r["letter_rev"], file_numeric=r["numeric_rev"],
            schedule_rev=r["schedule_rev"],
        )

    # Sixth pass: target paths
    for r in rows:
        tp = build_target_paths(
            cust_ref=r["cust_ref"], letter_rev=r["letter_rev"], numeric_rev=r["numeric_rev"],
            type_code=r["type_code"], form=r["form"], bucket=r["type_bucket"],
            discipline=r["discipline"], title=r["title"], extension=r["extension"],
            submission_folder=r["submission_folder"], source_filename=r["source_filename"],
        )
        r.update(tp)

    # Seventh pass: collision detection
    detect_target_collisions(rows)

    # Test alias: legacy column the integration test uses
    for r in rows:
        r["filename"] = r["source_filename"]

    return rows
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_pipeline.py -v -k enrich
```

Expected: passes.

- [ ] **Step 5: Run all tests so far to confirm no regressions**

```bash
.venv/Scripts/pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add classifier.py tests/test_pipeline.py
git commit -m "feat: enrich_files pipeline orchestration (7 passes)"
```

---

## Task 19: CSV writer

**Files:**
- Create: `tests/test_writers.py`
- Modify: `classifier.py` (Section A)

- [ ] **Step 1: Write failing tests**

`tests/test_writers.py`:

```python
import csv
from classifier import write_csv, CSV_COLUMNS


def test_csv_columns_match_spec():
    # 33 columns total per spec §9
    assert len(CSV_COLUMNS) == 33
    expected_first_5 = ["source_path", "source_filename", "submission_folder",
                        "subfolder", "cust_ref"]
    assert list(CSV_COLUMNS[:5]) == expected_first_5
    assert "letter_rev" in CSV_COLUMNS
    assert "numeric_rev" in CSV_COLUMNS
    assert "form" in CSV_COLUMNS
    assert "bucket_score" in CSV_COLUMNS
    assert "runner_up_bucket" in CSV_COLUMNS
    assert "is_latest_letter" in CSV_COLUMNS
    assert "is_latest_numeric" in CSV_COLUMNS
    assert "revision_drift" in CSV_COLUMNS
    assert "target_collision" in CSV_COLUMNS
    assert CSV_COLUMNS[-1] == "notes"


def test_write_csv_roundtrip(tmp_path):
    rows = [
        {col: "" for col in CSV_COLUMNS}
        for _ in range(2)
    ]
    rows[0]["cust_ref"] = "16-01-19-2602"
    rows[0]["title"] = "VALVE LIST"
    rows[0]["is_latest"] = True
    rows[0]["is_archive"] = False
    rows[1]["cust_ref"] = "16-01-08-2606"
    out = tmp_path / "x.csv"
    write_csv(rows, out)
    assert out.exists()

    with out.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        loaded = list(reader)
    assert len(loaded) == 2
    assert loaded[0]["cust_ref"] == "16-01-19-2602"
    assert loaded[0]["title"] == "VALVE LIST"
    assert loaded[0]["is_latest"] == "true"
    assert loaded[0]["is_archive"] == "false"
    # Extra/missing columns in input dicts shouldn't break the writer
    for col in CSV_COLUMNS:
        assert col in loaded[0]


def test_write_csv_empty_string_for_missing(tmp_path):
    rows = [{"cust_ref": "16-01-19-2602"}]  # everything else missing
    out = tmp_path / "x.csv"
    write_csv(rows, out)
    with out.open(newline="", encoding="utf-8") as f:
        loaded = list(csv.DictReader(f))
    assert loaded[0]["title"] == ""
    assert loaded[0]["pcs_doc_no"] == ""
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k csv
```

Expected: fail with ImportError.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section A:

```python
CSV_COLUMNS: tuple[str, ...] = (
    "source_path", "source_filename", "submission_folder", "subfolder",
    "cust_ref", "is_crs", "is_transmittal_cover", "is_archive",
    "letter_rev", "numeric_rev", "extension",
    "pcs_doc_no", "title", "discipline", "schedule_rev",
    "type_code", "form", "type_bucket", "bucket_score",
    "runner_up_bucket", "runner_up_score", "bucket_source", "bucket_confidence",
    "bundle_id", "is_latest_letter", "is_latest_numeric", "is_latest",
    "revision_drift", "match_status",
    "proposed_target_folder", "proposed_target_filename",
    "target_collision", "notes",
)


def _csv_value(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return ""
    return str(v)


def write_csv(rows: list[dict], path: Path | str) -> None:
    """Write the classified rows to CSV. Missing columns -> empty string.
    Booleans serialised as lowercase 'true'/'false'."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for r in rows:
            writer.writerow([_csv_value(r.get(col, "")) for col in CSV_COLUMNS])
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k csv
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_writers.py
git commit -m "feat: CSV writer (33 columns)"
```

---

## Task 20: Audit writer

**Files:**
- Modify: `tests/test_writers.py`
- Modify: `classifier.py` (Section C)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_writers.py`:

```python
from classifier import write_audit


def test_write_audit_creates_file(tmp_path):
    rows = [{
        "source_filename": "x.pdf", "cust_ref": "16-01-19-2602",
        "is_crs": False, "is_transmittal_cover": False, "is_archive": False,
        "type_bucket": "Drawings", "bucket_source": "weighted",
        "bucket_confidence": "high", "bucket_score": 5,
        "runner_up_bucket": "Documents", "runner_up_score": 0,
        "form": "Drawing", "discipline": "PIPNG", "match_status": "matched",
        "submission_folder": "S1", "is_latest": True,
        "letter_rev": "A", "numeric_rev": "", "schedule_rev": "A",
        "revision_drift": "aligned",
        "proposed_target_folder": "Drawing/Drawings/PIPNG/",
        "proposed_target_filename": "16-01-19-2602_LA_DWG_FOO.pdf",
        "target_collision": False,
        "notes": "",
    }]
    out = tmp_path / "audit.txt"
    write_audit(rows=rows, schedule_df=None, override_count=0,
                override_unknown_refs=[], path=out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    # Each spec'd section header present
    for header in ("Counts", "Bucket", "Schedule coverage", "Refs not in schedule",
                   "Fallthrough", "Ambiguous", "Revision drift",
                   "Multi-discipline", "Target collisions", "Override hits"):
        assert header in text


def test_audit_logs_unknown_overrides(tmp_path):
    out = tmp_path / "audit.txt"
    write_audit(rows=[], schedule_df=None, override_count=0,
                override_unknown_refs=["16-99-99-9999"], path=out)
    text = out.read_text(encoding="utf-8")
    assert "16-99-99-9999" in text
    assert "no effect" in text.lower()
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k audit
```

Expected: fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section C:

```python
def write_audit(*, rows: list[dict], schedule_df, override_count: int,
                override_unknown_refs: list[str], path) -> None:
    """Write the human-readable audit text per spec §10."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _count(field: str) -> Counter:
        return Counter(r.get(field, "") for r in rows)

    lines: list[str] = []
    lines.append("=== Counts ===")
    lines.append(f"Total files: {len(rows)}")
    for field in ("match_status", "bucket_confidence", "bucket_source", "form"):
        lines.append(f"\nBy {field}:")
        for k, c in _count(field).most_common():
            lines.append(f"  {k or '(empty)'}: {c}")

    lines.append("\n=== Bucket x discipline matrix ===")
    matrix = Counter((r.get("type_bucket", ""), r.get("discipline", "")) for r in rows)
    buckets = sorted({b for (b, _) in matrix})
    disciplines = sorted({d for (_, d) in matrix})
    header = "bucket".ljust(20) + " | " + " | ".join(d.rjust(8) for d in disciplines)
    lines.append(header)
    for b in buckets:
        cells = [str(matrix.get((b, d), 0)).rjust(8) for d in disciplines]
        lines.append(b.ljust(20) + " | " + " | ".join(cells))

    lines.append("\n=== Schedule coverage ===")
    if schedule_df is not None and len(schedule_df):
        present = {r["cust_ref"] for r in rows if r.get("cust_ref")}
        missing = [ref for ref in schedule_df["cust_ref"] if ref not in present]
        lines.append(f"Schedule docs with files: {len(schedule_df) - len(missing)} / {len(schedule_df)}")
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

    lines.append("\n=== Fallthrough titles (bucket_source=fallback, score=0) ===")
    fallthrough = [r for r in rows if r.get("bucket_source") == "fallback"]
    lines.append(f"Count: {len(fallthrough)}")
    for r in fallthrough[:80]:
        lines.append(f"  [{r.get('discipline','UNK')}] {r.get('title','')} :: {r.get('source_filename','')}")
    if len(fallthrough) > 80:
        lines.append(f"  ... and {len(fallthrough) - 80} more")

    lines.append("\n=== Ambiguous classifications (gap <= 1) ===")
    ambig = [r for r in rows
             if isinstance(r.get("bucket_score"), int)
             and isinstance(r.get("runner_up_score"), int)
             and r["bucket_score"] > 0
             and r["bucket_score"] - r["runner_up_score"] <= 1]
    lines.append(f"Count: {len(ambig)}")
    for r in ambig[:30]:
        lines.append(f"  {r.get('cust_ref','')} {r.get('type_bucket','')}({r['bucket_score']}) "
                     f"vs {r.get('runner_up_bucket','')}({r['runner_up_score']}): {r.get('title','')[:80]}")

    lines.append("\n=== Revision drift ===")
    drift_counts = _count("revision_drift")
    for k, c in drift_counts.most_common():
        lines.append(f"  {k}: {c}")
    actionable = [r for r in rows if r.get("revision_drift") in ("schedule_newer", "cross_axis")]
    if actionable:
        lines.append(f"\nActionable (schedule_newer or cross_axis):")
        for r in actionable[:50]:
            lines.append(f"  {r.get('cust_ref','')}  drift={r.get('revision_drift','')}  "
                         f"file=L{r.get('letter_rev','')}/N{r.get('numeric_rev','')}  "
                         f"sched={r.get('schedule_rev','')}")

    lines.append("\n=== Multi-discipline submissions ===")
    submission_disc: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r.get("discipline") and r["discipline"] != "UNK":
            submission_disc[r["submission_folder"]].add(r["discipline"])
    multi = {s: ds for s, ds in submission_disc.items() if len(ds) > 2}
    lines.append(f"Count: {len(multi)}")
    for s, ds in list(multi.items())[:30]:
        lines.append(f"  {s}: {sorted(ds)}")

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
```

- [ ] **Step 4: Run, expect pass**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k audit
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_writers.py
git commit -m "feat: audit writer (10 sections)"
```

---

## Task 21: Dossier self-test

**Files:**
- Modify: `tests/test_writers.py`
- Modify: `classifier.py` (Section C)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_writers.py`:

```python
from classifier import run_dossier_selftest


def test_selftest_returns_metrics(sample_dossier_path, tmp_path):
    out = tmp_path / "selftest.txt"
    result = run_dossier_selftest(sample_dossier_path, out)
    assert "accuracy" in result
    assert "total" in result
    assert "correct" in result
    assert 0.0 <= result["accuracy"] <= 1.0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Accuracy:" in text


def test_selftest_high_baseline_on_real_dossier(real_dossier_path, tmp_path):
    out = tmp_path / "selftest.txt"
    result = run_dossier_selftest(real_dossier_path, out)
    # Spec §11: initial gate at 85.5%
    assert result["accuracy"] >= 0.855, f"Got {result['accuracy']:.3f}"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k selftest
```

Expected: 2 fail.

- [ ] **Step 3: Implement**

Append to `classifier.py` Section C:

```python
def run_dossier_selftest(dossier_path, out_path) -> dict:
    """Classify each dossier row by its title alone and compare to its known Type.

    Returns {accuracy, total, correct, mismatches: list[dict]}. Writes a human-readable
    report to out_path.
    """
    df = load_dossier(dossier_path)
    total = len(df)
    correct = 0
    mismatches: list[dict] = []
    confusion: dict[tuple[str, str], int] = defaultdict(int)
    for _, r in df.iterrows():
        expected = TYPE_TO_BUCKET.get(r["type_code"], "Documents")
        scores = score_buckets(r["title"], "")
        picked = pick_bucket(scores)
        predicted = picked["bucket"]
        confusion[(expected, predicted)] += 1
        if predicted == expected:
            correct += 1
        else:
            mismatches.append({
                "type_code": r["type_code"], "expected": expected,
                "predicted": predicted, "title": r["title"],
            })
    acc = correct / total if total else 1.0

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("=== Dossier self-test ===")
    lines.append(f"Total: {total}")
    lines.append(f"Correct: {correct}")
    lines.append(f"Accuracy: {acc:.4f} ({correct}/{total})")

    lines.append("\n=== Confusion (expected -> predicted): count ===")
    for (e, p), c in sorted(confusion.items(), key=lambda x: -x[1]):
        marker = " " if e == p else "*"
        lines.append(f"  {marker} {e:18} -> {p:18} : {c}")

    lines.append("\n=== Mismatches ===")
    for m in mismatches:
        lines.append(f"  type={m['type_code']:5} expected={m['expected']:18} "
                     f"predicted={m['predicted']:18} title={m['title'][:90]}")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"accuracy": acc, "total": total, "correct": correct,
            "mismatches": mismatches}
```

- [ ] **Step 4: Run, expect pass (real dossier baseline)**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k selftest
```

Expected: 2 passed. The real-dossier accuracy is printed and is ≥0.855.

- [ ] **Step 5: Commit**

```bash
git add classifier.py tests/test_writers.py
git commit -m "feat: dossier self-test (CI gate)"
```

---

## Task 22: CLI entry point + idempotency

**Files:**
- Modify: `tests/test_writers.py`
- Modify: `classifier.py` (Section C)

- [ ] **Step 1: Add failing test**

Append to `tests/test_writers.py`:

```python
import subprocess
import sys
from pathlib import Path


def test_cli_runs_on_real_data(real_schedule_path, real_dossier_path,
                               real_tree_path, tmp_path):
    out_dir = tmp_path / "out"
    overrides = tmp_path / "ov.csv"
    overrides.write_text("cust_ref,bucket\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "classifier.py",
         "--schedule", str(real_schedule_path),
         "--dossier", str(real_dossier_path),
         "--tree", str(real_tree_path),
         "--overrides", str(overrides),
         "--output-dir", str(out_dir),
         "--no-selftest"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "classified_files.csv").exists()
    assert (out_dir / "classification_audit.txt").exists()
    # Selftest skipped
    assert not (out_dir / "dossier_selftest.txt").exists()


def test_cli_idempotent(real_schedule_path, real_dossier_path,
                       real_tree_path, tmp_path):
    out_dir = tmp_path / "out"
    overrides = tmp_path / "ov.csv"
    overrides.write_text("cust_ref,bucket\n", encoding="utf-8")
    cmd = [sys.executable, "classifier.py",
           "--schedule", str(real_schedule_path),
           "--dossier", str(real_dossier_path),
           "--tree", str(real_tree_path),
           "--overrides", str(overrides),
           "--output-dir", str(out_dir),
           "--no-selftest"]
    cwd = Path(__file__).resolve().parents[1]
    subprocess.run(cmd, cwd=cwd, check=True, timeout=60)
    csv1 = (out_dir / "classified_files.csv").read_bytes()
    subprocess.run(cmd, cwd=cwd, check=True, timeout=60)
    csv2 = (out_dir / "classified_files.csv").read_bytes()
    assert csv1 == csv2, "CSV changed across identical reruns"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k cli
```

Expected: fail (CLI not implemented).

- [ ] **Step 3: Implement CLI**

Replace the `if __name__ == "__main__":` block at the bottom of `classifier.py` with:

```python
import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Document classifier (Phase 1)")
    parser.add_argument("--schedule", default="4. List of DOC + Schedule (Correct doc).xls")
    parser.add_argument("--dossier", default="50703-EPC Dossier Index - PDF (Updated on 27-03-2014).xlsx")
    parser.add_argument("--tree", default="Transmittals.txt")
    parser.add_argument("--overrides", default="overrides/ref_to_bucket.csv")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--no-selftest", action="store_true",
                        help="Skip the dossier self-test CI gate.")
    parser.add_argument("--gate-threshold", type=float, default=0.855,
                        help="Minimum dossier-selftest accuracy required (default: 0.855).")
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    overrides = load_overrides(args.overrides)
    schedule_df = load_schedule(args.schedule)
    sched_refs = set(schedule_df["cust_ref"])
    override_unknown = [ref for ref in overrides if ref not in sched_refs]

    rows = enrich_files(
        schedule_path=args.schedule,
        dossier_path=args.dossier,
        tree_path=args.tree,
        overrides_path=args.overrides,
    )

    write_csv(rows, out_dir / "classified_files.csv")
    write_audit(
        rows=rows, schedule_df=schedule_df,
        override_count=sum(1 for r in rows if r.get("bucket_source") == "override"),
        override_unknown_refs=override_unknown,
        path=out_dir / "classification_audit.txt",
    )

    if not args.no_selftest:
        result = run_dossier_selftest(args.dossier, out_dir / "dossier_selftest.txt")
        if result["accuracy"] < args.gate_threshold:
            print(f"FAIL: dossier-selftest accuracy {result['accuracy']:.4f} "
                  f"below gate {args.gate_threshold:.4f}", file=sys.stderr)
            return 1
        print(f"OK: dossier-selftest accuracy {result['accuracy']:.4f} "
              f">= gate {args.gate_threshold:.4f}")

    print(f"OK: {len(rows)} rows -> {out_dir / 'classified_files.csv'}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
```

(Note: also add `import sys` at the top of the file if not already present.)

- [ ] **Step 4: Run CLI tests, expect pass**

```bash
.venv/Scripts/pytest tests/test_writers.py -v -k cli
```

Expected: 2 passed.

- [ ] **Step 5: Run full suite**

```bash
.venv/Scripts/pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add classifier.py tests/test_writers.py
git commit -m "feat: CLI entry point with idempotency + selftest gate"
```

---

## Task 23: End-to-end run on real data + acceptance check

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Run the CLI on real inputs**

```bash
.venv/Scripts/python classifier.py
```

Expected output: `OK: dossier-selftest accuracy 0.XXXX >= gate 0.8550` followed by `OK: ~3902 rows -> output/classified_files.csv`.

- [ ] **Step 2: Inspect outputs**

```bash
ls -la output/
.venv/Scripts/python -c "import pandas as pd; df=pd.read_csv('output/classified_files.csv'); print('rows:', len(df)); print(df['type_bucket'].value_counts()); print('high conf:', (df['bucket_confidence']=='high').mean())"
head -50 output/classification_audit.txt
head -30 output/dossier_selftest.txt
```

Eyeball: row count near 3,902; bucket distribution looks plausible; high-confidence ratio ≥0.75; selftest ≥0.855.

- [ ] **Step 3: Write acceptance test**

`tests/test_integration.py`:

```python
"""Acceptance criteria tests per spec §14."""
import csv
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(out_dir: Path) -> tuple[float, list[dict]]:
    overrides = out_dir / "ov.csv"
    overrides.write_text("cust_ref,bucket\n", encoding="utf-8")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, "classifier.py",
         "--overrides", str(overrides),
         "--output-dir", str(out_dir)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    elapsed = time.time() - t0
    assert result.returncode == 0, result.stderr
    with (out_dir / "classified_files.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return elapsed, rows


def test_acceptance_1_runs_under_15_seconds(tmp_path):
    elapsed, _ = _run_cli(tmp_path / "out")
    assert elapsed < 15.0, f"CLI took {elapsed:.1f}s (budget 15s)"


def test_acceptance_2_row_count_close_to_3902(tmp_path):
    _, rows = _run_cli(tmp_path / "out")
    assert 3895 <= len(rows) <= 3910


def test_acceptance_3_cust_ref_populated_90_percent(tmp_path):
    _, rows = _run_cli(tmp_path / "out")
    populated = sum(1 for r in rows if r["cust_ref"])
    assert populated / len(rows) >= 0.90


def test_acceptance_4_discipline_populated_95_percent(tmp_path):
    _, rows = _run_cli(tmp_path / "out")
    non_unk = sum(1 for r in rows if r["discipline"] and r["discipline"] != "UNK")
    assert non_unk / len(rows) >= 0.95


def test_acceptance_5_high_confidence_75_percent(tmp_path):
    _, rows = _run_cli(tmp_path / "out")
    high = sum(1 for r in rows if r["bucket_confidence"] == "high")
    medium = sum(1 for r in rows if r["bucket_confidence"] == "medium")
    low = sum(1 for r in rows if r["bucket_confidence"] == "low")
    assert high / len(rows) >= 0.75, f"high={high/len(rows):.2%}"
    assert medium / len(rows) >= 0.15, f"medium={medium/len(rows):.2%}"
    assert low / len(rows) <= 0.10, f"low={low/len(rows):.2%}"


def test_acceptance_6_selftest_gate_passes(tmp_path):
    out_dir = tmp_path / "out"
    overrides = out_dir / "ov.csv"
    out_dir.mkdir()
    overrides.write_text("cust_ref,bucket\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "classifier.py",
         "--overrides", str(overrides),
         "--output-dir", str(out_dir)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "dossier_selftest.txt").exists()
    text = (out_dir / "dossier_selftest.txt").read_text(encoding="utf-8")
    # Parse "Accuracy: 0.XXXX"
    line = next(l for l in text.splitlines() if l.startswith("Accuracy:"))
    acc = float(line.split()[1])
    assert acc >= 0.855


def test_acceptance_7_fallthrough_under_120(tmp_path):
    _, rows = _run_cli(tmp_path / "out")
    fallthrough = sum(1 for r in rows if r["bucket_source"] == "fallback")
    assert fallthrough <= 120, f"got {fallthrough} fallthrough titles"


def test_acceptance_8_idempotent(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    overrides = out_dir / "ov.csv"
    overrides.write_text("cust_ref,bucket\n", encoding="utf-8")
    cmd = [sys.executable, "classifier.py",
           "--overrides", str(overrides),
           "--output-dir", str(out_dir),
           "--no-selftest"]
    subprocess.run(cmd, cwd=ROOT, check=True, timeout=60)
    a = (out_dir / "classified_files.csv").read_bytes()
    subprocess.run(cmd, cwd=ROOT, check=True, timeout=60)
    b = (out_dir / "classified_files.csv").read_bytes()
    assert a == b
```

- [ ] **Step 4: Run acceptance suite**

```bash
.venv/Scripts/pytest tests/test_integration.py -v
```

Expected: all 8 acceptance tests pass. If any fail, fix the relevant rule (most likely the keyword bank for #5/#7) and re-run.

- [ ] **Step 5: Update gate threshold to (measured − 2pp) per spec §11**

Read the actual selftest accuracy from `output/dossier_selftest.txt`, subtract 0.02, update the default in `classifier.py:main()`'s `--gate-threshold` argparse default. Example: if measured 0.94, set default to 0.92.

```bash
grep "Accuracy:" output/dossier_selftest.txt
# Note the value, then edit classifier.py manually:
#   parser.add_argument("--gate-threshold", type=float, default=<measured-0.02>, ...)
```

- [ ] **Step 6: Final commit**

```bash
git add classifier.py tests/test_integration.py
git commit -m "test: acceptance criteria suite (spec §14) + lock in post-run gate"
```

- [ ] **Step 7: Run final suite, expect green**

```bash
.venv/Scripts/pytest -v
```

Expected: every test passes.

---

## Self-review (post-plan checklist)

**1. Spec coverage** — every section traced to a task:

| Spec section | Task(s) |
|---|---|
| §1-3 Problem / goal / baseline | Task 23 (acceptance verifies metrics) |
| §4 Architecture (sections A/B/C, 7-pass pipeline) | Tasks 0, 18 |
| §5.1 Form (5 values, two passes) | Task 8 |
| §5.2 Bucket taxonomy + keyword weights | Task 5 |
| §6.1 Filename normalisation | Task 1 |
| §6.1a Named regexes | Tasks 2, 5 |
| §6.2 Bucket resolution chain | Tasks 6, 7, 13, 18 |
| §6.3 Discipline resolution (5 tiers) | Task 12 |
| §7.1-7.3 Two-axis revision parsing + drift | Tasks 3, 4, 15, 16 |
| §8 Bundling | Task 14 |
| §9 33-column CSV | Task 19 |
| §10 Audit (10 sections) | Task 20 |
| §11 Dossier self-test (CI gate) | Task 21 |
| §12 Out of scope | Excluded — no archive extraction, no `FROM CLIENT`, no copying |
| §13 Tech stack | Task 0 |
| §14 Acceptance criteria | Task 23 |
| §15 Open questions | Phase 2; not in plan |

**2. Placeholder scan** — none present. All steps contain runnable code or exact commands. Two areas where the plan is intentionally light: (a) acceptance #5 thresholds may need a single keyword-bank tweak after first run — Task 23 step 4 has the explicit feedback loop; (b) gate threshold tuning is an explicit step with a concrete edit instruction in Task 23 step 5.

**3. Type consistency** — verified: `extract_revs` returns `(letter_rev, numeric_rev)` tuple in Task 3 and is consumed unchanged in Tasks 4 (`inherit_rev_from_siblings` reads target dict's `letter_rev`/`numeric_rev`) and 18 (pipeline). `pick_bucket` returns dict with `bucket`/`score_sum`/`score_top`/`confidence`/`runner_up_bucket`/`runner_up_score`, used identically in Tasks 7 and 18 and 21. `resolve_form_pre`/`resolve_form_post` signatures match between Tasks 8 and 18. `compute_is_latest_for_group` mutates rows in place and returns them; Task 18 uses both the side-effect and the return. `CSV_COLUMNS` defined in Task 19 as 33 entries — matches the 33-column count in test_pipeline.py's `enrich_files` test (Task 18) and the spec §9 schema. `classify_revision_drift` keyword args (`file_letter`, `file_numeric`, `schedule_rev`) consistent across Tasks 16 and 18. `derive_discipline` keyword args identical between Tasks 12 and 18.

Plan complete and saved to `docs/plans/2026-04-30-classifier.md`.
