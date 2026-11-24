#!/usr/bin/env python3
"""tribunal_log.py — 红队台账管理（tribunal.json）。

状态机：open -> fixed | dispositioned。禁止物理删除任何条目。
确定性：不记录墙钟时间，历史用逻辑序号 seq 排序。

用法：
  tribunal_log.py --findings findings_roundN.json --ledger tribunal.json   # 入账（幂等）
  tribunal_log.py --ledger tribunal.json --fix <id> --note "..." [--operator who]
  tribunal_log.py --ledger tribunal.json --disposition <id> accept-risk|reject --reason "..."
  tribunal_log.py --ledger tribunal.json --status                          # 打印汇总
退出码：0 成功；2 输入/文件错误；3 未知 id 或非法状态迁移。
"""
import argparse
import json
import sys

VALID_DISPOSITIONS = ("accept-risk", "reject")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_ledger(ledger, path):
    ledger["summary"] = {
        "total": len(ledger["entries"]),
        "open": sum(1 for e in ledger["entries"].values() if e["status"] == "open"),
        "fixed": sum(1 for e in ledger["entries"].values() if e["status"] == "fixed"),
        "dispositioned": sum(1 for e in ledger["entries"].values() if e["status"] == "dispositioned"),
        "open_errors": sum(
            1 for e in ledger["entries"].values()
            if e["status"] == "open" and e["severity"] == "error"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_ledger(path):
    try:
        return load_json(path)
    except FileNotFoundError:
        return {"version": 1, "entries": {}}


def append_history(entry, action, actor, note):
    entry["history"].append({
        "seq": len(entry["history"]) + 1,
        "action": action,
        "actor": actor,
        "note": note,
    })


def cmd_ingest(ledger, findings_path):
    rep = load_json(findings_path)
    new = 0
    for f in rep.get("findings", []):
        if f["id"] in ledger["entries"]:
            continue  # 幂等：已入账的 finding 不重置状态、不重复
        ledger["entries"][f["id"]] = {
            "id": f["id"],
            "rule": f["rule"],
            "slide": f["slide"],
            "severity": f["severity"],
            "status": "open",
            "round_opened": rep.get("round"),
            "evidence": f["evidence"],
            "suggested_fix": f["suggested_fix"],
            "disposition": None,
            "history": [{
                "seq": 1, "action": "open",
                "actor": "redteam_scan",
                "note": f"round {rep.get('round')} 检出",
            }],
        }
        new += 1
    return new


def get_entry(ledger, fid):
    e = ledger["entries"].get(fid)
    if e is None:
        print(f"ERROR: 未知 finding id: {fid}", file=sys.stderr)
        sys.exit(3)
    return e


def print_summary(ledger):
    s = ledger.get("summary", {})
    print(f"entries={s.get('total', 0)} open={s.get('open', 0)} "
          f"fixed={s.get('fixed', 0)} dispositioned={s.get('dispositioned', 0)} "
          f"open_errors={s.get('open_errors', 0)}")
    for e in ledger["entries"].values():
        print(f"  {e['id']:12s} {e['rule']} {e['severity']:5s} {e['status']:13s} "
              f"slide={e['slide']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="红队台账状态机管理")
    ap.add_argument("--findings", help="findings_roundN.json（入账）")
    ap.add_argument("--ledger", required=True, help="tribunal.json 路径")
    ap.add_argument("--fix", metavar="ID", help="将条目标记为 fixed")
    ap.add_argument("--note", help="--fix 的说明")
    ap.add_argument("--disposition", nargs=2, metavar=("ID", "TYPE"),
                    help=f"正式裁决，TYPE ∈ {VALID_DISPOSITIONS}")
    ap.add_argument("--reason", help="--disposition 的理由（必填）")
    ap.add_argument("--operator", default="agent", help="操作者标识")
    ap.add_argument("--status", action="store_true", help="仅打印台账汇总")
    args = ap.parse_args(argv)

    ledger = load_ledger(args.ledger)

    if args.status:
        save_ledger(ledger, args.ledger)
        print_summary(ledger)
        return 0

    if args.findings:
        try:
            new = cmd_ingest(ledger, args.findings)
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: 无法读取 findings: {e}", file=sys.stderr)
            return 2
        save_ledger(ledger, args.ledger)
        print(f"ingested {new} new finding(s) -> {args.ledger}")
        print_summary(ledger)
        return 0

    if args.fix:
        e = get_entry(ledger, args.fix)
        if e["status"] != "open":
            print(f"ERROR: {args.fix} 当前状态 {e['status']}，仅 open 可迁移", file=sys.stderr)
            return 3
        e["status"] = "fixed"
        append_history(e, "fix", args.operator, args.note or "")
        save_ledger(ledger, args.ledger)
        print(f"fixed {args.fix} by {args.operator}")
        return 0

    if args.disposition:
        fid, dtype = args.disposition
        if dtype not in VALID_DISPOSITIONS:
            print(f"ERROR: disposition 必须是 {VALID_DISPOSITIONS}", file=sys.stderr)
            return 3
        if not args.reason:
            print("ERROR: --disposition 必须配 --reason（裁决需正式理由）", file=sys.stderr)
            return 3
        e = get_entry(ledger, fid)
        if e["status"] != "open":
            print(f"ERROR: {fid} 当前状态 {e['status']}，仅 open 可迁移", file=sys.stderr)
            return 3
        e["status"] = "dispositioned"
        e["disposition"] = {"type": dtype, "reason": args.reason}
        append_history(e, "disposition", args.operator, f"{dtype}: {args.reason}")
        save_ledger(ledger, args.ledger)
        print(f"dispositioned {fid} as {dtype} by {args.operator}")
        return 0

    print("ERROR: 需要一个动作：--findings / --fix / --disposition / --status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
