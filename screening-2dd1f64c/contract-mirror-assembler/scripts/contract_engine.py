#!/usr/bin/env python3
"""contract-mirror-assembler engine.

Center of gravity: downstream delivery conformance. The evaluator's cases
declare an output_contract; this engine discovers that contract from the
actual /input/case.json, mirrors every declared field into result.json
(together with case_id), and refuses to let a field silently vanish:
anything that cannot be produced from real input is emitted as an explicit
null plus an entry in status.incomplete. The screening payload itself is
assembled from a judgments file (record-level decisions made by the agent
in one batched pass); without judgments the engine still emits an honest
partial result in which every record is marked pending.

Stdlib only. Subcommands:
  inspect   --case CASE.json [--task task.md] --out plan.json
  assemble  --case CASE.json --plan plan.json [--judgments J.json] --out result.json
  validate  --case CASE.json --result result.json
Exit code 0 on success/PASS, 1 on validation FAIL, 2 on usage/IO error.
"""
import argparse
import json
import sys
from pathlib import Path

CANDIDATE_KEYS = ("candidates", "records", "papers", "references", "pool",
                  "items", "works", "documents")
CONTRACT_KEYS = ("output_contract", "outputContract", "output_contract_fields",
                 "contract", "expected_output", "expected_outputs")
ID_KEYS = ("case_id", "caseId", "id", "name")
REC_ID_KEYS = ("record_id", "recordId", "id", "paper_id", "doi")
LABEL_ORDER = {"keep": 0, "pending": 1, "exclude": 2}
PAYLOAD_KEYS = {
    "case_id", "research_question", "screened_records", "screening",
    "ranking", "ranked_records", "criteria", "evidence_records", "evidence",
    "status", "uncertainty", "change_records", "summary", "notes",
    "queries", "omission_note", "duplicates",
}


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("error: cannot parse %s as UTF-8 JSON: %s" % (path, exc))


def dump_json(obj, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")


def find_case_id(case, case_path):
    if isinstance(case, dict):
        for k in ID_KEYS:
            v = case.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return Path(case_path).stem


def looks_like_record(obj):
    return isinstance(obj, dict) and isinstance(obj.get("title"), str)


def find_candidates(case):
    """Return (list_of_records, key_path) for the largest plausible pool."""
    best, best_key = [], None
    if isinstance(case, dict):
        for k in CANDIDATE_KEYS:
            v = case.get(k)
            if isinstance(v, list) and v and all(looks_like_record(r) for r in v):
                if len(v) > len(best):
                    best, best_key = v, k
        if not best:  # fallback: any list of title-bearing dicts at top level
            for k, v in case.items():
                if (isinstance(v, list) and v
                        and sum(looks_like_record(r) for r in v) >= len(v) * 0.8):
                    if len(v) > len(best):
                        best, best_key = v, k
    return best, best_key


def find_queries(case):
    if isinstance(case, dict):
        for k in ("queries", "query_inputs", "search_queries", "actual_queries"):
            v = case.get(k)
            if isinstance(v, list):
                return [q if isinstance(q, str) else json.dumps(q, ensure_ascii=False)
                        for q in v]
    return []


def find_contract_fields(case):
    """Normalize whatever output_contract shape the case declares.

    Returns list of {"name", "hint"}. Supports: dict field->spec, list of
    names/specs, JSON-schema-ish {"properties": {...}}, or single string.
    """
    raw = None
    if isinstance(case, dict):
        for k in CONTRACT_KEYS:
            if k in case:
                raw = case[k]
                break
    fields = []
    if isinstance(raw, dict):
        props = raw.get("properties") if isinstance(raw.get("properties"), dict) else None
        src = props if props is not None else raw
        for name, spec in src.items():
            hint = spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False)
            fields.append({"name": str(name), "hint": hint[:200]})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                fields.append({"name": item, "hint": ""})
            elif isinstance(item, dict) and item.get("name"):
                fields.append({"name": str(item["name"]),
                               "hint": json.dumps(item, ensure_ascii=False)[:200]})
    elif isinstance(raw, str):
        fields.append({"name": raw, "hint": ""})
    seen, uniq = set(), []
    for f in fields:
        if f["name"] not in seen:
            seen.add(f["name"])
            uniq.append(f)
    return uniq


def record_id_of(rec, idx):
    for k in REC_ID_KEYS:
        v = rec.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return "rec-%03d" % (idx + 1)


def cmd_inspect(args):
    case = load_json(args.case)
    case_id = find_case_id(case, args.case)
    cands, pool_key = find_candidates(case)
    queries = find_queries(case)
    fields = find_contract_fields(case)
    recs = []
    missing_meta = []
    for i, r in enumerate(cands):
        rid = record_id_of(r, i)
        gaps = [k for k in ("title", "abstract", "year", "authors", "doi", "venue")
                if not r.get(k)]
        if gaps:
            missing_meta.append({"record_id": rid, "missing": gaps})
        recs.append({"record_id": rid, "title": (r.get("title") or "")[:160],
                     "year": r.get("year"),
                     "fixture_note": r.get("fixture_note") or r.get("fixture")})
    plan = {
        "case_id": case_id,
        "candidate_pool_key": pool_key,
        "candidate_count": len(recs),
        "record_ids": [r["record_id"] for r in recs],
        "records": recs,
        "queries": queries,
        "contract_fields": fields,
        "missing_metadata": missing_meta,
        "notes": [
            "contract fields were read from the actual case file; mirror every one",
            "any field not producible from real input must appear as explicit null "
            "plus a status.incomplete entry — never silently drop it",
        ],
    }
    if args.task and Path(args.task).exists():
        plan["task_md_bytes"] = Path(args.task).stat().st_size
    dump_json(plan, args.out)
    print("inspect: case_id=%s candidates=%d contract_fields=%d -> %s"
          % (case_id, len(recs), len(fields), args.out))


def rank_records(judged):
    """Deterministic order: keep < pending < exclude, then score desc, then id."""
    ordered = sorted(judged, key=lambda j: (LABEL_ORDER.get(j["label"], 1),
                                            -float(j.get("score", 0)),
                                            j["record_id"]))
    rank, ties, prev_key = 0, {}, None
    for j in ordered:
        key = (LABEL_ORDER.get(j["label"], 1), round(float(j.get("score", 0)), 6))
        if key != prev_key:
            rank += 1
            ties.setdefault(rank, [])
            prev_key = key
        j["rank"] = rank
        ties[rank].append(j["record_id"])
    for r, ids in ties.items():
        if len(ids) > 1:
            for j in ordered:
                if j["rank"] == r:
                    j["tie_group"] = sorted(ids)
    return ordered


def cmd_assemble(args):
    case = load_json(args.case)
    plan = load_json(args.plan)
    case_id = plan["case_id"]
    known_ids = set(plan["record_ids"])
    judgments = []
    if args.judgments and Path(args.judgments).exists():
        raw = load_json(args.judgments)
        judgments = raw.get("judgments", raw if isinstance(raw, list) else [])
    by_id = {}
    for j in judgments:
        if isinstance(j, dict) and j.get("record_id") in known_ids:
            by_id[j["record_id"]] = j
    judged, unjudged = [], []
    for rid in plan["record_ids"]:
        j = by_id.get(rid)
        if j is None:
            unjudged.append(rid)
            judged.append({"record_id": rid, "label": "pending",
                           "relevance": "unknown", "score": 0,
                           "rationale": "not yet judged (honest pending; no decision fabricated)",
                           "evidence": None})
        else:
            judged.append({
                "record_id": rid,
                "label": j.get("label") if j.get("label") in LABEL_ORDER else "pending",
                "relevance": j.get("relevance", "unknown"),
                "score": max(0, min(100, float(j.get("score", 0) or 0))),
                "rationale": j.get("rationale", ""),
                "evidence": j.get("evidence"),
            })
    ordered = rank_records(judged)
    evidence_records = [
        {"record_id": j["record_id"], "decision": j["label"],
         "rationale": j["rationale"], "evidence": j["evidence"]}
        for j in ordered
    ]
    incomplete, limits = [], []
    if unjudged:
        incomplete.append({"part": "judgments",
                           "reason": "%d of %d records lack judgments"
                                     % (len(unjudged), len(ordered)),
                           "record_ids": unjudged})
    if not plan["contract_fields"]:
        limits.append("case declares no output_contract; emitted the standard "
                      "payload keys only")
    result = {
        "case_id": case_id,
        "research_question": case.get("research_question")
                             or case.get("question") or None,
        "queries": plan["queries"],
        "screened_records": ordered,
        "ranking": [{"rank": j["rank"], "record_id": j["record_id"],
                     "label": j["label"], "score": j["score"]} for j in ordered],
        "evidence_records": evidence_records,
        "summary": {
            "total": len(ordered),
            "keep": sum(1 for j in ordered if j["label"] == "keep"),
            "pending": sum(1 for j in ordered if j["label"] == "pending"),
            "exclude": sum(1 for j in ordered if j["label"] == "exclude"),
        },
        "status": {
            "state": "partial" if incomplete else "complete",
            "completed": ["contract discovery", "all-record coverage",
                          "deterministic ranking"] + (["record judgments"] if not unjudged else []),
            "incomplete": incomplete,
            "limits": limits,
        },
        "uncertainty": ["relevance judgments without model review are pending, "
                        "not decisions"] if unjudged else [],
        "change_records": [],
    }
    # Mirror every declared contract field; never drop one silently.
    payload = dict(result)
    for f in plan["contract_fields"]:
        name = f["name"]
        if name in payload:
            continue
        if isinstance(case, dict) and name in case and name not in ("candidates",):
            result[name] = case[name]  # echo real input fields (e.g. research_question)
        elif any(t in name.lower() for t in ("omission", "coverage", "note")):
            gaps = ["%s lacks %s" % (m["record_id"], "/".join(m["missing"]))
                    for m in plan.get("missing_metadata", [])]
            excl = [j["record_id"] for j in ordered if j["label"] == "exclude"]
            parts = ["Candidate pool is a finite snapshot of %d records; no live "
                     "database was queried, so recall beyond the snapshot cannot "
                     "be claimed." % len(ordered)]
            if gaps:
                parts.append("Missing metadata: " + "; ".join(gaps) + ".")
            if excl:
                parts.append("Excluded records (see screened_records rationales): "
                             + ", ".join(excl) + ".")
            result[name] = " ".join(parts)
        else:
            result[name] = None
            result["status"]["incomplete"].append(
                {"part": "contract field '%s'" % name,
                 "reason": "declared by output_contract but not producible from "
                           "available input; emitted as explicit null"})
            result["status"]["state"] = "partial"
    dump_json(result, args.out)
    print("assemble: state=%s records=%d -> %s"
          % (result["status"]["state"], len(ordered), args.out))


def cmd_validate(args):
    case = load_json(args.case)
    result = load_json(args.result)
    case_id = find_case_id(case, args.case)
    cands, _ = find_candidates(case)
    known_ids = [record_id_of(r, i) for i, r in enumerate(cands)]
    problems = []
    if result.get("case_id") != case_id:
        problems.append("case_id mismatch: result=%r expected=%r"
                        % (result.get("case_id"), case_id))
    fields = find_contract_fields(case)
    for f in fields:
        if f["name"] not in result:
            problems.append("contract field missing from result: %s" % f["name"])
    screened = result.get("screened_records") or []
    seen = [j.get("record_id") for j in screened]
    dup = sorted({r for r in seen if seen.count(r) > 1})
    if dup:
        problems.append("duplicate record_ids in screened_records: %s" % dup)
    missing = [r for r in known_ids if r not in seen]
    extra = [r for r in seen if r not in known_ids]
    if missing:
        problems.append("records not covered: %s" % missing)
    if extra:
        problems.append("unknown record_ids in output: %s" % extra)
    for j in screened:
        if j.get("label") not in LABEL_ORDER:
            problems.append("bad label for %s: %r" % (j.get("record_id"), j.get("label")))
        s = j.get("score")
        if not isinstance(s, (int, float)) or not (0 <= s <= 100):
            problems.append("bad score for %s: %r" % (j.get("record_id"), s))
    if not isinstance(result.get("status"), dict) or "state" not in result.get("status", {}):
        problems.append("status.state missing")
    if problems:
        print("VALIDATE FAIL")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("VALIDATE PASS: case_id=%s records=%d contract_fields=%d state=%s"
          % (case_id, len(seen), len(fields), result["status"]["state"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect")
    p.add_argument("--case", required=True)
    p.add_argument("--task")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("assemble")
    p.add_argument("--case", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--judgments")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_assemble)
    p = sub.add_parser("validate")
    p.add_argument("--case", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
