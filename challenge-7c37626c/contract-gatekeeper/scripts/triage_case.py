#!/usr/bin/env python3
"""Input triage: classify the case branch, derive the capability matrix, and
bank an early honest-partial result.json BEFORE any analysis. Stdlib only.
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def local(tag):
    return tag.rsplit("}", 1)[-1]


def detect_branch(input_root, artifacts):
    has_math = False
    for key in ("publisher_source_xml", "source_formulas_xml"):
        p = artifacts.get(key)
        if p and (input_root / p).exists() and (input_root / p).suffix == ".xml":
            try:
                root = ET.parse(input_root / p).getroot()
                if any(local(el.tag) == "math" for el in root.iter()):
                    has_math = True
            except ET.ParseError:
                # corrupt XML is still an XML branch, with a repair note
                return "xml_rich_corrupt" if key == "publisher_source_xml" else "xml_subset_corrupt"
    if has_math:
        if artifacts.get("publisher_source_xml") and (input_root / artifacts["publisher_source_xml"]).exists():
            return "xml_rich"
        return "formula_subset_only"
    pdf = artifacts.get("pdf")
    if pdf and (input_root / pdf).exists():
        return "pdf_only"
    return "metrics_only"


CAPABILITIES = {
    "xml_rich": {"transcription": True, "symbol_grounding": True,
                 "derivation_mapping": True, "numeric_verification": True},
    "formula_subset_only": {"transcription": True, "symbol_grounding": "context_needed",
                            "derivation_mapping": "subset_only",
                            "numeric_verification": "context_needed"},
    "xml_rich_corrupt": {"transcription": "repair_first", "symbol_grounding": "repair_first",
                         "derivation_mapping": "repair_first", "numeric_verification": "repair_first"},
    "xml_subset_corrupt": {"transcription": "repair_first", "symbol_grounding": "repair_first",
                           "derivation_mapping": "repair_first", "numeric_verification": "repair_first"},
    "pdf_only": {"transcription": "visual_only", "symbol_grounding": "visual_only",
                 "derivation_mapping": "visual_only", "numeric_verification": "values_needed"},
    "metrics_only": {"transcription": False, "symbol_grounding": False,
                     "derivation_mapping": False, "numeric_verification": False},
}

LIMITATIONS = {
    "metrics_only": [
        "no formula representation in the snapshot",
        "no per-item predictions or recalculable raw data",
        "formula-level tasks are insufficient_evidence; only explicit "
        "reported metrics may be restated (with their conditions)"],
    "pdf_only": [
        "no markup layer; transcription must be done visually and marked accordingly"],
    "xml_rich_corrupt": ["publisher XML malformed; repair/salvage before structural use"],
    "xml_subset_only": [
        "formula subset lacks full prose context; definitions must be "
        "confirmed against the PDF or the case's other materials"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    input_root, work, out = Path(args.input), Path(args.work), Path(args.out)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    case_path = input_root / "case.json"
    case, note = {}, "case.json missing; contract unknown"
    if case_path.exists():
        try:
            case = json.loads(case_path.read_text(encoding="utf-8"))
            note = "triaged before analysis"
        except Exception as exc:
            note = "case.json unreadable: %s" % exc

    artifacts = case.get("artifacts") or {}
    branch = detect_branch(input_root, artifacts) if case else "contract_unknown"
    caps = CAPABILITIES.get(branch, {})

    files = sorted(str(p.relative_to(input_root)) for p in input_root.rglob("*") if p.is_file())
    triage = {"branch": branch, "capabilities": caps,
              "limitations": LIMITATIONS.get(branch, []),
              "files": files, "note": note}
    (work / "triage.json").write_text(json.dumps(triage, indent=2, ensure_ascii=False),
                                      encoding="utf-8")

    result = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "answers": {},
        "evidence": [],
        "uncertainty": {
            "stage": "triage",
            "notes": [note],
            "branch": branch,
            "limitations": LIMITATIONS.get(branch, []),
        },
        "artifacts": {"work_dir": str(work), "input_files": files,
                      "triage": str(work / "triage.json")},
    }
    for field in (case.get("output_contract") or {}).get("required_fields", []):
        result.setdefault(field, None)
    (out / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("triage: branch=%s caps=%s -> early partial banked" % (branch, list(caps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
