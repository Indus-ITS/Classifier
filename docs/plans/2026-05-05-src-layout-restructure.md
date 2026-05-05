# src-layout Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganise the Classifier codebase into a `src/`-based Python package with single-responsibility modules, replace ad-hoc scripts with console scripts, and delete the test suite — without changing any output byte.

**Architecture:** Mechanical migration of existing code into a layered package (`cli` → `routing`/`pipeline` → `core` → `io`). Spec at `docs/superpowers/specs/2026-05-05-src-layout-restructure-design.md` is the source of truth for layout, layering rules, and the no-duplication rule. Verification is via golden-file byte diff captured before any code moves.

**Tech Stack:** Python 3.10+, pandas, setuptools (PEP 621 `pyproject.toml`), no test framework (tests are deleted).

**Conventions for this plan:**
- All paths are relative to the repo root `c:\Users\MrError\Documents\GitHub\Classifier\`.
- Shell snippets are PowerShell unless prefixed with `bash:`. Use `python` (not `.venv/Scripts/python`) — adjust if your venv is not on PATH.
- "Move" means: copy the function/class verbatim into the new file (with whatever imports it needs), then delete the original. Do not rewrite logic. The no-duplication rule from the spec applies: if two new modules want the same helper, hoist it to `src/classifier/core/shared.py`.
- Every task ends with a commit. The commit messages below are suggested; feel free to keep them but do not skip the commit.

---

## File responsibility map (locks in decomposition)

This is the target. Every function/class from the existing code lands in exactly one of these files. Refer back to the spec for detailed contents.

```
src/classifier/
├── __init__.py                     empty
├── config/
│   ├── __init__.py                 sunset re-exports (see Task 3)
│   ├── paths.py                    path constants + GATE_THRESHOLD
│   ├── buckets.py                  BUCKETS, BUCKET_TO_CLASS, TYPE_TO_BUCKET, BUCKET_PRIMARY_CODE
│   ├── keywords.py                 KEYWORD_RULES, DISCIPLINE_KEYWORD_RULES
│   ├── patterns.py                 REF_PATTERN, CRS_PATTERN, COVER_PATTERN
│   └── schema.py                   CSV_COLUMNS
├── core/                           pure logic, no I/O, no upward imports
│   ├── __init__.py                 empty
│   ├── normalisation.py            normalise_filename
│   ├── extraction.py               extract_ref, extract_letter_rev, extract_numeric_rev,
│   │                               extract_revs, inherit_rev_from_siblings, _esc_ref
│   ├── scoring.py                  score_buckets, pick_bucket, fold_to_class
│   ├── discipline.py               discipline_from_keywords, derive_discipline,
│   │                               build_seg2_discipline_map
│   ├── form.py                     is_crs_filename, is_cover_filename,
│   │                               resolve_form_pre, resolve_form_post
│   ├── revisions.py                assign_bundle_id, compute_is_latest_for_group,
│   │                               classify_revision_drift
│   ├── targets.py                  build_target_paths, detect_target_collisions,
│   │                               _sanitise_title, _rev_token
│   └── shared.py                   create only if a helper is needed by 2+ modules
├── pipeline/                       orchestration
│   ├── __init__.py                 empty
│   ├── enrich.py                   enrich_files
│   ├── audit.py                    write_audit
│   └── selftest.py                 run_dossier_selftest
├── io/                             infrastructure (file readers/writers)
│   ├── __init__.py                 empty
│   ├── schedule_reader.py          load_schedule (xls), plus the local load_rows used by classify
│   ├── dossier_reader.py           load_dossier
│   ├── transmittals.py             parse_transmittals
│   ├── overrides_reader.py         load_overrides
│   └── csv_writer.py               write_csv, _csv_value
├── routing/                        application layer for sort-files
│   ├── __init__.py                 empty
│   ├── schedule_refs.py            load_schedule_refs, safe_discipline, safe_title
│   ├── matching.py                 FileMatch, MatchResult, classify_title,
│   │                               match_files, _iter_source_files
│   ├── plan.py                     RoutePlan, build_plan, _name_with_title, _class_folder_for
│   ├── analysis.py                 plan_summary, plan_summary_by_class_discipline, find_collisions
│   ├── resolution.py               resolve_duplicates
│   └── execute.py                  execute_plan, clean_empty_dirs
├── cli/                            presentation only
│   ├── __init__.py                 empty
│   ├── classify.py                 main() — was classifier.py
│   ├── sort.py                     main() — was sort_files.py
│   ├── colors.py                   _Color, _color_enabled
│   ├── prompts.py                  _prompt, _prompt_path
│   └── reporting.py                _print_match_summary, _print_plan_summary, _print_progress
└── tools/                          standalone utilities, each with its own main()
    ├── __init__.py                 empty
    ├── dump_buckets.py             was helpers/dump_bucket_mapping.py
    ├── dump_undefined.py
    ├── evaluate.py                 was helpers/evaluate_corpus.py
    └── harvest.py                  was helpers/harvest_labelled.py
```

---

## Task 1: Capture golden-file snapshots

**Why:** Migration is byte-identical only if we can prove it. Snapshots before the first edit; diffs after the last.

**Files:**
- Create: `output/_golden/classified.csv`
- Create: `output/_golden/bucket_mapping.csv`
- Create: `output/_golden/undefined_for_review.csv`

- [ ] **Step 1: Run the existing entry points to produce current outputs**

```
python classifier.py
python helpers/dump_bucket_mapping.py
python helpers/dump_undefined.py
```

Expected: `output/classified.csv`, `output/bucket_mapping.csv`, `output/undefined_for_review.csv` exist and have non-zero size.

- [ ] **Step 2: Snapshot them into `output/_golden/`**

```
mkdir output\_golden
copy output\classified.csv          output\_golden\classified.csv
copy output\bucket_mapping.csv      output\_golden\bucket_mapping.csv
copy output\undefined_for_review.csv output\_golden\undefined_for_review.csv
```

Expected: three files in `output/_golden/`. Note their sizes for sanity later.

- [ ] **Step 3: Add `output/_golden/` to git (commit them so we can diff during/after)**

```
git add output/_golden
git commit -m "chore: snapshot golden outputs before src-layout restructure"
```

---

## Task 2: Scaffold the package and `pyproject.toml`

**Files:**
- Create: `pyproject.toml`
- Create: `src/classifier/__init__.py`
- Create: `src/classifier/{config,core,pipeline,io,routing,cli,tools}/__init__.py`

- [ ] **Step 1: Create the package directory tree**

```
mkdir src
mkdir src\classifier
mkdir src\classifier\config
mkdir src\classifier\core
mkdir src\classifier\pipeline
mkdir src\classifier\io
mkdir src\classifier\routing
mkdir src\classifier\cli
mkdir src\classifier\tools
```

- [ ] **Step 2: Create empty `__init__.py` for each package**

For each of `src/classifier/`, `src/classifier/config/`, `src/classifier/core/`, `src/classifier/pipeline/`, `src/classifier/io/`, `src/classifier/routing/`, `src/classifier/cli/`, `src/classifier/tools/`, create an empty `__init__.py`.

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "classifier"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pandas",
    "openpyxl",
    "xlrd",
]

[project.scripts]
classify       = "classifier.cli.classify:main"
sort-files     = "classifier.cli.sort:main"
dump-buckets   = "classifier.tools.dump_buckets:main"
dump-undefined = "classifier.tools.dump_undefined:main"
evaluate       = "classifier.tools.evaluate:main"
harvest        = "classifier.tools.harvest:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 4: Verify the package imports cleanly**

```
pip install -e .
python -c "import classifier; print(classifier.__file__)"
```

Expected: prints a path under `src/classifier/__init__.py`. No `ModuleNotFoundError`.

- [ ] **Step 5: Commit**

```
git add pyproject.toml src/classifier
git commit -m "feat: scaffold src/classifier package and pyproject.toml"
```

---

## Task 3: Migrate `config.py` → `config/` subpackage

**Files:**
- Create: `src/classifier/config/paths.py`, `buckets.py`, `keywords.py`, `patterns.py`, `schema.py`
- Modify: `src/classifier/config/__init__.py` (sunset re-exports)
- Delete (later in Task 11): `config.py` at repo root

- [ ] **Step 1: Read `config.py` once and cut it apart**

Open `config.py`. Move each constant to the file listed in the responsibility map above. **Copy verbatim** — same values, same comments, same `from __future__ import annotations`.

`paths.py`:
```python
"""I/O paths and the dossier self-test gate threshold."""
from __future__ import annotations

SCHEDULE_PATH = "input/schedule.xls"
DOSSIER_PATH = "input/dossier.xlsx"
TREE_PATH = "input/transmittals.txt"
OVERRIDES_PATH = "overrides/ref_to_bucket.csv"
OUTPUT_DIR = "output"

GATE_THRESHOLD = 0.935
```

`buckets.py`: contains `BUCKETS`, `BUCKET_TO_CLASS`, `TYPE_TO_BUCKET`, `BUCKET_PRIMARY_CODE` (with their docstrings).

`keywords.py`: contains `KEYWORD_RULES` and `DISCIPLINE_KEYWORD_RULES` (with their docstrings).

`patterns.py`: contains `REF_PATTERN`, `CRS_PATTERN`, `COVER_PATTERN`.

`schema.py`: contains `CSV_COLUMNS`.

- [ ] **Step 2: Write `src/classifier/config/__init__.py` with sunset re-exports**

```python
"""Backwards-compatible re-exports.

SUNSET: remove these re-exports after the next two changes that touch the
classifier package, or by 2026-08-01 — whichever comes first. New code MUST
import from the specific submodule (e.g. `from classifier.config.keywords
import KEYWORD_RULES`).
"""
from classifier.config.paths import (
    SCHEDULE_PATH,
    DOSSIER_PATH,
    TREE_PATH,
    OVERRIDES_PATH,
    OUTPUT_DIR,
    GATE_THRESHOLD,
)
from classifier.config.buckets import (
    BUCKETS,
    BUCKET_TO_CLASS,
    TYPE_TO_BUCKET,
    BUCKET_PRIMARY_CODE,
)
from classifier.config.keywords import KEYWORD_RULES, DISCIPLINE_KEYWORD_RULES
from classifier.config.patterns import REF_PATTERN, CRS_PATTERN, COVER_PATTERN
from classifier.config.schema import CSV_COLUMNS

__all__ = [
    "SCHEDULE_PATH", "DOSSIER_PATH", "TREE_PATH", "OVERRIDES_PATH",
    "OUTPUT_DIR", "GATE_THRESHOLD",
    "BUCKETS", "BUCKET_TO_CLASS", "TYPE_TO_BUCKET", "BUCKET_PRIMARY_CODE",
    "KEYWORD_RULES", "DISCIPLINE_KEYWORD_RULES",
    "REF_PATTERN", "CRS_PATTERN", "COVER_PATTERN",
    "CSV_COLUMNS",
]
```

- [ ] **Step 3: Verify**

```
python -c "from classifier.config.keywords import KEYWORD_RULES; print(len(KEYWORD_RULES))"
python -c "from classifier.config import BUCKETS, KEYWORD_RULES; print(len(BUCKETS), len(KEYWORD_RULES))"
```

Expected: both print `10 10` (or `10` for the first command). No errors.

- [ ] **Step 4: Commit**

```
git add src/classifier/config
git commit -m "refactor: split config.py into classifier.config subpackage"
```

> Note: do NOT delete `config.py` yet. Other in-tree code (`classifier.py`, `helpers/*.py`) still imports `from config import ...`. Final cleanup is Task 11.

---

## Task 4: Migrate `helpers/router_lib.py` → `routing/`

**Files:**
- Create: `src/classifier/routing/schedule_refs.py`, `matching.py`, `plan.py`, `analysis.py`, `resolution.py`, `execute.py`
- (Later) Delete: `helpers/router_lib.py`

`router_lib.py` is self-contained (only imports stdlib + `pandas`). Split per the responsibility map.

- [ ] **Step 1: `routing/schedule_refs.py`**

Move from `helpers/router_lib.py`:
- `safe_discipline` (line 63)
- `safe_title` (line 81)
- `load_schedule_refs` (line 119)

Imports needed: `from __future__ import annotations`, `import re`, `from pathlib import Path`, `import pandas as pd`.

- [ ] **Step 2: `routing/matching.py`**

Move:
- `FileMatch` dataclass (line 34)
- `MatchResult` dataclass (line 46)
- `classify_title` (line 149)
- `_iter_source_files` (line 171)
- `match_files` (line 197)

Note: `classify_title` calls `score_buckets`, `pick_bucket`, `fold_to_class`. Import them from `classifier.core.scoring` (which is created in Task 5). For now, leave the import line referencing the future module and accept the temporary `ImportError` — it will resolve when Task 5 completes. Step 7 below verifies this.

```python
from classifier.core.scoring import score_buckets, pick_bucket, fold_to_class
from classifier.config.buckets import BUCKET_TO_CLASS
```

- [ ] **Step 3: `routing/plan.py`**

Move:
- `RoutePlan` (line 111)
- `build_plan` (line 249)
- `_name_with_title` (line 285)
- `_class_folder_for` (line 437)

Also import the data structures it uses: `from classifier.routing.matching import FileMatch, MatchResult`, `from classifier.routing.schedule_refs import safe_discipline, safe_title`.

- [ ] **Step 4: `routing/analysis.py`**

Move:
- `plan_summary` (line 298)
- `plan_summary_by_class_discipline` (line 317)
- `find_collisions` (line 342)

Imports: `from classifier.routing.plan import RoutePlan`.

- [ ] **Step 5: `routing/resolution.py`**

Move:
- `resolve_duplicates` (line 362)

Imports: `from classifier.routing.plan import RoutePlan`.

- [ ] **Step 6: `routing/execute.py`**

Move:
- `clean_empty_dirs` (line 448)
- `execute_plan` (line 470)

Imports: `from classifier.routing.plan import RoutePlan`.

- [ ] **Step 7: Verify the routing layer imports**

This will fail until Task 5 lands `classifier.core.scoring`. Skip for now — re-run after Task 5.

- [ ] **Step 8: Commit**

```
git add src/classifier/routing
git commit -m "refactor: split router_lib into classifier.routing submodules"
```

---

## Task 5: Migrate `helpers/classifier_lib.py` → `core/`, `pipeline/`, `io/`

**Files:** (every file listed in core/, pipeline/, io/ in the responsibility map)

This is the longest task. `classifier_lib.py` is 1033 lines and intermingles pure logic, pandas-driven loading, and a `main()`. Cut it apart in this order:

- [ ] **Step 1: `core/normalisation.py`**

Move `normalise_filename` (line 30). Imports: `from __future__ import annotations`, `import re`, `import unicodedata` if used.

- [ ] **Step 2: `core/extraction.py`**

Move:
- `_esc_ref` (line 62)
- `extract_ref` (line 45)
- `extract_letter_rev` (line 66)
- `extract_numeric_rev` (line 81)
- `extract_revs` (line 96)
- `inherit_rev_from_siblings` (line 101)

Imports: `from classifier.config.patterns import REF_PATTERN`, `from classifier.core.normalisation import normalise_filename` if needed.

- [ ] **Step 3: `core/form.py`**

Move:
- `is_crs_filename` (line 51)
- `is_cover_filename` (line 56)
- `resolve_form_pre` (line 206)
- `resolve_form_post` (line 221)

Imports: `from classifier.config.patterns import CRS_PATTERN, COVER_PATTERN`, `from classifier.core.normalisation import normalise_filename` if needed.

- [ ] **Step 4: `core/scoring.py`**

Move:
- `score_buckets` (line 137)
- `pick_bucket` (line 161)
- `fold_to_class` (line 190)

Imports: `from classifier.config.keywords import KEYWORD_RULES`, `from classifier.config.buckets import BUCKETS, BUCKET_TO_CLASS` (whichever the originals reference).

- [ ] **Step 5: `core/discipline.py`**

Move:
- `discipline_from_keywords` (line 441)
- `build_seg2_discipline_map` (line 562)
- `derive_discipline` (line 569)

Imports: `from classifier.config.keywords import DISCIPLINE_KEYWORD_RULES`, plus pandas where needed.

- [ ] **Step 6: `core/revisions.py`**

Move:
- `assign_bundle_id` (line 266)
- `compute_is_latest_for_group` (line 283)
- `classify_revision_drift` (line 333)

- [ ] **Step 7: `core/targets.py`**

Move:
- `_sanitise_title` (line 381)
- `_rev_token` (line 388)
- `build_target_paths` (line 398)
- `detect_target_collisions` (line 418)

Imports: `from classifier.config.buckets import BUCKET_PRIMARY_CODE`.

- [ ] **Step 8: `io/csv_writer.py`**

Move:
- `_csv_value` (line 449)
- `write_csv` (line 459)

This is the generic `write_csv` from `classifier_lib.py`. It is distinct from the simpler local `write_csv` in `classifier.py` (Task 7 will keep the latter as a private helper inside `cli/classify.py` since it has a different signature).

- [ ] **Step 9: `io/schedule_reader.py`**

Move:
- `load_schedule` (line 480)

Imports: `import pandas as pd`, `from pathlib import Path`.

- [ ] **Step 10: `io/dossier_reader.py`**

Move:
- `load_dossier` (line 496)

- [ ] **Step 11: `io/transmittals.py`**

Move:
- `parse_transmittals` (line 517)

- [ ] **Step 12: `io/overrides_reader.py`**

Move:
- `load_overrides` (line 247)

Imports: `import csv`, `from pathlib import Path`.

- [ ] **Step 13: `pipeline/enrich.py`**

Move:
- `enrich_files` (line 595)

This is the orchestration that calls everything above. Update its imports to pull from the new locations:

```python
from classifier.config.buckets import (
    BUCKETS, BUCKET_TO_CLASS, TYPE_TO_BUCKET, BUCKET_PRIMARY_CODE,
)
from classifier.config.patterns import REF_PATTERN, CRS_PATTERN, COVER_PATTERN
from classifier.core.normalisation import normalise_filename
from classifier.core.extraction import (
    extract_ref, extract_revs, inherit_rev_from_siblings,
)
from classifier.core.form import (
    is_crs_filename, is_cover_filename, resolve_form_pre, resolve_form_post,
)
from classifier.core.scoring import score_buckets, pick_bucket, fold_to_class
from classifier.core.discipline import (
    discipline_from_keywords, derive_discipline, build_seg2_discipline_map,
)
from classifier.core.revisions import (
    assign_bundle_id, compute_is_latest_for_group, classify_revision_drift,
)
from classifier.core.targets import build_target_paths, detect_target_collisions
from classifier.io.schedule_reader import load_schedule
from classifier.io.dossier_reader import load_dossier
from classifier.io.transmittals import parse_transmittals
from classifier.io.overrides_reader import load_overrides
```

Trim this list to exactly what `enrich_files` actually calls.

- [ ] **Step 14: `pipeline/audit.py`**

Move:
- `write_audit` (line 795)

Update imports to use the new locations as in Step 13.

- [ ] **Step 15: `pipeline/selftest.py`**

Move:
- `run_dossier_selftest` (line 940)

- [ ] **Step 16: Drop `classifier_lib.main` for now**

The `main()` at line 980 is the legacy enrich/audit/selftest CLI. It is not exposed as a console script in the new layout. Do not migrate it. (If it turns out to be needed, it would become `cli/enrich.py` in a follow-up.)

- [ ] **Step 17: Verify the entire core+io+pipeline+routing tree imports**

```
python -c "import classifier.core.scoring, classifier.core.extraction, classifier.core.form, classifier.core.discipline, classifier.core.revisions, classifier.core.targets, classifier.core.normalisation; print('core ok')"
python -c "import classifier.io.csv_writer, classifier.io.schedule_reader, classifier.io.dossier_reader, classifier.io.transmittals, classifier.io.overrides_reader; print('io ok')"
python -c "import classifier.pipeline.enrich, classifier.pipeline.audit, classifier.pipeline.selftest; print('pipeline ok')"
python -c "import classifier.routing.schedule_refs, classifier.routing.matching, classifier.routing.plan, classifier.routing.analysis, classifier.routing.resolution, classifier.routing.execute; print('routing ok')"
```

Expected: each line prints `<layer> ok`. Fix any `ImportError` by checking that the function actually landed where you said and the import path matches.

- [ ] **Step 18: Commit**

```
git add src/classifier/core src/classifier/io src/classifier/pipeline
git commit -m "refactor: split classifier_lib into core/io/pipeline submodules"
```

---

## Task 6: Migrate `sort_files.py` → `cli/sort.py` (+ colors, prompts, reporting)

**Files:**
- Create: `src/classifier/cli/colors.py`, `prompts.py`, `reporting.py`, `sort.py`
- (Later) Delete: `sort_files.py`

- [ ] **Step 1: `cli/colors.py`**

Move from `sort_files.py`:
- `_Color` class (lines 53-86)
- `_color_enabled` (lines 89-96)

Imports: `import os`, `import sys`.

- [ ] **Step 2: `cli/prompts.py`**

Move:
- `_prompt` (lines 197-216)
- `_prompt_path` (lines 219-228)

Imports: `import sys`, `from pathlib import Path`.

- [ ] **Step 3: `cli/reporting.py`**

Move:
- `_print_match_summary` (lines 234-245)
- `_print_plan_summary` (lines 248-270)
- `_print_progress` (lines 273-282)

Imports:
```python
import sys
from pathlib import Path
from classifier.cli.colors import _Color
from classifier.routing.analysis import plan_summary, plan_summary_by_class_discipline
```

- [ ] **Step 4: `cli/sort.py`**

Move what remains of `sort_files.py`:
- the module docstring
- `parse_args` (lines 102-191)
- `main` (lines 288-401)
- `if __name__ == "__main__": sys.exit(main())` block

Update imports at the top:
```python
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from classifier.cli.colors import _Color, _color_enabled
from classifier.cli.prompts import _prompt, _prompt_path
from classifier.cli.reporting import (
    _print_match_summary, _print_plan_summary, _print_progress,
)
from classifier.routing.schedule_refs import load_schedule_refs
from classifier.routing.matching import match_files
from classifier.routing.plan import build_plan
from classifier.routing.analysis import find_collisions
from classifier.routing.resolution import resolve_duplicates
from classifier.routing.execute import execute_plan, clean_empty_dirs
```

- [ ] **Step 5: Smoke-test `sort-files`**

```
sort-files --help
```

Expected: full argparse help text, exit 0.

- [ ] **Step 6: Commit**

```
git add src/classifier/cli/colors.py src/classifier/cli/prompts.py src/classifier/cli/reporting.py src/classifier/cli/sort.py
git commit -m "refactor: move sort_files into classifier.cli (colors, prompts, reporting, sort)"
```

---

## Task 7: Migrate `classifier.py` → `cli/classify.py`

**Files:**
- Create: `src/classifier/cli/classify.py`
- (Later) Delete: `classifier.py`

- [ ] **Step 1: Write `cli/classify.py`**

Copy `classifier.py` verbatim into `src/classifier/cli/classify.py`. Update its imports:

```python
from __future__ import annotations
import csv
from pathlib import Path
from collections import Counter

import pandas as pd

from classifier.config.buckets import BUCKET_TO_CLASS
from classifier.core.scoring import score_buckets, pick_bucket, fold_to_class
from classifier.core.discipline import discipline_from_keywords
```

The local `load_rows` and `write_csv` functions stay private to this module (they have a different signature than `io.csv_writer.write_csv`). Move the `from collections import Counter` to the top — don't leave it inside `main`.

- [ ] **Step 2: Run the new entry point**

```
classify
```

Expected: prints "Wrote output/classified.csv (N rows)" plus the breakdown tables. Exit 0.

- [ ] **Step 3: Golden-file diff (the big one)**

PowerShell:
```
fc /b output\classified.csv output\_golden\classified.csv
```

Expected: `FC: no differences encountered`. **If there is any difference, stop — do not commit.** Investigate which migration step changed behaviour. Most likely culprit: an import that pulled a stale constant from old `config.py` instead of `classifier.config.*`.

- [ ] **Step 4: Commit**

```
git add src/classifier/cli/classify.py
git commit -m "refactor: move classifier.py to classifier.cli.classify"
```

---

## Task 8: Migrate `helpers/dump_*`, `evaluate_corpus`, `harvest_labelled` → `tools/`

**Files:**
- Create: `src/classifier/tools/dump_buckets.py`, `dump_undefined.py`, `evaluate.py`, `harvest.py`

For each script: copy the file into the new location, update its imports to use `classifier.config.*`, `classifier.core.*`, `classifier.io.*` instead of `config` / `helpers.classifier_lib`. Each must expose a `main()` function (wrap the existing top-level script body if it doesn't already).

- [ ] **Step 1: `tools/dump_buckets.py`** (was `helpers/dump_bucket_mapping.py`, 175 lines)

Copy file. Update imports. Wrap top-level code in `def main():` and add `if __name__ == "__main__": main()` at the bottom if not already there.

- [ ] **Step 2: `tools/dump_undefined.py`** (was `helpers/dump_undefined.py`, 61 lines)

Same procedure.

- [ ] **Step 3: `tools/evaluate.py`** (was `helpers/evaluate_corpus.py`, 146 lines)

Same procedure.

- [ ] **Step 4: `tools/harvest.py`** (was `helpers/harvest_labelled.py`, 362 lines)

Same procedure.

- [ ] **Step 5: Smoke-test each tool**

```
dump-buckets
dump-undefined
```

Expected: each writes its CSV under `output/` and exits 0.

- [ ] **Step 6: Golden-file diff for the dumps**

```
fc /b output\bucket_mapping.csv output\_golden\bucket_mapping.csv
fc /b output\undefined_for_review.csv output\_golden\undefined_for_review.csv
```

Both must report no differences. Stop if either differs.

- [ ] **Step 7: Smoke-run `evaluate` and `harvest` if the input corpus is present**

```
harvest
evaluate
```

These depend on `input/classified/` being populated. If it's missing, skip and note that they could not be smoke-tested in this environment.

- [ ] **Step 8: Commit**

```
git add src/classifier/tools
git commit -m "refactor: move offline helpers into classifier.tools subpackage"
```

---

## Task 9: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the Quick start section**

Old block (lines 17-26) becomes:

```markdown
## Quick start

```bash
pip install -e .

# 1. Classify schedule rows
classify

# 2. (Optional) Sort the referenced files into class folders
sort-files --schedule "input/To be classified/sahil schedule.xls" \
           --source-dir /path/to/your/docs
```
```

- [ ] **Step 2: Replace the Entry points table**

Update the table (lines 38-46) to:

| Command | What it does | Output |
|---|---|---|
| `classify` | Classify schedule rows | `output/classified.csv` |
| `sort-files` | Interactive CLI: sort/copy files into class folders | files moved/copied into class folders |
| `harvest` | Build the labelled corpus from `input/classified/` | `output/helpers/labelled_corpus.csv` |
| `evaluate` | Measure classifier accuracy on the labelled corpus | `output/helpers/evaluation_report.txt` |
| `dump-buckets` | Dump description → bucket → class mapping | `output/bucket_mapping.csv` |
| `dump-undefined` | Filter `output/classified.csv` to `class=Undefined` rows | `output/undefined_for_review.csv` |

- [ ] **Step 3: Replace the Layout block**

Replace lines 50-86 with:

```
classifier/
├── pyproject.toml                # package metadata + console scripts
├── README.md
├── requirements.txt
│
├── src/classifier/               # the package
│   ├── config/                   # tunables (paths, buckets, keywords, patterns, schema)
│   ├── core/                     # pure logic (scoring, extraction, normalisation, ...)
│   ├── pipeline/                 # orchestration (enrich, audit, selftest)
│   ├── io/                       # file readers/writers
│   ├── routing/                  # sort-files matching/planning/execution
│   ├── cli/                      # console entry points + presentation helpers
│   └── tools/                    # offline diagnostic commands
│
├── input/   output/   overrides/
└── docs/    specs/ + plans/
```

- [ ] **Step 4: Update remaining file links**

Search README for `classifier.py`, `sort_files.py`, `helpers/`, `config.py` and replace with the new module path or console command. The Tests section (lines 302-319) must be removed entirely — see Task 10.

- [ ] **Step 5: Commit**

```
git add README.md
git commit -m "docs: update README for src-layout"
```

---

## Task 10: Delete tests, helpers, root scripts, caches

**Files:**
- Delete: `tests/`, `helpers/`, `classifier.py`, `sort_files.py`, `config.py`
- Delete: `__pycache__/`, `helpers/__pycache__/`, `tests/__pycache__/`
- Delete: `sortted_tree.txt`
- Modify: `README.md` (remove the Tests section)

- [ ] **Step 1: Delete the test suite**

```
git rm -r tests
```

- [ ] **Step 2: Delete the old helpers package**

```
git rm -r helpers
```

- [ ] **Step 3: Delete the root-level scripts and old config**

```
git rm classifier.py sort_files.py config.py
```

- [ ] **Step 4: Delete the stale tree dump**

```
git rm sortted_tree.txt
```

- [ ] **Step 5: Remove untracked `__pycache__` directories**

```
Remove-Item -Recurse -Force __pycache__, helpers\__pycache__, tests\__pycache__ -ErrorAction SilentlyContinue
```

- [ ] **Step 6: Remove the Tests section from README**

In `README.md`, delete the `## Tests` section (was lines 302-319 before Task 9 edits) and the "226 tests passing" bullet under Engineering hygiene.

- [ ] **Step 7: Commit**

```
git add README.md
git commit -m "chore: remove tests, helpers, and root scripts after src-layout migration"
```

---

## Task 11: Final verification

**Files:** none modified.

- [ ] **Step 1: Re-install and smoke all entry points**

```
pip install -e .
classify
sort-files --help
dump-buckets
dump-undefined
```

Expected: each exits 0. `classify`, `dump-buckets`, `dump-undefined` write to `output/`.

- [ ] **Step 2: Final golden-file diff**

```
fc /b output\classified.csv          output\_golden\classified.csv
fc /b output\bucket_mapping.csv      output\_golden\bucket_mapping.csv
fc /b output\undefined_for_review.csv output\_golden\undefined_for_review.csv
```

All three must report no differences.

- [ ] **Step 3: Layering check (forbidden imports)**

Use Grep (or `git grep`) to confirm the one-directional import rule:

```
git grep -n "from classifier.cli"      src/classifier/core src/classifier/io src/classifier/routing src/classifier/pipeline
git grep -n "from classifier.pipeline" src/classifier/core src/classifier/io
git grep -n "from classifier.routing"  src/classifier/core src/classifier/io
git grep -n "from classifier.io"       src/classifier/core
```

Each command should print **nothing**. Any hit is a layering violation — fix it before finishing.

- [ ] **Step 4: Confirm no dangling references to old modules**

```
git grep -nE "from (helpers|config)( |\.|$)|import (helpers|config)( |$)" -- "src/**" "*.py" "*.md"
```

Expected: no hits in `src/`. README hits are OK only inside fenced "old" examples (there shouldn't be any after Task 9).

- [ ] **Step 5: Final commit (if anything was tweaked in steps 3-4)**

```
git add -A
git commit -m "chore: layering and reference cleanup post-restructure"
```

- [ ] **Step 6: Optionally remove the golden snapshot directory**

The migration is verified. The golden snapshot has done its job. Either keep it (as a permanent regression baseline) or remove it:

```
git rm -r output/_golden
git commit -m "chore: drop golden snapshot now that src-layout migration is verified"
```

Default recommendation: **remove it.** Leaving it invites someone to confuse it with current output.

---

## Self-review notes

- Spec coverage: every section of the spec maps to a task — config split (T3), router_lib split (T4), classifier_lib split (T5), CLI extraction (T6, T7), tools migration (T8), README (T9), deletions (T10), pyproject + console scripts (T2), golden diff (T1, T7, T8, T11), layering check (T11), sunset re-export comment (T3 step 2).
- Placeholder scan: every step has either an exact command or a code block. No "TBD"s.
- Type/name consistency: function and class names match the existing source 1:1; only file locations change. The two `write_csv` functions (one in `classifier.py`, one in `classifier_lib.py`) are explicitly distinguished in T5 step 8 / T7 step 1.
