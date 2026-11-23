#!/usr/bin/env python3
"""Fail-closed completeness gate for derivation step skeletons.

Each step must carry: from, to, action, justification (an algebraic rule,
substitution or citation — not a restatement), locator (section/paragraph/
equation), and an assumptions list (present even when empty). References to
formulas absent from graph.json, and steps whose justification is empty or
shorter than a few characters, fail the gate; defective steps are named and
the case status degrades to partial. Stdlib only.
"""
import argparse
import json
import sys
from pathlib import Path

REQUIRED = ["from", "to", "action", "justification", "locator", "assumptions"]


def gate_step(step, known_ids):
    problems = []
    for field in REQUIRED:
        if field not in step or step[field] in (None, ""):
            problems.append("missing field %r" % field)
    just = str(step.get("justification") or "").strip()
    if just and len(just) < 8:
        problems.append("justification too thin to be checkable: %r" % just)
    for ref_field in ("from", "to"):
        ref = step.get(ref_field)
        if isinstance(ref, str) and ref.startswith("eq") and ref not in known_ids:
            problems.append("%s references unknown formula %r" % (ref_field, ref))
    if not isinstance(step.get("assumptions"), list):
        problems.append("assumptions must be a list (empty list is allowed)")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)

    steps_doc = json.loads((work / "steps.json").read_text(encoding="utf-8"))
    steps = steps_doc.get("steps", [])
    known = set()
    gp = work / "graph.json"
    if gp.exists():
        g = json.loads(gp.read_text(encoding="utf-8"))
        known = {n["id"] for n in g.get("nodes", [])}

    rows = []
    for i, step in enumerate(steps):
        problems = gate_step(step, known)
        rows.append({"step_id": step.get("step_id", "step-%d" % (i + 1)),
                     "problems": problems, "accepted": not problems})
    defective = [r["step_id"] for r in rows if not r["accepted"]]
    report = {
        "steps_total": len(steps),
        "steps_accepted": len(rows) - len(defective),
        "defective_steps": defective,
        "rows": rows,
    }
    (work / "gate_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    rp = out / "result.json"
    if rp.exists():
        result = json.loads(rp.read_text(encoding="utf-8"))
        g = json.loads(gp.read_text(encoding="utf-8")) if gp.exists() else {}
        unresolved = g.get("unresolved_citations", [])
        if not steps and not g.get("nodes"):
            result["status"] = "insufficient_evidence"
        elif defective or unresolved:
            result["status"] = "partial"
        else:
            result["status"] = "success"
        result.setdefault("answers", {})["derivation_map"] = {
            "graph_summary": g.get("summary"),
            "unresolved_citations": unresolved,
            "gated_steps": rows,
            "artifacts": {"graph_json": str(gp), "graph_mmd": str(work / "graph.mmd")},
        }
        if (work / "graph.png").exists():
            result["answers"]["derivation_map"]["artifacts"]["graph_png"] = str(work / "graph.png")
        result.setdefault("uncertainty", {})["defective_steps"] = defective
        result.setdefault("artifacts", {})["gate_report"] = str(work / "gate_report.json")
        rp.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print("gate: %d/%d steps accepted, defective=%s -> %s"
          % (report["steps_accepted"], report["steps_total"],
             defective, work / "gate_report.json"))


if __name__ == "__main__":
    main()
