#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""budget_ledger.py — 仅追加式预算账本（JSONL，sha256 链式完整性）。

命令：
  append  追加一条事件（plan/spend/checkpoint/degrade/note）到 ledger.jsonl。
  state   纯粹从账本重算 budget_state.json（已用/剩余 requests、seconds、tokens）。
  verify  校验整链 sha256（每行哈希 = sha256(规范JSON(去除 line_hash 的行体))）。

退出码：0 正常；1 违反（链断裂、账本损坏）；2 用法错误。
仅使用 Python 标准库。
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

GENESIS = "0" * 64
VALID_KINDS = ("plan", "spend", "checkpoint", "degrade", "note")
DIMS = ("requests", "seconds", "tokens")
DEFAULT_BUDGET = {"requests": 64, "seconds": 900, "tokens": 16384}


def canon(obj):
    """确定性 JSON 序列化：键排序、紧凑分隔符、保留非 ASCII。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def line_hash(body):
    return sha(canon(body))


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read_lines(path):
    if not os.path.exists(path):
        return []
    lines = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
    return lines


def verify_chain(lines):
    """逐行校验 seq 连续性、prev_hash 链接与 line_hash 重算值。"""
    prev = GENESIS
    for i, ln in enumerate(lines):
        for key in ("seq", "ts", "kind", "payload", "prev_hash", "line_hash"):
            if key not in ln:
                return False, "line %d: 缺少字段 %s" % (i, key)
        if ln["seq"] != i:
            return False, "line %d: seq 不连续（得到 %r）" % (i, ln["seq"])
        if ln["prev_hash"] != prev:
            return False, "line %d: prev_hash 链接断裂" % i
        body = {k: ln[k] for k in ("seq", "ts", "kind", "payload", "prev_hash")}
        if ln["line_hash"] != line_hash(body):
            return False, "line %d: line_hash 与载荷不符（疑似篡改）" % i
        prev = ln["line_hash"]
    return True, "ok"


def load_json_arg(text_or_path):
    if os.path.exists(text_or_path):
        with open(text_or_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(text_or_path)


def cmd_append(args):
    if args.kind not in VALID_KINDS:
        print("错误：未知事件类型 %r，合法值：%s" % (args.kind, ",".join(VALID_KINDS)), file=sys.stderr)
        return 2
    try:
        payload = load_json_arg(args.payload)
    except (ValueError, OSError) as exc:
        print("错误：payload 不是合法 JSON 或不可读：%s" % exc, file=sys.stderr)
        return 2
    lines = read_lines(args.ledger)
    ok, msg = verify_chain(lines)
    if not ok:
        # 账本已损坏：拒绝在断裂的链上继续追加。
        print("违反：账本损坏，拒绝追加：%s" % msg, file=sys.stderr)
        return 1
    prev = lines[-1]["line_hash"] if lines else GENESIS
    body = {"seq": len(lines), "ts": now_iso(), "kind": args.kind,
            "payload": payload, "prev_hash": prev}
    rec = dict(body)
    rec["line_hash"] = line_hash(body)
    os.makedirs(os.path.dirname(os.path.abspath(args.ledger)), exist_ok=True)
    with open(args.ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({"appended_seq": rec["seq"], "line_hash": rec["line_hash"]},
                     ensure_ascii=False))
    return 0


def recompute_spent(lines):
    spent = {d: 0 for d in DIMS}
    n_events = 0
    for ln in lines:
        n_events += 1
        if ln["kind"] == "spend":
            p = ln["payload"]
            for d in DIMS:
                spent[d] += int(p.get(d, 0))
    return spent, n_events


def cmd_state(args):
    lines = read_lines(args.ledger)
    ok, msg = verify_chain(lines)
    if not ok:
        print("违反：账本损坏，无法重算状态：%s" % msg, file=sys.stderr)
        return 1
    if args.budget:
        try:
            budget = load_json_arg(args.budget)
        except (ValueError, OSError) as exc:
            print("错误：budget 不是合法 JSON 或不可读：%s" % exc, file=sys.stderr)
            return 2
    else:
        budget = dict(DEFAULT_BUDGET)
    for d in DIMS:
        budget.setdefault(d, DEFAULT_BUDGET[d])
    spent, n_events = recompute_spent(lines)
    remaining = {d: budget[d] - spent[d] for d in DIMS}
    state = {
        "version": 1,
        "budget": budget,
        "spent": spent,
        "remaining": remaining,
        "events": n_events,
        "ledger_head": lines[-1]["line_hash"] if lines else GENESIS,
        "recomputed_at": now_iso(),
        "source": "recomputed-from-ledger",
    }
    if args.policy:
        try:
            policy = load_json_arg(args.policy)
            th = policy.get("degrade_threshold", {})
            state["below_threshold"] = [d for d in DIMS
                                        if d in th and remaining[d] < th[d]]
        except (ValueError, OSError):
            state["below_threshold"] = []
    out = args.out or "budget_state.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"state_file": out, "remaining": remaining,
                      "events": n_events}, ensure_ascii=False))
    return 0


def cmd_verify(args):
    lines = read_lines(args.ledger)
    ok, msg = verify_chain(lines)
    if not ok:
        print("违反：%s" % msg, file=sys.stderr)
        return 1
    print(json.dumps({"verify": "ok", "lines": len(lines),
                      "head": lines[-1]["line_hash"] if lines else GENESIS},
                     ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="仅追加式预算账本（sha256 链）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_app = sub.add_parser("append", help="追加一条事件")
    p_app.add_argument("--ledger", required=True, help="ledger.jsonl 路径")
    p_app.add_argument("--kind", required=True, help="plan/spend/checkpoint/degrade/note")
    p_app.add_argument("--payload", required=True,
                       help="JSON 字符串，或指向 JSON 文件的路径")

    p_st = sub.add_parser("state", help="从账本重算 budget_state.json")
    p_st.add_argument("--ledger", required=True)
    p_st.add_argument("--budget", help="预算 JSON 字符串或文件（缺省 64/900/16384）")
    p_st.add_argument("--policy", help="scheduling_policy.json（用于标注 below_threshold）")
    p_st.add_argument("--out", help="输出路径（缺省 ./budget_state.json）")

    p_v = sub.add_parser("verify", help="校验 sha256 链")
    p_v.add_argument("--ledger", required=True)

    args = ap.parse_args(argv)
    if args.cmd == "append":
        return cmd_append(args)
    if args.cmd == "state":
        return cmd_state(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
