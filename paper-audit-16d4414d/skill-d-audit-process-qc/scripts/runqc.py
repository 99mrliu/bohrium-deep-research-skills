#!/usr/bin/env python3
"""runqc.py — 审查过程质量控制引擎 for paper-audit skills.

Pure Python 3.8+ standard library. Deterministic except wall-clock timestamps.
Zero dependencies. It does not audit the paper; it makes the AUDIT itself
reviewable: atomic checkpoints, coverage ledger, budget safety net,
rerun-consistency check, and a finalize gate that refuses dishonest status.

Subcommands:
  init       --work DIR --output DIR --case case.json   skeleton result.json (atomic) + journal
  checkpoint --work DIR --output DIR --stage NAME [--note T] [--field K --value JSON]
  coverage   --work DIR --item NAME --status examined|pending|skipped|unchecked [--reason T]
  budget     --work DIR --requests N                    safety net vs 64-request budget
  reruncheck --work DIR --previous F1 --current F2      STABLE/DRIFT findings diff
  finalize   --work DIR --output DIR                    contract + honesty gate (exit 5 = dishonest)

Exit codes: 0 ok; 3 fatal input error; budget 6 = over critical threshold;
finalize 5 = gate violations (dishonest or incomplete result.json).
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

BUDGET_REQUESTS = 64
WARN_AT, CRITICAL_AT = 40, 56


def eprint(*a):
    print(*a, file=sys.stderr)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def atomic_write_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def journal(work, stage, note, extra=None):
    entry = {"ts": now(), "stage": stage, "note": note}
    if extra:
        entry.update(extra)
    rj = os.path.join(work, "result_snapshot.sha")
    if os.path.isfile(rj):
        with open(rj, encoding="utf-8") as fh:
            entry["result_sha256"] = fh.read().strip()
    with open(os.path.join(work, "journal.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def find_keys(obj, names, path=""):
    """Recursively find first occurrence of each key name in a nested JSON."""
    found = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in names and k not in found:
                found[k] = v
            sub = find_keys(v, names, path + "/" + k)
            for kk, vv in sub.items():
                found.setdefault(kk, vv)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            sub = find_keys(v, names, "%s/%d" % (path, i))
            for kk, vv in sub.items():
                found.setdefault(kk, vv)
    return found


# -------------------------------------------------------------------- init
def cmd_init(args):
    os.makedirs(args.work, exist_ok=True)
    if not os.path.isfile(args.case):
        eprint("FATAL: case file not found: %s" % args.case)
        return 3
    case = load_json(args.case)
    keys = find_keys(case, {"case_id", "output_contract"})
    case_id = keys.get("case_id")
    if case_id is None:
        eprint("FATAL: case_id not found in case.json; cannot build result skeleton")
        return 3
    contract = keys.get("output_contract") or {}
    if isinstance(contract, dict):
        fields = list(contract.keys())
    elif isinstance(contract, list):
        fields = [f if isinstance(f, str) else f.get("name", str(f)) for f in contract]
    else:
        fields = []
    skeleton = {"case_id": case_id,
                "status": "in_progress",
                "provenance": {"engine": "runqc init", "created": now()},
                "uncertainty": []}
    for f in fields:
        skeleton.setdefault(f, None)
    out_path = os.path.join(args.output, "result.json")
    atomic_write_json(out_path, skeleton)
    atomic_write(os.path.join(args.work, "result_snapshot.sha"),
                 sha256_text(json.dumps(skeleton, sort_keys=True)) + "\n")
    atomic_write_json(os.path.join(args.work, "contract.json"), {
        "case_id": case_id, "output_contract_fields": fields,
        "contract_source": os.path.abspath(args.case)})
    atomic_write_json(os.path.join(args.work, "coverage_ledger.json"), {"items": {}})
    atomic_write_json(os.path.join(args.work, "budget.json"), {
        "requests_used": 0, "budget": BUDGET_REQUESTS})
    journal(args.work, "init",
            "skeleton with %d contract fields written atomically" % len(fields))
    print(json.dumps({"status": "ok", "case_id": case_id,
                      "contract_fields": fields}, ensure_ascii=False))
    return 0


# -------------------------------------------------------------- checkpoint
def cmd_checkpoint(args):
    out_path = os.path.join(args.output, "result.json")
    if not os.path.isfile(out_path):
        eprint("FATAL: %s missing; run init first" % out_path)
        return 3
    result = load_json(out_path)
    if args.field:
        try:
            value = json.loads(args.value) if args.value is not None else None
        except json.JSONDecodeError:
            value = args.value
        result[args.field] = value
    atomic_write_json(out_path, result)
    atomic_write(os.path.join(args.work, "result_snapshot.sha"),
                 sha256_text(json.dumps(result, sort_keys=True)) + "\n")
    journal(args.work, args.stage, args.note or "",
            {"field_set": args.field} if args.field else {})
    print(json.dumps({"status": "ok", "stage": args.stage,
                      "result_bytes": os.path.getsize(out_path)}, ensure_ascii=False))
    return 0


# --------------------------------------------------------------- coverage
def cmd_coverage(args):
    ledger_path = os.path.join(args.work, "coverage_ledger.json")
    if not os.path.isfile(ledger_path):
        eprint("FATAL: coverage ledger missing; run init first")
        return 3
    ledger = load_json(ledger_path)
    if args.status in ("skipped", "unchecked") and not args.reason:
        eprint("FATAL: status %s requires --reason (honesty rule)" % args.status)
        return 3
    ledger["items"][args.item] = {"status": args.status,
                                  "reason": args.reason or "",
                                  "ts": now()}
    atomic_write_json(ledger_path, ledger)
    journal(args.work, "coverage", "%s -> %s" % (args.item, args.status))
    counts = {}
    for v in ledger["items"].values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print(json.dumps({"status": "ok", "ledger_counts": counts}, ensure_ascii=False))
    return 0


# ----------------------------------------------------------------- budget
def cmd_budget(args):
    path = os.path.join(args.work, "budget.json")
    if not os.path.isfile(path):
        eprint("FATAL: budget file missing; run init first")
        return 3
    b = load_json(path)
    b["requests_used"] = args.requests
    atomic_write_json(path, b)
    left = BUDGET_REQUESTS - args.requests
    level = "ok"
    rc = 0
    if args.requests >= CRITICAL_AT:
        level = "critical: 立即保存当前 result.json 并收尾，只留 finalize 所需请求"
        rc = 6
    elif args.requests >= WARN_AT:
        level = "warn: 停止开新检查线，优先把已确认发现写入交付物"
    journal(args.work, "budget", "%d/%d used (%s)" % (args.requests, BUDGET_REQUESTS, level))
    print(json.dumps({"requests_left": left, "level": level}, ensure_ascii=False))
    return rc


# ------------------------------------------------------------- reruncheck
def norm_findings(f):
    return {str(x.get("id", i)): {k: x.get(k) for k in
                                  ("sentence_id", "category", "severity", "status")}
            for i, x in enumerate(f)}


def cmd_reruncheck(args):
    if not (os.path.isfile(args.previous) and os.path.isfile(args.current)):
        eprint("FATAL: both findings files must exist")
        return 3
    prev, cur = norm_findings(load_json(args.previous)), norm_findings(load_json(args.current))
    diffs = []
    for fid in sorted(set(prev) | set(cur)):
        if fid not in prev:
            diffs.append({"id": fid, "diff": "added_in_rerun"})
        elif fid not in cur:
            diffs.append({"id": fid, "diff": "missing_in_rerun"})
        elif prev[fid] != cur[fid]:
            changed = {k: [prev[fid].get(k), cur[fid].get(k)]
                       for k in prev[fid] if prev[fid].get(k) != cur[fid].get(k)}
            diffs.append({"id": fid, "diff": "changed", "fields": changed})
    verdict = "DRIFT" if diffs else "STABLE"
    atomic_write_json(os.path.join(args.work, "reruncheck.json"), {
        "verdict": verdict, "diffs": diffs,
        "note": "DRIFT 不一定是错误（材料/预算不同），但必须逐条在报告中解释；"
                "无法解释的 DRIFT 说明过程不可复核，相关 finding 降级为待复核"})
    journal(args.work, "reruncheck", "%s (%d diffs)" % (verdict, len(diffs)))
    print(json.dumps({"verdict": verdict, "diffs": len(diffs)}, ensure_ascii=False))
    return 0


# --------------------------------------------------------------- finalize
def cmd_finalize(args):
    out_path = os.path.join(args.output, "result.json")
    contract_path = os.path.join(args.work, "contract.json")
    if not os.path.isfile(out_path) or not os.path.isfile(contract_path):
        eprint("FATAL: run init first")
        return 3
    result = load_json(out_path)
    contract = load_json(contract_path)
    violations = []

    if result.get("case_id") != contract["case_id"]:
        violations.append("case_id 与 case.json 不一致")
    for f in contract["output_contract_fields"]:
        if f not in result:
            violations.append("output_contract 字段缺失: %s" % f)

    status = str(result.get("status", ""))
    ledger = load_json(os.path.join(args.work, "coverage_ledger.json"))
    open_items = {k: v for k, v in ledger["items"].items()
                  if v["status"] in ("pending", "skipped", "unchecked")}
    if open_items and status in ("success", "通过", "complete", "completed", "done"):
        violations.append(
            "存在未检查/跳过项（%s），整体 status 不得为 %r；应为 partial 并逐项列明"
            % (", ".join(sorted(open_items)), status))
    if status == "in_progress":
        violations.append("status 仍为 in_progress；finalize 前必须改为 success/partial/failed")

    journal_path = os.path.join(args.work, "journal.jsonl")
    n_checkpoints = 0
    if os.path.isfile(journal_path):
        with open(journal_path, encoding="utf-8") as fh:
            n_checkpoints = sum(1 for ln in fh if ln.strip())
    if n_checkpoints < 2:
        violations.append("journal 检查点过少；过程不可复核")

    record = {"ts": now(), "verdict": "PASS" if not violations else "FAIL",
              "violations": violations, "journal_entries": n_checkpoints,
              "open_items": sorted(open_items)}
    atomic_write_json(os.path.join(args.work, "finalize_report.json"), record)
    journal(args.work, "finalize", record["verdict"])
    if violations:
        for v in violations:
            eprint("GATE VIOLATION: %s" % v)
        return 5
    print(json.dumps({"status": "ok", "verdict": "PASS",
                      "journal_entries": n_checkpoints}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--work", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--case", required=True)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("checkpoint")
    p.add_argument("--work", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--field")
    p.add_argument("--value")
    p.set_defaults(fn=cmd_checkpoint)
    p = sub.add_parser("coverage")
    p.add_argument("--work", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--status", required=True,
                   choices=["examined", "pending", "skipped", "unchecked"])
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_coverage)
    p = sub.add_parser("budget")
    p.add_argument("--work", required=True)
    p.add_argument("--requests", type=int, required=True)
    p.set_defaults(fn=cmd_budget)
    p = sub.add_parser("reruncheck")
    p.add_argument("--work", required=True)
    p.add_argument("--previous", required=True)
    p.add_argument("--current", required=True)
    p.set_defaults(fn=cmd_reruncheck)
    p = sub.add_parser("finalize")
    p.add_argument("--work", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(fn=cmd_finalize)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
