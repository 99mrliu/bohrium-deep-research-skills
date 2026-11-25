#!/usr/bin/env python3
"""render_qc.py — reconciliation gate for rendered deliverables.

Parses deliverable.md and preview.html BACK (regex over [[anchor]] tags and
data-anchor attributes) and reconciles them against blocks.jsonl +
anchor_map.json:

  * every input block id has exactly one anchor in anchor_map
  * every anchor appears exactly once in deliverable.md
  * every anchor appears exactly once in preview.html
  * counts reconcile: blocks == anchors == md == html
  * no anchor in any artifact that is not in anchor_map

Emits:
  render_qc.json : status pass|fail, counts, missing/extra/duplicated per
                   artifact, warnings (e.g. blocks with bbox=null rendered
                   anyway — a warning, never a crash).
  result.json    : contract-aware summary. --case points to case.json; its
                   case_id and every output_contract field are echoed. A
                   field whose artifact is missing is set to
                   {"value": null, "explanation": "..."} — never invented.
                   QC fail => result status "failed" with a handoff note;
                   never a silent pass.

Exit code: 0 on pass, 3 on QC fail, 2 on IO/usage errors.
Deterministic: no timestamps. Python 3 stdlib only.
"""
import argparse
import json
import os
import re
import sys

MD_ANCHOR_RE = re.compile(r"\[\[(p\d+-b\d+)\]\]")
HTML_ANCHOR_RE = re.compile(r'data-anchor="(p\d+-b\d+)"')


def count_anchors(path, rx):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    counts = {}
    for m in rx.findall(text):
        counts[m] = counts.get(m, 0) + 1
    return counts


def diff(expected, found_counts):
    """missing: in expected, absent from found; duplicated: found > 1;
    extra: in found, not in expected."""
    exp = set(expected)
    got = set(found_counts)
    return {
        "missing": sorted(exp - got),
        "duplicated": sorted(a for a, n in found_counts.items()
                             if n > 1 and a in exp),
        "extra": sorted(got - exp),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Reconcile rendered deliverables against anchored blocks")
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--anchor-map", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--html", required=True)
    ap.add_argument("--case", required=True,
                    help="path to case.json (case_id + output_contract)")
    ap.add_argument("--out-qc", required=True)
    ap.add_argument("--out-result", required=True)
    ap.add_argument("--outdir", required=True,
                    help="directory that output_contract paths are relative to")
    args = ap.parse_args()

    # ---- load inputs -----------------------------------------------------
    try:
        blocks = [json.loads(l) for l in open(args.blocks, encoding="utf-8")
                  if l.strip()]
        with open(args.anchor_map, encoding="utf-8") as f:
            anchor_map = json.load(f)
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("error: cannot load inputs: %s\n" % e)
        return 2

    case_id = case.get("case_id", "unknown-case")
    contract = case.get("output_contract", {}) or {}

    entries = anchor_map.get("anchors", [])
    anchor_of_block = {e["block_id"]: e["anchor"] for e in entries}
    expected = [e["anchor"] for e in entries]
    expected_set = set(expected)

    problems = []
    warnings = []

    # ---- check 1: upstream schema must have been valid -------------------
    if not anchor_map.get("schema_valid", False):
        problems.append("anchor_map.schema_valid is false: %s"
                        % "; ".join(anchor_map.get("schema_errors", [])))

    # ---- check 2: anchor_map covers every input block id exactly once ----
    block_ids = [b.get("id") for b in blocks]
    uncovered = [b for b in block_ids if b not in anchor_of_block]
    if uncovered:
        problems.append("%d block id(s) not covered by anchor_map: %s"
                        % (len(uncovered), ", ".join(map(str, uncovered))))
    if len(anchor_of_block) != len(entries):
        problems.append("anchor_map contains duplicated block ids")

    # ---- checks 3-5: reconcile anchors inside both artifacts -------------
    try:
        md_counts = count_anchors(args.md, MD_ANCHOR_RE)
    except OSError as e:
        sys.stderr.write("error: cannot read %s: %s\n" % (args.md, e))
        return 2
    try:
        html_counts = count_anchors(args.html, HTML_ANCHOR_RE)
    except OSError as e:
        sys.stderr.write("error: cannot read %s: %s\n" % (args.html, e))
        return 2

    md_diff = diff(expected_set, md_counts)
    html_diff = diff(expected_set, html_counts)
    for name, d in (("deliverable.md", md_diff), ("preview.html", html_diff)):
        for key in ("missing", "duplicated", "extra"):
            if d[key]:
                problems.append("%s: %d %s anchor(s): %s"
                                % (name, len(d[key]), key,
                                   ", ".join(d[key][:20])))

    # ---- check 6: counts reconcile ---------------------------------------
    counts = {
        "blocks_in": len(blocks),
        "anchors_in_map": len(entries),
        "anchors_in_md": sum(md_counts.values()),
        "anchors_in_html": sum(html_counts.values()),
    }
    if not (counts["blocks_in"] == counts["anchors_in_map"]
            == counts["anchors_in_md"] == counts["anchors_in_html"]):
        problems.append("block/anchor counts do not reconcile: %s"
                        % json.dumps(counts, sort_keys=True))

    # ---- warnings (never fatal) -------------------------------------------
    nobbox = [e["anchor"] for e in entries if e.get("bbox") is None]
    if nobbox:
        warnings.append("%d block(s) have bbox=null and were rendered without "
                        "coordinates (title/meta show 'bbox: n/a'): %s"
                        % (len(nobbox), ", ".join(nobbox)))
    unres = [e["anchor"] for e in entries if e.get("kind") == "unresolved"]
    if unres:
        warnings.append("%d unresolved block(s) kept and highlighted: %s"
                        % (len(unres), ", ".join(unres)))

    status = "pass" if not problems else "fail"

    qc = {
        "case_id": case_id,
        "status": status,
        "counts": counts,
        "zero_silent_drops": status == "pass",
        "checks": {
            "anchor_map_schema_valid": bool(anchor_map.get("schema_valid",
                                                           False)),
            "anchor_map_covers_all_blocks": not uncovered,
            "deliverable_md": md_diff,
            "preview_html": html_diff,
        },
        "problems": problems,
        "warnings": warnings,
        "handoff": (None if status == "pass" else
                    "Reconciliation failed: some parsed blocks are missing, "
                    "duplicated, or unexpected in the rendered deliverables. "
                    "Hand back to the upstream parse/render step; do NOT ship "
                    "these deliverables."),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out_qc)), exist_ok=True)
    with open(args.out_qc, "w", encoding="utf-8") as f:
        json.dump(qc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---- contract-aware result.json ---------------------------------------
    artifact_paths = {
        "deliverable_md": args.md,
        "preview_html": args.html,
        "anchor_map": args.anchor_map,
        "render_qc": args.out_qc,
    }
    result = {"case_id": case_id}
    if status == "fail":
        result["status"] = "failed"
    elif warnings:
        result["status"] = "success"  # rendered fully; warnings disclosed below
    else:
        result["status"] = "success"

    for field in contract:
        if field == "uncertainty":
            result[field] = warnings if warnings else []
            continue
        path = artifact_paths.get(field)
        rel = None
        if path:
            try:
                rel = os.path.relpath(path, args.outdir)
            except ValueError:
                rel = path
        if path and os.path.isfile(path) and status != "fail":
            result[field] = rel
        elif path and os.path.isfile(path) and status == "fail":
            result[field] = {"value": rel,
                             "explanation": "artifact exists but QC failed; "
                                            "do not consume it"}
        else:
            result[field] = {"value": None,
                             "explanation": "artifact %r was not produced"
                                            % (path or field)}

    result["sources"] = [
        os.path.basename(args.blocks),
        os.path.basename(args.anchor_map),
    ]
    result["uncertainty_note"] = (
        "Synthetic example: all blocks were fabricated for this bundle; "
        "warnings list blocks rendered with incomplete geometry."
        if warnings else "No unresolved rendering risks detected.")
    result["change_record"] = [
        "anchor_map.py: validated blocks.jsonl schema, assigned stable "
        "p{page}-b{seq} anchors",
        "render_preview.py: rendered deliverable.md (anchors inline, "
        "header/footer appendix) and self-contained preview.html",
        "render_qc.py: parsed both artifacts back, reconciled anchors "
        "(%s)" % status,
    ]
    if status == "fail":
        result["handoff"] = qc["handoff"]

    with open(args.out_result, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    sys.stdout.write("qc %s: blocks=%d md=%d html=%d problems=%d warnings=%d\n"
                     % (status, counts["blocks_in"], counts["anchors_in_md"],
                        counts["anchors_in_html"], len(problems),
                        len(warnings)))
    return 0 if status == "pass" else 3


if __name__ == "__main__":
    sys.exit(main())
