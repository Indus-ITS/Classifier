# Document Classifier

Classifies engineering deliverable rows from project schedule sheets into
two classes — **Drawings** or **Documents** — and (optionally) sorts the
referenced files into class folders for transmittal.

The classification is keyword-based: regex rules score the document title
against ten internal buckets (Drawings, Isometrics, Datasheets,
Specifications, Calculations, Reports, Lists/MTOs/BOMs,
Procedures/Plans, CRS, Documents) and the winning bucket folds into one
of the two user-facing classes. A third class, **Undefined**, is returned
when no keyword fires — those rows go to a separate file for human
review rather than being silently dumped into Documents.

## Quick start

```bash
.venv/Scripts/pip install -r requirements.txt

# 1. Classify schedule rows
.venv/Scripts/python classifier.py

# 2. (Optional) Sort the referenced files into class folders
.venv/Scripts/python sort_files.py --schedule "input/To be classified/sahil schedule.xls" \
                                    --source-dir /path/to/your/docs
```

`classifier.py` reads every `*.xls*` under `input/To be classified/` and
writes [output/classified.csv](output/classified.csv).

`sort_files.py` is an interactive CLI that takes the same schedule plus a
directory of files (named by `cust_ref`) and routes them into
`Drawings/`, `Documents/`, `Undefined/`, `Unmatched/` either in-place or
by copying to a destination directory. Run with `--help` for full
options.

## Entry points

| Script | What it does | Output |
|---|---|---|
| [classifier.py](classifier.py) | Classify schedule rows | [output/classified.csv](output/classified.csv) |
| [sort_files.py](sort_files.py) | Interactive CLI: sort/copy files into class folders based on the schedule | files moved/copied into `Drawings/` `Documents/` `Undefined/` `Unmatched/` |
| [helpers/harvest_labelled.py](helpers/harvest_labelled.py) | Build the 73k-row labelled corpus from `input/classified/` | [output/helpers/labelled_corpus.csv](output/helpers/labelled_corpus.csv) |
| [helpers/evaluate_corpus.py](helpers/evaluate_corpus.py) | Measure classifier accuracy on the labelled corpus | [output/helpers/evaluation_report.txt](output/helpers/evaluation_report.txt) + per-row predictions CSV |
| [helpers/dump_bucket_mapping.py](helpers/dump_bucket_mapping.py) | Dump the description → bucket → class mapping for senior review | [output/bucket_mapping.csv](output/bucket_mapping.csv) |
| [helpers/dump_undefined.py](helpers/dump_undefined.py) | Filter `output/classified.csv` to just the rows where `class=Undefined` | [output/undefined_for_review.csv](output/undefined_for_review.csv) |

## Layout

```
classifier/
├── classifier.py              # main classifier - run this
├── sort_files.py              # interactive CLI to route files into class folders
├── config.py                  # tunables: keyword bank, BUCKET_TO_CLASS fold,
│                              #   discipline rules, regex patterns
├── README.md
├── requirements.txt
│
├── helpers/                   # library + offline tools (not part of the main run)
│   ├── classifier_lib.py      # bucket scoring, fold helper, ref/rev extraction
│   ├── router_lib.py          # pure file-routing logic (used by sort_files.py)
│   ├── harvest_labelled.py    # builds the labelled corpus from input/classified/
│   ├── evaluate_corpus.py     # measures accuracy on the labelled corpus
│   ├── dump_bucket_mapping.py # writes output/bucket_mapping.csv
│   └── dump_undefined.py      # writes output/undefined_for_review.csv
│
├── input/
│   ├── To be classified/      # *.xls schedule sheets to classify
│   └── classified/            # labelled reference indices (drive the corpus)
│
├── output/
│   ├── classified.csv         # ← MAIN classifier output
│   ├── bucket_mapping.csv     # description → bucket → class for senior review
│   ├── undefined_for_review.csv  # rows that need human review
│   └── helpers/               # diagnostic outputs
│       ├── labelled_corpus.csv
│       ├── labelled_predictions.csv
│       ├── evaluation_report.txt
│       └── dossier_selftest.txt
│
├── overrides/                 # placeholder for cust_ref -> bucket overrides
├── tests/                     # pytest suite (226 tests)
└── docs/
    ├── specs/                 # design docs (latest: 2026-05-01-two-class-fold-design.md)
    └── plans/                 # implementation plans
```

## Output schema — [output/classified.csv](output/classified.csv)

| Column | Meaning |
|---|---|
| `title` | Document title from the schedule |
| `doc_number` | PCS Doc No. (project document number) |
| `cust_ref` | Customer reference number (e.g. `16-01-19-2602`) |
| `revision` | Revision letter / number from the schedule |
| `discipline` | Discipline as recorded in the schedule (CIVIL, INST, PIPNG, etc.) |
| `class` | **Primary classification** — `Drawings`, `Documents`, or `Undefined` (no keyword fired — needs human review) |
| `subtype` | 10-bucket label (Drawings, Isometrics, Datasheets, Specifications, Calculations, Reports, Lists_MTOs_BOMs, Procedures_Plans, CRS, Documents) — kept as a finer-grained sub-routing hint |
| `source_sheet` | Filename of the schedule the row came from |
| `discipline_inferred` | Discipline guessed from title keywords (diagnostic — compare against `discipline`) |
| `score` | Total weight that fired in the winning subtype |
| `top_weight` | Highest single weight that fired (drives confidence) |
| `confidence` | `high` (top weight 5) / `medium` (3-4) / `low` (1-2 or fallthrough) |
| `runner_up` | Second-place subtype |
| `runner_up_score` | Second-place score (close calls = ambiguous classifications) |

The first seven columns are the user-facing identity + classification;
the rest are explainability fields useful when auditing or tuning.
`class` is what most consumers care about; `subtype` is preserved so the
existing 10-bucket sub-routing remains available.

**Filtering tip:** for clean classifications use `class != "Undefined"`;
for items needing human review use `class == "Undefined"`.

## sort_files.py — interactive file routing

Given a schedule and a directory whose filenames embed the schedule's
`cust_ref` numbers, this CLI splits the files into class folders.

```bash
# Interactive (prompts for mode + destination + confirmation)
python sort_files.py --schedule schedule.xls --source-dir ./docs

# Non-interactive copy
python sort_files.py --schedule schedule.xls --source-dir ./docs \
    --mode copy --dest-dir ./sorted --yes

# Non-interactive in-place sort
python sort_files.py --schedule schedule.xls --source-dir ./docs \
    --mode in-place --yes
```

| Flag | Purpose |
|---|---|
| `--schedule PATH` | Schedule `.xls` (must have Sheet1 with `Cust Ref #` and `Title`) |
| `--source-dir PATH` | Directory containing the files (top level only by default) |
| `--recursive`, `-r` | Walk subdirectories. Files already inside class folders (`Drawings/`, `Documents/`, etc.) are skipped so re-runs are safe. |
| `--clean-empty-dirs` | After execution, remove any subdirectories that are now empty. Useful with `--recursive --mode in-place` to clean up emptied transmittal folders. |
| `--on-duplicate {error\|skip\|rename}` | What to do when two source files would land at the same destination (common with `--recursive` when the same document was re-sent across transmittals). `error` (default): abort with the collision list. `skip`: keep the first source by path order, drop the rest. `rename`: keep all by appending a numeric suffix (`foo.pdf`, `foo-2.pdf`, `foo-3.pdf`, ...). |
| `--include-title` | Append the schedule's Title to the destination filename: `<original_stem> - <safe_title><ext>`. The title is sanitized for filesystem safety (path-unsafe chars → `_`) and truncated to `--title-max-len`. Files with no schedule match (Unmatched) keep their original name. |
| `--title-max-len N` | Max characters of the title to include (default 100). |
| `--mode {in-place\|copy}` | Skip the mode prompt |
| `--dest-dir PATH` | Destination for copy mode (skips the dest prompt) |
| `--yes`, `-y` | Skip the final confirmation |
| `--no-color` | Disable ANSI color (auto-disabled when not a TTY or when `NO_COLOR` is set) |

**Resulting folder layout:**

The sort always produces a **two-level `class / discipline / file`** tree.
Discipline comes from the schedule's `Discip` column and is sanitized for
filesystem safety (`ENGG QA/QC` → `ENGG_QA_QC`, missing → `_UNKNOWN`):

```
<dest>/
├── Drawings/
│   ├── CIVIL/        matched, class==Drawings, discipline==CIVIL
│   ├── PIPNG/
│   ├── INST/
│   ├── ELEC/
│   ├── MECH/
│   ├── PROC/
│   ├── HSE/
│   ├── ENGG_HSE/     ('ENGG HSE' sanitized)
│   ├── ENGG_QA_QC/   ('ENGG QA/QC' sanitized)
│   └── ...
├── Documents/
│   ├── CIVIL/
│   ├── PIPNG/
│   ├── INST/
│   └── ...
├── Undefined/        matched class==Undefined, still grouped by discipline
│   ├── PIPNG/
│   ├── INST/
│   └── ...
└── Unmatched/        no schedule match - kept flat (no discipline available)
    └── *.pdf
```

Safety:
- **Collision detection** — aborts before any I/O if a destination path
  already exists or two source files would map to the same destination.
- **In-place re-run safety** — files already at their target are no-ops.
- **Honest reporting** — separately counts files with no `cust_ref` in
  the name, files whose ref isn't in the schedule, and schedule rows
  with no matching file on disk.

## How to iterate on accuracy

1. Edit keyword rules in [config.py](config.py) — `KEYWORD_RULES[bucket]`
   is the main lever. Weights are 1-5; weight 5 is required for `high`
   confidence.
2. Re-run `python classifier.py` and inspect `output/classified.csv`.
3. Check what's still falling through:

   ```bash
   python helpers/dump_undefined.py     # writes output/undefined_for_review.csv
   ```

4. Measure regression-impact at scale on the 73k-row labelled corpus:

   ```bash
   python helpers/harvest_labelled.py   # rebuilds output/helpers/labelled_corpus.csv
   python helpers/evaluate_corpus.py    # writes evaluation_report.txt + per-row predictions
   ```

   The corpus is built from labelled reference indices under
   `input/classified/` (Sahil/Shah/Asab/Qusahwira drawing & document
   indices). Each row's `expected_bucket` is derived from the project's
   own doc-type code, not from the title — so the measurement is
   independent of the keyword bank.

5. Run unit tests with `.venv/Scripts/pytest -q`.

### Typo tolerance policy

The keyword bank uses targeted regex tolerance for real typos seen in
the data (e.g. `arra?n?g(e)?ment` for ARRANGEMENT/ARRANGMENT/ARRAGEMENT,
`requ[a-z]{2,5}tion` for REQUISITION/REQUSITION/REQUISTION/REQUISTATION).

**Generic fuzzy matching (Levenshtein/soundex) is intentionally not
used** — it introduces unpredictable false positives that are expensive
to debug. When a new typo surfaces in
`output/undefined_for_review.csv`, the fix is to relax the relevant
regex pattern and pin it with a regression test in
[tests/test_keyword_bank.py](tests/test_keyword_bank.py).

## Tunables in `config.py`

| Constant | What it does |
|---|---|
| `BUCKETS` | The 10 internal content buckets (don't reorder) |
| `BUCKET_TO_CLASS` | 10-bucket → 2-class fold (Drawings or Documents) |
| `KEYWORD_RULES` | `{bucket: [(regex, weight 1-5), ...]}` — bucket scoring |
| `TYPE_TO_BUCKET` | 3-letter dossier Type code → bucket |
| `BUCKET_PRIMARY_CODE` | Bucket → 3-letter code used in proposed target filename |
| `DISCIPLINE_KEYWORD_RULES` | `[(regex, discipline), ...]` — fallback discipline inference |
| `REF_PATTERN`, `CRS_PATTERN`, `COVER_PATTERN` | Regex strings used by `helpers/classifier_lib.py` |
| `GATE_THRESHOLD` | Self-test pass bar for the older 256-row dossier selftest |

## Current quality (last measured)

### On the 73,000-row labelled corpus
| Metric | Value |
|---|---|
| **Class accuracy** (Drawings / Documents / Undefined) | **95.71%** |
| Subtype accuracy (10 buckets) | 95.62% |
| Drawings subtype recall | 94.7% |
| Isometrics subtype recall | 100% |
| Datasheets subtype recall | 88.7% |

### On the live schedule output (4,027 rows)
| Metric | Value |
|---|---|
| Drawings (class) | 2,624 (65.2%) |
| Documents (class) | 1,392 (34.6%) |
| **Undefined (class)** | **11 (0.3%)** — flagged for human review |
| High-confidence rows | 69.9% |
| Low-confidence rows | 4.6% |

### Engineering hygiene
- **226 tests passing** (unit + regression + router_lib)
- Spec: [docs/specs/2026-05-01-two-class-fold-design.md](docs/specs/2026-05-01-two-class-fold-design.md)
- Plan: [docs/plans/2026-05-01-two-class-fold.md](docs/plans/2026-05-01-two-class-fold.md)

The 11 remaining Undefined rows are genuinely ambiguous from the title
alone (area codes like `SY-RDS-1`, descriptive well titles, one-off
correspondence) — they can't be reliably resolved by keyword
classification and need either human review or doc-number-prefix
decoding.

## Bucket → Class mapping

The 10-bucket → 2-class fold lives in `BUCKET_TO_CLASS` in
[config.py](config.py):

| Bucket | Class |
|---|---|
| Drawings | **Drawings** |
| Isometrics | **Drawings** |
| Datasheets | Documents |
| Specifications | Documents |
| Calculations | Documents |
| Reports | Documents |
| Lists_MTOs_BOMs | Documents |
| Procedures_Plans | Documents |
| CRS | Documents |
| Documents | Documents |

Plus the **Undefined** class is returned when `score_sum == 0` (no
keyword fired). This is implemented in
`helpers.classifier_lib.fold_to_class()` and used by both
[classifier.py](classifier.py) and
[helpers/evaluate_corpus.py](helpers/evaluate_corpus.py) so they apply
the same rule.

For senior review of the underlying doc-code → bucket → class mapping,
run `python helpers/dump_bucket_mapping.py` and share
[output/bucket_mapping.csv](output/bucket_mapping.csv) (115 unique
mappings, sorted by class then bucket).

## Tests

```bash
.venv/Scripts/pytest -q
# 226 passed
```

Test files:

| File | Coverage |
|---|---|
| [tests/test_class_fold.py](tests/test_class_fold.py) | `BUCKET_TO_CLASS` mapping, `fold_to_class()` helper, end-to-end class derivation |
| [tests/test_classify.py](tests/test_classify.py) | `score_buckets`, `pick_bucket`, form resolution, structural invariants |
| [tests/test_extract.py](tests/test_extract.py) | `extract_ref`, `extract_letter_rev`, `extract_numeric_rev`, sibling-rev inheritance |
| [tests/test_keyword_bank.py](tests/test_keyword_bank.py) | Real-data regression tests pinning every keyword fix |
| [tests/test_normalise.py](tests/test_normalise.py) | `normalise_filename` (NFKC, dash variants, NBSP) |
| [tests/test_regressions.py](tests/test_regressions.py) | Bug-anchored regressions for the original v3-output review |
| [tests/test_router_lib.py](tests/test_router_lib.py) | File matching, plan building, collision detection, copy/move execution |
