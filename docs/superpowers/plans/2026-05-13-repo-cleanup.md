# Repo Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip `src/classifier/` to the ~13 files needed by the three new entry points (`classify`, `convert-classified`, `build-type-enum`); remove the legacy `sort-files` cluster, legacy diagnostic tools, and dead modules.

**Architecture:** Pure deletion plus three small edits (`pyproject.toml`, `src/classifier/config/__init__.py`, `README.md`) and one rename (`docs/specs/`+`docs/plans/` → `docs/archive/`). No new code. No behavior change to surviving modules. Verification is hash-equality of generated artifacts before vs after.

**Tech Stack:** No new deps. Existing pandas / stdlib only.

**Verification:** No automated tests (per standing user direction). Each task ends with hand-verification via `git status`, smoke-import checks, or pipeline re-runs. Final task compares pre/post hashes of `input/classified_csv/` and `output/classified.csv`.

**Spec:** `docs/superpowers/specs/2026-05-13-repo-cleanup-design.md`

---

## File map

**Deleted (~33 files):**
- `src/classifier/cli/`: `sort.py`, `colors.py`, `prompts.py`, `reporting.py`
- `src/classifier/io/`: `csv_writer.py`, `schedule_reader.py`, `dossier_reader.py`, `transmittals.py`, `related_xlsx.py`
- `src/classifier/routing/` — entire package
- `src/classifier/pipeline/` — entire package
- `src/classifier/config/`: `schema.py`, `patterns.py`, `paths.py`
- `src/classifier/core/`: `discipline.py`, `extraction.py`, `form.py`, `normalisation.py`, `revisions.py`, `targets.py`
- `src/classifier/tools/`: `dump_buckets.py`, `dump_undefined.py`, `evaluate.py`, `harvest.py`

**Modified:**
- `pyproject.toml` — drop 5 entry points
- `src/classifier/config/__init__.py` — strip dead re-exports
- `README.md` — drop legacy commands from Console scripts table

**Moved:**
- `docs/specs/*` → `docs/archive/specs/*`
- `docs/plans/*` → `docs/archive/plans/*`

**Created:**
- `.baseline-hashes.json` — temp file (committed never; cleaned up by final verification)

---

## Task 1: Capture baseline hashes

**Files:**
- Create (temp, not committed): `.baseline-hashes.json`

- [ ] **Step 1: Capture hashes of generated artifacts**

Run:
```
.venv/Scripts/python -c "
import hashlib, pathlib, json
def hash_tree(root):
    h = hashlib.sha256()
    for p in sorted(pathlib.Path(root).rglob('*'), key=lambda x: str(x).lower()):
        if p.is_file(): h.update(p.read_bytes())
    return h.hexdigest()
baseline = {
    'classified_csv': hash_tree('input/classified_csv'),
    'output_classified_csv': hashlib.sha256(pathlib.Path('output/classified.csv').read_bytes()).hexdigest(),
}
pathlib.Path('.baseline-hashes.json').write_text(json.dumps(baseline, indent=2))
print(baseline)
"
```
Expected: prints a dict with two sha256 hexdigests. File `.baseline-hashes.json` exists in repo root.

- [ ] **Step 2: Add baseline file to `.gitignore` (one-shot — keeps it from being committed by accident)**

Append the literal line `.baseline-hashes.json` to `.gitignore`. If the file already contains it, skip.

Verify:
```
grep -n "^\.baseline-hashes\.json$" .gitignore
```
Expected: exactly one match.

- [ ] **Step 3: Commit the .gitignore update**

```
git add .gitignore
git commit -m "chore: gitignore the cleanup baseline hash file"
```

No `.baseline-hashes.json` should appear in `git status` after this commit.

---

## Task 2: Delete sort-files cluster

**Files (deleted, all via `git rm`):**
- `src/classifier/cli/sort.py`
- `src/classifier/cli/colors.py`
- `src/classifier/cli/prompts.py`
- `src/classifier/cli/reporting.py`
- `src/classifier/io/related_xlsx.py`
- `src/classifier/routing/__init__.py`
- `src/classifier/routing/analysis.py`
- `src/classifier/routing/dedup.py`
- `src/classifier/routing/execute.py`
- `src/classifier/routing/folders.py`
- `src/classifier/routing/matching.py`
- `src/classifier/routing/plan.py`
- `src/classifier/routing/resolution.py`
- `src/classifier/routing/schedule_refs.py`

- [ ] **Step 1: Delete the sort-files CLI helpers and the routing package**

Run from project root:
```
git rm src/classifier/cli/sort.py \
       src/classifier/cli/colors.py \
       src/classifier/cli/prompts.py \
       src/classifier/cli/reporting.py \
       src/classifier/io/related_xlsx.py
git rm -r src/classifier/routing
```

If `src/classifier/routing/__pycache__/` exists locally but isn't tracked, `git rm -r` will report it as not tracked — that's fine. Manually remove the dir:
```
rm -rf src/classifier/routing/__pycache__ 2>/dev/null || true
```

- [ ] **Step 2: Verify nothing imports the deleted modules**

Run:
```
git grep -n "classifier.cli.sort\|classifier.cli.colors\|classifier.cli.prompts\|classifier.cli.reporting\|classifier.io.related_xlsx\|classifier.routing" -- src/classifier
```
Expected: no output.

- [ ] **Step 3: Commit**

```
git commit -m "chore: drop sort-files cluster (cli helpers + io.related_xlsx + routing/)

The sort-files pipeline is superseded by the canonical-CSV workflow.
Removed: cli/sort.py + colors/prompts/reporting helpers, io/related_xlsx.py,
and the entire routing/ package (9 modules). pyproject.toml entry point
update happens in a later task."
```

---

## Task 3: Delete pipeline package

**Files (deleted):**
- `src/classifier/pipeline/__init__.py`
- `src/classifier/pipeline/audit.py`
- `src/classifier/pipeline/enrich.py`
- `src/classifier/pipeline/selftest.py`

- [ ] **Step 1: Delete the package**

```
git rm -r src/classifier/pipeline
rm -rf src/classifier/pipeline/__pycache__ 2>/dev/null || true
```

- [ ] **Step 2: Verify no surviving imports**

```
git grep -n "classifier.pipeline" -- src/classifier
```
Expected: no output.

- [ ] **Step 3: Commit**

```
git commit -m "chore: drop classifier.pipeline package (enrich/audit/selftest)

All three modules belonged to the old xls-walking workflow and have no
consumers in the canonical-CSV pipeline."
```

---

## Task 4: Delete legacy diagnostic tools

**Files (deleted):**
- `src/classifier/tools/dump_buckets.py`
- `src/classifier/tools/dump_undefined.py`
- `src/classifier/tools/evaluate.py`
- `src/classifier/tools/harvest.py`

- [ ] **Step 1: Delete the four tool modules**

```
git rm src/classifier/tools/dump_buckets.py \
       src/classifier/tools/dump_undefined.py \
       src/classifier/tools/evaluate.py \
       src/classifier/tools/harvest.py
```

- [ ] **Step 2: Verify**

```
git grep -n "classifier.tools.dump_buckets\|classifier.tools.dump_undefined\|classifier.tools.evaluate\|classifier.tools.harvest" -- src/classifier
```
Expected: no output.

`src/classifier/tools/` should now contain only `__init__.py`, `build_type_enum.py`, `convert_classified.py`:
```
ls src/classifier/tools/*.py
```
Expected: exactly three files.

- [ ] **Step 3: Commit**

```
git commit -m "chore: drop legacy diagnostic tools (dump_buckets/dump_undefined/evaluate/harvest)

Tuning helpers for the old multi-column classify output; the
canonical-CSV pipeline doesn't need them. pyproject.toml entry points
removed in a later task."
```

---

## Task 5: Delete legacy IO + dead core modules

**Files (deleted):**
- `src/classifier/io/csv_writer.py`
- `src/classifier/io/schedule_reader.py`
- `src/classifier/io/dossier_reader.py`
- `src/classifier/io/transmittals.py`
- `src/classifier/core/discipline.py`
- `src/classifier/core/extraction.py`
- `src/classifier/core/form.py`
- `src/classifier/core/normalisation.py`
- `src/classifier/core/revisions.py`
- `src/classifier/core/targets.py`

- [ ] **Step 1: Delete the modules**

```
git rm src/classifier/io/csv_writer.py \
       src/classifier/io/schedule_reader.py \
       src/classifier/io/dossier_reader.py \
       src/classifier/io/transmittals.py \
       src/classifier/core/discipline.py \
       src/classifier/core/extraction.py \
       src/classifier/core/form.py \
       src/classifier/core/normalisation.py \
       src/classifier/core/revisions.py \
       src/classifier/core/targets.py
```

- [ ] **Step 2: Verify**

```
git grep -nE "classifier\.io\.(csv_writer|schedule_reader|dossier_reader|transmittals)|classifier\.core\.(discipline|extraction|form|normalisation|revisions|targets)" -- src/classifier
```
Expected: no output.

`src/classifier/core/` should now contain only `__init__.py` and `scoring.py`:
```
ls src/classifier/core/*.py
```
Expected: exactly two files.

- [ ] **Step 3: Commit**

```
git commit -m "chore: drop legacy IO + dead core modules

io.csv_writer/schedule_reader/dossier_reader/transmittals belonged
to the old xls walker. core.discipline/extraction/form/normalisation/
revisions/targets were only used by the deleted routing/pipeline
packages and the deleted classify-old."
```

---

## Task 6: Delete dead config and trim config/__init__

**Files:**
- Delete: `src/classifier/config/schema.py`, `src/classifier/config/patterns.py`, `src/classifier/config/paths.py`
- Modify: `src/classifier/config/__init__.py`

- [ ] **Step 1: Delete the three config modules**

```
git rm src/classifier/config/schema.py \
       src/classifier/config/patterns.py \
       src/classifier/config/paths.py
```

- [ ] **Step 2: Replace `src/classifier/config/__init__.py` with a minimal docstring**

The current file re-exports symbols from modules we just deleted (it would now fail to import). Replace its entire contents with:

```python
"""classifier.config package.

Each submodule (``buckets``, ``keywords``, ``type_enum``) is the source
of truth for its own data. Import directly from the submodule; this
package init intentionally exposes nothing.
"""
```

- [ ] **Step 3: Verify nothing imports the deleted config modules or relies on the package-level re-exports**

```
git grep -nE "classifier\.config\.(schema|patterns|paths)|classifier\.config import (SCHEDULE_PATH|DOSSIER_PATH|TREE_PATH|OUTPUT_DIR|GATE_THRESHOLD|REF_PATTERN|CRS_PATTERN|COVER_PATTERN|CSV_COLUMNS)" -- src/classifier
```
Expected: no output.

Spot-check the surviving imports work:
```
.venv/Scripts/python -c "
from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.config.keywords import KEYWORD_RULES, DISCIPLINE_KEYWORD_RULES
from classifier.config.type_enum import KNOWN_TYPES, OBSERVED_OUTLIERS
print('config ok')
"
```
Expected: prints `config ok`.

- [ ] **Step 4: Commit**

```
git add src/classifier/config/__init__.py
git commit -m "chore: drop dead config (schema/patterns/paths), trim config/__init__

Only buckets, keywords, and the generated type_enum remain. The
__init__ no longer re-exports anything (the old re-exports targeted
deleted submodules); callers always import from the explicit submodule."
```

---

## Task 7: Drop legacy entry points, reinstall, smoke-test

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read the current `pyproject.toml`**

Run: `cat pyproject.toml`

The `[project.scripts]` block currently contains:
```
classify       = "classifier.cli.classify:main"
sort-files     = "classifier.cli.sort:main"
dump-buckets   = "classifier.tools.dump_buckets:main"
dump-undefined = "classifier.tools.dump_undefined:main"
evaluate       = "classifier.tools.evaluate:main"
harvest        = "classifier.tools.harvest:main"
convert-classified = "classifier.tools.convert_classified:main"
build-type-enum    = "classifier.tools.build_type_enum:main"
```

- [ ] **Step 2: Replace the `[project.scripts]` block**

Edit `pyproject.toml` so `[project.scripts]` contains exactly these three lines (column-aligned for readability, matching existing style):

```toml
[project.scripts]
classify           = "classifier.cli.classify:main"
convert-classified = "classifier.tools.convert_classified:main"
build-type-enum    = "classifier.tools.build_type_enum:main"
```

- [ ] **Step 3: Reinstall the package so console scripts are refreshed**

```
.venv/Scripts/pip install -e .
```
Expected: succeeds with `Successfully installed classifier-0.1.0`.

- [ ] **Step 4: Smoke-test all three entry points import cleanly**

```
.venv/Scripts/python -c "
import importlib
for mod in ('classifier.cli.classify',
            'classifier.tools.convert_classified',
            'classifier.tools.build_type_enum'):
    importlib.import_module(mod)
print('imports ok')
"
```
Expected: prints `imports ok`.

- [ ] **Step 5: Run each entry point end-to-end (regenerating artifacts)**

```
.venv/Scripts/python -m classifier.tools.convert_classified
.venv/Scripts/python -m classifier.tools.build_type_enum
.venv/Scripts/python -m classifier.cli.classify
```

Expected for each: clean exit (no traceback). `classify` prints the doc_type / type-fill summary it printed before cleanup.

- [ ] **Step 6: Commit**

```
git add pyproject.toml
git commit -m "chore: drop legacy entry points from pyproject

[project.scripts] now lists only the three commands the canonical-CSV
pipeline exposes: classify, convert-classified, build-type-enum."
```

---

## Task 8: Update README and archive old docs

**Files:**
- Modify: `README.md`
- Move: `docs/specs/*` → `docs/archive/specs/*`
- Move: `docs/plans/*` → `docs/archive/plans/*`

- [ ] **Step 1: Read the current `README.md`**

`cat README.md`

Locate the `## Console scripts` table. It currently lists more than three commands (anything with `sort-files`, `dump-buckets`, `dump-undefined`, `evaluate`, `harvest` is now stale).

- [ ] **Step 2: Update the `## Console scripts` table**

Replace the table body so it lists exactly these three commands (preserve the existing table header style; trim any prose elsewhere in the README that mentions the deleted commands):

```markdown
| Command              | What it does |
|----------------------|--------------|
| `classify`           | Read `input/To be classified/document.csv`, fill `doc_type` (normalized to `drawing`/`document`) and `type` (filled only when empty, via the lookup built from `input/classified_csv/`), write `output/classified.csv`. Schema-preserving: same 28 columns, same order, same row count. |
| `convert-classified` | Walk `input/classified/**/*.xls*` (skipping `void/`), convert each parseable sheet to a 28-column CSV under `input/classified_csv/`. Output is committed so the lookup is reproducible offline. |
| `build-type-enum`    | Re-scan `input/classified_csv/` and regenerate `src/classifier/config/type_enum.py` (the canonical 3-letter `type` enum). |
```

(If the README contains additional prose describing the old `sort-files` workflow, delete those sections. Leave intro and install/dev sections alone.)

- [ ] **Step 3: Move the legacy docs into an archive directory**

```
mkdir -p docs/archive/specs docs/archive/plans
git mv docs/specs/2026-04-30-classifier-design.md       docs/archive/specs/
git mv docs/specs/2026-05-01-two-class-fold-design.md   docs/archive/specs/
git mv docs/specs/2026-05-05-src-layout-restructure-design.md docs/archive/specs/
git mv docs/plans/2026-04-30-classifier.md               docs/archive/plans/
git mv docs/plans/2026-05-01-two-class-fold.md           docs/archive/plans/
git mv docs/plans/2026-05-05-src-layout-restructure.md   docs/archive/plans/
```

Verify the source dirs are now empty:
```
ls docs/specs docs/plans
```
Expected: each directory exists but is empty (or `ls` reports them absent on some shells).

If empty, remove them:
```
rmdir docs/specs docs/plans
```

- [ ] **Step 4: Commit**

```
git add README.md
git commit -m "docs: trim README to three entry points; archive old specs/plans

The pre-canonical-CSV specs and plans are moved into docs/archive/
(git mv preserves blame). docs/superpowers/{specs,plans}/ are
untouched; they hold the current generation of project artifacts."
```

---

## Task 9: Final verification + baseline hash check

**Files:**
- Read: `.baseline-hashes.json`
- Delete (after check): `.baseline-hashes.json`

- [ ] **Step 1: Run the spec's verification battery**

```
.venv/Scripts/python -c "
import importlib, pathlib, re
# 1. surviving entry points still import
for mod in ('classifier.cli.classify',
            'classifier.tools.convert_classified',
            'classifier.tools.build_type_enum'):
    importlib.import_module(mod)
print('imports ok')

# 2. no dangling routing/pipeline imports in src
banned = re.compile(r'classifier\\.(routing|pipeline)\\.')
hits = []
for p in pathlib.Path('src/classifier').rglob('*.py'):
    text = p.read_text(encoding='utf-8')
    if banned.search(text):
        hits.append(str(p))
assert not hits, f'dangling imports: {hits}'
print('no dangling routing/pipeline imports')

# 3. surviving config exports
from classifier.config.buckets import BUCKET_TO_CLASS, TYPE_TO_BUCKET
from classifier.config.keywords import KEYWORD_RULES, DISCIPLINE_KEYWORD_RULES
from classifier.config.type_enum import KNOWN_TYPES, OBSERVED_OUTLIERS
print('config ok')
"
```
Expected: three `ok` lines, no traceback.

- [ ] **Step 2: Confirm surviving layout matches spec**

```
find src/classifier -name '*.py' -not -path '*__pycache__*' | sort
```
Expected output (exactly 16 lines: 10 content modules + 6 `__init__.py` files):
```
src/classifier/__init__.py
src/classifier/cli/__init__.py
src/classifier/cli/classify.py
src/classifier/config/__init__.py
src/classifier/config/buckets.py
src/classifier/config/keywords.py
src/classifier/config/type_enum.py
src/classifier/core/__init__.py
src/classifier/core/scoring.py
src/classifier/io/__init__.py
src/classifier/io/normalize.py
src/classifier/io/schema.py
src/classifier/io/type_lookup.py
src/classifier/tools/__init__.py
src/classifier/tools/build_type_enum.py
src/classifier/tools/convert_classified.py
```
Confirm none of the deleted modules (`sort.py`, `routing/*`, `pipeline/*`, `dump_*.py`, `evaluate.py`, `harvest.py`, `csv_writer.py`, `schedule_reader.py`, `dossier_reader.py`, `transmittals.py`, `related_xlsx.py`, `discipline.py`, `extraction.py`, `form.py`, `normalisation.py`, `revisions.py`, `targets.py`, `schema.py`, `patterns.py`, `paths.py`) appear.

- [ ] **Step 3: Re-run the pipeline and compare artifact hashes to baseline**

```
.venv/Scripts/python -m classifier.tools.convert_classified > /dev/null
.venv/Scripts/python -m classifier.tools.build_type_enum > /dev/null
.venv/Scripts/python -m classifier.cli.classify > /dev/null

.venv/Scripts/python -c "
import hashlib, pathlib, json
def hash_tree(root):
    h = hashlib.sha256()
    for p in sorted(pathlib.Path(root).rglob('*'), key=lambda x: str(x).lower()):
        if p.is_file(): h.update(p.read_bytes())
    return h.hexdigest()
baseline = json.loads(pathlib.Path('.baseline-hashes.json').read_text())
current = {
    'classified_csv': hash_tree('input/classified_csv'),
    'output_classified_csv': hashlib.sha256(pathlib.Path('output/classified.csv').read_bytes()).hexdigest(),
}
assert baseline == current, f'hashes drifted:\\n  baseline={baseline}\\n  current={current}'
print('hashes match baseline')
pathlib.Path('.baseline-hashes.json').unlink()
print('baseline file cleaned up')
"
```
Expected: prints `hashes match baseline` and `baseline file cleaned up`.

- [ ] **Step 4: Confirm working tree is clean**

```
git status
```
Expected: clean (nothing to commit). `.baseline-hashes.json` should be absent (deleted in Step 3, was gitignored anyway).

No commit needed for Task 9 — it's verification only.
