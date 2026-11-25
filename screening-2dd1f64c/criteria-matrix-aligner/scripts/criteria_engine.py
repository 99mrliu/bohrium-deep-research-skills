#!/usr/bin/env python3
"""criteria-matrix-aligner engine.

Center of gravity: upstream criterion fidelity. The screening standard is
NOT invented by the agent: the criterion registry is extracted verbatim from
the case's own annotation standard (keys such as annotation_standard /
screening_criteria / criteria / inclusion / exclusion, with an explicit
source pointer per criterion; criteria that must be derived from
research_question / retrieval_scope are honestly marked derived:true).
Every record then receives a per-criterion verdict matrix (record x
criterion, verdict in {met, unmet, unknown}, plus a verbatim quote from the
record's own title/abstract), so agreement with the annotation standard is
auditable cell by cell. Labels, scores and ranks are recomputed from the
matrix by deterministic rules only; without a matrix the engine still emits
an honest partial result with every record pending.

Stdlib only. Subcommands:
  extract   --case CASE.json [--task task.md] --out criteria.json
  decide    --case CASE.json --criteria criteria.json [--matrix matrix.json] --out result.json
  validate  --case CASE.json --criteria criteria.json --result result.json
Exit code 0 on success/PASS, 1 on validation FAIL, 2 on usage/IO error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CANDIDATE_KEYS = ("candidates", "records", "papers", "references", "pool",
                  "items")
STANDARD_KEYS = ("annotation_standard", "screening_criteria", "criteria",
                 "inclusion_criteria", "inclusion",
                 "exclusion_criteria", "exclusion")
STANDARD_SUBKEYS = ("inclusion", "inclusion_criteria", "exclusion",
                    "exclusion_criteria", "criteria", "rules", "items")
CRIT_TEXT_KEYS = ("text", "criterion", "description", "statement", "rule")
CONTRACT_KEYS = ("output_contract", "outputContract", "output_contract_fields",
                 "contract", "expected_output", "expected_outputs")
ID_KEYS = ("case_id", "caseId", "id", "name")
REC_ID_KEYS = ("record_id", "recordId", "id", "paper_id", "doi")
VERDICTS = ("met", "unmet", "unknown")
LABEL_ORDER = {"keep": 0, "pending": 1, "exclude": 2}
DECISION_OF = {"keep": "direct", "pending": "indirect", "exclude": "none"}
TASK_HEAD_RE = re.compile(r"^\s*#+.*(标准|判据|criteria|criterion|inclusion|"
                          r"exclusion|纳入|排除|screening)", re.IGNORECASE)
TASK_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+(.+?)\s*$")


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
    """Return (list_of_records, key_path) for the most plausible pool."""
    best, best_key = [], None
    if isinstance(case, dict):
        for k in CANDIDATE_KEYS:
            v = case.get(k)
            if isinstance(v, list) and v and all(looks_like_record(r) for r in v):
                if len(v) > len(best):
                    best, best_key = v, k
        if not best:  # fallback: largest top-level list of title-bearing dicts
            for k, v in case.items():
                if (isinstance(v, list) and v
                        and all(looks_like_record(r) for r in v)):
                    if len(v) > len(best):
                        best, best_key = v, k
    return best, best_key


def record_id_of(rec, idx):
    for k in REC_ID_KEYS:
        v = rec.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return "rec-%03d" % (idx + 1)


def find_contract_fields(case):
    """Normalize whatever output_contract shape the case declares."""
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


def _criterion_text(item):
    if isinstance(item, str) and item.strip():
        return item.strip()
    if isinstance(item, dict):
        for k in CRIT_TEXT_KEYS:
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def flatten_standard(obj, path, out):
    """Collect verbatim criterion texts from any nested standard shape."""
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            text = _criterion_text(item)
            if text is not None:
                out.append({"text": text, "source": "%s[%d]" % (path, i)})
            elif isinstance(item, (list, dict)):
                flatten_standard(item, "%s[%d]" % (path, i), out)
    elif isinstance(obj, dict):
        text = _criterion_text(obj)
        if text is not None:
            out.append({"text": text, "source": path})
            return
        keys = [k for k in STANDARD_SUBKEYS if isinstance(obj.get(k), (list, dict))]
        keys += [k for k, v in obj.items()
                 if k not in keys and isinstance(v, (list, dict))]
        for k in keys:
            flatten_standard(obj[k], "%s.%s" % (path, k), out)
    elif isinstance(obj, str) and obj.strip():
        out.append({"text": obj.strip(), "source": path})


def extract_criteria(case, task_path, notes):
    """Verbatim-first criterion registry; derived criteria marked honestly."""
    raw = []
    if isinstance(case, dict):
        for k in STANDARD_KEYS:
            if k in case:
                flatten_standard(case[k], k, raw)
    seen, criteria = set(), []
    for c in raw:
        if c["text"] not in seen:
            seen.add(c["text"])
            criteria.append({"text": c["text"], "source": c["source"],
                             "derived": False})
    if criteria:
        notes.append("criteria extracted verbatim from the case annotation "
                     "standard; each carries a source key path")
        return criteria
    # Fallback 1: criterion-shaped bullet lines in task.md.
    if task_path and Path(task_path).exists():
        lines = Path(task_path).read_text(encoding="utf-8").splitlines()
        in_section = False
        for n, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#"):
                in_section = bool(TASK_HEAD_RE.match(line))
                continue
            if in_section:
                m = TASK_BULLET_RE.match(line)
                if m:
                    criteria.append({"text": m.group(1),
                                     "source": "task.md:L%d" % n,
                                     "derived": False})
        if criteria:
            notes.append("no annotation standard in case.json; criteria taken "
                         "verbatim from task.md criterion section lines")
            return criteria
    # Fallback 2: derive from research_question / retrieval_scope (marked).
    for k in ("research_question", "retrieval_scope", "question", "scope"):
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, str) and v.strip():
            criteria.append({"text": v.strip(), "source": k, "derived": True})
    if criteria:
        notes.append("WARNING: no annotation standard found; criteria derived "
                     "from research_question/retrieval_scope and marked "
                     "derived:true — alignment with the labeling standard "
                     "cannot be guaranteed for derived criteria")
    else:
        notes.append("WARNING: no annotation standard and no research question; "
                     "criterion registry is empty, all records stay pending")
    return criteria


def cmd_extract(args):
    case = load_json(args.case)
    case_id = find_case_id(case, args.case)
    notes = []
    criteria = extract_criteria(case, args.task, notes)
    for i, c in enumerate(criteria):
        c["criterion_id"] = "c%d" % (i + 1)
        criteria[i] = {"criterion_id": c["criterion_id"], "text": c["text"],
                       "source": c["source"], "derived": c["derived"]}
    cands, pool_key = find_candidates(case)
    record_ids = [record_id_of(r, i) for i, r in enumerate(cands)]
    if pool_key:
        notes.append("candidate pool located at key '%s' (%d records)"
                     % (pool_key, len(record_ids)))
    else:
        notes.append("WARNING: no candidate pool found; record_ids is empty")
    fixtures = [record_id_of(r, i) for i, r in enumerate(cands)
                if isinstance(r, dict) and (r.get("fixture_note") or r.get("fixture"))]
    if fixtures:
        notes.append("records %s carry fixture_note labels: provenance only, "
                     "never usable as ground truth for verdicts" % fixtures)
    out = {"case_id": case_id, "criteria": criteria,
           "record_ids": record_ids, "notes": notes}
    dump_json(out, args.out)
    print("extract: case_id=%s criteria=%d (derived=%d) records=%d -> %s"
          % (case_id, len(criteria),
             sum(1 for c in criteria if c["derived"]), len(record_ids),
             args.out))


def verdict_label(verdicts):
    vals = [v["verdict"] for v in verdicts]
    if not vals:
        return "pending"
    if any(v == "unmet" for v in vals):
        return "exclude"
    if all(v == "met" for v in vals):
        return "keep"
    return "pending"


def verdict_score(verdicts):
    total = len(verdicts)
    if total == 0:
        return 0
    met = sum(1 for v in verdicts if v["verdict"] == "met")
    unmet = sum(1 for v in verdicts if v["verdict"] == "unmet")
    raw = 100.0 * met / total - 50.0 * unmet / total
    return int(round(max(0.0, min(100.0, raw))))


def rank_records(judged):
    """Deterministic: tier keep<pending<exclude, then score desc, then id."""
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


def cmd_decide(args):
    case = load_json(args.case)
    crit = load_json(args.criteria)
    case_id = crit.get("case_id") or find_case_id(case, args.case)
    criteria = crit.get("criteria") or []
    record_ids = crit.get("record_ids") or []
    cells = {}
    matrix_supplied = bool(args.matrix) and Path(args.matrix).exists()
    if matrix_supplied:
        raw = load_json(args.matrix)
        cell_list = raw.get("cells", raw if isinstance(raw, list) else [])
        for c in cell_list:
            if not isinstance(c, dict):
                continue
            key = (c.get("record_id"), c.get("criterion_id"))
            if key in cells:
                continue  # first cell wins; duplicates reported by validate
            verdict = c.get("verdict")
            cells[key] = {"verdict": verdict if verdict in VERDICTS else "unknown",
                          "quote": c.get("quote") if isinstance(c.get("quote"), str)
                                   else None}
    cands, _ = find_candidates(case)
    titles = {record_id_of(r, i): (r.get("title") or "")
              for i, r in enumerate(cands)}
    judged, unknown_cells = [], 0
    for rid in record_ids:
        verdicts = []
        for c in criteria:
            cell = cells.get((rid, c["criterion_id"]))
            if cell is None:
                cell = {"verdict": "unknown", "quote": None}
            if cell["verdict"] == "unknown":
                unknown_cells += 1
            verdicts.append({"criterion_id": c["criterion_id"],
                             "verdict": cell["verdict"], "quote": cell["quote"]})
        label = verdict_label(verdicts)
        judged.append({"record_id": rid,
                       "title": titles.get(rid, ""),
                       "label": label,
                       "decision": DECISION_OF[label],
                       "score": verdict_score(verdicts),
                       "verdicts": verdicts})
    ordered = rank_records(judged)
    total_cells = len(record_ids) * len(criteria)
    incomplete, limits, uncertainty = [], [], []
    if not matrix_supplied:
        incomplete.append({"part": "verdict matrix",
                           "reason": "no --matrix supplied; every cell is "
                                     "unknown and every record is pending "
                                     "(honest partial, nothing fabricated)"})
        uncertainty.append("without a verdict matrix no screening decision "
                           "has been made; pending is not a decision")
    elif unknown_cells:
        incomplete.append({"part": "verdict matrix",
                           "reason": "%d of %d cells are unknown (e.g. missing "
                                     "abstracts); affected records stay pending"
                                     % (unknown_cells, total_cells)})
        uncertainty.append("unknown verdicts reflect missing or ambiguous "
                           "evidence in the record itself, not silent exclusion")
    if not criteria:
        limits.append("no annotation standard could be extracted; no criterion "
                      "matrix could be formed")
    if any(c.get("derived") for c in criteria):
        limits.append("part of the criterion registry is derived from "
                      "research_question/retrieval_scope (derived:true), not "
                      "verbatim from an annotation standard")
    if not find_contract_fields(case):
        limits.append("case declares no output_contract; emitted the standard "
                      "payload keys only")
    summary = {"total": len(ordered),
               "keep": sum(1 for j in ordered if j["label"] == "keep"),
               "pending": sum(1 for j in ordered if j["label"] == "pending"),
               "exclude": sum(1 for j in ordered if j["label"] == "exclude"),
               "cells": total_cells,
               "cells_met": sum(1 for j in ordered for v in j["verdicts"]
                                if v["verdict"] == "met"),
               "cells_unmet": sum(1 for j in ordered for v in j["verdicts"]
                                  if v["verdict"] == "unmet"),
               "cells_unknown": unknown_cells}
    result = {
        "case_id": case_id,
        "criteria": criteria,
        "screened_records": ordered,
        "ranking": [{"rank": j["rank"], "record_id": j["record_id"],
                     "label": j["label"], "decision": j["decision"],
                     "score": j["score"]} for j in ordered],
        "evidence_records": [
            {"record_id": j["record_id"], "label": j["label"],
             "evidence": [{"criterion_id": v["criterion_id"],
                           "verdict": v["verdict"], "quote": v["quote"]}
                          for v in j["verdicts"] if v["quote"] is not None]}
            for j in ordered],
        "summary": summary,
        "status": {
            "state": "partial" if incomplete else "complete",
            "completed": ["verbatim criterion registry extraction",
                          "all-record coverage",
                          "deterministic label/score/rank from matrix"]
                         + (["per-criterion verdict matrix"] if matrix_supplied else []),
            "incomplete": incomplete,
            "limits": limits,
        },
        "uncertainty": uncertainty,
        "change_records": [],
    }
    # Mirror every declared contract field; never drop one silently.
    payload = dict(result)
    for f in find_contract_fields(case):
        name = f["name"]
        if name in payload:
            continue
        if isinstance(case, dict) and name in case and name not in CANDIDATE_KEYS:
            result[name] = case[name]  # echo same-named real input field
        elif any(t in name.lower() for t in ("omission", "coverage", "note")):
            gaps = []
            for i, r in enumerate(cands):
                miss = [k for k in ("title", "abstract", "year", "authors",
                                    "doi", "venue") if not r.get(k)]
                if miss:
                    gaps.append("%s lacks %s" % (record_id_of(r, i),
                                                 "/".join(miss)))
            parts = ["Candidate pool is a finite snapshot of %d records; no "
                     "live database was queried, so recall beyond the snapshot "
                     "cannot be claimed." % len(ordered),
                     "%d of %d verdict cells are unknown; affected records are "
                     "pending, never silently excluded."
                     % (unknown_cells, total_cells)]
            if gaps:
                parts.append("Missing metadata: " + "; ".join(gaps) + ".")
            fixtures = [record_id_of(r, i) for i, r in enumerate(cands)
                        if isinstance(r, dict) and r.get("fixture_note")]
            if fixtures:
                parts.append("Fixture-labelled records %s were screened on "
                             "their own metadata only; fixture_note served as "
                             "provenance, not as a verdict source." % fixtures)
            result[name] = " ".join(parts)
        else:
            result[name] = None
            result["status"]["incomplete"].append(
                {"part": "contract field '%s'" % name,
                 "reason": "declared by output_contract but not producible "
                           "from available input; emitted as explicit null"})
            result["status"]["state"] = "partial"
    dump_json(result, args.out)
    print("decide: state=%s records=%d keep=%d pending=%d exclude=%d "
          "unknown_cells=%d -> %s"
          % (result["status"]["state"], len(ordered), summary["keep"],
             summary["pending"], summary["exclude"], unknown_cells, args.out))


def cmd_validate(args):
    case = load_json(args.case)
    crit = load_json(args.criteria)
    result = load_json(args.result)
    case_id = find_case_id(case, args.case)
    criteria = crit.get("criteria") or []
    crit_ids = [c["criterion_id"] for c in criteria]
    cands, _ = find_candidates(case)
    by_id = {record_id_of(r, i): r for i, r in enumerate(cands)}
    known_ids = list(by_id.keys())
    problems = []
    if result.get("case_id") != case_id:
        problems.append("case_id mismatch: result=%r expected=%r"
                        % (result.get("case_id"), case_id))
    for f in find_contract_fields(case):
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
    unknown_cells = 0
    for j in screened:
        rid = j.get("record_id")
        rec = by_id.get(rid) or {}
        haystacks = [t for t in (rec.get("title"), rec.get("abstract"))
                     if isinstance(t, str)]
        verdicts = j.get("verdicts") or []
        got = [v.get("criterion_id") for v in verdicts]
        if len(set(got)) != len(got):
            problems.append("duplicate criterion cells for %s" % rid)
        for cid in crit_ids:
            if cid not in got:
                problems.append("matrix incomplete: %s lacks cell %s" % (rid, cid))
        for v in verdicts:
            if v.get("verdict") not in VERDICTS:
                problems.append("bad verdict for %s/%s: %r"
                                % (rid, v.get("criterion_id"), v.get("verdict")))
            if v.get("verdict") == "unknown":
                unknown_cells += 1
            q = v.get("quote")
            if q is not None:
                if not isinstance(q, str) or not any(q in h for h in haystacks):
                    problems.append("quote for %s/%s is not a verbatim substring "
                                    "of that record's title or abstract: %r"
                                    % (rid, v.get("criterion_id"), q))
        exp_label = verdict_label([{"verdict": v.get("verdict")}
                                   for v in verdicts]) if verdicts else "pending"
        if j.get("label") != exp_label:
            problems.append("label for %s inconsistent with decision rule: "
                            "result=%r recomputed=%r"
                            % (rid, j.get("label"), exp_label))
        exp_score = verdict_score(verdicts)
        if j.get("score") != exp_score:
            problems.append("score for %s inconsistent: result=%r recomputed=%r"
                            % (rid, j.get("score"), exp_score))
        if j.get("label") in DECISION_OF and \
                j.get("decision") not in (None, DECISION_OF.get(j.get("label"))):
            problems.append("decision for %s inconsistent with label: %r"
                            % (rid, j.get("decision")))
    if not isinstance(result.get("status"), dict) \
            or result.get("status", {}).get("state") not in ("complete", "partial"):
        problems.append("status.state missing or not complete|partial")
    if problems:
        print("VALIDATE FAIL")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("VALIDATE PASS: case_id=%s records=%d criteria=%d unknown_cells=%d "
          "state=%s"
          % (case_id, len(seen), len(crit_ids), unknown_cells,
             result["status"]["state"]))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract")
    p.add_argument("--case", required=True)
    p.add_argument("--task")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("decide")
    p.add_argument("--case", required=True)
    p.add_argument("--criteria", required=True)
    p.add_argument("--matrix")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_decide)
    p = sub.add_parser("validate")
    p.add_argument("--case", required=True)
    p.add_argument("--criteria", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
