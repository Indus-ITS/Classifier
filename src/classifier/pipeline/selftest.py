"""Dossier-driven self-test: title-only classification vs known Type code."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from classifier.config.buckets import TYPE_TO_BUCKET
from classifier.core.scoring import pick_bucket, score_buckets
from classifier.io.dossier_reader import load_dossier


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
