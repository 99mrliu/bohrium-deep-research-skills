#!/usr/bin/env python3
"""checkpoint.py — partial-first 检查点机制: 任何时刻中断都有诚实产物。

子命令:
  init     --workdir W --outdir O --case case.json
           读完 case.json 后立即把骨架 result.json (status=partial, 契约键全 null,
           case_id 正确) 原子写入 /app/output。此后任何中断都有诚实 partial。
  promote  --workdir W --outdir O --field key=value
           随工作推进逐字段升级 (value 先按 JSON 解析, 失败则按字符串)。
  assemble --workdir W --outdir O --chapters DIR
           把编辑完成的章节复制到 outdir/edited_chapters/ 并登记 edited_chapters 字段。
  finalize --workdir W --outdir O
           仅当 gates_report.json 全 PASS 且契约字段无 null 时置 status=complete,
           否则拒绝(非零退出)并保持诚实 partial。
  validate --workdir W --outdir O --case case.json
           体检 result.json: 可解析 / case_id 匹配 / 契约键齐全 / complete 时无 null。
  status   --workdir W --outdir O

每次写操作原子(tmp+rename)并追加 checkpoint.log 一行, 时间为相对秒数
(取自 budget.json 的 used_seconds, 不用绝对时间戳, 保证可复现)。
仅依赖 python3 标准库。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

SCHEMA = "checkpoint/v1"


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".ckpt-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def result_path(outdir):
    return os.path.join(outdir, "result.json")


def state_path(workdir):
    return os.path.join(workdir, "checkpoint_state.json")


def budget_seconds(workdir):
    """相对秒数时钟: 取 budget.json 的 used_seconds; 无账本则 0。"""
    p = os.path.join(workdir, "budget.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return int(json.load(fh).get("used_seconds", 0))
        except (ValueError, OSError):
            return 0
    return 0


def log_line(workdir, op, **kv):
    line = "t=%ds op=%s" % (budget_seconds(workdir), op)
    for k in sorted(kv):
        line += " %s=%s" % (k, kv[k])
    with open(os.path.join(workdir, "checkpoint.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print("[checkpoint] %s" % line)


def load_result(outdir):
    p = result_path(outdir)
    if not os.path.exists(p):
        sys.stderr.write("ERROR: %s 不存在, 先运行 checkpoint.py init (partial-first)\n" % p)
        raise SystemExit(2)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def load_state(workdir):
    with open(state_path(workdir), encoding="utf-8") as fh:
        return json.load(fh)


def cmd_init(args):
    with open(args.case, encoding="utf-8") as fh:
        case = json.load(fh)
    fields = case.get("output_contract", {}).get("fields", [])
    if not isinstance(fields, list) or not fields:
        sys.stderr.write("ERROR: case.json 缺 output_contract.fields, 无法建立契约骨架\n")
        raise SystemExit(2)
    result = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "sources": [],
        "problems": [],
    }
    if "note" in case:
        result["note"] = case["note"]
    for f in fields:
        result[f] = None
    os.makedirs(args.workdir, exist_ok=True)
    os.makedirs(args.outdir, exist_ok=True)
    atomic_write_json(result_path(args.outdir), result)
    atomic_write_json(state_path(args.workdir), {
        "schema": SCHEMA,
        "case_id": case.get("case_id"),
        "fields": fields,
    })
    log_line(args.workdir, "init", status="partial", fields=len(fields))
    print("[checkpoint] partial-first 骨架已写入 %s (status=partial, %d 个契约键全 null)"
          % (result_path(args.outdir), len(fields)))


def cmd_promote(args):
    if "=" not in args.field:
        sys.stderr.write("ERROR: --field 需要 key=value 形式\n")
        raise SystemExit(2)
    key, raw = args.field.split("=", 1)
    try:
        value = json.loads(raw)
    except ValueError:
        value = raw
    result = load_result(args.outdir)
    result[key] = value
    atomic_write_json(result_path(args.outdir), result)
    log_line(args.workdir, "promote", field=key, status=result.get("status"))


def cmd_assemble(args):
    result = load_result(args.outdir)
    dest = os.path.join(args.outdir, "edited_chapters")
    os.makedirs(dest, exist_ok=True)
    names = sorted(f for f in os.listdir(args.chapters) if f.endswith(".md"))
    if not names:
        sys.stderr.write("ERROR: %s 下没有 .md 章节\n" % args.chapters)
        raise SystemExit(2)
    for n in names:
        shutil.copyfile(os.path.join(args.chapters, n), os.path.join(dest, n))
    if "edited_chapters" in result:
        result["edited_chapters"] = ["edited_chapters/%s" % n for n in names]
    else:
        result.setdefault("problems", []).append(
            "契约未声明 edited_chapters, 章节已复制到 edited_chapters/ 但未登记字段")
    atomic_write_json(result_path(args.outdir), result)
    log_line(args.workdir, "assemble", chapters=len(names), status=result.get("status"))
    print("[checkpoint] 已复制 %d 个章节到 edited_chapters/" % len(names))


def cmd_finalize(args):
    result = load_result(args.outdir)
    state = load_state(args.workdir)
    gates = os.path.join(args.workdir, "gates_report.json")
    if os.path.exists(gates):
        with open(gates, encoding="utf-8") as fh:
            rep = json.load(fh)
        if rep.get("overall") != "PASS":
            failed = rep.get("failed_items", [])
            sys.stderr.write(
                "ERROR: 验收门未全过 (overall=%s, failed=%s), 拒绝置 complete; "
                "保持诚实 partial 并用 promote 更新 problems 字段\n"
                % (rep.get("overall"), failed))
            raise SystemExit(3)
    nulls = [f for f in state["fields"] if result.get(f) is None]
    if nulls:
        sys.stderr.write(
            "ERROR: 契约字段仍为 null: %s; 请填实值, 或显式填 \"NOT APPLICABLE — 原因\" "
            "后再 finalize\n" % nulls)
        raise SystemExit(4)
    result["status"] = "complete"
    atomic_write_json(result_path(args.outdir), result)
    log_line(args.workdir, "finalize", status="complete")
    print("[checkpoint] status=complete")


def cmd_validate(args):
    problems = []
    p = result_path(args.outdir)
    result = None
    if not os.path.exists(p):
        problems.append("result.json 不存在")
    else:
        try:
            with open(p, encoding="utf-8") as fh:
                result = json.load(fh)
        except ValueError as e:
            problems.append("result.json 不是合法 JSON: %s" % e)
    fields = []
    case_id = None
    if args.case and os.path.exists(args.case):
        with open(args.case, encoding="utf-8") as fh:
            case = json.load(fh)
        fields = case.get("output_contract", {}).get("fields", [])
        case_id = case.get("case_id")
    if result is not None:
        if case_id is not None and result.get("case_id") != case_id:
            problems.append("case_id 不匹配: result=%r case=%r" % (result.get("case_id"), case_id))
        if result.get("status") not in ("partial", "complete"):
            problems.append("status 非法: %r" % result.get("status"))
        for f in fields:
            if f not in result:
                problems.append("契约键缺失: %s" % f)
        if result.get("status") == "complete":
            for f in fields:
                if result.get(f) is None:
                    problems.append("status=complete 但契约字段为 null: %s" % f)
    for prob in problems:
        print("- %s" % prob)
    if problems:
        print("[validate] FAIL (%d 个问题)" % len(problems))
        raise SystemExit(1)
    print("[validate] OK")


def cmd_status(args):
    result = load_result(args.outdir)
    nulls = [k for k, v in result.items()
             if k not in ("case_id", "status", "sources", "problems", "note") and v is None]
    print(json.dumps({
        "status": result.get("status"),
        "null_fields": nulls,
        "problems": result.get("problems", []),
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="partial-first checkpoint (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="立即写 partial 骨架 result.json")
    p.add_argument("--workdir", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--case", required=True)
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("promote", help="逐字段升级 result.json")
    p.add_argument("--workdir", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--field", required=True, help="key=value (value 尝试 JSON 解析)")
    p.set_defaults(fn=cmd_promote)

    p = sub.add_parser("assemble", help="复制编辑后章节并登记字段")
    p.add_argument("--workdir", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--chapters", required=True)
    p.set_defaults(fn=cmd_assemble)

    p = sub.add_parser("finalize", help="验收门全过后置 complete")
    p.add_argument("--workdir", required=True)
    p.add_argument("--outdir", required=True)
    p.set_defaults(fn=cmd_finalize)

    p = sub.add_parser("validate", help="体检 result.json")
    p.add_argument("--workdir", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--case", default=None)
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("status", help="查看当前 partial 完成度")
    p.add_argument("--workdir", required=True)
    p.add_argument("--outdir", required=True)
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
