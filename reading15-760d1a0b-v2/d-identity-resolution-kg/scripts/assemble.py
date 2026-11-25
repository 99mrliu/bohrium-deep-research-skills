#!/usr/bin/env python3
"""assemble.py — build result.json mirroring the case's output_contract, and
copy the signature artifacts to the output directory.

Reads work artifacts (corpus, graph, query_results, verify_report,
extraction_report, merge/nonmerge/conflict registries) and writes
<output>/result.json plus copies of graph.json, merge_ledger.json,
nonmerge_registry.json, conflict_registry.json, entity_map.json,
query_results.json, verify_report.json.

Contract mirroring is dynamic: every key declared in case.json's
output_contract is produced; a key that cannot be produced is set to null and
recorded in "unproduced_contract_keys" — never silently omitted. Safe to run
early: missing stages yield an honest "partial" status.

Usage: python3 assemble.py --work /app/work --output /app/output
"""
import argparse
import os
import shutil
import sys

import kgcommon as K

SIGNATURE_FILES = ["graph.json", "merge_ledger.json", "nonmerge_registry.json",
                   "conflict_registry.json", "entity_map.json",
                   "query_results.json", "verify_report.json"]


def _try_load(work, name, missing):
    path = os.path.join(work, name)
    if not os.path.isfile(path):
        missing.append(name)
        return None
    try:
        return K.load_json(path)
    except Exception as exc:
        missing.append("%s (unparsable: %s)" % (name, exc))
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    work, output = args.work, args.output
    os.makedirs(output, exist_ok=True)

    missing = []
    corpus = _try_load(work, "corpus.json", missing)
    if corpus is None:
        print("ERROR: corpus.json missing; run discover.py first", file=sys.stderr)
        return 2
    graph = _try_load(work, "graph.json", missing)
    queries = _try_load(work, "query_results.json", missing)
    verify = _try_load(work, "verify_report.json", missing)
    extraction = _try_load(work, "extraction_report.json", missing)
    merges = _try_load(work, "merge_ledger.json", missing)
    nonmerges = _try_load(work, "nonmerge_registry.json", missing)
    conflicts = _try_load(work, "conflict_registry.json", missing)
    adj_report = _try_load(work, "adjudication_report.json", missing)

    contract = corpus.get("output_contract") or {}
    unproduced = []

    evidence_notes = []
    if extraction:
        evidence_notes.extend(extraction.get("notes", []))
    if verify:
        evidence_notes.append(
            "quote-integrity: %d/%d evidence items verified as exact substrings"
            % (verify.get("evidence_passed", 0), verify.get("evidence_checked", 0)))
    for w in corpus.get("warnings", []):
        evidence_notes.append("discovery warning: %s" % w)

    uncertainty = []
    if graph:
        singles = [n["canonical_surface"] for n in graph["nodes"]
                   if n.get("singleton")]
        if singles:
            uncertainty.append("singleton entities not involved in any merge "
                               "decision: %s" % ", ".join(sorted(singles)))
    if adj_report:
        if adj_report.get("defaulted"):
            uncertainty.append("%d candidate pair(s) fell back to conservative "
                               "default nonmerge" % adj_report["defaulted"])
        if adj_report.get("quarantine"):
            uncertainty.append("%d adjudication decision(s) quarantined; see "
                               "adjudication_report.json"
                               % len(adj_report["quarantine"]))
    if queries:
        for q in queries.get("queries", []):
            if q.get("status") != "answered":
                uncertainty.append("query %s status=%s (%s)"
                                   % (q.get("query_id"), q.get("status"),
                                      q.get("note", "")))

    identity_resolution = None
    if merges is not None and nonmerges is not None and conflicts is not None:
        identity_resolution = {
            "merge_ledger": merges,
            "nonmerge_registry": nonmerges,
            "conflict_registry": conflicts,
        }

    available = {
        "case_id": corpus.get("case_id"),
        "status": None,  # filled below
        "graph": graph,
        "queries": (queries or {}).get("queries"),
        "evidence_notes": evidence_notes,
        "unreported": (extraction or {}).get("unreported"),
        "uncertainty": uncertainty,
        "identity_resolution": identity_resolution,
    }

    result = {}
    for key in sorted(contract):
        if key == "status":
            continue
        value = available.get(key)
        if value is None:
            unproduced.append({"key": key,
                               "reason": "stage output missing or unavailable"})
        result[key] = value
    for key in sorted(available):  # bundle extras beyond the declared contract
        if key not in result and key != "status":
            result[key] = available[key]

    verify_ok = bool(verify) and verify.get("verdict") == "pass"
    if missing:
        status, reason = "partial", "missing stage outputs: %s" % ", ".join(missing)
    elif unproduced:
        status, reason = "partial", "contract keys set to null: %s" % ", ".join(
            u["key"] for u in unproduced)
    elif not verify_ok:
        status, reason = "partial", "evidence verification did not pass cleanly"
    else:
        status, reason = "success", None
    result["status"] = status
    if reason:
        result["status_reason"] = reason
    result["unproduced_contract_keys"] = unproduced
    result["sources"] = [{
        "source_id": s["source_id"], "role": s["role"], "doi": s["doi"],
        "title": s["title"], "authors": s["authors"],
        "sha256_ok": s.get("sha256_ok"),
        "paragraph_count": len(s["paragraphs"]),
    } for s in corpus.get("sources", [])]

    K.dump_json(result, os.path.join(output, "result.json"))
    copied = []
    for name in SIGNATURE_FILES:
        src = os.path.join(work, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(output, name))
            copied.append(name)
    print("assemble: status=%s; result.json + %d artifact(s) -> %s"
          % (status, len(copied), output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
