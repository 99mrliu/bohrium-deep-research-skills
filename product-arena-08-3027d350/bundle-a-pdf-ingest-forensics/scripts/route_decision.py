#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
route_decision.py — fuse intake + glyph evidence into a routing decision
and a contract-aware result.json skeleton (stdlib only).

Inputs:
  --intake  intake_report.json   (from pdf_probe.py)
  --glyph   glyph_audit.json     (from glyph_audit.py; optional)
  --case    /input/case.json     (optional for the synthetic example)

Routing vocabulary:
  direct_text_layer   every page has a trustworthy text layer -> parse it
  ocr_handoff         NO page has a usable text layer -> hand whole doc to OCR
  mixed_pagelevel     some pages direct, some pages OCR -> per-page plan
  refuse_with_handoff unreadable input (e.g. encrypted) -> stop, honest report

Honesty rules:
  * any scanned / mojibake / rotated / duplicate / unmeasured page
    => result.json status "partial" (never "success")
  * encrypted or zero pages
    => route refuse_with_handoff, status "failed"
  * contract fields we cannot fill stay EMPTY and are explained
    in `uncertainty`; we never fabricate content.

Output: OUTDIR/route_decision.json and OUTDIR/result.json
Exit codes: 0 = direct route, 2 = partial route, 3 = refuse/failed.
"""
import argparse
import json
import os
import re
import sys

ROUTE_SCHEMA = "pdf-ingest-forensics/route_decision/v1"
RESULT_SCHEMA = "pdf-ingest-forensics/result/v1"

GLYPH_RESCUE_SEVERITIES = ("medium", "high")  # text layer untrustworthy


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _glyph_page_map(glyph):
    """Map page numbers to glyph severity, using pageNN-style filenames."""
    page_sev = {}
    if not glyph:
        return page_sev
    for fr in glyph.get("files", []):
        m = re.search(r"(\d+)", os.path.basename(fr.get("file", "")))
        if m:
            page_sev[int(m.group(1))] = fr
    return page_sev


def decide(intake, glyph):
    """Return (route, assignments, route_reasons)."""
    reasons = []
    if intake.get("status") == "failed" or intake.get("encrypted"):
        reasons.extend(intake.get("reasons", []))
        reasons.append("input unreadable; refuse to parse and hand back an "
                       "honest failure instead of guessing content")
        return "refuse_with_handoff", [], reasons

    page_sev = _glyph_page_map(glyph)
    assignments = []
    n_direct = 0
    n_ocr = 0
    for p in intake.get("pages", []):
        page_no = p.get("page")
        action = "direct_text_layer"
        preasons = []
        flags = p.get("flags", [])
        if "scanned_candidate" in flags:
            action = "ocr_handoff"
            preasons.append("image(s) present but <%d extractable chars; "
                            "no usable text layer" % 20)
        g = page_sev.get(page_no)
        if g and g.get("severity") in GLYPH_RESCUE_SEVERITIES:
            if action == "direct_text_layer":
                action = "ocr_handoff"
            preasons.append("glyph corruption severity=%s (%s); extracted text "
                            "is untrustworthy, re-acquire via OCR"
                            % (g.get("severity"), "; ".join(g.get("reasons", []))))
        if "rotated" in flags:
            preasons.append("page /Rotate=%s; apply rotation before any "
                            "layout/table analysis" % p.get("rotate"))
        if p.get("duplicate_of"):
            preasons.append("duplicate of page %s; parse once, record mapping"
                            % p["duplicate_of"])
        if p.get("char_count") is None:
            preasons.append("text-layer coverage unknown for this page")
        if not preasons:
            preasons.append("clean text layer")
        if action == "ocr_handoff":
            n_ocr += 1
        else:
            n_direct += 1
        assignments.append({
            "page": page_no,
            "action": action,
            "char_count": p.get("char_count"),
            "image_count": p.get("image_count"),
            "rotate": p.get("rotate"),
            "duplicate_of": p.get("duplicate_of"),
            "reasons": preasons,
        })

    total = len(assignments)
    if total == 0:
        route = "refuse_with_handoff"
        reasons.append("no pages to route")
    elif n_ocr == 0:
        route = "direct_text_layer"
        reasons.append("all %d pages have a usable text layer" % total)
    elif n_direct == 0:
        route = "ocr_handoff"
        reasons.append("no page has a usable text layer; hand entire document "
                       "to OCR (%d pages)" % total)
    else:
        route = "mixed_pagelevel"
        reasons.append("%d/%d pages direct, %d/%d pages need OCR"
                       % (n_direct, total, n_ocr, total))
    if not intake.get("summary", {}).get("text_layer_measured", True):
        reasons.append("WARNING: text-layer coverage was not measured; routing "
                       "is provisional and must be re-confirmed after measuring")
    return route, assignments, reasons


def build_result(case, intake, glyph, route, assignments, out_dir):
    """Contract-aware result.json skeleton; unknown fields stay empty."""
    case = case or {}
    case_id = case.get("case_id", "UNKNOWN_CASE")
    contract = case.get("output_contract", {})
    if isinstance(contract, list):
        contract = {k: "" for k in contract}

    uncertainty = []
    # honest status
    if route == "refuse_with_handoff":
        status = "failed"
        uncertainty.append("input could not be read at all; no content was "
                           "extracted and none was guessed")
    else:
        anomalies = intake.get("summary", {})
        flagged = (anomalies.get("scanned_pages") or anomalies.get("rotated_pages")
                   or anomalies.get("duplicate_pairs")
                   or (glyph or {}).get("flagged_files")
                   or not anomalies.get("text_layer_measured", True))
        status = "partial" if flagged else "success"

    fields = {}
    for name in contract:
        if name == "page_map" and route != "refuse_with_handoff":
            fields[name] = {str(a["page"]): a["action"] for a in assignments}
        elif name == "intake_notes":
            fields[name] = ("route=%s; %s" % (route, "; ".join(
                intake.get("reasons", []) or ["no anomalies detected"])))
        elif name == "uncertainty":
            fields[name] = uncertainty
        else:
            fields[name] = ""
            uncertainty.append("field '%s' left empty: content extraction is "
                               "downstream of this triage skill and was not "
                               "performed" % name)
    if "uncertainty" in fields:
        fields["uncertainty"] = uncertainty

    return {
        "schema": RESULT_SCHEMA,
        "case_id": case_id,
        "status": status,
        "route": route,
        "fields": fields,
        "sources": [
            os.path.join(out_dir, "intake_report.json"),
            os.path.join(out_dir, "glyph_audit.json"),
            os.path.join(out_dir, "route_decision.json"),
        ],
        "uncertainty": uncertainty,
        "change_record": [
            "route_decision.py: fused intake_report + glyph_audit into route "
            "'%s'; contract fields echoed, unfilled fields left empty and "
            "explained in uncertainty" % route,
        ],
    }, status


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fuse intake + glyph audit into a routing decision.")
    ap.add_argument("--intake", required=True, help="intake_report.json")
    ap.add_argument("--glyph", help="glyph_audit.json (optional)")
    ap.add_argument("--case", help="case.json with case_id/output_contract "
                                   "(optional for the synthetic example)")
    ap.add_argument("--out", default=".", help="output directory")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    intake = _load(args.intake)
    glyph = _load(args.glyph) if args.glyph and os.path.isfile(args.glyph) else None
    case = _load(args.case) if args.case and os.path.isfile(args.case) else None

    route, assignments, reasons = decide(intake, glyph)
    decision = {
        "schema": ROUTE_SCHEMA,
        "tool": "route_decision.py",
        "route": route,
        "reasons": reasons,
        "page_assignments": assignments,
        "inputs": {
            "intake": os.path.abspath(args.intake),
            "glyph": os.path.abspath(args.glyph) if args.glyph else None,
            "case": os.path.abspath(args.case) if args.case else None,
        },
    }
    with open(os.path.join(args.out, "route_decision.json"), "w",
              encoding="utf-8") as fh:
        json.dump(decision, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    result, status = build_result(case, intake, glyph, route, assignments,
                                  args.out)
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(json.dumps({
        "route": route,
        "result_status": status,
        "pages": len(assignments),
        "ocr_pages": [a["page"] for a in assignments if a["action"] == "ocr_handoff"],
        "out": os.path.abspath(args.out),
    }, ensure_ascii=False))
    return {"failed": 3, "partial": 2}.get(status, 0)


if __name__ == "__main__":
    sys.exit(main())
