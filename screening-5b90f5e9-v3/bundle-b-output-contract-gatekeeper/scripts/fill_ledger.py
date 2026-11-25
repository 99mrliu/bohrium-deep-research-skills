#!/usr/bin/env python3
"""fill_ledger.py — 填充台账（fill ledger）。

逐字段追踪 fill_state（filled / null_with_reason / pending）、填充来源产物路径、填充时间。
mark 子命令可同时把值写入 result.json——禁止“静默空字段”：任何 null 必须有 reason。

子命令：
  init    从 contract_spec.json 初始化台账（scaffold 已内置，供独立使用）
  mark    标记字段填充状态，可选 --value 同步写入 result.json
  report  打印台账汇总；--strict 时存在 pending 字段则退出码 3

退出码：0=成功；2=用法/IO/内部错误；3=台账规则违规（如缺 reason、来源产物不存在）。
幂等：重复 mark 同一（字段, 状态, 来源, 原因, 值）只刷新时间戳，不产生重复历史。

仅使用 Python 标准库。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

FILL_STATES = ("filled", "null_with_reason", "pending")


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def parse_value(raw):
    """--value 优先按 JSON 解析，失败则按纯字符串。"""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def cmd_init(args):
    spec = load_json(args.spec)
    case_id = spec.get("case_id")
    if not case_id:
        print("ERROR: spec 缺 case_id", file=sys.stderr)
        return 3
    if os.path.isfile(args.ledger):
        ledger = load_json(args.ledger)
    else:
        ledger = {"ledger_version": "1.0", "case_id": case_id, "created_at": utcnow(),
                  "fields": {}, "history": []}
    for f in spec.get("contract_fields") or []:
        ledger["fields"].setdefault(
            f, {"fill_state": "pending", "source_artifact": None, "reason": None,
                "updated_at": utcnow()})
    ledger["updated_at"] = utcnow()
    dump_json(args.ledger, ledger)
    print(f"OK: 台账初始化 {args.ledger} fields={len(ledger['fields'])}")
    return 0


def cmd_mark(args):
    if args.state not in FILL_STATES:
        print(f"ERROR: 非法 fill_state {args.state!r}，词表: {FILL_STATES}", file=sys.stderr)
        return 2
    if not os.path.isfile(args.ledger):
        print(f"ERROR: 台账不存在: {args.ledger}（先 scaffold 或 init）", file=sys.stderr)
        return 3
    ledger = load_json(args.ledger)
    if args.field not in ledger["fields"]:
        print(f"ERROR: 字段 {args.field!r} 不在台账中（合同外字段，禁止静默新增）", file=sys.stderr)
        return 3

    value = parse_value(args.value) if args.value is not None else None

    # --- 台账规则 ---
    if args.state == "null_with_reason" and not (args.reason and args.reason.strip()):
        print("ERROR: null_with_reason 必须提供非空 --reason（禁止静默空字段）", file=sys.stderr)
        return 3
    if args.state == "filled":
        if value is None and not args.source and not args.allow_existing:
            print("ERROR: filled 需要 --value 或 --source 之一（或 --allow-existing 确认沿用现值）",
                  file=sys.stderr)
            return 3
        if args.source and not os.path.exists(args.source):
            print(f"ERROR: 来源产物不存在: {args.source}", file=sys.stderr)
            return 3

    if args.state == "filled" and args.allow_existing:
        if not os.path.isfile(args.result):
            print(f"ERROR: result.json 不存在: {args.result}", file=sys.stderr)
            return 3
        existing = load_json(args.result).get(args.field)
        if existing is None or existing == [] or existing == "":
            print(f"ERROR: --allow-existing 但 result.json[{args.field!r}] 仍为空，不能标 filled",
                  file=sys.stderr)
            return 3

    # --- 同步写入 result.json ---
    if args.value is not None or args.state == "null_with_reason":
        if not os.path.isfile(args.result):
            print(f"ERROR: result.json 不存在: {args.result}", file=sys.stderr)
            return 3
        result = load_json(args.result)
        if args.field not in result:
            print(f"ERROR: result.json 缺字段 {args.field!r}（合同字段被删除？）", file=sys.stderr)
            return 3
        if args.value is not None:
            result[args.field] = value
        elif args.state == "null_with_reason":
            result[args.field] = None
        records = result.get("change_records")
        if isinstance(records, list):
            records.append({"ts": utcnow(), "actor": "fill_ledger.py",
                            "change": f"field_marked:{args.field}",
                            "detail": f"state={args.state}" + (f" reason={args.reason}" if args.reason else "")})
        dump_json(args.result, result)

    # --- 更新台账 ---
    entry = ledger["fields"][args.field]
    entry.update({
        "fill_state": args.state,
        "source_artifact": args.source,
        "reason": args.reason,
        "updated_at": utcnow(),
    })
    ledger["updated_at"] = utcnow()
    sig = {"field": args.field, "state": args.state, "source": args.source,
           "reason": args.reason, "value": json.dumps(value, ensure_ascii=False, sort_keys=True)}
    hist = ledger["history"]
    if hist and all(hist[-1].get(k) == v for k, v in sig.items()):
        hist[-1]["ts"] = utcnow()  # 幂等：相同标记只刷新时间
    else:
        hist.append(dict(sig, ts=utcnow(), actor="fill_ledger.py"))
    dump_json(args.ledger, ledger)
    print(f"OK: {args.field} -> {args.state}")
    return 0


def cmd_report(args):
    if not os.path.isfile(args.ledger):
        print(f"ERROR: 台账不存在: {args.ledger}", file=sys.stderr)
        return 3
    ledger = load_json(args.ledger)
    counts = {s: 0 for s in FILL_STATES}
    print(f"{'字段':<28} {'fill_state':<18} {'来源产物':<40} 原因")
    for name, e in ledger["fields"].items():
        counts[e["fill_state"]] = counts.get(e["fill_state"], 0) + 1
        print(f"{name:<28} {e['fill_state']:<18} {str(e.get('source_artifact'))[:40]:<40} {e.get('reason') or ''}")
    print(f"\n汇总: filled={counts['filled']} null_with_reason={counts['null_with_reason']} "
          f"pending={counts['pending']}")
    if args.strict and counts["pending"] > 0:
        print("STRICT: 存在 pending 字段", file=sys.stderr)
        return 3
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="填充台账：追踪字段级 fill_state")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--result", default=None)
    ap.add_argument("--spec", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    pm = sub.add_parser("mark")
    pm.add_argument("--field", required=True)
    pm.add_argument("--state", required=True, choices=FILL_STATES)
    pm.add_argument("--value", default=None, help="写入 result.json 的值（JSON 或字符串）")
    pm.add_argument("--source", default=None, help="填充来源产物路径")
    pm.add_argument("--reason", default=None, help="null_with_reason 的必填原因")
    pm.add_argument("--allow-existing", action="store_true",
                    help="确认沿用 result.json 中已有的非空值")

    pr = sub.add_parser("report")
    pr.add_argument("--strict", action="store_true")

    args = ap.parse_args(argv)
    try:
        args.ledger = args.ledger or os.path.join(args.work, "fill_ledger.json")
        args.result = args.result or os.path.join(args.output, "result.json")
        args.spec = args.spec or os.path.join(args.work, "contract_spec.json")
        if args.cmd == "init":
            return cmd_init(args)
        if args.cmd == "mark":
            return cmd_mark(args)
        if args.cmd == "report":
            return cmd_report(args)
        return 2
    except SystemExit:
        raise
    except Exception as e:
        print(f"FATAL: fill_ledger 内部错误: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
