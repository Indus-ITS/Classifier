"""Leave-one-out evaluation of the type-keyword classifier.

For each training row R:
  * Re-learn rules from all training rows except R.
  * Score R's title against the leave-one-out rules.
  * Compare picked type to R's true type.

Prints:
  * Per-class precision / recall / coverage for classes with rules.
  * Overall confusion matrix (top mistaken pairings).
  * The new end-to-end ``classify`` summary for context.

Not an entry point. Run with::

    .venv/Scripts/python scripts/eval_type_keywords.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from classifier.core.type_scoring import (
    MIN_SCORE,
    candidate_phrases,
    canonicalize_title,
    pick_type,
)
from classifier.tools.learn_type_keywords import _collect_rows, learn


def _score_with_rules(title: str,
                       rules: dict[str, tuple[tuple[str, float], ...]]
                       ) -> dict[str, tuple[float, int]]:
    """Mirror of score_types but against an explicitly-provided rules dict.

    Mirrors the per-type longest-match span consumption used by
    ``classifier.core.type_scoring.score_types`` and returns the same
    ``(score, n_phrases)`` tuple shape.
    """
    tokens = canonicalize_title(title)
    if not tokens:
        return {}
    scores: dict[str, tuple[float, int]] = {}
    for type_code, type_rules in rules.items():
        consumed: list[tuple[int, int]] = []
        total = 0.0
        n_phrases = 0
        for phrase_text, weight in type_rules:
            phrase = phrase_text.split(" ")
            if not phrase or len(phrase) > len(tokens):
                continue
            found = -1
            for i in range(len(tokens) - len(phrase) + 1):
                if all(tokens[i + j] == phrase[j] for j in range(len(phrase))):
                    found = i
                    break
            if found < 0:
                continue
            end = found + len(phrase)
            if any(not (end <= cs or found >= ce) for cs, ce in consumed):
                continue
            consumed.append((found, end))
            total += weight
            n_phrases += 1
        if total > 0:
            scores[type_code] = (total, n_phrases)
    return scores


def main() -> None:
    rows = _collect_rows()
    print(f"loaded {len(rows)} training rows")

    # Precompute tokenization once.
    tokenized = [(t, title, canonicalize_title(title)) for t, title, _ in rows]

    # Per-class counters
    n_class: Counter[str] = Counter(t for t, _, _ in rows)
    tp: Counter[str] = Counter()          # picked == true (high confidence)
    picked_high: Counter[str] = Counter() # picked anything (high) for class
    confusions: Counter[tuple[str, str]] = Counter()
    coverage_class: defaultdict[str, list[bool]] = defaultdict(list)

    for i, (true_type, _, _) in enumerate(rows):
        loo = rows[:i] + rows[i+1:]
        rules, _, _ = learn(loo)
        title = rows[i][1]
        scores = _score_with_rules(title, rules)
        pick = pick_type(scores)
        if pick["confidence"] == "high":
            picked_high[pick["type"]] += 1
            coverage_class[true_type].append(True)
            if pick["type"] == true_type:
                tp[true_type] += 1
            else:
                confusions[(true_type, pick["type"])] += 1
        else:
            coverage_class[true_type].append(False)

    print()
    print(f"{'type':5s} {'support':>7s} {'prec':>6s} {'recall':>7s} {'cover':>6s}")
    for t in sorted(n_class):
        support = n_class[t]
        prec_denom = picked_high[t]
        prec = (tp[t] / prec_denom) if prec_denom else float("nan")
        rec = tp[t] / support if support else 0.0
        cov_list = coverage_class.get(t, [])
        cov = sum(cov_list) / len(cov_list) if cov_list else 0.0
        prec_str = f"{prec:6.2%}" if prec_denom else "  n/a "
        print(f"{t:5s} {support:>7d} {prec_str} {rec:>6.2%} {cov:>5.1%}")

    total_high = sum(picked_high.values())
    total_tp = sum(tp.values())
    overall_prec = (total_tp / total_high) if total_high else 0.0
    overall_cov = total_high / len(rows)
    print()
    print(f"overall: high-confidence picks = {total_high} / {len(rows)} "
          f"(coverage {overall_cov:.1%})")
    print(f"overall precision (high-confidence only): {overall_prec:.1%}")
    print(f"MIN_SCORE={MIN_SCORE}; one-off classes (< 4 rows) excluded from rules.")

    if confusions:
        print()
        print("top 10 (true -> picked) misclassifications:")
        for (true_t, picked_t), n in confusions.most_common(10):
            print(f"  {true_t:5s} -> {picked_t:5s}  x{n}")


if __name__ == "__main__":
    main()
