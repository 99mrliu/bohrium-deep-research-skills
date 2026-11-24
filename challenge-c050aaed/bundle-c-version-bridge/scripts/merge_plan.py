#!/usr/bin/env python3
"""merge_plan.py -- explicit, non-destructive merge plan per document cluster.

For each cluster in the version graph this emits: the canonical file, the
duplicates to ALIAS (never delete), migrated/shifted/orphaned/native
annotation counts, and a conflict queue: annotations coming from different
versions whose anchored_text lands on the SAME canonical page region
(500-char buckets) while their contents disagree. Conflicts are grouped for
human review; nothing is auto-resolved.

--read-only RELPATH may be repeated to list files the case rules say must be
kept untouched (read-only inputs); they are recorded in the plan.

"requires_human_review" collects conflicts, shifted, orphaned and error
annotations. When it is empty the plan is fully automatic
("fully_automatic": true).

Deterministic: stable sorts, no wall-clock. Exit codes: 0 ok,
2 usage/input error, 3 degraded (migration report contained error records).
"""
import argparse
import json
import sys

SCHEMA = "version-bridge/merge_plan@1"
GENERATOR = "merge_plan.py 1.0.0"
REGION_SIZE = 500
ALIAS_POLICY = ("alias only: non-canonical members stay on disk untouched and "
                "are recorded as aliases of the canonical file; input files "
                "are never deleted, moved or overwritten")


def eprint(*a):
    print(*a, file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Produce a non-destructive merge plan per cluster from a "
                    "version graph and a migration report.")
    ap.add_argument("--graph", required=True, help="version_graph.json")
    ap.add_argument("--migration", required=True,
                    help="migration_report.jsonl")
    ap.add_argument("--out", required=True, help="output merge_plan.json")
    ap.add_argument("--read-only", action="append", default=[],
                    metavar="RELPATH",
                    help="file the case rules mark read-only (repeatable)")
    args = ap.parse_args(argv)

    try:
        with open(args.graph, encoding="utf-8") as fh:
            graph = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        eprint(f"error: cannot read graph: {exc}")
        return 2
    try:
        recs = []
        with open(args.migration, encoding="utf-8") as fh:
            for ln, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    eprint(f"error: migration line {ln}: {exc}")
                    return 2
    except OSError as exc:
        eprint(f"error: cannot read migration report: {exc}")
        return 2

    clusters = graph.get("clusters", [])
    file_to_cluster = {}
    for c in clusters:
        for m in c["members"]:
            file_to_cluster[m] = c["cluster_id"]

    recs_by_cluster = {}
    outside_graph = 0
    had_error = False
    for r in recs:
        src = (r.get("source") or {}).get("file")
        cid = file_to_cluster.get(src)
        if cid is None:
            outside_graph += 1
            continue
        recs_by_cluster.setdefault(cid, []).append(r)
        if r.get("status") == "error":
            had_error = True

    review = []
    out_clusters = []
    canonical_rule = None
    for c in sorted(clusters, key=lambda x: x["cluster_id"]):
        cid = c["cluster_id"]
        canonical_rule = c.get("canonical_rule", canonical_rule)
        members = sorted(c["members"])
        aliases = [m for m in members if m != c["canonical"]]
        crecs = sorted(recs_by_cluster.get(cid, []),
                       key=lambda r: str(r.get("annotation_id", "")))

        counts = {}
        for r in crecs:
            s = r.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1

        # conflict queue: same canonical page region, different source
        # versions, disagreeing contents
        regions = {}
        for r in crecs:
            t = r.get("target")
            if (r.get("status") in ("migrated", "shifted", "native")
                    and isinstance(t, dict) and t.get("page") is not None):
                start = t.get("char_start")
                ridx = (start // REGION_SIZE) if isinstance(start, int) else 0
                regions.setdefault((t["page"], ridx), []).append(r)
        conflicts = []
        for key in sorted(regions, key=lambda k: (str(k[0]), k[1])):
            group = sorted(regions[key],
                           key=lambda r: str(r.get("annotation_id", "")))
            # Within one region bucket, keep only annotations whose target
            # char spans actually overlap (transitively); a region is coarse,
            # overlapping spans are what really collide.
            comps = []  # list of [span_lo, span_hi, [records]]
            for r in sorted(group, key=lambda r: (
                    (r.get("target") or {}).get("char_start") or 0)):
                t = r.get("target") or {}
                lo = t.get("char_start")
                hi = t.get("char_end")
                if not isinstance(lo, int) or not isinstance(hi, int):
                    lo, hi = 0, REGION_SIZE  # unknown span: whole region
                for comp in comps:
                    if lo < comp[1] and comp[0] < hi:  # overlap
                        comp[0] = min(comp[0], lo)
                        comp[1] = max(comp[1], hi)
                        comp[2].append(r)
                        break
                else:
                    comps.append([lo, hi, [r]])
            for span_lo, span_hi, members in comps:
                files = {r["source"]["file"] for r in members}
                contents = {str(r.get("annotation_id")): r.get("contents")
                            for r in members}
                if len(files) >= 2 and len(set(contents.values())) >= 2:
                    page, ridx = key
                    entry = {
                        "canonical_page": page,
                        "region_index": ridx,
                        "region_char_span": [ridx * REGION_SIZE,
                                             (ridx + 1) * REGION_SIZE],
                        "overlap_char_span": [span_lo, span_hi],
                        "annotations": [
                            {"annotation_id": r["annotation_id"],
                             "source_file": r["source"]["file"],
                             "contents": r.get("contents")}
                            for r in sorted(
                                members,
                                key=lambda r: str(r.get("annotation_id", "")))],
                        "reason": ("annotations from different versions land "
                                   "on overlapping spans of the same "
                                   "canonical page region with disagreeing "
                                   "contents; grouped for human review, no "
                                   "auto-resolution"),
                    }
                    conflicts.append(entry)
                    review.append({
                        "kind": "conflict",
                        "cluster_id": cid,
                        "annotation_ids": [a["annotation_id"]
                                           for a in entry["annotations"]],
                        "reason": entry["reason"],
                    })

        for r in crecs:
            aid = str(r.get("annotation_id", ""))
            st = r.get("status")
            if st == "shifted":
                review.append({"kind": "shifted", "cluster_id": cid,
                               "annotation_ids": [aid],
                               "reason": "alignment ratio in [0.7, 0.9); "
                                         "placement on the canonical version "
                                         "is uncertain"})
            elif st == "orphaned":
                review.append({"kind": "orphaned", "cluster_id": cid,
                               "annotation_ids": [aid],
                               "reason": "no acceptable match on the canonical "
                                         "version; kept on the source version"})
            elif st == "error":
                review.append({"kind": "error", "cluster_id": cid,
                               "annotation_ids": [aid],
                               "reason": r.get("note", "processing error")})

        out_clusters.append({
            "cluster_id": cid,
            "canonical": c["canonical"],
            "aliases": aliases,
            "alias_policy": ALIAS_POLICY,
            "annotation_counts": counts,
            "conflict_queue": conflicts,
        })

    review.sort(key=lambda e: (e["kind"], e["cluster_id"],
                               [str(x) for x in e["annotation_ids"]]))
    plan = {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "policy": {
            "deletion": ALIAS_POLICY,
            "conflict_resolution": "none automatic; conflicts are grouped for "
                                   "human review",
            "region_size_chars": REGION_SIZE,
            "canonical_rule": canonical_rule,
        },
        "read_only": sorted(set(args.read_only)),
        "clusters": out_clusters,
        "annotations_outside_graph": outside_graph,
        "requires_human_review": review,
        "fully_automatic": not review,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        eprint(f"error: cannot write output: {exc}")
        return 2

    eprint(f"merge_plan: {len(out_clusters)} clusters, "
           f"{len(review)} items need human review, "
           f"fully_automatic={plan['fully_automatic']}")
    return 3 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
