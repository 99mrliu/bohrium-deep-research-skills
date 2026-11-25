#!/usr/bin/env python3
"""assemble.py — assemble final deliverables + audit certificate (stage 7).

Mirrors the output_contract keys declared in case.json dynamically: every
declared key appears in result.json (a key that cannot be produced is set to
null with the reason recorded in "uncertainty" — never silently omitted).
Also writes the signature artifact audit_certificate.json with measurable
per-iteration metrics and the baseline-vs-final quality gain, plus
quarantine.json for rejected items.

Usage:
    python3 assemble.py --work /app/work --output /app/output

Python 3.9+, standard library only. Deterministic artifacts; the only
wall-clock timestamp lives under result.json -> run_meta.
"""
import argparse
import datetime
import glob
import json
import os
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def build_certificate(work, case_id):
    iters = []
    for path in sorted(glob.glob(os.path.join(work, "audit_report.iter*.json"))):
        rep = load_json(path)
        iters.append({"iteration": rep.get("iteration"),
                      "draft_file": rep.get("draft_file"),
                      "metrics": rep.get("metrics")})
    iters.sort(key=lambda r: r.get("iteration") or 0)
    final = iters[-1]["metrics"] if iters else {}
    baseline = iters[0]["metrics"] if iters else {}

    def gain(key):
        b, f = baseline.get(key), final.get(key)
        if isinstance(b, (int, float)) and isinstance(f, (int, float)):
            return round(f - b, 1)
        return None

    quarantine_path = os.path.join(work, "quarantine.json")
    quarantined = 0
    if os.path.isfile(quarantine_path):
        quarantined = len(load_json(quarantine_path).get("items") or [])

    verdict = "pass"
    if not iters:
        verdict = "no-audit-run"
    elif (final.get("repair") or 0) > 0 or (final.get("rejected") or 0) > 0:
        verdict = "pass-with-quarantine" if quarantined else "incomplete"

    return {
        "certificate": "evidence-audit-loop",
        "case_id": case_id,
        "max_iterations": 2,
        "iterations_run": len(iters),
        "iterations": iters,
        "baseline_vs_final": {
            "baseline_iteration": baseline.get("items_total") and iters[0]["iteration"],
            "final_iteration": iters[-1]["iteration"] if iters else None,
            "quote_precision_gain_pp": gain("quote_precision_pct"),
            "address_validity_gain_pp": gain("address_validity_pct"),
            "attribution_accuracy_gain_pp": gain("attribution_accuracy_pct"),
            "paragraph_coverage_gain_pp": gain("paragraph_coverage_pct"),
            "accepted_items_gain": gain("accepted"),
        },
        "final_metrics": final,
        "quarantined_count": quarantined,
        "verdict": verdict,
        "interpretation": ("Compare baseline (first audit of the raw model draft) with final "
                           "(audit after the bounded repair loop). Positive *_gain_pp values are "
                           "percentage-point quality gains attributable to the audit-repair loop; "
                           "an unaudited baseline pipeline would have shipped the baseline numbers."),
    }


def main():
    ap = argparse.ArgumentParser(description="Assemble final deliverables and audit certificate")
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    work, outdir = args.work, args.output
    os.makedirs(outdir, exist_ok=True)

    corpus = load_json(os.path.join(work, "corpus.json"))
    graph = load_json(os.path.join(work, "graph.json"))
    queries = load_json(os.path.join(work, "queries.json"))
    case_id = corpus.get("case_id")
    contract = corpus.get("output_contract") or {}

    certificate = build_certificate(work, case_id)
    dump_json(certificate, os.path.join(work, "audit_certificate.json"))

    quarantine_path = os.path.join(work, "quarantine.json")
    if os.path.isfile(quarantine_path):
        quarantine = load_json(quarantine_path)
    else:
        quarantine = {"note": "no items rejected; quarantine empty", "items": []}

    uncertainty = []
    final_metrics = certificate.get("final_metrics") or {}
    cov = final_metrics.get("paragraph_coverage_pct")
    if isinstance(cov, (int, float)) and cov < 100.0:
        uncertainty.append("paragraph coverage is %.1f%%; uncited paragraphs are listed in "
                           "audit_report.json -> uncited_paragraphs" % cov)
    for r in queries.get("results") or []:
        for u in r.get("undetermined") or []:
            uncertainty.append("[%s] %s" % (r.get("query_id"), u))
    for w in corpus.get("discovery_warnings") or []:
        uncertainty.append("[discover] %s" % w)
    uncertainty = sorted(set(uncertainty))

    evidence_notes = sorted([
        "every node/edge carries source_id + paragraph_id (organizer JATS paragraph id; "
        "this package has no PDF page numbers) + a verbatim quote verified as an exact "
        "substring of the cited paragraph by scripts/audit.py",
        "audit verdicts per item are in audit_report.json; failing items were repaired via "
        "repair_queue.json (bounded loop, max 2 iterations)",
        "numeric conflicts under different conditions are preserved as separate claim nodes "
        "linked by conflicts-with edges (never merged)",
        "cross-paper merges require a normalized_key + explicit reason; explicit non-merges "
        "are recorded in graph.nonmerges",
        "rejected items (still failing after the final audit) are in quarantine.json and "
        "excluded from the graph",
    ])

    status = "success"
    status_reason = "all stages completed"
    if certificate.get("verdict") not in ("pass",):
        status = "partial"
        status_reason = "audit verdict=%s; see quarantine.json and audit_report.json" % certificate.get("verdict")

    available = {
        "case_id": case_id,
        "status": status,
        "status_reason": status_reason,
        "graph": graph,
        "queries": queries.get("results") or [],
        "evidence_notes": evidence_notes,
        "unreported": graph.get("unreported") or [],
        "uncertainty": uncertainty,
        "audit_certificate": certificate,
        "quarantine": quarantine,
        "sources": sorted((corpus.get("sources") or {}).keys()),
    }

    result = {"case_id": case_id}
    missing_keys = []
    if isinstance(contract, dict) and contract:
        for key in sorted(contract.keys()):
            if key in available:
                result[key] = available[key]
            else:
                result[key] = None
                missing_keys.append(key)
    else:
        for key in sorted(available.keys()):
            result[key] = available[key]
    if missing_keys:
        result.setdefault("uncertainty", [])
        result["uncertainty"] = sorted(set(result["uncertainty"] + [
            "output_contract key '%s' could not be produced by this pipeline; set to null" % k
            for k in missing_keys]))
    result["status"] = status
    result["status_reason"] = status_reason
    result["sources"] = available["sources"]
    result["run_meta"] = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pipeline": "c-evidence-audit-loop-kg",
        "note": "wall-clock fields live only inside run_meta; all other artifacts are deterministic",
    }

    dump_json(result, os.path.join(outdir, "result.json"))
    for name in ("graph.json", "queries.json", "audit_certificate.json", "quarantine.json",
                 "audit_report.json", "repair_queue.json"):
        src = os.path.join(work, name)
        if os.path.isfile(src):
            dump_json(load_json(src), os.path.join(outdir, name))

    print("assemble: result.json status=%s | certificate verdict=%s "
          "(quote %s%% -> %s%%, addr %s%% -> %s%%)" % (
              status, certificate.get("verdict"),
              (certificate.get("iterations") or [{}])[0].get("metrics", {}).get("quote_precision_pct"),
              final_metrics.get("quote_precision_pct"),
              (certificate.get("iterations") or [{}])[0].get("metrics", {}).get("address_validity_pct"),
              final_metrics.get("address_validity_pct")))
    print("assemble: deliverables written to %s" % outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
