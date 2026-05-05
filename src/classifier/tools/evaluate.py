"""Run the bucket classifier against output/helpers/labelled_corpus.csv and
report two accuracy numbers in parallel:

  * class accuracy   - bucket-level prediction folded to {Drawings, Documents}
  * subtype accuracy - bucket-level prediction matched exactly

Also writes a per-row predictions CSV and a confusion matrix at both
levels (10x10 subtype + 2x2 class). Run from the project root::

    evaluate
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from classifier.config.buckets import BUCKET_TO_CLASS
from classifier.core.scoring import fold_to_class, pick_bucket, score_buckets

CORPUS = Path("output/helpers/labelled_corpus.csv")
OUT_PRED = Path("output/helpers/labelled_predictions.csv")
OUT_REPORT = Path("output/helpers/evaluation_report.txt")


def main() -> None:
    df = pd.read_csv(CORPUS, dtype=str).fillna("")
    n = len(df)
    pred_rows = []
    correct_subtype = 0
    correct_class = 0
    confusion_subtype: dict = defaultdict(int)
    confusion_class: dict = defaultdict(int)
    errors_by_expected: dict = defaultdict(list)

    for _, r in df.iterrows():
        title = r["title"]
        expected_subtype = r["expected_bucket"]
        scores = score_buckets(title, "")
        pick = pick_bucket(scores)
        predicted_subtype = pick["bucket"]
        expected_class = BUCKET_TO_CLASS.get(expected_subtype, expected_subtype)
        predicted_class = fold_to_class(pick, BUCKET_TO_CLASS)
        pred_rows.append({
            "source": r["source"],
            "doc_code": r["doc_code"],
            "title": title,
            "expected_subtype": expected_subtype,
            "predicted_subtype": predicted_subtype,
            "expected_class": expected_class,
            "predicted_class": predicted_class,
            "bucket_score": pick["score_sum"],
            "bucket_top_weight": pick["score_top"],
            "confidence": pick["confidence"],
            "runner_up": pick["runner_up_bucket"],
            "runner_up_score": pick["runner_up_score"],
        })
        confusion_subtype[(expected_subtype, predicted_subtype)] += 1
        confusion_class[(expected_class, predicted_class)] += 1
        if expected_subtype == predicted_subtype:
            correct_subtype += 1
        if expected_class == predicted_class:
            correct_class += 1
        else:
            errors_by_expected[expected_subtype].append((predicted_subtype, title))

    OUT_PRED.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PRED.open("w", newline="", encoding="utf-8") as f:
        cols = ["source", "doc_code", "title",
                "expected_subtype", "predicted_subtype",
                "expected_class", "predicted_class",
                "bucket_score", "bucket_top_weight", "confidence",
                "runner_up", "runner_up_score"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(pred_rows)

    lines = []
    def L(s=""): lines.append(s)
    L("=" * 78)
    L(f"Corpus evaluation: {n} rows")
    L("-" * 78)
    L(f"  Class accuracy   (Drawings/Documents): {correct_class/n:.4f}  ({correct_class}/{n})")
    L(f"  Subtype accuracy (10 buckets):         {correct_subtype/n:.4f}  ({correct_subtype}/{n})")
    L("=" * 78)
    L()

    L("Class confusion matrix (rows=expected, cols=predicted):")
    classes = sorted({c for pair in confusion_class for c in pair})
    header = "  " + " ".join(f"{c:>10s}" for c in classes)
    L(header)
    for er in classes:
        row = f"  {er:8s} " + " ".join(f"{confusion_class[(er, ec)]:>10d}" for ec in classes)
        L(row)
    L()

    L("Per-subtype recall (rows where expected = X, % correctly predicted):")
    expected_counts = Counter(df["expected_bucket"])
    for b, total in expected_counts.most_common():
        right = confusion_subtype[(b, b)]
        L(f"  {b:18s} {right}/{total}  ({100*right/total:.1f}%)")
    L()

    L("Top 30 subtype confusion pairs (expected -> predicted, where they differ):")
    errs = [(k, v) for k, v in confusion_subtype.items() if k[0] != k[1]]
    errs.sort(key=lambda x: -x[1])
    for (e, p), c in errs[:30]:
        L(f"  {c:>6}  {e:18s} -> {p}")
    L()

    err_counts_by_expected = Counter()
    for (e, p), c in errs:
        err_counts_by_expected[e] += c
    L("Sample mispredictions per expected subtype (max 12 per bucket):")
    for b, _ in err_counts_by_expected.most_common():
        rows = errors_by_expected[b]
        seen = set()
        sample = []
        for pred, title in rows:
            if title in seen:
                continue
            seen.add(title)
            sample.append((pred, title))
            if len(sample) >= 12:
                break
        L(f"\n--- expected subtype = {b} ({err_counts_by_expected[b]} errors total) ---")
        for pred, title in sample:
            L(f"  pred={pred:18s} | {title[:130]}")
    L()

    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:20]))
    print(f"\n... full report at {OUT_REPORT}")
    print(f"per-row predictions at {OUT_PRED}")


if __name__ == "__main__":
    main()
