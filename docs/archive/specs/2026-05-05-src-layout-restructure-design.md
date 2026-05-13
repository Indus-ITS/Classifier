# src-layout restructure — design

**Date:** 2026-05-05
**Status:** Approved (Q1/Q2/Q3 confirmed)

## Goal

Reorganize the Classifier codebase into a `src/`-based Python package with
single-responsibility modules, rename entry points and offline tools for
clarity, and remove the test suite.

## Non-goals

- No behavior changes. The classifier output (`output/classified.csv`) and
  `sort-files` routing must be byte-identical to the current implementation.
- No refactoring of regex/keyword logic.
- No changes to `docs/specs/` or `docs/plans/` filenames or contents.
- No changes to `input/`, `output/`, `overrides/` directories.

## Target layout

```
classifier/
├── README.md                       (updated: new commands + import paths)
├── requirements.txt
├── pyproject.toml                  NEW
├── docs/  input/  output/  overrides/   (unchanged)
└── src/classifier/
    ├── __init__.py
    ├── config/
    │   ├── __init__.py             re-exports for back-compat
    │   ├── paths.py                SCHEDULE_PATH, DOSSIER_PATH, TREE_PATH,
    │   │                           OVERRIDES_PATH, OUTPUT_DIR, GATE_THRESHOLD
    │   ├── buckets.py              BUCKETS, BUCKET_TO_CLASS, TYPE_TO_BUCKET,
    │   │                           BUCKET_PRIMARY_CODE
    │   ├── keywords.py             KEYWORD_RULES, DISCIPLINE_KEYWORD_RULES
    │   ├── patterns.py             REF_PATTERN, CRS_PATTERN, COVER_PATTERN
    │   └── schema.py               CSV_COLUMNS
    ├── core/                       pure logic, no I/O
    │   ├── __init__.py
    │   ├── normalisation.py        normalise_filename
    │   ├── extraction.py           extract_ref, extract_letter_rev,
    │   │                           extract_numeric_rev, extract_revs,
    │   │                           inherit_rev_from_siblings
    │   ├── scoring.py              score_buckets, pick_bucket, fold_to_class
    │   ├── discipline.py           discipline_from_keywords, derive_discipline,
    │   │                           build_seg2_discipline_map
    │   ├── form.py                 is_crs_filename, is_cover_filename,
    │   │                           resolve_form_pre, resolve_form_post
    │   ├── revisions.py            assign_bundle_id,
    │   │                           compute_is_latest_for_group,
    │   │                           classify_revision_drift
    │   └── targets.py              build_target_paths,
    │                                detect_target_collisions, _sanitise_title,
    │                                _rev_token
    ├── pipeline/                   orchestration over core+io
    │   ├── __init__.py
    │   ├── enrich.py               enrich_files()
    │   ├── audit.py                write_audit()
    │   └── selftest.py             run_dossier_selftest()
    ├── routing/
    │   ├── __init__.py
    │   ├── schedule_refs.py        load_schedule_refs, safe_discipline,
    │   │                           safe_title
    │   ├── matching.py             FileMatch, MatchResult, match_files,
    │   │                           classify_title, _iter_source_files
    │   ├── plan.py                 RoutePlan, build_plan,
    │   │                           _name_with_title, _class_folder_for
    │   ├── analysis.py             plan_summary,
    │   │                           plan_summary_by_class_discipline,
    │   │                           find_collisions
    │   ├── resolution.py           resolve_duplicates
    │   └── execute.py              execute_plan, clean_empty_dirs
    ├── io/
    │   ├── __init__.py
    │   ├── schedule_reader.py      pandas xls reader for "To be classified/*.xls"
    │   ├── dossier_reader.py       load_dossier
    │   ├── transmittals.py         parse_transmittals
    │   ├── overrides_reader.py     load_overrides   (moved from core/ — it's CSV loading)
    │   └── csv_writer.py           generic CSV writer (was _csv_value/write_csv)
    ├── cli/
    │   ├── __init__.py
    │   ├── classify.py             entry: was classifier.py
    │   ├── sort.py                 entry: was sort_files.py
    │   ├── colors.py               _Color class, _color_enabled
    │   ├── prompts.py              _prompt, _prompt_path
    │   └── reporting.py            _print_match_summary, _print_plan_summary,
    │                               _print_progress
    └── tools/
        ├── __init__.py
        ├── dump_buckets.py         was helpers/dump_bucket_mapping.py
        ├── dump_undefined.py
        ├── evaluate.py             was helpers/evaluate_corpus.py
        └── harvest.py              was helpers/harvest_labelled.py
```

## pyproject.toml

```toml
[project]
name = "classifier"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["pandas", "openpyxl", "xlrd"]

[project.scripts]
classify     = "classifier.cli.classify:main"
sort-files   = "classifier.cli.sort:main"
dump-buckets = "classifier.tools.dump_buckets:main"
dump-undefined = "classifier.tools.dump_undefined:main"
evaluate     = "classifier.tools.evaluate:main"
harvest      = "classifier.tools.harvest:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

After install (`pip install -e .`), users run:

```
classify
sort-files --schedule ... --source-dir ...
```

## Renames (user-visible)

| Old | New |
|---|---|
| `classifier.py`                    | console: `classify`              |
| `sort_files.py`                    | console: `sort-files`            |
| `helpers/dump_bucket_mapping.py`   | console: `dump-buckets`          |
| `helpers/dump_undefined.py`        | console: `dump-undefined`        |
| `helpers/evaluate_corpus.py`       | console: `evaluate`              |
| `helpers/harvest_labelled.py`      | console: `harvest`               |

## Deletions

- `tests/` (whole directory)
- `__pycache__/`, `helpers/__pycache__/`, `tests/__pycache__/`
- `helpers/` (becomes empty after content is moved)
- `classifier.py`, `sort_files.py`, `config.py` at project root (replaced by package)
- `sortted_tree.txt` (stale tree dump)

## Behavior contract

- `classify` reads the same `input/To be classified/*.xls` files and writes
  the same `output/classified.csv` with the same columns and same row order.
- `sort-files` accepts the same flags (`--schedule`, `--source-dir`,
  `--recursive`, `--clean-empty-dirs`, `--include-title`, `--title-max-len`,
  `--on-duplicate`, `--mode`, `--dest-dir`, `--yes`, `--no-color`) and
  produces the same folder layout.
- All `tools/` commands keep their current outputs.

## Migration constraints (rules during the split)

These rules apply only during the restructure pass. They prevent the
"emotionally homeless module" / "two copies of the same regex" failure
modes that come from a mechanical file-split.

1. **No logic duplication.** Every function moves exactly once; nothing is
   copied. If two new modules feel like they need the same helper, put the
   helper in `core/shared.py` (create on demand) and import from there. Do
   not paste regex literals or normalisation snippets into multiple files.
2. **`cli/` is presentation-only.** No classification logic, no path
   resolution, no business decisions. `cli/` modules may import from
   `routing/`, `pipeline/`, and `core/` but those layers may NOT import
   from `cli/`. If a `cli/` module starts deciding *what* to do (vs. *how*
   to display it), the logic belongs in `core/` or `pipeline/`.
3. **Architecture flow is one-directional:**

   ```
   presentation (cli)
       ↓
   application (routing, pipeline)
       ↓
   domain (core)
       ↓
   infrastructure (io)
   ```

   Concretely: `core/` imports nothing from `pipeline/`, `routing/`,
   `cli/`, or `io/` (except for type-hint-only imports under
   `TYPE_CHECKING`). `io/` imports from `core/` only. `pipeline/` and
   `routing/` may import from `core/` and `io/`. `cli/` may import from
   anywhere below it but nothing imports back up.
4. **`config/__init__.py` re-exports are temporary.** Marked with a
   sunset comment: remove after the next two changes that touch the
   classifier package, or by 2026-08-01, whichever comes first. New code
   must import from the specific submodule (`from classifier.config.keywords
   import KEYWORD_RULES`), not from `classifier.config`.

## Risks

- **Import cycles** between `core/`, `pipeline/`, `io/`. Mitigation:
  `core/` imports nothing from `pipeline/` or `io/`; `pipeline/` may import
  from both; `io/` may import from `core/` only for type hints.
- **Hidden cross-references** in `helpers/classifier_lib.py` between functions
  now landing in different modules. Mitigation: do the split as one mechanical
  pass, then run `python -m classifier.cli.classify` and
  `dump-buckets`/`evaluate`/`harvest` once each end-to-end before declaring
  done.
- **README rot.** README has many file links. Mitigation: update README in
  the same change.

## Verification (no automated tests — manual smoke checks)

1. **Golden-file diff (mandatory, runs before anything else moves).**
   Before starting the migration, run the existing classifier and snapshot
   its output:

   ```
   python classifier.py
   copy output\classified.csv output\classified.golden.csv
   ```

   After the migration, run the new entry point and byte-diff:

   ```
   classify
   fc /b output\classified.csv output\classified.golden.csv
   ```

   The diff must be empty. Same procedure for `dump-buckets` and
   `dump-undefined` outputs. This is the only defence against pandas
   version drift, ordering changes, and float/string normalisation
   regressions — none of which a code review will catch.
2. `pip install -e .` succeeds.
3. `classify` produces `output/classified.csv` with the expected header and
   non-zero rows.
4. `sort-files --help` prints, `dump-buckets` and `dump-undefined` run.
5. `python -c "from classifier.core.scoring import score_buckets, pick_bucket, fold_to_class; print('ok')"`
6. No references to `helpers.` or top-level `config` remain in code.
7. **Layering check** — grep for forbidden upward imports:
   - `from classifier.cli` should not appear under `core/`, `io/`,
     `routing/`, `pipeline/`.
   - `from classifier.pipeline` and `from classifier.routing` should not
     appear under `core/` or `io/`.
