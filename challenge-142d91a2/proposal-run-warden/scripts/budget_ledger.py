#!/usr/bin/env python3
"""budget_ledger.py -- append-only 预算台账与超限预警。

每次模型调用后由 Agent 自记一行（JSONL，只增不改）：
  用途 purpose / 估计 tokens / 剩余请求数 requests_left / 阶段 phase

子命令：
  add     LEDGER --purpose TEXT --tokens N --requests-left M [--phase P]
  report  LEDGER [--requests-budget 64] [--warn-ratio 0.8]

report 判定已用请求占比 > warn-ratio（默认 80%）时：
  打印【强制收尾指令】并以退出码 2 报警；否则退出码 0。
"""
import argparse
import datetime
import json
import os
import sys

FINALIZE_DIRECTIVE = """\
【强制收尾指令】预算用量已超过阈值，立即执行且只执行：
  1. 停止一切新起草与重构（冻结改进）；
  2. 只填当前降级层级可完成的空缺字段；
  3. 运行 contract_guard.py 终检，按 guard_report 修复可速修项；
  4. checkpoint.py status 确认最终诚实状态后停止。"""


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_entries(path):
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                sys.exit("台账第 %d 行不是有效 JSON（append-only 文件禁止手改）" % ln)
    return entries


def cmd_add(a):
    entry = {
        "at": _utc_now(),
        "seq": len(_read_entries(a.ledger)) + 1,
        "purpose": a.purpose,
        "tokens_est": a.tokens,
        "requests_left": a.requests_left,
        "phase": a.phase,
    }
    directory = os.path.dirname(os.path.abspath(a.ledger))
    os.makedirs(directory, exist_ok=True)
    with open(a.ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    used = a.requests_budget - a.requests_left
    ratio = used / a.requests_budget
    out = {"logged": entry, "requests_used": used,
           "usage_pct": round(ratio * 100, 1)}
    if ratio > a.warn_ratio:
        out["warning"] = "over_threshold"
        print(json.dumps(out, ensure_ascii=False))
        print(FINALIZE_DIRECTIVE)
        sys.exit(2)
    print(json.dumps(out, ensure_ascii=False))


def cmd_report(a):
    entries = _read_entries(a.ledger)
    if not entries:
        sys.exit("台账为空：至少先用 add 记录一行")
    total_tokens = sum(e.get("tokens_est") or 0 for e in entries)
    last_left = entries[-1].get("requests_left")
    used = a.requests_budget - last_left if last_left is not None else None
    ratio = (used / a.requests_budget) if used is not None else 0.0
    report = {
        "entries": len(entries),
        "tokens_est_total": total_tokens,
        "requests_budget": a.requests_budget,
        "requests_used": used,
        "usage_pct": round(ratio * 100, 1),
        "phases_seen": sorted({e.get("phase") or "unphased" for e in entries}),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if ratio > a.warn_ratio:
        print(FINALIZE_DIRECTIVE)
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(
        description="append-only 预算台账与超限预警（详见文件顶部 docstring）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="追加一行台账")
    p.add_argument("ledger")
    p.add_argument("--purpose", required=True)
    p.add_argument("--tokens", type=int, required=True, help="本次调用估计 tokens")
    p.add_argument("--requests-left", type=int, required=True)
    p.add_argument("--phase", default=None)
    p.add_argument("--requests-budget", type=int, default=64)
    p.add_argument("--warn-ratio", type=float, default=0.8)

    p = sub.add_parser("report", help="汇总台账并按阈值预警")
    p.add_argument("ledger")
    p.add_argument("--requests-budget", type=int, default=64)
    p.add_argument("--warn-ratio", type=float, default=0.8)

    a = ap.parse_args()
    {"add": cmd_add, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
