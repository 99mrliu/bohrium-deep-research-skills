#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_loop.py — bounded, journal-keeping repair loop.

The agent reads audit_report.json, writes an ops file (JSON list), and this
driver applies the ops to the SVG (with existence checks), re-runs the
full audit battery via audit_run.py, and appends an entry to
fix_journal.json. At most --max-iters (default 3) iterations; the loop
stops early when zero error-severity violations remain. Remaining
violations are NEVER hidden: the final report path and error count are
printed and written into the journal so they can land in result.json
exceptions.

Supported ops (each applied only if its target exists; otherwise the op
is recorded as failed and the loop continues):
  {"op": "rename-label",        "entity": "<id>", "new_label": "..."}
  {"op": "set-edge-kind",       "edge": "<id>", "kind": "inhibits"}
  {"op": "set-edge-endpoints",  "edge": "<id>", "from": "A", "to": "B"}
  {"op": "swap-edge-direction", "edge": "<id>"}
  {"op": "set-edge-evidence",   "edge": "<id>", "evidence": "uncertain"}
  {"op": "add-legend-item",     "item": "<item>", "meaning": "...",
                                 "color": "#rrggbb"}
  {"op": "remove-legend-item",  "item": "<item>"}
  {"op": "set-fill",            "target": "<svg element id>",
                                 "color": "#rrggbb"}

Usage:
  fix_loop.py --svg figure.svg --claims claims.json --ops ops.json
              --workdir work/fix [--png figure.png] [--pdf figure.pdf]
              [--before-svg before.svg] [--max-iters 3]
Exit 0 if the final audit has zero errors, 1 otherwise.
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_conventions as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# individual ops (return None on success, error string on failure)
# --------------------------------------------------------------------------

def op_rename_label(root, op):
    g = C.find_by_id(root, C.ENTITY_PREFIX + op.get("entity", ""))
    if g is None:
        return "entity '%s' not found" % op.get("entity")
    t = C.find_child_by_class(g, "entity-label", "text")
    if t is None:
        return "entity '%s' has no entity-label text" % op.get("entity")
    t.text = op.get("new_label", "")
    return None


def _edge_group(root, op):
    g = C.find_by_id(root, C.EDGE_PREFIX + op.get("edge", ""))
    return g, (None if g is not None
               else "edge '%s' not found" % op.get("edge"))


def op_set_edge_kind(root, op):
    g, err = _edge_group(root, op)
    if err:
        return err
    kind = op.get("kind")
    if kind not in C.EDGE_KINDS:
        return "unknown edge kind '%s'" % kind
    g.set("data-edge-kind", kind)
    line = C.find_child_by_class(g, "edge-line")
    marker = C.EDGE_MARKERS.get(kind)
    if line is not None:
        if marker:
            line.set("marker-end", "url(#%s)" % marker)
        elif line.get("marker-end"):
            del line.attrib["marker-end"]
        if kind == "inhibits":
            line.set("stroke", "#c0392b")
        else:
            line.set("stroke", "#333333")
    # badge maintenance
    badge_txt = C.find_child_by_class(g, "edge-badge", "text")
    badge_bg = C.find_child_by_class(g, "edge-badge-bg")
    want = C.EDGE_BADGES.get(kind, "")
    if badge_txt is not None and not want:
        g.remove(badge_txt)
        if badge_bg is not None:
            g.remove(badge_bg)
    elif badge_txt is not None:
        badge_txt.text = want
    elif want and line is not None and line.get("x1"):
        mx = (float(line.get("x1")) + float(line.get("x2"))) / 2.0
        my = (float(line.get("y1")) + float(line.get("y2"))) / 2.0
        bg = C.ET.SubElement(g, "circle")
        bg.set("cx", str(mx)); bg.set("cy", str(my)); bg.set("r", "10")
        bg.set("fill", "#ffffff"); bg.set("stroke", "#333333")
        bg.set("class", "edge-badge-bg")
        bt = C.ET.SubElement(g, "text")
        bt.set("x", str(mx)); bt.set("y", str(my + 4))
        bt.set("font-size", "11"); bt.set("text-anchor", "middle")
        bt.set("class", "edge-badge")
        bt.text = want
    return None


def op_set_edge_endpoints(root, op):
    g, err = _edge_group(root, op)
    if err:
        return err
    if not op.get("from") or not op.get("to"):
        return "set-edge-endpoints needs 'from' and 'to'"
    g.set("data-from", op["from"])
    g.set("data-to", op["to"])
    return None


def op_swap_edge_direction(root, op):
    g, err = _edge_group(root, op)
    if err:
        return err
    frm, to = g.get("data-from"), g.get("data-to")
    if not frm or not to:
        return "edge '%s' lacks data-from/data-to" % op.get("edge")
    g.set("data-from", to)
    g.set("data-to", frm)
    line = C.find_child_by_class(g, "edge-line")
    if line is not None and C.localname(line.tag) == "line":
        C.swap_line_endpoints(line)
    return None


def op_set_edge_evidence(root, op):
    g, err = _edge_group(root, op)
    if err:
        return err
    ev = op.get("evidence")
    if ev not in C.EVIDENCE_VALUES:
        return "unknown evidence '%s'" % ev
    g.set("data-evidence", ev)
    line = C.find_child_by_class(g, "edge-line")
    if line is not None:
        if ev == "uncertain":
            line.set("stroke-dasharray", C.UNCERTAIN_DASH)
        elif line.get("stroke-dasharray"):
            del line.attrib["stroke-dasharray"]
    return None


def op_add_legend_item(root, op):
    leg = C.find_by_id(root, C.LEGEND_ID)
    if leg is None:
        return "no legend group (id='%s') in SVG" % C.LEGEND_ID
    item = op.get("item")
    if not item:
        return "add-legend-item needs 'item'"
    if C.find_by_id(root, C.SWATCH_PREFIX + item) is not None:
        return "legend item '%s' already exists" % item
    # place below the last existing item
    y = None
    x = None
    for g in leg.iter():
        gid = g.get("id") or ""
        if gid.startswith(C.SWATCH_PREFIX):
            sw = C.find_child_by_class(g, "swatch", "rect")
            if sw is not None:
                y = max(y or 0.0, float(sw.get("y", 0)) + 26)
                x = x or float(sw.get("x", 0))
    if y is None:
        frame = C.find_child_by_class(leg, "legend-frame", "rect")
        x = float(frame.get("x", 0)) + 12 if frame is not None else 12.0
        y = float(frame.get("y", 0)) + 14 if frame is not None else 14.0
    g = C.ET.SubElement(leg, "g")
    g.set("id", C.SWATCH_PREFIX + item)
    g.set("class", "legend-item")
    sw = C.ET.SubElement(g, "rect")
    sw.set("x", str(x)); sw.set("y", str(y))
    sw.set("width", "18"); sw.set("height", "14")
    sw.set("fill", op.get("color", "#cccccc")); sw.set("stroke", "#555555")
    sw.set("class", "swatch")
    tx = C.ET.SubElement(g, "text")
    tx.set("x", str(x + 26)); tx.set("y", str(y + 12))
    tx.set("font-size", "11"); tx.set("class", "legend-label")
    meaning = op.get("meaning", "")
    tx.text = ("%s: %s" % (item, meaning)) if meaning else item
    # grow the frame if needed
    frame = C.find_child_by_class(leg, "legend-frame", "rect")
    if frame is not None:
        bottom = float(frame.get("y", 0)) + float(frame.get("height", 0))
        if y + 22 > bottom:
            frame.set("height", str(y + 22 - float(frame.get("y", 0))))
    return None


def op_remove_legend_item(root, op):
    leg = C.find_by_id(root, C.LEGEND_ID)
    if leg is None:
        return "no legend group in SVG"
    target = C.find_by_id(root, C.SWATCH_PREFIX + op.get("item", ""))
    if target is None:
        return "legend item '%s' not found" % op.get("item")
    for parent in root.iter():
        if target in list(parent):
            parent.remove(target)
            return None
    return "legend item '%s' has no removable parent" % op.get("item")


def op_set_fill(root, op):
    el = C.find_by_id(root, op.get("target", ""))
    if el is None:
        return "target element '%s' not found" % op.get("target")
    box = C.find_child_by_class(el, "swatch")
    if box is None:
        box = C.find_child_by_class(el, "entity-box")
    if box is None and C.localname(el.tag) in ("rect", "circle", "ellipse"):
        box = el
    if box is None:
        for ch in el.iter():
            if C.localname(ch.tag) in ("rect", "circle", "ellipse"):
                box = ch
                break
    if box is None:
        return "no paintable shape under '%s'" % op.get("target")
    box.set("fill", op.get("color", "#cccccc"))
    return None


OPS = {
    "rename-label": op_rename_label,
    "set-edge-kind": op_set_edge_kind,
    "set-edge-endpoints": op_set_edge_endpoints,
    "swap-edge-direction": op_swap_edge_direction,
    "set-edge-evidence": op_set_edge_evidence,
    "add-legend-item": op_add_legend_item,
    "remove-legend-item": op_remove_legend_item,
    "set-fill": op_set_fill,
}


def apply_ops(svg_path, ops):
    tree = C.parse_svg(svg_path)
    root = tree.getroot()
    applied, failed = [], []
    for i, op in enumerate(ops):
        fn = OPS.get(op.get("op"))
        if fn is None:
            failed.append({"index": i, "op": op,
                           "error": "unknown op '%s'" % op.get("op")})
            continue
        err = fn(root, copy.deepcopy(op))
        if err:
            failed.append({"index": i, "op": op, "error": err})
        else:
            applied.append(op)
    C.register_ns()
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    return applied, failed


def run_audit(args, svg_path, out_dir):
    cmd = [sys.executable, os.path.join(HERE, "audit_run.py"),
           "--claims", args.claims, "--svg", svg_path, "--out", out_dir]
    if args.png:
        cmd += ["--png", args.png]
    if args.pdf:
        cmd += ["--pdf", args.pdf]
    if args.before_svg:
        cmd += ["--before-svg", args.before_svg]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    report_path = os.path.join(out_dir, "audit_report.json")
    if not os.path.exists(report_path):
        return None
    with open(report_path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--ops", required=True,
                    help="JSON list of ops; re-read every iteration so the "
                         "agent can rewrite it between rounds")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--png")
    ap.add_argument("--pdf")
    ap.add_argument("--before-svg")
    ap.add_argument("--max-iters", type=int, default=3)
    args = ap.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    work_svg = os.path.join(args.workdir, "figure_fixed.svg")
    shutil.copyfile(args.svg, work_svg)
    journal = []

    for it in range(1, args.max_iters + 1):
        with open(args.ops, encoding="utf-8") as fh:
            ops = json.load(fh)
        if not isinstance(ops, list):
            print("ops file must be a JSON list", file=sys.stderr)
            return 2
        applied, failed = apply_ops(work_svg, ops)
        out_dir = os.path.join(args.workdir, "audit_iter%d" % it)
        report = run_audit(args, work_svg, out_dir)
        if report is None:
            journal.append({"iteration": it, "ops_applied": applied,
                            "ops_failed": failed,
                            "error": "audit_run produced no report"})
            break
        entry = {
            "iteration": it,
            "ops_applied": applied,
            "ops_failed": failed,
            "errors": report["summary"]["errors"],
            "warnings": report["summary"]["warnings"],
            "skipped": report["summary"]["skipped"],
            "report": os.path.join(out_dir, "audit_report.json"),
            "remaining_violations": report["violations"],
        }
        journal.append(entry)
        print("fix_loop iteration %d: %d ops applied, %d failed -> "
              "%d errors remain" % (it, len(applied), len(failed),
                                    entry["errors"]))
        if entry["errors"] == 0:
            break

    journal_path = os.path.join(args.workdir, "fix_journal.json")
    with open(journal_path, "w", encoding="utf-8") as fh:
        json.dump({"fixed_svg": work_svg, "iterations": journal},
                  fh, indent=2, ensure_ascii=False)
    last = journal[-1] if journal else {}
    remaining = last.get("errors", -1)
    print("fix_loop done: journal=%s, final errors=%s" % (
        journal_path, remaining))
    if remaining != 0:
        print("NOTE: %s error(s) remain — they must be reported in "
              "result.json exceptions, not hidden." % remaining)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
