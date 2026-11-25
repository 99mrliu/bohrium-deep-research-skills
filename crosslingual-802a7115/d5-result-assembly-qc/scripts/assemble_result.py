#!/usr/bin/env python3
"""assemble_result.py — assemble /app/output/result.json for the Harbor
runtime contract of the cross-lingual retrieval challenge.

Reads /input/case.json (case_id, output_contract) plus an Agent-prepared
values file (hits, coverage, sources, uncertainty, change_records, status,
and any case-specific fields) and produces result.json that:

- carries the true case_id from case.json (never guessed);
- mirrors EVERY field named in output_contract — fields the Agent did not
  supply are written as null and explicitly logged in change_records and
  uncertainty instead of being silently dropped or fabricated;
- guarantees the honesty scaffolding exists: status, sources, uncertainty,
  change_records arrays/objects even when empty;
- refuses to mark status=ok when hits are empty unless an explicit
  empty-result note is present.

Stdlib only, offline. Exit code 0 on success, 2 when case.json is unreadable
(a minimal failed result.json is still written).
"""
import argparse
import json
import os
import sys

SCAFFOLD = {
    "sources": list,
    "uncertainty": list,
    "change_records": list,
}


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def contract_keys(output_contract):
    if isinstance(output_contract, dict):
        return list(output_contract.keys())
    if isinstance(output_contract, list):
        keys = []
        for item in output_contract:
            if isinstance(item, str):
                keys.append(item)
            elif isinstance(item, dict) and item.get("name"):
                keys.append(item["name"])
        return keys
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--values", required=True,
                    help="Agent-prepared JSON with result field values")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    result_path = os.path.join(args.out, "result.json")

    try:
        case = load_json(args.case)
    except Exception as exc:  # noqa: BLE001
        minimal = {
            "case_id": None,
            "status": "failed",
            "uncertainty": [f"case.json unreadable at {args.case}: {exc}"],
            "sources": [], "change_records": [
                "assemble_result: wrote minimal failed result.json"],
        }
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(minimal, fh, ensure_ascii=False, indent=2)
        print(json.dumps({"status": "failed", "reason": str(exc)}))
        return 2

    case_id = case.get("case_id") or case.get("id")
    output_contract = case.get("output_contract")
    values = load_json(args.values)
    if not isinstance(values, dict):
        values = {"value": values}

    change_records = list(values.get("change_records", []))
    uncertainty = list(values.get("uncertainty", []))

    result = dict(values)
    result["case_id"] = case_id
    if result.get("case_id") != case_id:
        change_records.append("case_id forced to case.json value")

    for key, typ in SCAFFOLD.items():
        if not isinstance(result.get(key), typ):
            result[key] = [] if typ is list else {}
    result["uncertainty"] = uncertainty
    result["change_records"] = change_records

    for key in contract_keys(output_contract):
        if key not in result:
            result[key] = None
            change_records.append(
                f"output_contract field '{key}' not supplied; written as null")
            uncertainty.append(
                f"output_contract field '{key}' has no value (null); "
                "not fabricated")

    status = result.get("status")
    hits = result.get("hits")
    if status not in ("ok", "partial", "failed"):
        status = "partial"
        change_records.append(
            f"status normalized to 'partial' (was {result.get('status')!r})")
    if status == "ok" and isinstance(hits, list) and not hits:
        has_note = any("empty" in str(u).lower() or "no result" in str(u).lower()
                       or "空" in str(u) for u in uncertainty)
        if not has_note:
            status = "partial"
            uncertainty.append(
                "hits is empty but no empty-result justification was given; "
                "status downgraded to partial")
            change_records.append("status downgraded ok->partial: empty hits")
    result["status"] = status

    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps({
        "status": status, "case_id": case_id,
        "contract_fields": len(contract_keys(output_contract)),
        "nulled_fields": [k for k in contract_keys(output_contract)
                          if result.get(k) is None],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
