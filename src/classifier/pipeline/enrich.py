"""Phase-1 enrichment pipeline: walk transmittal records, classify each one."""
from __future__ import annotations

from collections import Counter, defaultdict

from classifier.config.buckets import BUCKET_PRIMARY_CODE, TYPE_TO_BUCKET
from classifier.core.discipline import (
    build_seg2_discipline_map,
    derive_discipline,
)
from classifier.core.extraction import extract_ref, extract_revs, inherit_rev_from_siblings
from classifier.core.form import (
    is_cover_filename,
    is_crs_filename,
    resolve_form_post,
    resolve_form_pre,
)
from classifier.core.normalisation import normalise_filename
from classifier.core.revisions import (
    assign_bundle_id,
    classify_revision_drift,
    compute_is_latest_for_group,
)
from classifier.core.scoring import pick_bucket, score_buckets
from classifier.core.targets import build_target_paths, detect_target_collisions
from classifier.io.dossier_reader import load_dossier
from classifier.io.overrides_reader import load_overrides
from classifier.io.schedule_reader import load_schedule
from classifier.io.transmittals import parse_transmittals


def enrich_files(*, schedule_path, dossier_path, tree_path,
                 overrides_path) -> list:
    """Run the full Phase-1 pipeline. Returns list of populated row dicts."""
    schedule_df = load_schedule(schedule_path)
    dossier_df = load_dossier(dossier_path)
    raw = parse_transmittals(tree_path)
    overrides = load_overrides(overrides_path)

    schedule_disc = {r["cust_ref"]: r["discipline"] for _, r in schedule_df.iterrows()}
    schedule_rev = {r["cust_ref"]: r["schedule_rev"] for _, r in schedule_df.iterrows()}
    schedule_title = {r["cust_ref"]: r["title"] for _, r in schedule_df.iterrows()}
    schedule_pcs = {r["cust_ref"]: r["pcs_doc_no"] for _, r in schedule_df.iterrows()}
    seg2_map = build_seg2_discipline_map(schedule_df)
    dossier_by_doc = {r["doc_no"]: r for _, r in dossier_df.iterrows()}

    # Pass 1: per-record extraction
    rows: list = []
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

    # Pass 2: sibling rev inheritance
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
            r["notes"] = (r["notes"] + (" | " if r["notes"] else "")
                          + "rev_inherited_from_sibling").strip()

    # Per-submission discipline majority
    sub_disciplines = defaultdict(list)
    for r in rows:
        if r["cust_ref"] and r["cust_ref"] in schedule_disc:
            sub_disciplines[r["submission_folder"]].append(schedule_disc[r["cust_ref"]])
    sub_majority: dict = {}
    multi_disc: dict = {}
    for sub, ds in sub_disciplines.items():
        c = Counter(ds)
        sub_majority[sub] = c.most_common(1)[0][0] if c else ""
        multi_disc[sub] = len(c) > 2

    # Pass 3: classify
    for r in rows:
        norm = r.pop("_norm_filename")
        cust_ref = r["cust_ref"]
        title = schedule_title.get(cust_ref, "")
        type_code_dossier = ""
        if cust_ref in dossier_by_doc:
            if not title:
                title = dossier_by_doc[cust_ref]["title"]
            type_code_dossier = dossier_by_doc[cust_ref]["type_code"]
        r["title"] = title
        r["pcs_doc_no"] = schedule_pcs.get(cust_ref, "")
        r["schedule_rev"] = schedule_rev.get(cust_ref, "")

        if cust_ref and cust_ref in overrides:
            bucket = overrides[cust_ref]
            bucket_source = "override"
            confidence = "high"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif r["is_archive"]:
            bucket = "Documents"
            bucket_source = "archive"
            confidence = "low"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif r["is_transmittal_cover"]:
            bucket = "Documents"
            bucket_source = "cover_sheet"
            confidence = "low"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif r["is_crs"]:
            bucket = "CRS"
            bucket_source = "crs_pin"
            confidence = "high"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        elif type_code_dossier and type_code_dossier in TYPE_TO_BUCKET:
            bucket = TYPE_TO_BUCKET[type_code_dossier]
            bucket_source = "dossier_type"
            confidence = "high"
            score_sum = score_top = 0
            runner_up, runner_score = "", 0
        else:
            scores = score_buckets(title, norm)
            picked = pick_bucket(scores)
            bucket = picked["bucket"]
            bucket_source = "weighted" if picked["score_sum"] > 0 else "fallback"
            confidence = picked["confidence"]
            score_sum, score_top = picked["score_sum"], picked["score_top"]
            runner_up = picked["runner_up_bucket"]
            runner_score = picked["runner_up_score"]

        r["type_bucket"] = bucket
        r["bucket_source"] = bucket_source
        r["bucket_confidence"] = confidence
        r["bucket_score"] = score_sum
        r["runner_up_bucket"] = runner_up
        r["runner_up_score"] = runner_score

        pre = resolve_form_pre(norm, has_ref=bool(cust_ref))
        r["form"] = pre if pre else resolve_form_post(norm, bucket)

        r["type_code"] = type_code_dossier or BUCKET_PRIMARY_CODE[bucket]

        sub = r["submission_folder"]
        r["discipline"] = derive_discipline(
            cust_ref=cust_ref, title=title, filename=norm,
            schedule_lookup=schedule_disc, seg2_map=seg2_map,
            submission_majority=sub_majority.get(sub, ""),
            multi_disc_submission=multi_disc.get(sub, False),
        )

        r["bundle_id"] = assign_bundle_id(cust_ref, r["letter_rev"],
                                          r["numeric_rev"], sub)

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

    # Pass 4: is_latest per ref
    by_ref = defaultdict(list)
    for r in rows:
        if r["cust_ref"]:
            by_ref[r["cust_ref"]].append(r)
    for group in by_ref.values():
        compute_is_latest_for_group(group)
    for r in rows:
        if not r["cust_ref"]:
            r.setdefault("is_latest_letter", False)
            r.setdefault("is_latest_numeric", False)
            r.setdefault("is_latest", False)

    # Pass 5: revision drift
    for r in rows:
        r["revision_drift"] = classify_revision_drift(
            file_letter=r["letter_rev"], file_numeric=r["numeric_rev"],
            schedule_rev=r["schedule_rev"],
        )

    # Pass 6: target paths
    for r in rows:
        tp = build_target_paths(
            cust_ref=r["cust_ref"], letter_rev=r["letter_rev"],
            numeric_rev=r["numeric_rev"], type_code=r["type_code"],
            form=r["form"], bucket=r["type_bucket"], discipline=r["discipline"],
            title=r["title"], extension=r["extension"],
            submission_folder=r["submission_folder"],
            source_filename=r["source_filename"],
        )
        r.update(tp)

    # Pass 7: collisions
    detect_target_collisions(rows)

    # Pass 8: deterministic sort - by source_path. This makes CSV output stable
    # across runs regardless of upstream parse-order changes (idempotency).
    rows.sort(key=lambda r: r.get("source_path", ""))

    return rows
