#!/usr/bin/env python3
"""Contract-driven result.json assembler/checker for incremental-import-reconciler.

The case file (/input/case.json) is the single source of truth: the original
case_id and EVERY field named by output_contract are carried into
/app/output/result.json. Fields are populated only from artifacts that really
exist on disk (heuristic field-name -> artifact mapping, overridable with
--set); input files are hashed into `sources`; unfinished work stays visible
through status=partial and uncertainty notes instead of being papered over.

Usage:
  make_result.py --case /input/case.json --out /app/output/result.json --status partial
  make_result.py --case /input/case.json --out /app/output/result.json --status success
  make_result.py --case /input/case.json --out /app/output/result.json \
      --set import_manifest=/app/output/import_manifest.json
  make_result.py --case /input/case.json --out /app/output/result.json --validate
"""
import argparse
import hashlib
import json
import os
import sys

# Field-name keywords -> candidate artifacts under the output directory.
# Evaluated top to bottom; the first keyword that matches the field name wins,
# then the first file of that row that exists. Tuned to the artifacts this
# skill produces: import_manifest.json, updated_state.json,
# reconciliation_report.md, change_records.jsonl, evidence/evidence_index.json.
ARTIFACT_HINTS = [
    (("manifest", "classification", "candidate", "pool", "decision", "results"),
     ["import_manifest.json"]),
    (("state", "library"),
     ["updated_state.json"]),
    (("change", "audit", "jsonl", "applied"),
     ["change_records.jsonl"]),
    (("report", "reconciliation", "status", "summary", "uncertainty"),
     ["reconciliation_report.md"]),
    (("evidence", "provenance", "trace", "hash", "log"),
     ["evidence/evidence_index.json", "reconciliation_report.md"]),
]

ALLOWED_STATUS = ("success", "partial", "failed")


def file_sha12(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def contract_field_names(case):
    contract = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        names = []
        for item in contract:
            names.append(item["name"] if isinstance(item, dict) and "name" in item
                         else str(item))
        return names
    return []


def guess_artifact(field_name, out_dir):
    lowered = field_name.lower()
    for keywords, relatives in ARTIFACT_HINTS:
        if any(k in lowered for k in keywords):
            for rel in relatives:
                candidate = os.path.join(out_dir, rel)
                if os.path.isfile(candidate):
                    return candidate
    return None


def hash_input_tree(case_path):
    """Every file in the input directory tree becomes a hashed source entry."""
    root = os.path.dirname(os.path.abspath(case_path))
    sources = []
    for dirpath, _sub, files in os.walk(root):
        for fn in sorted(files):
            full = os.path.join(dirpath, fn)
            if os.path.isfile(full):
                sources.append({"path": full,
                                "sha256_12": file_sha12(full),
                                "bytes": os.path.getsize(full)})
    return sources


def assemble(case_path, out_path, status, explicit_sets, uncertainty_notes):
    case = read_json(case_path)
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    result = read_json(out_path) if os.path.isfile(out_path) else {}
    result["case_id"] = case.get("case_id") or case.get("id") or "UNKNOWN"
    result["status"] = status
    for field in contract_field_names(case):
        if field in explicit_sets:
            result[field] = explicit_sets[field]
        elif not result.get(field):
            artifact = guess_artifact(field, out_dir)
            if artifact:
                result[field] = artifact
            else:
                result.setdefault(field, None)
    result["sources"] = hash_input_tree(case_path)
    notes = list(result.get("uncertainty") or [])
    for note in uncertainty_notes:
        if note not in notes:
            notes.append(note)
    result["uncertainty"] = notes
    result["generated_by"] = ("incremental-import-reconciler make_result.py "
                              "(offline, stdlib)")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return result


def check(case_path, out_path):
    problems = []
    if not os.path.isfile(out_path):
        print("VALIDATE ERROR: result file does not exist: %s" % out_path)
        return 1
    case = read_json(case_path)
    result = read_json(out_path)
    expected_id = case.get("case_id") or case.get("id")
    if expected_id and result.get("case_id") != expected_id:
        problems.append("case_id mismatch: result has %r, case has %r"
                        % (result.get("case_id"), expected_id))
    for field in contract_field_names(case):
        value = result.get(field)
        if value in (None, "", [], {}):
            problems.append("contract field %r is empty" % field)
        elif isinstance(value, str) and value.startswith("/") \
                and not os.path.isfile(value):
            problems.append("contract field %r points to missing file %s"
                            % (field, value))
    if result.get("status") not in ALLOWED_STATUS:
        problems.append("status must be one of %s" % (ALLOWED_STATUS,))
    if result.get("status") == "success" and result.get("uncertainty"):
        problems.append("status=success but uncertainty is non-empty: %s"
                        % result["uncertainty"])
    for problem in problems:
        print("VALIDATE ERROR:", problem)
    if not problems:
        print("VALIDATE OK: %d contract fields, case_id=%s, status=%s"
              % (len(contract_field_names(case)), result.get("case_id"),
                 result.get("status")))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", choices=ALLOWED_STATUS, default=None)
    ap.add_argument("--set", dest="explicit_sets", action="append", default=[],
                    metavar="FIELD=PATH",
                    help="pin a contract field to a concrete artifact path")
    ap.add_argument("--uncertainty", action="append", default=[],
                    help="append an honest limitation note")
    ap.add_argument("--validate", action="store_true",
                    help="check an existing result.json instead of writing one")
    args = ap.parse_args()
    if args.validate:
        sys.exit(check(args.case, args.out))
    explicit = {}
    for pair in args.explicit_sets:
        key, _eq, value = pair.partition("=")
        explicit[key.strip()] = value.strip()
    result = assemble(args.case, args.out, args.status or "partial",
                      explicit, args.uncertainty)
    fields = contract_field_names(read_json(args.case))
    filled = sum(1 for f in fields if result.get(f))
    print("WROTE %s status=%s contract_fields_filled=%d/%d uncertainty=%d"
          % (args.out, result["status"], filled, len(fields),
             len(result["uncertainty"])))


if __name__ == "__main__":
    main()
