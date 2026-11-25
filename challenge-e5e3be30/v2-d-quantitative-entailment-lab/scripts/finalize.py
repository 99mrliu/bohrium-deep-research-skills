#!/usr/bin/env python3
"""Merge explicit Agent semantic verdicts with computed entailment evidence.

The verifier never maps within_tolerance to supported or outside_tolerance to
contradicted. Each claim's four-level verdict and rationale must come from the
Agent-authored JSON passed with --verdicts.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
from contract import VERDICTS, assemble, audit, case_identifier, find_contract
from quantlib import InputError, read_json, write_json


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def claim_list(document):
    claims = document.get("claims") if isinstance(document, dict) else document
    if not isinstance(claims, list):
        raise InputError("claims document must contain a claims list")
    return claims


def draft_verdicts(claims, report):
    return [
        {"claim_id": claim["id"], "question": claim["question"], "verdict": None,
         "verdict_origin": "agent_required", "rationale": "Pending Agent semantic adjudication; computations are not verdicts.",
         "quantitative_evidence": [item for item in report.get("derived", []) if item["claim_id"] == claim["id"]]}
        for claim in claims
    ]


def integrate_verdicts(claims, report, document):
    if not isinstance(document, dict) or document.get("adjudicator") != "agent":
        raise InputError("verdicts document must explicitly declare adjudicator=agent")
    supplied = document.get("verdicts")
    if not isinstance(supplied, list):
        raise InputError("verdicts document requires a verdicts list")
    by_claim = {}
    for item in supplied:
        if not isinstance(item, dict) or not isinstance(item.get("claim_id"), str):
            raise InputError("each Agent verdict requires claim_id")
        if item["claim_id"] in by_claim:
            raise InputError("duplicate Agent verdict: " + item["claim_id"])
        by_claim[item["claim_id"]] = item
    expected = {claim["id"] for claim in claims}
    if set(by_claim) != expected:
        raise InputError("Agent verdict ids differ from claim ids: missing=%s extra=%s" %
                         (sorted(expected - set(by_claim)), sorted(set(by_claim) - expected)))
    evidence_ids = {item["id"] for item in report.get("derived", [])}
    evidence_ids.update(item["id"] for item in report.get("statistical_tests", []))
    evidence_ids.update(item["id"] for item in report.get("observations", []))
    observation_ids = {item["id"] for item in report.get("observations", [])}
    output = []
    for claim in claims:
        item = by_claim[claim["id"]]
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            raise InputError(claim["id"] + " verdict must be one of " + ", ".join(sorted(VERDICTS)))
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise InputError(claim["id"] + " requires an Agent rationale")
        cited = item.get("evidence_ids", [])
        if not isinstance(cited, list) or any(value not in evidence_ids for value in cited):
            raise InputError(claim["id"] + " cites an unknown or non-list evidence_ids")
        source_ids = item.get("source_ids", [])
        if not isinstance(source_ids, list) or any(value not in observation_ids for value in source_ids):
            raise InputError(claim["id"] + " cites an unknown observation in source_ids")
        calculations = [record for record in report.get("derived", []) if record["claim_id"] == claim["id"]]
        if calculations and not cited:
            raise InputError(claim["id"] + " has computed evidence but does not cite it")
        output.append({
            "claim_id": claim["id"], "question": claim["question"], "verdict": verdict,
            "verdict_origin": "agent", "rationale": rationale,
            "evidence_ids": cited, "source_ids": source_ids,
            "quantitative_evidence": calculations,
        })
    return output


def verdict_summary(verdicts):
    counts = {value: 0 for value in sorted(VERDICTS)}
    for item in verdicts:
        if item.get("verdict") in counts:
            counts[item["verdict"]] += 1
    counts["unresolved"] = sum(item.get("verdict") is None for item in verdicts)
    return counts


def finalize(case, claims_document, report, verdict_document, context):
    claims = claim_list(claims_document)
    contract = find_contract(case)
    now = timestamp()
    if verdict_document is None:
        verdicts = draft_verdicts(claims, report)
        status = "partial"
        uncertainties = context.get("uncertainty", []) + ["Agent semantic adjudication has not been integrated; null verdicts are not evidence judgments."]
        action = "computed_evidence_draft_written"
    else:
        verdicts = integrate_verdicts(claims, report, verdict_document)
        status = "success"
        uncertainties = list(context.get("uncertainty", []))
        action = "agent_verdicts_integrated"
    changes = list(context.get("change_records", [])) + [{"at": now, "action": action}]
    full_context = dict(context)
    full_context.update({
        "case_id": case_identifier(case), "claim_verdicts": verdicts, "status": status,
        "uncertainty": uncertainties, "change_records": changes,
        "quantitative_report": report, "derived": report.get("derived", []),
        "observations": report.get("observations", []), "warnings": report.get("warnings", []),
        "summary": verdict_summary(verdicts),
    })
    result, field_status = assemble(contract, full_context)
    verification = audit(result, contract, field_status, len(claims))
    if status == "success" and (verification["errors"] or verification["unresolved_fields"]):
        status = "partial"
        full_context["status"] = status
        full_context["uncertainty"] = uncertainties + ["Contract or final coverage checks did not pass; status downgraded to partial."]
        result, field_status = assemble(contract, full_context)
        verification = audit(result, contract, field_status, len(claims))
    return result, verification


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--verdicts", help="Agent-authored verdict JSON; omitted means an honest partial draft")
    parser.add_argument("--context", required=True, help="run-context.json created by run.py")
    parser.add_argument("--out", required=True)
    parser.add_argument("--verification-out")
    args = parser.parse_args(argv)
    try:
        result, verification = finalize(
            read_json(args.case), read_json(args.claims), read_json(args.report),
            read_json(args.verdicts) if args.verdicts else None, read_json(args.context))
        write_json(args.out, result)
        verification_path = args.verification_out or str(Path(args.out).parent / "verification.json")
        write_json(verification_path, verification)
        print({"status": result["status"], "result": args.out, "contract_check": verification["contract_check"]})
        return 0 if result["status"] == "success" else 2
    except (InputError, OSError, ValueError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
