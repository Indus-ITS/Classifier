"""Write the audit text report alongside the classified CSV."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path


def write_audit(*, rows: list, schedule_df, path) -> None:
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

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
