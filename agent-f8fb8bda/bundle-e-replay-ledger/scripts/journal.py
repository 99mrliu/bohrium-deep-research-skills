#!/usr/bin/env python3
"""journal.py — append-only JSONL 运行日志（哈希链防篡改）。

子命令：
  init    --journal PATH                       写第 0 笔 genesis（prev_digest = "0"*64）
  append  --journal PATH --tool NAME --args-json JSON
          --results-count N --results-digest HEX --status {ok,failed,retry,empty}
          [--note TEXT]
  verify  --journal PATH                       重算全链，篡改/缺笔/插入 -> exit 1
  replay  --journal PATH                       打印复跑清单（供第三方逐笔重放比对）
  stats   --journal PATH                       按工具统计调用/失败/重试/empty

哈希规则（确定性，时间戳 ts 不参与哈希）：
  entry_digest = SHA256( prev_digest + canonical_json(hashed_fields) )
  canonical_json = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
  hashed_fields  = {seq, tool, args, results_count, results_digest, status, note}

退出码：0 通过；1 门控违例（逐项失败清单打到 stdout）；2 用法/IO 错误。
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import time

GENESIS_PREV = "0" * 64
STATUSES = ("ok", "failed", "retry", "empty")
HASHED_KEYS = ("seq", "tool", "args", "results_count", "results_digest", "status", "note")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_digest(prev_digest, entry):
    body = {k: entry[k] for k in HASHED_KEYS}
    payload = prev_digest + canonical(body)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def now_ts():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def read_journal(path):
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[FAIL] 第 {lineno} 行不是合法 JSON: {e}")
                sys.exit(1)
    return entries


def cmd_init(args):
    if os.path.exists(args.journal) and os.path.getsize(args.journal) > 0:
        print(f"[ERROR] 日志已存在且非空（append-only，禁止覆盖）: {args.journal}", file=sys.stderr)
        sys.exit(2)
    genesis = {
        "seq": 0,
        "tool": "genesis",
        "args": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "purpose": "run journal genesis (synthetic marker allowed)",
        },
        "results_count": 0,
        "results_digest": GENESIS_PREV,
        "status": "ok",
        "note": "genesis entry; prev_digest is 64 zeros",
        "prev_digest": GENESIS_PREV,
        "ts": now_ts(),
    }
    genesis["entry_digest"] = entry_digest(GENESIS_PREV, genesis)
    os.makedirs(os.path.dirname(os.path.abspath(args.journal)), exist_ok=True)
    with open(args.journal, "w", encoding="utf-8") as f:
        f.write(json.dumps(genesis, ensure_ascii=False) + "\n")
    print(f"[OK] genesis written: {args.journal}")
    print(f"     entry_digest={genesis['entry_digest']}")
    sys.exit(0)


def cmd_append(args):
    if not os.path.exists(args.journal):
        print(f"[ERROR] 日志不存在，请先 init: {args.journal}", file=sys.stderr)
        sys.exit(2)
    try:
        tool_args = json.loads(args.args_json)
    except json.JSONDecodeError as e:
        print(f"[ERROR] --args-json 不是合法 JSON: {e}", file=sys.stderr)
        sys.exit(2)
    entries = read_journal(args.journal)
    prev = entries[-1]
    entry = {
        "seq": prev["seq"] + 1,
        "tool": args.tool,
        "args": tool_args,
        "results_count": args.results_count,
        "results_digest": args.results_digest,
        "status": args.status,
        "note": args.note or "",
        "prev_digest": prev["entry_digest"],
        "ts": now_ts(),
    }
    entry["entry_digest"] = entry_digest(entry["prev_digest"], entry)
    with open(args.journal, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[OK] seq={entry['seq']} tool={entry['tool']} status={entry['status']} "
          f"entry_digest={entry['entry_digest']}")
    sys.exit(0)


def cmd_verify(args):
    if not os.path.exists(args.journal):
        print(f"[ERROR] 日志不存在: {args.journal}", file=sys.stderr)
        sys.exit(2)
    entries = read_journal(args.journal)
    failures = []
    if not entries:
        failures.append("日志为空，缺少 genesis")
    else:
        if entries[0].get("prev_digest") != GENESIS_PREV or entries[0].get("seq") != 0:
            failures.append("seq=0: genesis 的 prev_digest 不是 64 个 0 或 seq 不为 0")
    for i, e in enumerate(entries):
        seq = e.get("seq")
        if seq != i:
            failures.append(f"seq={seq}: 序号不连续（期望 {i}，疑似缺笔或插入）")
            continue
        expected_prev = GENESIS_PREV if i == 0 else entries[i - 1].get("entry_digest")
        if e.get("prev_digest") != expected_prev:
            failures.append(f"seq={seq}: prev_digest 与上一笔 entry_digest 不衔接（断链）")
            continue
        try:
            recomputed = entry_digest(e["prev_digest"], e)
        except KeyError as ke:
            failures.append(f"seq={seq}: 缺少哈希必需字段 {ke}")
            continue
        if e.get("entry_digest") != recomputed:
            failures.append(f"seq={seq}: entry_digest 重算不一致（内容被篡改）")
    if failures:
        print("[GATE FAIL] 哈希链校验未通过：")
        for f_ in failures:
            print(f"  - {f_}")
        sys.exit(1)
    print(f"[OK] 哈希链完整：共 {len(entries)} 笔（含 genesis），全部校验通过")
    sys.exit(0)


def cmd_replay(args):
    if not os.path.exists(args.journal):
        print(f"[ERROR] 日志不存在: {args.journal}", file=sys.stderr)
        sys.exit(2)
    entries = read_journal(args.journal)
    plan = []
    for e in entries:
        if e.get("tool") == "genesis":
            continue
        plan.append({
            "seq": e["seq"],
            "tool": e["tool"],
            "args": e["args"],
            "expect_results_count": e["results_count"],
            "expect_results_digest": e["results_digest"],
            "recorded_status": e["status"],
        })
    print(json.dumps({
        "replay_instructions": "按 seq 逐笔重放 tool+args，重算返回内容 SHA-256，"
                               "与 expect_results_digest / expect_results_count 比对；"
                               "empty/failed 笔应与重放时的真实失败语义一致。",
        "steps": plan,
    }, ensure_ascii=False, indent=2))
    sys.exit(0)


def cmd_stats(args):
    if not os.path.exists(args.journal):
        print(f"[ERROR] 日志不存在: {args.journal}", file=sys.stderr)
        sys.exit(2)
    entries = read_journal(args.journal)
    by_tool = {}
    for e in entries:
        t = e.get("tool", "?")
        s = by_tool.setdefault(t, {"calls": 0, "ok": 0, "failed": 0, "retry": 0, "empty": 0})
        s["calls"] += 1
        st = e.get("status")
        if st in STATUSES:
            s[st] += 1
    print(json.dumps({
        "total_entries_including_genesis": len(entries),
        "note": "empty（检索为空）与 failed（工具报错）分开计数；retry 保留每次重试",
        "by_tool": by_tool,
    }, ensure_ascii=False, indent=2))
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(description="append-only 运行日志（哈希链）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("--journal", required=True)
    pi.set_defaults(fn=cmd_init)

    pa = sub.add_parser("append")
    pa.add_argument("--journal", required=True)
    pa.add_argument("--tool", required=True)
    pa.add_argument("--args-json", required=True)
    pa.add_argument("--results-count", required=True, type=int)
    pa.add_argument("--results-digest", required=True)
    pa.add_argument("--status", required=True, choices=STATUSES)
    pa.add_argument("--note", default="")
    pa.set_defaults(fn=cmd_append)

    pv = sub.add_parser("verify")
    pv.add_argument("--journal", required=True)
    pv.set_defaults(fn=cmd_verify)

    pr = sub.add_parser("replay")
    pr.add_argument("--journal", required=True)
    pr.set_defaults(fn=cmd_replay)

    ps = sub.add_parser("stats")
    ps.add_argument("--journal", required=True)
    ps.set_defaults(fn=cmd_stats)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
