#!/usr/bin/env python3
"""gate_check.py — stage gates G0..G8 for the frontier-run-gates bundle.

Gates are checkpoints, not substitutes for judgment (see references/gates.md):
  G0 contract read        case.json parsed; case_id + output_contract fields in manifest
  G1 corpus ingested      canon.jsonl exists; every record has id + year
  G2 slices computed      slices.json exists; sum(annual counts) == records with year
  G3 themes computed      cohorts.json exists with year cohorts
  G4 representatives      representatives.json exists with non-empty phases
  G5 gaps recorded        gaps.json exists; "none" requires a non-empty reason
  G6 evidence integrity   every record_id cited in result_draft.json resolves in
                          evidence_matrix.jsonl
  G7 uncertainty          uncertainty section of result_draft.json is non-empty
  G8 contract lint        contract_lint clean on (case, result_draft, evidence matrix)

Usage:
  gate_check.py --work DIR            run all gates G0..G8
  gate_check.py --work DIR --gate G3  run a single gate

Prints JSON. Exit 1 if the requested gate (or any gate in a full run) fails.
Stdlib only. No network.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_manifest as rm  # noqa: E402
import contract_lint  # noqa: E402

GATE_NAMES = ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _missing(path, violations, what):
    if not os.path.isfile(path):
        violations.append("%s_missing: %s" % (what, os.path.basename(path)))
        return True
    return False


# ------------------------------------------------------------------- gates

def gate_g0(work, manifest):
    v = []
    case_info = (manifest or {}).get("case") or {}
    if not case_info:
        v.append("case_not_recorded: manifest has no `case` section "
                 "(run mini_pipeline or record the contract read)")
        return v
    if not case_info.get("case_id"):
        v.append("case_id_missing: manifest.case.case_id is empty")
    fields = case_info.get("output_contract_fields") or []
    if not fields:
        v.append("output_contract_missing: no output_contract fields recorded "
                 "(fall back to the four canonical fields and record the "
                 "assumption)")
    case_path = case_info.get("path")
    if case_path and os.path.isfile(case_path):
        try:
            load_json(case_path)
        except (OSError, json.JSONDecodeError) as exc:
            v.append("case_unparseable: %s" % exc)
    else:
        v.append("case_file_missing: %s" % case_path)
    return v


def gate_g1(work, manifest):
    v = []
    path = os.path.join(work, "canon.jsonl")
    if _missing(path, v, "canon"):
        return v
    rows = load_jsonl(path)
    if not rows:
        v.append("canon_empty: canon.jsonl has no records")
        return v
    bad = [r.get("id", "?") for r in rows
           if not r.get("id") or not isinstance(r.get("year"), int)]
    for rid in bad:
        v.append("canon_record_incomplete: record %r lacks id or integer year"
                 % rid)
    return v


def gate_g2(work, manifest):
    v = []
    path = os.path.join(work, "slices.json")
    if _missing(path, v, "slices"):
        return v
    slices = load_json(path)
    annual = slices.get("years") or []
    total = sum(int(a.get("count", 0)) for a in annual)
    with_year = slices.get("records_with_year")
    if total != with_year:
        v.append("count_closure_broken: sum(annual counts)=%d != "
                 "records_with_year=%r" % (total, with_year))
    canon_path = os.path.join(work, "canon.jsonl")
    if os.path.isfile(canon_path):
        canon = load_jsonl(canon_path)
        n = len([r for r in canon if isinstance(r.get("year"), int)])
        if n != with_year:
            v.append("canon_slice_mismatch: canon records with year=%d != "
                     "records_with_year=%r" % (n, with_year))
    return v


def gate_g3(work, manifest):
    v = []
    path = os.path.join(work, "cohorts.json")
    if _missing(path, v, "cohorts"):
        return v
    cohorts = load_json(path)
    if "years" not in cohorts:
        v.append("cohorts_shape: cohorts.json lacks the `years` list")
    return v


def gate_g4(work, manifest):
    v = []
    path = os.path.join(work, "representatives.json")
    if _missing(path, v, "representatives"):
        return v
    reps = load_json(path)
    phases = reps.get("phases") or []
    if not phases:
        v.append("representatives_empty: no phases drafted")
    for p in phases:
        if "candidates" not in p:
            v.append("phase_%s_no_candidates_key" % p.get("phase", "?"))
    return v


def gate_g5(work, manifest):
    v = []
    path = os.path.join(work, "gaps.json")
    if _missing(path, v, "gaps"):
        return v
    gaps = load_json(path)
    items = gaps.get("gaps") or []
    status = gaps.get("status", "")
    if not items or status in ("none", "none_recorded"):
        reason = str(gaps.get("reason", "")).strip()
        if not reason:
            v.append("gaps_none_without_reason: gaps recorded as none but no "
                     "reason given (honest none requires a stated reason)")
    return v


def gate_g6(work, manifest):
    v = []
    em_path = os.path.join(work, "evidence_matrix.jsonl")
    draft_path = os.path.join(work, "result_draft.json")
    if _missing(em_path, v, "evidence_matrix"):
        return v
    if _missing(draft_path, v, "result_draft"):
        return v
    ids = {r.get("record_id") for r in load_jsonl(em_path)
           if isinstance(r, dict) and r.get("record_id")}
    draft = load_json(draft_path)
    for jp, rid in contract_lint.find_evidence_refs(draft):
        if rid not in ids:
            v.append("dangling_evidence %s: %r not in evidence_matrix.jsonl"
                     % (jp, rid))
    return v


def gate_g7(work, manifest):
    v = []
    draft_path = os.path.join(work, "result_draft.json")
    if _missing(draft_path, v, "result_draft"):
        return v
    draft = load_json(draft_path)
    fields = ((manifest or {}).get("case") or {}).get(
        "output_contract_fields") or []
    unc_field = next((f for f in fields if "uncertainty" in f), "uncertainty")
    unc = draft.get(unc_field)
    if unc is None or unc == "" or unc == [] or unc == {}:
        v.append("uncertainty_empty: %s section of result_draft.json must be "
                 "non-empty (conflicts, biases, coverage limits, items needing "
                 "human verification)" % unc_field)
    return v


def gate_g8(work, manifest):
    v = []
    case_info = (manifest or {}).get("case") or {}
    case_path = case_info.get("path")
    draft_path = os.path.join(work, "result_draft.json")
    em_path = os.path.join(work, "evidence_matrix.jsonl")
    if not case_path or not os.path.isfile(case_path):
        return ["case_file_missing: cannot run contract lint"]
    if _missing(draft_path, v, "result_draft"):
        return v
    em = em_path if os.path.isfile(em_path) else None
    _, violations = contract_lint.lint(case_path, draft_path, em)
    v.extend(violations)
    return v


GATES = {
    "G0": gate_g0, "G1": gate_g1, "G2": gate_g2, "G3": gate_g3,
    "G4": gate_g4, "G5": gate_g5, "G6": gate_g6, "G7": gate_g7,
    "G8": gate_g8,
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage-gate checker G0..G8.")
    ap.add_argument("--work", required=True)
    ap.add_argument("--gate", default=None,
                    help="single gate, e.g. G3; default runs all gates")
    args = ap.parse_args(argv)

    if args.gate and args.gate not in GATES:
        print(json.dumps({"error": "unknown_gate", "gate": args.gate,
                          "known": GATE_NAMES}, ensure_ascii=False))
        return 1

    manifest = rm.load(args.work)
    if manifest is None:
        print(json.dumps({"status": "fail",
                          "violations": ["manifest_missing: %s" %
                                         os.path.join(args.work, "manifest.json")]},
                         ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    try:
        if args.gate:
            violations = GATES[args.gate](args.work, manifest)
            report = {"gate": args.gate,
                      "status": "pass" if not violations else "fail",
                      "violations": violations}
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not violations else 1

        results = []
        for name in GATE_NAMES:
            violations = GATES[name](args.work, manifest)
            results.append({"gate": name,
                            "status": "pass" if not violations else "fail",
                            "violations": violations})
        overall = "pass" if all(r["status"] == "pass" for r in results) else "fail"
        print(json.dumps({"status": overall, "gates": results},
                         ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if overall == "pass" else 1
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error",
                          "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
