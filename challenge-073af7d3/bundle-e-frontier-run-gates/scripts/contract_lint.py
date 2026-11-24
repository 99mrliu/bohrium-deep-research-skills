#!/usr/bin/env python3
"""contract_lint.py — enforce the output contract of case.json on result.json.

Rules (see references/contract_rules.md):
  R1 status: result.status must be in the status enum.
  R2 case_id: result.case_id must match case.case_id.
  R3 fields: every field in case.output_contract.fields must be present.
  R4 empty fields: a field that is empty (null/""/[]/{}) is a violation.
     A field that is a placeholder object — a dict whose ONLY key is a
     non-empty "note" — is allowed only when status is partial / blocked_* /
     failed; under status "ok" it is a violation.
  R5 evidence: every evidence reference of form {"record_id": "..."} anywhere
     in the result must resolve against the evidence matrix (when given).

If case.json has no output_contract, the four canonical deliverable fields are
assumed and the assumption is reported (not a violation).

Exit 0 when clean, 1 on any violation or unreadable input. Stdlib only.
"""
import argparse
import json
import os
import sys

STATUS_ENUM = ("ok", "partial", "blocked_no_corpus", "blocked_no_contract", "failed")
NON_OK_STATUSES = ("partial", "blocked_no_corpus", "blocked_no_contract", "failed")
CANONICAL_FIELDS = ("trend_summary", "theme_evolution",
                    "representative_works", "research_gaps")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_ids(evidence_matrix_path):
    ids = set()
    if not evidence_matrix_path:
        return ids
    with open(evidence_matrix_path, encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        return ids
    rows = []
    try:
        data = json.loads(text)
        rows = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    for row in rows:
        if isinstance(row, dict):
            rid = row.get("record_id") or row.get("id")
            if isinstance(rid, str):
                ids.add(rid)
    return ids


def field_state(value):
    """filled | noted_empty (dict with only a non-empty note) | empty."""
    if value is None or value == "" or value == [] or value == {}:
        return "empty"
    if isinstance(value, dict) and set(value.keys()) <= {"note"} \
            and str(value.get("note", "")).strip():
        return "noted_empty"
    return "filled"


def find_evidence_refs(obj, path="$"):
    """Yield (json_path, record_id) for every dict containing a record_id str."""
    refs = []
    if isinstance(obj, dict):
        rid = obj.get("record_id")
        if isinstance(rid, str):
            refs.append((path + ".record_id", rid))
        for key in sorted(obj.keys()):
            refs.extend(find_evidence_refs(obj[key], "%s.%s" % (path, key)))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            refs.extend(find_evidence_refs(item, "%s[%d]" % (path, i)))
    return refs


def lint(case_path, result_path, evidence_matrix_path=None):
    """Return (report_dict, violations_list). Pure function; no I/O side effects."""
    violations = []
    notes = []

    case = load_json(case_path)
    result = load_json(result_path)

    case_id = case.get("case_id")
    contract = case.get("output_contract") or {}
    fields = list(contract.get("fields") or [])
    if not fields:
        fields = list(CANONICAL_FIELDS)
        notes.append("case.json has no output_contract.fields; assumed canonical "
                     "fields: %s (record this assumption in the result)"
                     % ", ".join(fields))

    # R1 status enum
    status = result.get("status")
    if status not in STATUS_ENUM:
        violations.append(
            "invalid_status $.status: %r not in %s"
            % (status, list(STATUS_ENUM)))

    # R2 case_id match
    if result.get("case_id") != case_id:
        violations.append(
            "case_id_mismatch $.case_id: result has %r, case.json has %r"
            % (result.get("case_id"), case_id))

    # R3 + R4 fields
    for f in fields:
        if f not in result:
            violations.append(
                "missing_field $.%s: contract field absent from result" % f)
            continue
        state = field_state(result[f])
        if state == "empty":
            violations.append(
                "empty_field $.%s: empty content allowed only as a dict with a "
                "non-empty 'note' under status partial/blocked_*/failed" % f)
        elif state == "noted_empty" and status == "ok":
            violations.append(
                "placeholder_under_ok $.%s: placeholder note object but "
                "status is 'ok'" % f)

    # R5 evidence references
    refs = find_evidence_refs(result)
    ids = load_ids(evidence_matrix_path) if evidence_matrix_path else set()
    if evidence_matrix_path:
        for jp, rid in refs:
            if rid not in ids:
                violations.append(
                    "dangling_evidence %s: %r not found in evidence matrix %s"
                    % (jp, rid, os.path.basename(evidence_matrix_path)))

    report = {
        "case": os.path.abspath(case_path),
        "result": os.path.abspath(result_path),
        "case_id": case_id,
        "status": status,
        "fields_checked": len(fields),
        "refs_checked": len(refs),
        "notes": notes,
        "violations": violations,
        "verdict": "clean" if not violations else "violations",
    }
    return report, violations


def main(argv=None):
    ap = argparse.ArgumentParser(description="Output-contract linter.")
    ap.add_argument("--case", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--evidence-matrix", default=None)
    args = ap.parse_args(argv)
    try:
        report, violations = lint(args.case, args.result, args.evidence_matrix)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "error",
                          "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
