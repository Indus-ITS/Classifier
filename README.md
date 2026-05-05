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
pip install -e .

# 1. Classify schedule rows
classify

# 2. (Optional) Sort the referenced files into class folders
sort-files --schedule "input/To be classified/sahil schedule.xls" \
           --source-dir /path/to/your/docs
```

`classify` reads every `*.xls*` under `input/To be classified/` and
writes [output/classified.csv](output/classified.csv).

`sort-files` is an interactive CLI that takes the same schedule plus a
directory of files (named by `cust_ref`) and routes them into
`Drawings/`, `Documents/`, `Undefined/`, `Unmatched/` either in-place or
by copying to a destination directory. Run with `--help` for full
options.

## Console scripts

| Command | What it does | Output |
|---|---|---|
| `classify` | Classify schedule rows | [output/classified.csv](output/classified.csv) |
| `sort-files` | Interactive CLI: sort/copy files into class folders | files moved/copied into `Drawings/` `Documents/` `Undefined/` `Unmatched/` |
| `harvest` | Build the labelled corpus from `input/classified/` | `output/helpers/labelled_corpus.csv` |
| `evaluate` | Measure classifier accuracy on the labelled corpus | `output/helpers/evaluation_report.txt` + per-row predictions CSV |
| `dump-buckets` | Dump the description → bucket → class mapping for senior review | `output/bucket_mapping.csv` |
| `dump-undefined` | Filter `output/classified.csv` to just the rows where `class=Undefined` | `output/undefined_for_review.csv` |

## Layout

```
classifier/
├── pyproject.toml                    # package metadata + console scripts
├── README.md
├── requirements.txt
│
├── src/classifier/                   # the package
│   ├── config/                       # tunables (paths, buckets, keywords, patterns, schema)
│   ├── core/                         # pure logic (scoring, extraction, normalisation, ...)
│   ├── pipeline/                     # orchestration (enrich, audit, selftest)
│   ├── io/                           # file readers/writers (schedule, dossier, transmittals, overrides, csv)
│   ├── routing/                      # sort-files matching/planning/execution
│   ├── cli/                          # console entry points + presentation helpers
│   └── tools/                        # offline diagnostic commands
│
├── input/
│   ├── To be classified/             # *.xls schedule sheets to classify
│   └── classified/                   # labelled reference indices (drive the corpus)
│
├── output/
│   ├── classified.csv                # ← MAIN classifier output
│   ├── bucket_mapping.csv            # description → bucket → class for senior review
│   ├── undefined_for_review.csv      # rows that need human review
│   └── helpers/                      # diagnostic outputs (labelled_corpus.csv, evaluation_report.txt, ...)
│
├── overrides/                        # placeholder for cust_ref → bucket overrides
└── docs/
    ├── specs/                        # design docs
    └── plans/                        # implementation plans
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

## sort-files — interactive file routing

Given a schedule and a directory whose filenames embed the schedule's
`cust_ref` numbers, this CLI splits the files into class folders.

```bash
# Interactive (prompts for mode + destination + confirmation)
sort-files --schedule schedule.xls --source-dir ./docs

# Non-interactive copy
sort-files --schedule schedule.xls --source-dir ./docs \
           --mode copy --dest-dir ./sorted --yes

# Non-interactive in-place sort
sort-files --schedule schedule.xls --source-dir ./docs \
           --mode in-place --yes
```

| Flag | Purpose |
|---|---|
| `--schedule PATH` | Schedule `.xls` (must have Sheet1 with `Cust Ref #` and `Title`) |
| `--source-dir PATH` | Directory containing the files (top level only by default) |
| `--recursive`, `-r` | Walk subdirectories. Files already inside class folders (`Drawings/`, `Documents/`, etc.) are skipped so re-runs are safe. |
| `--clean-empty-dirs` | After execution, remove any subdirectories that are now empty. Useful with `--recursive --mode in-place` to clean up emptied transmittal folders. |
| `--on-duplicate {error\|skip\|rename}` | What to do when two source files would land at the same destination. `error` (default): abort. `skip`: keep first by path order. `rename`: append numeric suffix (`foo.pdf`, `foo-2.pdf`, ...). |
| `--include-title` | Append the schedule's Title to the destination filename: `<original_stem> - <safe_title><ext>`. The title is sanitized for filesystem safety and truncated to `--title-max-len`. Files with no schedule match (Unmatched) keep their original name. |
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
│   └── ...
├── Documents/
│   └── ...
├── Undefined/        matched class==Undefined, still grouped by discipline
│   └── ...
└── Unmatched/        no schedule match — kept flat (no discipline available)
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

1. Edit keyword rules in
   [src/classifier/config/keywords.py](src/classifier/config/keywords.py) —
   `KEYWORD_RULES[bucket]` is the main lever. Weights are 1-5; weight 5
   is required for `high` confidence.
2. Re-run `classify` and inspect `output/classified.csv`.
3. Check what's still falling through:

   ```bash
   dump-undefined     # writes output/undefined_for_review.csv
   ```

4. Measure regression-impact at scale on the labelled corpus:

   ```bash
   harvest    # rebuilds output/helpers/labelled_corpus.csv
   evaluate   # writes evaluation_report.txt + per-row predictions
   ```

   The corpus is built from labelled reference indices under
   `input/classified/` (Sahil/Shah/Asab/Qusahwira drawing & document
   indices). Each row's `expected_bucket` is derived from the project's
   own doc-type code, not from the title — so the measurement is
   independent of the keyword bank.

### Typo tolerance policy

The keyword bank uses targeted regex tolerance for real typos seen in
the data (e.g. `arra?n?g(e)?ment` for ARRANGEMENT/ARRANGMENT/ARRAGEMENT,
`requ[a-z]{2,5}tion` for REQUISITION/REQUSITION/REQUISTION/REQUISTATION).

**Generic fuzzy matching (Levenshtein/soundex) is intentionally not
used** — it introduces unpredictable false positives that are expensive
to debug. When a new typo surfaces in
`output/undefined_for_review.csv`, the fix is to relax the relevant
regex pattern in
[src/classifier/config/keywords.py](src/classifier/config/keywords.py).

## Tunables

| Constant | Where | What it does |
|---|---|---|
| `BUCKETS` | [config/buckets.py](src/classifier/config/buckets.py) | The 10 internal content buckets (don't reorder) |
| `BUCKET_TO_CLASS` | [config/buckets.py](src/classifier/config/buckets.py) | 10-bucket → 2-class fold (Drawings or Documents) |
| `KEYWORD_RULES` | [config/keywords.py](src/classifier/config/keywords.py) | `{bucket: [(regex, weight 1-5), ...]}` — bucket scoring |
| `TYPE_TO_BUCKET` | [config/buckets.py](src/classifier/config/buckets.py) | 3-letter dossier Type code → bucket |
| `BUCKET_PRIMARY_CODE` | [config/buckets.py](src/classifier/config/buckets.py) | Bucket → 3-letter code used in proposed target filename |
| `DISCIPLINE_KEYWORD_RULES` | [config/keywords.py](src/classifier/config/keywords.py) | `[(regex, discipline), ...]` — fallback discipline inference |
| `REF_PATTERN`, `CRS_PATTERN`, `COVER_PATTERN` | [config/patterns.py](src/classifier/config/patterns.py) | Regex strings for ref / CRS / cover-sheet detection |
| `GATE_THRESHOLD` | [config/paths.py](src/classifier/config/paths.py) | Self-test pass bar for the 256-row dossier selftest |

## Bucket → Class mapping

The 10-bucket → 2-class fold lives in `BUCKET_TO_CLASS`:

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
[`fold_to_class()`](src/classifier/core/scoring.py) and used by both
`classify` and `evaluate` so they apply the same rule.

For senior review of the underlying doc-code → bucket → class mapping,
run `dump-buckets` and share
[output/bucket_mapping.csv](output/bucket_mapping.csv) (sorted by class
then bucket).

## Architecture

The package is layered, with imports flowing in one direction only:

```
presentation (cli)
    ↓
application (routing, pipeline)
    ↓
domain (core)
    ↓
infrastructure (io)
```

- **`core/`** is pure logic: regex extraction, scoring, revisions,
  target-path construction. No I/O, no upward imports.
- **`io/`** wraps file readers/writers (`pandas.read_excel`, CSV).
- **`pipeline/`** orchestrates `core/` + `io/` for the enrich/audit/selftest flows.
- **`routing/`** holds the file-routing logic for `sort-files`
  (matching, plan, analysis, resolution, execute).
- **`cli/`** is presentation only — argparse, prompts, ANSI colors,
  progress bars, formatted reports.
- **`tools/`** is the home of standalone diagnostic commands.
