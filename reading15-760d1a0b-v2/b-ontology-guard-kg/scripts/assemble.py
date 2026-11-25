#!/usr/bin/env python3
"""assemble.py — assemble result.json mirroring case.json's output_contract.

Reads <work> artifacts (case_snapshot.json, graph.json, query_results.json,
validation_report.json, quarantine.json, merge_ledger.json,
nonmerge_registry.json) and writes <output>/result.json plus copies of the
signature artifacts (validation_report.json, quarantine.json, graph.json,
query_results.json).

Contract discipline: result.json ALWAYS contains `case_id` plus every key
declared in the case's output_contract. A key that cannot be produced is set
to null with the reason recorded in `contract_notes` — never silently omitted.

Usage:
    python3 assemble.py --work /app/work --output /app/output

Python 3 standard library only. Deterministic output (sorted keys; the only
non-deterministic data, if any, would live under run_meta — none is written).
"""
import argparse
import json
import os
import shutil
import sys

BASE_KEYS = ["case_id", "status", "graph", "queries", "evidence_notes",
             "unreported", "uncertainty"]


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Assemble result.json from work artifacts.")
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    os.makedirs(args.output, exist_ok=True)

    case = load_json(os.path.join(args.work, "case_snapshot.json"), {})
    graph = load_json(os.path.join(args.work, "graph.json"))
    queries = load_json(os.path.join(args.work, "query_results.json"))
    vreport = load_json(os.path.join(args.work, "validation_report.json"))
    quarantine = load_json(os.path.join(args.work, "quarantine.json"))
    ledger = load_json(os.path.join(args.work, "merge_ledger.json"))
    registry = load_json(os.path.join(args.work, "nonmerge_registry.json"))
    state = load_json(os.path.join(args.work, "validation_state.json"), {})

    contract = case.get("output_contract")
    contract_keys = sorted(contract.keys()) if isinstance(contract, dict) else []
    for k in BASE_KEYS:
        if k not in contract_keys:
            contract_keys.append(k)

    missing = []
    if graph is None:
        missing.append("graph.json (run discover/validate/build first)")
    if queries is None:
        missing.append("query_results.json (run query.py)")
    if vreport is None:
        missing.append("validation_report.json (run validate_ontology.py)")

    notes = state.get("notes", [])
    evidence_notes = []
    if ledger and ledger.get("merges"):
        evidence_notes.append("cross-paper merges applied with reasons; see merge_ledger.json")
    if registry and registry.get("nonmerges"):
        evidence_notes.append("explicit non-merges recorded; see nonmerge_registry.json")
    if quarantine and quarantine.get("count"):
        evidence_notes.append("%d extraction item(s) quarantined by ontology validation; "
                              "see quarantine.json" % quarantine["count"])
    evidence_notes += [n.get("text", "") for n in notes if isinstance(n, dict)]

    uncertainty = []
    if queries:
        for r in queries.get("results", []):
            for u in r.get("undetermined", []):
                uncertainty.append("query %s: %s" % (r.get("query_id"), u))

    # decide honest status BEFORE mirroring the contract
    if missing and graph is None:
        status, status_reason = "unable", "missing artifacts: " + "; ".join(missing)
    elif missing:
        status, status_reason = "partial", "missing artifacts: " + "; ".join(missing)
    else:
        status, status_reason = "success", None

    produced = {
        "case_id": case.get("case_id"),
        "status": status,
        "graph": graph,
        "queries": (queries or {}).get("results"),
        "evidence_notes": evidence_notes,
        "unreported": state.get("unreported", []),
        "uncertainty": sorted(uncertainty),
        # bundle-specific extra keys (declared in the synthetic case contract too)
        "validation_report": vreport,
        "quarantine": quarantine,
        "merge_ledger": ledger,
        "nonmerge_registry": registry,
    }

    result = {}
    contract_notes = {}
    for key in contract_keys:
        if key in produced and produced[key] is not None:
            result[key] = produced[key]
        else:
            result[key] = None
            contract_notes[key] = "could not be produced: %s" % (
                "; ".join(missing) if missing else "not declared by this pipeline")
    # extra produced keys that were not in the contract are still attached
    for key, val in produced.items():
        if key not in result and val is not None:
            result[key] = val
    if contract_notes:
        result["contract_notes"] = {k: contract_notes[k] for k in sorted(contract_notes)}
    result["sources"] = load_json(os.path.join(args.work, "corpus.json"), {}).get("sources", {})
    if case.get("notice"):
        result["notice"] = case["notice"]
    if status_reason:
        result["status_reason"] = status_reason

    dump_json(os.path.join(args.output, "result.json"), result)
    for name in ("graph.json", "query_results.json", "validation_report.json",
                 "quarantine.json", "merge_ledger.json", "nonmerge_registry.json"):
        src = os.path.join(args.work, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(args.output, name))
    print("assemble: status=%s, contract keys=%d, notes=%d -> %s"
          % (result["status"], len(contract_keys), len(contract_notes), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
