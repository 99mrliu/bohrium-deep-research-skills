#!/usr/bin/env python3
"""Cross-layer consistency check for formula evidence:

  MathML structure (source-formulas.xml)  vs  publisher alttext (TeX)
  vs  numeric constants in the PDF text layer (pdftotext, if available).

Every agreement or disagreement is reported verbatim; nothing is silently
resolved. Stdlib only; pdftotext optional.
"""
import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from signature import find_math_nodes, latex_signature, mathml_signature, compare_multisets

NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]\s*10\^?\s*([−-]?\d+)", re.I)


def norm_const(m):
    exp = m.group(2).replace("−", "-")
    return "%se%s" % (m.group(1), int(exp))


def extract_constants(text):
    return set(norm_const(m) for m in NUM_RE.finditer(text or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default=None,
                    help="input root; default: parent of the case file")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    case_path = Path(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    input_root = Path(args.input) if args.input else case_path.parent
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    artifacts = (case.get("artifacts") or {})

    formulas_xml = artifacts.get("source_formulas_xml")
    publisher_xml = artifacts.get("publisher_source_xml")
    pdf = artifacts.get("pdf")

    report = {"formulas": [], "pdf_layer": {"status": "skipped"}}

    # Layer 1 vs layer 2: MathML structure vs alttext TeX.
    if formulas_xml and (input_root / formulas_xml).exists():
        try:
            root = ET.parse(input_root / formulas_xml).getroot()
        except ET.ParseError as exc:
            report["formulas_layer_error"] = (
                "source-formulas.xml malformed: %s (formula-level cross-check "
                "impossible; degrading)" % exc)
            root = None
        if root is not None:
          for node in find_math_nodes(root):
            fid = node.get("id")
            alttext = node.get("alttext")
            a, b = Counter(), Counter()
            mathml_signature(node, a)
            alt_source = alttext
            if alt_source is None and publisher_xml and (input_root / publisher_xml).exists():
                try:
                    pub_nodes = find_math_nodes(ET.parse(input_root / publisher_xml).getroot())
                    for src in pub_nodes:
                        if src.get("id") == fid:
                            alt_source = src.get("alttext")
                            break
                except ET.ParseError as exc:
                    report.setdefault("publisher_layer_error",
                                      "publisher XML malformed: %s" % exc)
            entry = {"id": fid, "alttext_present": alt_source is not None}
            if alt_source:
                latex_signature(alt_source, b)
                match, missing, extra = compare_multisets(a, b)
                entry["structure_agreement"] = "identical" if match else "divergent"
                if not match:
                    entry["missing_in_alttext"] = missing
                    entry["extra_in_alttext"] = extra
            else:
                entry["structure_agreement"] = "unverifiable_no_alttext"
            report["formulas"].append(entry)

    # Layer 3: numeric constants stated in XML text vs PDF text layer.
    if pdf and (input_root / pdf).exists():
        try:
            out = subprocess.run(["pdftotext", "-layout", str(input_root / pdf), "-"],
                                 capture_output=True, text=True, timeout=60)
            if out.returncode == 0 and out.stdout.strip():
                pdf_text = out.stdout
                xml_text = ""
                if publisher_xml and (input_root / publisher_xml).exists():
                    try:
                        pub_root = ET.parse(input_root / publisher_xml).getroot()
                        # join without separators so superscript exponents
                        # (e.g. "10" + "−5") re-attach to the mantissa
                        xml_text = "".join(pub_root.itertext())
                    except ET.ParseError as exc:
                        xml_text = ""
                        report["pdf_layer_xml_note"] = (
                            "publisher XML malformed (%s); constants cannot be "
                            "extracted from the XML layer" % exc)
                elif formulas_xml and (input_root / formulas_xml).exists():
                    try:
                        xml_text = " ".join(ET.parse(input_root / formulas_xml).getroot().itertext())
                    except ET.ParseError:
                        xml_text = ""
                xml_consts = extract_constants(xml_text)
                pdf_consts = extract_constants(pdf_text)
                report["pdf_layer"] = {
                    "status": "checked",
                    "constants_in_xml": sorted(xml_consts),
                    "constants_in_pdf": sorted(pdf_consts),
                    "missing_from_pdf": sorted(xml_consts - pdf_consts),
                    "only_in_pdf": sorted(pdf_consts - xml_consts),
                }
            else:
                report["pdf_layer"] = {"status": "unreadable", "reason": (out.stderr or "empty text layer").strip()[:300]}
        except FileNotFoundError:
            report["pdf_layer"] = {"status": "skipped", "reason": "pdftotext not available"}
        except subprocess.TimeoutExpired:
            report["pdf_layer"] = {"status": "skipped", "reason": "pdftotext timed out"}

    (work / "crosscheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for f in report["formulas"]:
        print("%s: %s" % (f["id"], f["structure_agreement"]))
    print("pdf_layer: %s" % report["pdf_layer"]["status"])
    print("report -> %s" % (work / "crosscheck.json"))


if __name__ == "__main__":
    main()
