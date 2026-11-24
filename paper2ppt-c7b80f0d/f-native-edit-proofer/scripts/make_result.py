#!/usr/bin/env python3
"""make_result.py -- assemble result.json from real measured reports.

Reads case.json (output_contract field names are taken from the case, never
hardcoded) plus the measured reports produced by the pipeline and emits a
result.json containing every contract field plus `uncertainties` and
`change_records`. All compliance_checks.actual values come from the measured
reports; nothing is asserted without a measurement.

Usage:
    python3 make_result.py --case case.json --deck deck.json \
        --work-dir work/ --output-dir output/ --out result.json
Exit 0 always (status field carries success/partial honesty); 2 on bad input.
"""
import argparse
import json
import os
import sys


def load(path, default=None):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def main():
    ap = argparse.ArgumentParser(description="Assemble result.json from "
                                     "measured pipeline reports.")
    ap.add_argument("--case", required=True)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    case = load(args.case)
    if not case:
        sys.stderr.write("make_result: ERROR cannot read case.json\n")
        return 2
    deck = load(args.deck, default={})
    w, o = args.work_dir, args.output_dir
    build = load(os.path.join(w, "build_report.json"), {})
    lint = load(os.path.join(w, "editability_report.json"), {})
    rt = load(os.path.join(w, "roundtrip_report.json"), {})
    rd = load(os.path.join(w, "render_report.json"), {})
    ev = load(os.path.join(w, "evidence_scan.json"), {})

    pptx_path = os.path.join(o, "presentation.pptx")
    slides = deck.get("slides", [])
    n_slides = build.get("slide_count", len(slides))

    # ---- content_map from deck.json + measured notes/render info ----
    rt_per = {p["slide"]: p for p in rt.get("per_slide", [])}
    content_map = []
    for i, sd in enumerate(slides, start=1):
        claims, sources = [], []
        for b in sd.get("bullets", []):
            if isinstance(b, dict):
                claims.append(b.get("text", ""))
                if b.get("source"):
                    sources.append({"kind": b["source"].get("kind", "paper"),
                                    "ref": b["source"].get("ref", ""),
                                    "locator": b["source"].get("locator", ""),
                                    "quote": b.get("quote", "")})
        figures = []
        if sd.get("figure"):
            figures.append({"file": sd["figure"]["file"],
                            "caption": sd["figure"].get("caption", ""),
                            "sidecar": sd["figure"].get("sidecar")})
        for e in sd.get("evidence", []):
            sources.append({"kind": e.get("kind", "paper"),
                            "ref": e.get("ref", ""),
                            "locator": e.get("locator", ""),
                            "quote": e.get("quote", "")})
        table = None
        if sd.get("table"):
            table = {"native": True, "columns": sd["table"]["columns"],
                     "rows": len(sd["table"]["rows"]),
                     "caption": sd["table"].get("caption", "")}
        notes_present = rt_per.get(i, {}).get(
            "notes", bool(sd.get("notes")))
        content_map.append({
            "slide": i, "role": sd.get("role", "bullets"),
            "title": sd.get("title", ""), "claims": claims,
            "figures": figures, "table": table, "sources": sources,
            "notes_present": notes_present,
            "notes_time_sec": sd.get("notes_time_sec"),
        })

    # ---- compliance_checks: every actual is measured ----
    task_max = deck.get("meta", {}).get("max_slides")
    lint_errors = lint.get("errors", [])
    ph_err = [e for e in lint_errors if e["check"] == "placeholder_free"]
    font_err = [e for e in lint_errors if e["check"] == "min_font_size"]
    notes_have = sum(1 for c in content_map if c["notes_present"])
    checks = [
        {"check": "slide_count",
         "expected": "<= %s" % (task_max or "?"),
         "actual": n_slides,
         "pass": (task_max is None or n_slides <= task_max)},
        {"check": "export_page_match",
         "expected": n_slides,
         "actual": rd.get("page_count") if rd.get("rendered") else
         "not_rendered",
         "pass": bool(rd.get("rendered")) and
         rd.get("page_count") == n_slides},
        {"check": "placeholder_free",
         "expected": 0,
         "actual": len(ph_err),
         "pass": len(ph_err) == 0},
        {"check": "min_font_size",
         "expected": ">=10pt footnote / >=14pt body",
         "actual": lint.get("min_run_pt"),
         "pass": len(font_err) == 0 and lint.get("min_run_pt") is not None},
        {"check": "evidence_coverage",
         "expected": 1.0,
         "actual": ev.get("coverage"),
         "pass": ev.get("coverage") == 1.0},
        {"check": "notes_coverage",
         "expected": n_slides,
         "actual": notes_have,
         "pass": notes_have == n_slides},
        {"check": "roundtrip_reopen",
         "expected": "PASS",
         "actual": rt.get("verdict"),
         "pass": rt.get("verdict") == "PASS"},
        {"check": "near_blank_pages",
         "expected": 0,
         "actual": len(rd.get("near_blank_pages", [])) if rd.get("rendered")
         else "not_rendered",
         "pass": rd.get("rendered", False) and
         not rd.get("near_blank_pages")},
    ]

    exceptions = []
    if rd.get("tool_missing"):
        exceptions.append({"kind": "tool_missing",
                           "detail": "render chain missing: %s"
                           % ", ".join(rd["tool_missing"])})
    for e in lint_errors:
        exceptions.append({"kind": "editability_error", "detail": str(e)})

    all_pass = all(c["pass"] for c in checks)
    status = "success" if all_pass else "partial"

    result_core = {
        "case_id": case.get("case_id"),
        "status": status,
        "editable_source": {
            "path": os.path.abspath(pptx_path),
            "format": "pptx",
            "slides": n_slides,
            "notes_present": notes_have == n_slides,
        },
        "export_artifact": {
            "pdf": rd.get("pdf"),
            "rendered": bool(rd.get("rendered")),
            "previews": rd.get("previews", []),
            "pages": rd.get("page_count", 0),
        },
        "content_map": content_map,
        "compliance_checks": checks,
        "exceptions": exceptions,
        "uncertainties": [
            "synthetic input only; no platform case was used",
            "font availability varies per machine; theme-font inheritance "
            "mitigates but does not eliminate substitution risk",
        ],
        "change_records": [
            {"version": 1, "slide": "all", "change": "initial native build",
             "reason": "first pass from deck.json",
             "rollback": "rebuild from deck.json is deterministic"},
        ],
    }

    # honor the case's output_contract field names verbatim
    contract = case.get("output_contract") or list(result_core)[:7]
    result = {}
    for field in contract:
        if field in result_core:
            result[field] = result_core[field]
        else:
            result[field] = None
            exceptions.append({"kind": "contract_field_unknown",
                               "detail": field})
    result["uncertainties"] = result_core["uncertainties"]
    result["change_records"] = result_core["change_records"]
    if status == "partial":
        failed = [c["check"] for c in checks if not c["pass"]]
        result.setdefault("exceptions", []).append(
            {"kind": "partial",
             "detail": "checks not passing: %s" % ", ".join(failed)})

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("make_result: status=%s checks_pass=%d/%d -> %s"
          % (status, sum(1 for c in checks if c["pass"]), len(checks),
             args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
