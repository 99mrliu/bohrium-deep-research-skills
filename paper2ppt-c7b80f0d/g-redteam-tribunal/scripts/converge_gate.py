#!/usr/bin/env python3
"""converge_gate.py — 红队收敛门禁。

判定（两条同时满足才 verdict=pass）：
  1. 台账中无 status=open 且 severity=error 的条目；
  2. 当前轮 findings 中无"新增 error"（rule+slide+evidence 键在上一轮 error 中不存在）。
warn 级条目不阻塞收敛，但全部计入报告。

用法：converge_gate.py --ledger tribunal.json --prev findings_round1.json \
        --cur findings_round2.json --report convergence.json
退出码：0 verdict=pass；1 verdict=fail；2 输入错误。
"""
import argparse
import json
import sys


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def err_key(f):
    return (f["rule"], f.get("slide") or 0,
            json.dumps(f.get("evidence", {}), sort_keys=True, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description="红队收敛门禁")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--prev", required=True, help="上一轮 findings JSON")
    ap.add_argument("--cur", required=True, help="当前轮 findings JSON")
    ap.add_argument("--report", required=True, help="convergence.json 输出")
    args = ap.parse_args(argv)

    try:
        ledger = load_json(args.ledger)
        prev = load_json(args.prev)
        cur = load_json(args.cur)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取输入: {e}", file=sys.stderr)
        return 2

    open_errors = sorted(
        e["id"] for e in ledger.get("entries", {}).values()
        if e.get("status") == "open" and e.get("severity") == "error")
    prev_errs = {err_key(f) for f in prev.get("findings", []) if f["severity"] == "error"}
    cur_errs = [f for f in cur.get("findings", []) if f["severity"] == "error"]
    new_errors = sorted(f["id"] for f in cur_errs if err_key(f) not in prev_errs)

    prev_ids = {f["id"] for f in prev.get("findings", [])}
    cur_ids = {f["id"] for f in cur.get("findings", [])}
    verdict = "pass" if (not open_errors and not new_errors) else "fail"

    report = {
        "verdict": verdict,
        "criteria": {
            "no_open_error_in_ledger": len(open_errors) == 0,
            "no_new_error_in_current_round": len(new_errors) == 0,
        },
        "open_error_ids": open_errors,
        "new_error_ids": new_errors,
        "prev_round": {"round": prev.get("round"), "total": prev.get("total"),
                       "counts": prev.get("counts")},
        "cur_round": {"round": cur.get("round"), "total": cur.get("total"),
                      "counts": cur.get("counts")},
        "resolved_since_prev": sorted(prev_ids - cur_ids),
        "remaining_warns": sorted(
            f["id"] for f in cur.get("findings", []) if f["severity"] == "warn"),
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"verdict={verdict} open_errors={len(open_errors)} "
          f"new_errors={len(new_errors)} resolved={len(report['resolved_since_prev'])} "
          f"-> {args.report}")
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
