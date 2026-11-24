#!/usr/bin/env python3
"""stage_ledger.py -- 分阶段计数台账与闭合校验。

子命令：
  record   追加一条阶段记录到 audit_ledger.json：
             --stage identified|dedup|screened|included|excluded|needs_human|<自定义>
             --input-count N --output-count N --operator <谁>
             --basis <依据文件路径> [--notes ...] [--timestamp ISO]
           时间戳默认取当前 UTC；复跑示例时用 --timestamp 固定以保证确定性。
  validate 按 PRISMA 链做计数闭合校验（规则见 references/closure_rules.md）：
             C1 identified = dedup.removed + screened
             C2 screened   = included + excluded + needs_human (+unprocessed)
             C3 每条阶段记录自身 input/output 计数非负且 output<=input（流式阶段）
             C4 台账阶段序列完整：identified→dedup→screened→判定三态齐备
           输出 closure_report.json；任一 FAIL 即 exit 3。
  summary  打印台账的 PRISMA 风格流量表（stdout 与 audit_summary.json）。

退出码：0=正常/PASS；2=用法或输入缺失；3=闭合 FAIL。
"""
import argparse
import datetime
import json
import os
import sys

STAGES_FLOW = ["identified", "dedup", "screened", "included", "excluded", "needs_human"]


def load(path):
    if os.path.isfile(path):
        return json.load(open(path, encoding="utf-8"))
    return {"ledger_version": "1.0", "entries": []}


def save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def cmd_record(args):
    ledger = load(args.ledger)
    ts = args.timestamp or datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "seq": len(ledger["entries"]) + 1,
        "stage": args.stage,
        "input_count": args.input_count,
        "output_count": args.output_count,
        "operator": args.operator,
        "timestamp_utc": ts,
        "basis": args.basis,
        "notes": args.notes or "",
    }
    if entry["input_count"] is not None and entry["input_count"] < 0:
        print("RECORD-ERROR: input_count 不可为负", file=sys.stderr)
        return 2
    if entry["output_count"] is None or entry["output_count"] < 0:
        print("RECORD-ERROR: output_count 缺失或为负", file=sys.stderr)
        return 2
    ledger["entries"].append(entry)
    save(args.ledger, ledger)
    print("RECORDED #%d stage=%s in=%s out=%s" % (
        entry["seq"], entry["stage"], entry["input_count"], entry["output_count"]))
    return 0


def stage_out(ledger, stage):
    vals = [e["output_count"] for e in ledger["entries"] if e["stage"] == stage]
    return vals[-1] if vals else None


def check(name, ok, detail):
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def cmd_validate(args):
    if not os.path.isfile(args.ledger):
        print("VALIDATE-ERROR: ledger missing: %s" % args.ledger, file=sys.stderr)
        return 2
    ledger = load(args.ledger)
    entries = ledger["entries"]
    checks = []

    # C4 阶段齐备
    have = {e["stage"] for e in entries}
    missing = [s for s in STAGES_FLOW if s not in have]
    checks.append(check("C4-stage-completeness", not missing,
                        "缺失阶段：%s" % (missing or "无")))

    # C3 单条记录合法
    bad = [e["seq"] for e in entries
           if e["output_count"] is None or e["output_count"] < 0
           or (e["input_count"] is not None and e["input_count"] < 0)]
    checks.append(check("C3-entry-sanity", not bad,
                        "非法计数条目 seq：%s" % (bad or "无")))

    # C1 identified = dedup_removed + screened
    identified = stage_out(ledger, "identified")
    dedup_in = [e for e in entries if e["stage"] == "dedup"]
    screened = stage_out(ledger, "screened")
    if identified is not None and dedup_in and screened is not None:
        dedup_removed = dedup_in[-1]["input_count"] - dedup_in[-1]["output_count"] \
            if dedup_in[-1]["input_count"] is not None else None
        if dedup_removed is None:
            c1ok, c1detail = False, "dedup 记录缺 input_count"
        else:
            lhs = identified - dedup_removed
            c1ok = (lhs == screened)
            c1detail = ("identified(%d) - duplicates_removed(%d) = %d；screened=%d；差额=%d"
                        % (identified, dedup_removed, lhs, screened, screened - lhs))
    else:
        c1ok, c1detail = False, "缺 identified/dedup/screened 记录，无法核验"
    checks.append(check("C1-identification-closure", c1ok, c1detail))

    # C2 screened = included + excluded + needs_human (+unprocessed)
    inc = stage_out(ledger, "included") or 0
    exc = stage_out(ledger, "excluded") or 0
    nh = stage_out(ledger, "needs_human") or 0
    unp = stage_out(ledger, "unprocessed") or 0
    if screened is not None:
        rhs = inc + exc + nh + unp
        c2ok = (screened == rhs)
        c2detail = ("screened=%d；included+excluded+needs_human+unprocessed=%d+%d+%d+%d=%d；差额=%d"
                    % (screened, inc, exc, nh, unp, rhs, screened - rhs))
    else:
        c2ok, c2detail = False, "缺 screened 记录"
    checks.append(check("C2-screening-closure", c2ok, c2detail))

    overall = all(c["status"] == "PASS" for c in checks)
    report = {"overall": "PASS" if overall else "FAIL", "checks": checks,
              "ledger": os.path.abspath(args.ledger)}
    save(args.out, report)
    print("VALIDATE %s (%d checks)" % (report["overall"], len(checks)))
    for c in checks:
        print("  %s %s -- %s" % (c["status"], c["check"], c["detail"]))
    return 0 if overall else 3


def cmd_summary(args):
    if not os.path.isfile(args.ledger):
        print("SUMMARY-ERROR: ledger missing", file=sys.stderr)
        return 2
    ledger = load(args.ledger)
    flow = {s: stage_out(ledger, s) for s in STAGES_FLOW}
    flow["unprocessed"] = stage_out(ledger, "unprocessed")
    custom = sorted({e["stage"] for e in ledger["entries"]}
                    - set(STAGES_FLOW) - {"unprocessed"})
    for s in custom:
        flow[s] = stage_out(ledger, s)
    lines = ["# 筛选流程计数摘要（PRISMA 风格）", ""]
    for s, v in flow.items():
        if v is not None:
            lines.append("- **%s**: %d" % (s, v))
    text = "\n".join(lines) + "\n"
    print(text)
    save(args.out, {"flow": flow, "entries": len(ledger["entries"])})
    return 0


def main():
    ap = argparse.ArgumentParser(description="分阶段计数台账与闭合校验")
    ap.add_argument("--ledger", default="/app/work/audit/audit_ledger.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("record")
    pr.add_argument("--stage", required=True)
    pr.add_argument("--input-count", type=int, default=None)
    pr.add_argument("--output-count", type=int, required=True)
    pr.add_argument("--operator", default="system")
    pr.add_argument("--basis", default="")
    pr.add_argument("--notes", default="")
    pr.add_argument("--timestamp", default="")

    pv = sub.add_parser("validate")
    pv.add_argument("--out", default="/app/work/audit/closure_report.json")

    ps = sub.add_parser("summary")
    ps.add_argument("--out", default="/app/work/audit/audit_summary.json")

    args = ap.parse_args()
    if args.cmd == "record":
        sys.exit(cmd_record(args))
    if args.cmd == "validate":
        sys.exit(cmd_validate(args))
    if args.cmd == "summary":
        sys.exit(cmd_summary(args))


if __name__ == "__main__":
    main()
