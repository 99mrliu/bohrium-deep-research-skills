#!/usr/bin/env python3
"""Merge forensic scan + cross-layer check into the final result.json.

Verdict rules (fail-closed):
  - any malformed XML or missing artifact            -> status partial
  - any formula layer disagreement or conflict       -> status partial
  - no formula-bearing artifacts at all              -> status insufficient_evidence
  - all checks pass                                  -> status success
The verdict names exactly which artifacts/formulas limited the status.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default=None)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    work, out = Path(args.work), Path(args.out)

    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    scan = json.loads((work / "forensic_report.json").read_text(encoding="utf-8"))
    cross = json.loads((work / "crosscheck.json").read_text(encoding="utf-8"))

    problems, notes = [], []

    for x in scan.get("xml", {}).values():
        if not x["well_formed"]:
            problems.append("malformed XML: %s (%s)" % (x["path"], x.get("error")))
        for item in x.get("math_nodes", []):
            if item.get("alttext") is None:
                notes.append("math node %s lacks alttext" % item.get("id"))

    subset = scan.get("subset_vs_source") or {}
    for item in subset.get("items", []):
        if item.get("matched_in_source") != "identical":
            problems.append("subset node %s: %s" % (item.get("id"), item.get("matched_in_source")))

    for f in cross.get("formulas", []):
        if f.get("structure_agreement") == "divergent":
            problems.append("formula %s: MathML/alttext divergence %s"
                            % (f.get("id"), f.get("extra_in_alttext")))
        elif f.get("structure_agreement") != "identical":
            notes.append("formula %s: %s" % (f.get("id"), f.get("structure_agreement")))

    layer = cross.get("pdf_layer", {})
    if layer.get("status") == "checked" and layer.get("missing_from_pdf"):
        problems.append("constants in XML but not in PDF text layer: %s"
                        % ", ".join(layer["missing_from_pdf"]))
    elif layer.get("status") != "checked":
        notes.append("PDF layer %s: %s" % (layer.get("status"), layer.get("reason", "no PDF artifact")))

    artifacts = (case.get("artifacts") or {})
    has_formula_source = any(k for k in ("publisher_source_xml", "source_formulas_xml") if artifacts.get(k))
    if not has_formula_source and not cross.get("formulas"):
        status = "insufficient_evidence"
        problems.append("no formula-bearing artifact provided; formula-level "
                        "verification impossible from available materials")
    elif problems:
        status = "partial"
    else:
        status = "success"

    verified = []
    for f in cross.get("formulas", []):
        if f.get("structure_agreement") == "identical":
            verified.append(f.get("id"))

    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    result["status"] = status
    result["answers"] = {
        "authenticity_verdict": {
            "status": status,
            "verified_formulas": verified,
            "problems": problems,
            "notes": notes,
        },
        "verified_formula_inventory": cross.get("formulas", []),
        "integrity_manifest": scan.get("files", []),
        "subset_vs_source": subset.get("items", []),
    }
    result["evidence"] = [
        {"artifact": f["path"], "sha256": f["sha256"], "bytes": f["bytes"]}
        for f in scan.get("files", [])
    ]
    result["uncertainty"] = {
        "problems": problems,
        "notes": notes,
        "rule": "status is success only if every layer check passed; any "
                "malformation, divergence or missing layer degrades it",
    }
    result["artifacts"].update({
        "forensic_report": str(work / "forensic_report.json"),
        "crosscheck": str(work / "crosscheck.json"),
    })
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("verdict: %s (%d problems, %d verified formulas)"
          % (status, len(problems), len(verified)))
    return 0 if status in ("success", "partial", "insufficient_evidence") else 1


if __name__ == "__main__":
    sys.exit(main())
