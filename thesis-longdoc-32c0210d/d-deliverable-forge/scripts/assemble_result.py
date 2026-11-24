#!/usr/bin/env python3
"""assemble_result.py — collect result_parts/ and atomically emit result.json.

Six hard gates. Any gate failure -> explicit entry in "problems", result.json is
STILL written (honest partial on disk first), and the exit code is non-zero.

  G1 contract-field      every output_contract.fields key must have a part file
                         (<field>.json or <field>.md); missing -> null + problem
  G2 case-id             result case_id must equal case.json case_id; if
                         parts/_meta.json declares a case_id it must match too
  G3 output-path-ghost   every "/app/output/..." path mentioned in any text part
                         must exist inside the real output dir (no ghost paths)
  G4 artifact-exists     every file listed in parts/artifacts.json must exist
                         inside the output dir
  G5 status-consistency  status=complete with non-empty problems -> forced
                         downgrade to partial (recorded in "limits")
  G6 json-parseable      every parts/*.json must parse; final result.json is
                         re-read and re-parsed as a self-check

Part file convention (result_parts dir):
  <field>.json / <field>.md  value for contract field <field>
  _meta.json                 {"case_id": ..., "status": "complete"|"partial"|"failed"}
  artifacts.json             list of delivered file paths relative to the output dir
  sources.json               list of input materials actually used

Exit codes: 0 = all gates pass; 1 = at least one gate failed (result.json still
written, problems recorded); 2 = case.json unreadable (minimal failed result
written if --output given).
"""
import argparse
import json
import os
import re
import sys

OUTPUT_PREFIX = "/app/output/"
PATH_RE = re.compile(r"/app/output/[A-Za-z0-9._/\-]+")
RESERVED_PARTS = ("_meta.json", "artifacts.json", "sources.json")
VALID_STATUS = ("complete", "partial", "failed")


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def load_json_file(path):
    """Return (value, error). error is None on success."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, json.JSONDecodeError) as e:
        return None, str(e)


def iter_strings(value):
    """Yield every string inside a nested JSON value (deterministic order)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from iter_strings(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def main():
    ap = argparse.ArgumentParser(description="Assemble result_parts/ into result.json with six hard gates.")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--parts-dir", required=True, help="dir holding result part files")
    ap.add_argument("--output-dir", required=True, help="real output dir (stands in for /app/output)")
    ap.add_argument("--output", required=True, help="path of result.json to write (inside output-dir)")
    ap.add_argument("--note", default=None, help="optional note copied into result.json (e.g. synthetic marker)")
    args = ap.parse_args()

    problems = []   # gate failures, each {"gate", "field"?, "detail"}
    limits = []     # honest limitations / forced adjustments

    case, err = load_json_file(args.case)
    if err is not None:
        problems.append({"gate": "G2-case-id", "detail": "case.json unreadable: %s" % err})
        minimal = {"case_id": None, "status": "failed", "problems": problems, "limits": limits}
        if args.note:
            minimal["note"] = args.note
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            atomic_write_json(args.output, minimal)
        except OSError:
            pass
        print("FAIL G2: case.json unreadable: %s" % err, file=sys.stderr)
        return 2

    case_id = case.get("case_id")
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    fields = contract.get("fields") if isinstance(contract.get("fields"), list) else []
    if not case_id:
        problems.append({"gate": "G2-case-id", "detail": "case.json has no case_id"})
    if not fields:
        problems.append({"gate": "G1-contract-field",
                         "detail": "case.json output_contract.fields missing or empty"})

    # ---- reserved parts: _meta.json / artifacts.json / sources.json ----------
    meta, meta_err = load_json_file(os.path.join(args.parts_dir, RESERVED_PARTS[0]))
    if meta_err is not None and os.path.isfile(os.path.join(args.parts_dir, RESERVED_PARTS[0])):
        problems.append({"gate": "G6-json-parseable", "detail": "_meta.json unparseable: %s" % meta_err})
        meta = None
    if not isinstance(meta, dict):
        meta = {}

    artifacts, art_err = load_json_file(os.path.join(args.parts_dir, RESERVED_PARTS[1]))
    if art_err is not None and os.path.isfile(os.path.join(args.parts_dir, RESERVED_PARTS[1])):
        problems.append({"gate": "G6-json-parseable", "detail": "artifacts.json unparseable: %s" % art_err})
        artifacts = None
    if artifacts is None:
        artifacts = []
    if not isinstance(artifacts, list) or not all(isinstance(a, str) for a in artifacts):
        problems.append({"gate": "G4-artifact-exists",
                         "detail": "artifacts.json must be a JSON list of relative path strings"})
        artifacts = []

    sources, src_err = load_json_file(os.path.join(args.parts_dir, RESERVED_PARTS[2]))
    if src_err is not None and os.path.isfile(os.path.join(args.parts_dir, RESERVED_PARTS[2])):
        problems.append({"gate": "G6-json-parseable", "detail": "sources.json unparseable: %s" % src_err})
        sources = None
    if not isinstance(sources, list):
        sources = []

    # ---- G1 + G6: load one value per contract field --------------------------
    values = {}
    for field in fields:
        jpath = os.path.join(args.parts_dir, field + ".json")
        mpath = os.path.join(args.parts_dir, field + ".md")
        if field in ("_meta", "artifacts", "sources"):
            problems.append({"gate": "G1-contract-field", "field": field,
                             "detail": "field name collides with a reserved part name"})
            values[field] = None
        elif os.path.isfile(jpath):
            value, perr = load_json_file(jpath)
            if perr is not None:
                values[field] = None
                problems.append({"gate": "G6-json-parseable", "field": field,
                                 "detail": "%s.json unparseable: %s" % (field, perr)})
            else:
                values[field] = value
        elif os.path.isfile(mpath):
            try:
                with open(mpath, encoding="utf-8") as f:
                    values[field] = f.read()
            except OSError as e:
                values[field] = None
                problems.append({"gate": "G1-contract-field", "field": field,
                                 "detail": "cannot read %s.md: %s" % (field, e)})
        else:
            values[field] = None
            problems.append({"gate": "G1-contract-field", "field": field,
                             "detail": "no result part (%s.json or %s.md); filled null (honest partial)"
                                       % (field, field)})

    # ---- G2: case_id consistency ---------------------------------------------
    meta_case_id = meta.get("case_id")
    if meta_case_id is not None and meta_case_id != case_id:
        problems.append({"gate": "G2-case-id",
                         "detail": "_meta.json case_id %r != case.json case_id %r" % (meta_case_id, case_id)})

    # ---- G3: every /app/output/... path mentioned in text parts must exist ---
    seen_paths = set()
    for field in fields:
        for text in iter_strings(values.get(field)):
            for match in PATH_RE.finditer(text):
                rel = match.group(0)[len(OUTPUT_PREFIX):]
                if rel in seen_paths:
                    continue
                seen_paths.add(rel)
                if ".." in rel.split("/"):
                    problems.append({"gate": "G3-output-path-ghost", "field": field,
                                     "detail": "path escapes output dir: %s" % match.group(0)})
                elif not os.path.isfile(os.path.join(args.output_dir, rel)):
                    problems.append({"gate": "G3-output-path-ghost", "field": field,
                                     "detail": "mentioned path does not exist: %s" % match.group(0)})

    # ---- G4: every declared artifact must exist -------------------------------
    for rel in artifacts:
        if rel.startswith("/") or ".." in rel.split("/"):
            problems.append({"gate": "G4-artifact-exists",
                             "detail": "artifact must be a relative path inside the output dir: %r" % rel})
        elif not os.path.isfile(os.path.join(args.output_dir, rel)):
            problems.append({"gate": "G4-artifact-exists",
                             "detail": "declared artifact missing on disk: %s" % rel})

    # ---- G5: status consistency ----------------------------------------------
    status = meta.get("status", "complete")
    if status not in VALID_STATUS:
        limits.append("invalid status %r in _meta.json; recomputed" % (status,))
        status = "complete"
    if problems and status == "complete":
        status = "partial"
        limits.append("status forced complete -> partial: problems is non-empty (gate G5)")
    if not problems and status == "failed":
        limits.append("_meta.json says failed but no gate failed; keeping declared status")

    # ---- assemble -------------------------------------------------------------
    result = {"case_id": case_id, "task": case.get("task"), "status": status}
    for field in fields:
        result[field] = values.get(field)
    result["artifacts"] = artifacts
    result["sources"] = sources
    result["problems"] = problems
    result["limits"] = limits
    result["generated_by"] = "assemble_result.py"
    if args.note:
        result["note"] = args.note

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    atomic_write_json(args.output, result)

    # ---- G6 final: re-read and re-parse the written result.json ---------------
    _, rerr = load_json_file(args.output)
    if rerr is not None:
        print("FAIL G6: written result.json does not re-parse: %s" % rerr, file=sys.stderr)
        return 1

    if problems:
        print("assemble: %d gate problem(s); result.json written as %s" % (len(problems), status))
        for p in problems:
            print("  [%s] %s%s" % (p["gate"], ("<%s> " % p["field"]) if p.get("field") else "", p["detail"]))
        return 1
    print("assemble: all gates pass; result.json status=%s -> %s" % (status, args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
