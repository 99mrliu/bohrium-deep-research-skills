#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_semantic_diff.py — compare the claims table (claims.json) against the
re-parsed figure graph (figure_graph.json). This is the core
claims-vs-figure consistency auditor.

Checks (severity in brackets):
  entity.missing          claims entity absent from figure          [error]
  entity.extra            figure entity not in claims               [warning]
  entity.label_mismatch   figure label differs from claims label    [error]
  entity.label_not_in_text  label not among <text> strings          [error]
  entity.compartment_mismatch                                        [warning]
  edge.missing            claims edge absent from figure            [error]
  edge.extra              figure edge not in claims                 [warning]
  edge.direction_reversed from/to exactly swapped                   [error]
  edge.endpoint_mismatch  from/to wrong (not a clean swap)          [error]
  edge.kind_mismatch      e.g. inhibits drawn as activates          [error]
  edge.evidence_mismatch  confirmed vs uncertain                    [warning]
  edge.endpoints_unreadable  no data-from/to; direction unchecked   [warning]
  legend.missing_item     claims legend item absent from legend     [error]
  legend.extra_item       legend item with no claims entry          [warning]
  legend.meaning_not_in_text  meaning string absent from <text>s    [warning]
  expected_label.missing  claims.expected_labels entry not rendered [error]

Every violation carries the claim's source locator so fixes can be traced
back to the paper/data. Violations are NEVER silently dropped.

Usage:
  audit_semantic_diff.py --claims claims.json --graph figure_graph.json \
      --out violations.json
Exit 0 always (results live in the JSON); non-zero only on bad input.
"""

import argparse
import json
import os
import sys


def viol(check, severity, detail, element=None, source=None):
    return {"auditor": "semantic_diff", "check": check, "severity": severity,
            "detail": detail, "element": element, "source": source}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.claims, encoding="utf-8") as fh:
        claims = json.load(fh)
    with open(args.graph, encoding="utf-8") as fh:
        graph = json.load(fh)

    violations, skipped = [], []
    fig_entities = {e["id"]: e for e in graph.get("entities", [])}
    fig_edges = {e["id"]: e for e in graph.get("edges", [])}
    fig_legend = {l["item"]: l for l in graph.get("legend", [])}
    texts = set(graph.get("texts", []))
    texts_joined = "\n".join(graph.get("texts", []))

    # ---- entities ------------------------------------------------------
    claim_ids = set()
    for ce in claims.get("entities", []):
        cid = ce.get("id")
        claim_ids.add(cid)
        fe = fig_entities.get(cid)
        if fe is None:
            violations.append(viol(
                "entity.missing", "error",
                "claims entity '%s' (%s) not found in figure" % (
                    cid, ce.get("label")),
                element=cid, source=ce.get("source")))
            continue
        label = ce.get("label")
        if label and fe.get("label") and fe["label"] != label:
            violations.append(viol(
                "entity.label_mismatch", "error",
                "entity '%s': claims label '%s' vs figure label '%s'" % (
                    cid, label, fe["label"]),
                element=cid, source=ce.get("source")))
        if label and label not in texts:
            violations.append(viol(
                "entity.label_not_in_text", "error",
                "entity '%s' label '%s' absent from SVG <text> strings" % (
                    cid, label),
                element=cid, source=ce.get("source")))
        if ce.get("type") and fe.get("type") and ce["type"] != fe["type"]:
            violations.append(viol(
                "entity.type_mismatch", "warning",
                "entity '%s': claims type '%s' vs figure type '%s'" % (
                    cid, ce["type"], fe["type"]),
                element=cid, source=ce.get("source")))
        if ce.get("compartment") and fe.get("compartment") \
                and ce["compartment"] != fe["compartment"]:
            violations.append(viol(
                "entity.compartment_mismatch", "warning",
                "entity '%s': claims compartment '%s' vs figure '%s'" % (
                    cid, ce["compartment"], fe["compartment"]),
                element=cid, source=ce.get("source")))
    for fid in fig_entities:
        if fid not in claim_ids:
            violations.append(viol(
                "entity.extra", "warning",
                "figure contains entity '%s' with no claims entry" % fid,
                element=fid))

    # ---- edges ---------------------------------------------------------
    claim_edge_ids = set()
    for ce in claims.get("edges", []):
        eid = ce.get("id")
        claim_edge_ids.add(eid)
        fe = fig_edges.get(eid)
        if fe is None:
            violations.append(viol(
                "edge.missing", "error",
                "claims edge '%s' (%s->%s, %s) not found in figure" % (
                    eid, ce.get("from"), ce.get("to"), ce.get("kind")),
                element=eid, source=ce.get("source")))
            continue
        if not fe.get("endpoints_machine_readable", True):
            violations.append(viol(
                "edge.endpoints_unreadable", "warning",
                "edge '%s' lacks data-from/data-to; direction could not be "
                "verified" % eid, element=eid, source=ce.get("source")))
        else:
            if fe["from"] == ce.get("to") and fe["to"] == ce.get("from"):
                violations.append(viol(
                    "edge.direction_reversed", "error",
                    "edge '%s' direction reversed: claims %s->%s, figure "
                    "draws %s->%s" % (eid, ce.get("from"), ce.get("to"),
                                      fe["from"], fe["to"]),
                    element=eid, source=ce.get("source")))
            elif fe["from"] != ce.get("from") or fe["to"] != ce.get("to"):
                violations.append(viol(
                    "edge.endpoint_mismatch", "error",
                    "edge '%s' endpoints: claims %s->%s, figure %s->%s" % (
                        eid, ce.get("from"), ce.get("to"),
                        fe["from"], fe["to"]),
                    element=eid, source=ce.get("source")))
        if ce.get("kind") and fe.get("kind") and ce["kind"] != fe["kind"]:
            violations.append(viol(
                "edge.kind_mismatch", "error",
                "edge '%s' kind: claims '%s' vs figure '%s'" % (
                    eid, ce["kind"], fe["kind"]),
                element=eid, source=ce.get("source")))
            if fe.get("kind_inferred"):
                violations.append(viol(
                    "edge.kind_inferred", "warning",
                    "edge '%s' kind was inferred from markers (no "
                    "data-edge-kind attribute)" % eid,
                    element=eid, source=ce.get("source")))
        if ce.get("evidence") and fe.get("evidence") \
                and ce["evidence"] != fe["evidence"]:
            violations.append(viol(
                "edge.evidence_mismatch", "warning",
                "edge '%s' evidence: claims '%s' vs figure '%s'" % (
                    eid, ce["evidence"], fe["evidence"]),
                element=eid, source=ce.get("source")))
        badge_expect = {"phosphorylates": "P", "ubiquitinates": "Ub"}.get(
            ce.get("kind"))
        if badge_expect and fe.get("badge") != badge_expect:
            violations.append(viol(
                "edge.badge_missing", "warning",
                "edge '%s' kind '%s' should carry badge '%s'" % (
                    eid, ce.get("kind"), badge_expect),
                element=eid, source=ce.get("source")))
    for fid in fig_edges:
        if fid not in claim_edge_ids:
            violations.append(viol(
                "edge.extra", "warning",
                "figure contains edge '%s' with no claims entry" % fid,
                element=fid))

    # ---- legend --------------------------------------------------------
    for li in claims.get("legend", []):
        item = li.get("item")
        fl = fig_legend.get(item)
        if fl is None:
            violations.append(viol(
                "legend.missing_item", "error",
                "claims legend item '%s' (%s) absent from figure legend" % (
                    item, li.get("meaning")),
                element=item))
            continue
        meaning = li.get("meaning")
        if meaning and meaning not in texts_joined:
            violations.append(viol(
                "legend.meaning_not_in_text", "warning",
                "legend item '%s' meaning '%s' not found among SVG texts"
                % (item, meaning), element=item))
    for fitem in fig_legend:
        if fitem not in {l.get("item") for l in claims.get("legend", [])}:
            violations.append(viol(
                "legend.extra_item", "warning",
                "figure legend item '%s' has no claims legend entry" % fitem,
                element=fitem))

    # ---- expected labels ----------------------------------------------
    for lab in claims.get("expected_labels", []):
        if lab not in texts and lab not in texts_joined:
            violations.append(viol(
                "expected_label.missing", "error",
                "expected label '%s' not rendered anywhere in the figure"
                % lab, element=lab))

    result = {"auditor": "semantic_diff", "violations": violations,
              "skipped": skipped}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    errs = sum(1 for v in violations if v["severity"] == "error")
    print("semantic_diff: %d errors, %d warnings" % (
        errs, len(violations) - errs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
