#!/usr/bin/env python3
"""contract_seal.py — 交付契约封口器：partial-first、异常分类法、seal 强校验。

子命令：

  begin   --case /input/case.json --out /app/output/result.json
          立即写 partial result.json（case_id + 全部契约字段空值 + status=partial
          + 空 change_log），并生成 /app/work/contract_checklist.md 待填清单。
  fill    --out result.json --set 字段=值 [--set ...]
          值以 / 或 [ 开头时按路径/JSON 处理；/app/output 路径立即校验存在性，
          不存在即拒绝填写（不让悬空引用活到 seal）。
  raise   --out result.json --kind 类别 --detail "..."
          按异常分类法登记一条异常：missing_material（材料缺失）/
          query_failure（查询或读取失败）/ unexplainable_result（无法解释的结果）/
          human_confirmation_needed（需人工确认）/ capability_limit（能力边界）。
          写入 exceptions 字段与 uncertainty。
  seal    --case case.json --out result.json [--status success|partial]
          success 封口校验：case_id 一致、契约字段全非空、引用路径全部存在、
          exceptions 非空（至少一句"无未解释异常"或异常条目）。不满足即拒绝
          （退出码 3），只允许 partial 封口并自动附原因。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

TAXONOMY = ["missing_material", "query_failure", "unexplainable_result",
            "human_confirmation_needed", "capability_limit"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fields_of(case):
    return [f["name"] for f in case.get("output_contract", {}).get("fields", [])]


def cmd_begin(args):
    case = json.load(open(args.case, encoding="utf-8"))
    res = {"case_id": case.get("case_id"), "status": "partial", "created_at": now(),
           "sources": [], "uncertainty": [], "change_log": [
               {"at": now(), "event": "begin", "detail": "partial-first 占位"}]}
    for n in fields_of(case):
        res[n] = [] if n in ("figures", "quality_evidence") else None
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    work = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.out))), "work")
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "contract_checklist.md"), "w", encoding="utf-8") as f:
        f.write("# 交付契约清单\n\n")
        for fld in case.get("output_contract", {}).get("fields", []):
            f.write(f"- [ ] `{fld['name']}` — {fld.get('description', '')}\n")
        f.write("\n全部勾选且 seal 通过后方可 success 交付；缺项以 raise 登记异常并 partial。\n")
    print(f"CONTRACT_BEGIN: partial written, {len(fields_of(case))} fields pending")


def cmd_fill(args):
    res = json.load(open(args.out, encoding="utf-8"))
    for kv in args.set:
        k, sep, v = kv.partition("=")
        if not sep:
            sys.exit(f"--set 需要 字段=值: {kv}")
        val = v
        if v.lstrip()[:1] in "[{\"":
            try:
                val = json.loads(v)
            except json.JSONDecodeError:
                import ast
                val = ast.literal_eval(v)  # 兼容单引号 Python 字面量
        def chk(x):
            if isinstance(x, str) and x.startswith("/app/output") and not os.path.exists(x):
                sys.exit(f"FILL_REFUSE: 路径不存在 {x}（先把产物落盘再填写）")
            if isinstance(x, list):
                for y in x:
                    chk(y)
        chk(val)
        res[k] = val
    res["change_log"].append({"at": now(), "event": "fill",
                              "detail": ";".join(k.split("=")[0] for k in args.set)})
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"CONTRACT_FILL: {len(args.set)} fields")


def cmd_raise(args):
    if args.kind not in TAXONOMY:
        sys.exit(f"kind 必须是 {TAXONOMY} 之一")
    res = json.load(open(args.out, encoding="utf-8"))
    entry = {"kind": args.kind, "detail": args.detail, "at": now()}
    cur = res.get("exceptions")
    if not isinstance(cur, list):
        cur = [] if cur in (None, "") else [{"kind": "note", "detail": cur}]
    cur.append(entry)
    res["exceptions"] = cur
    res.setdefault("uncertainty", []).append(f"[{args.kind}] {args.detail}")
    res["change_log"].append({"at": now(), "event": "raise", "detail": args.detail})
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"CONTRACT_RAISE: {args.kind} 登记完成")


def cmd_seal(args):
    case = json.load(open(args.case, encoding="utf-8"))
    res = json.load(open(args.out, encoding="utf-8"))
    problems = []
    if res.get("case_id") != case.get("case_id"):
        problems.append("case_id 与 case.json 不一致")
    empty = [n for n in fields_of(case) if res.get(n) in (None, "", [], {})]
    if empty:
        problems.append(f"契约字段为空: {empty}")
    def walk(v):
        if isinstance(v, str) and v.startswith("/app/output") and not os.path.exists(v):
            problems.append(f"引用路径不存在: {v}")
        elif isinstance(v, list):
            for x in v:
                walk(x)
    for n in fields_of(case):
        walk(res.get(n))
    exc = res.get("exceptions")
    if exc in (None, "", [], {}):
        problems.append("exceptions 为空：必须显式写'无未解释异常'或用 raise 登记异常")
    if problems and args.status == "success":
        for p in problems:
            print("SEAL_REFUSE:", p, file=sys.stderr)
        sys.exit(3)
    res["status"] = "success" if (args.status == "success" and not problems) else "partial"
    if problems:
        res.setdefault("uncertainty", []).append(
            "seal 时发现空缺（" + "; ".join(problems) + "），按诚实原则以 partial 交付")
    res["change_log"].append({"at": now(), "event": "seal", "detail": res["status"]})
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"CONTRACT_SEAL: status={res['status']} problems={len(problems)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("begin"); p.add_argument("--case", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("fill"); p.add_argument("--out", required=True); p.add_argument("--set", action="append", default=[])
    p = sub.add_parser("raise"); p.add_argument("--out", required=True); p.add_argument("--kind", required=True); p.add_argument("--detail", required=True)
    p = sub.add_parser("seal"); p.add_argument("--case", required=True); p.add_argument("--out", required=True)
    p.add_argument("--status", default="success", choices=["success", "partial"])
    args = ap.parse_args()
    {"begin": cmd_begin, "fill": cmd_fill, "raise": cmd_raise,
     "seal": cmd_seal}[args.cmd](args)


if __name__ == "__main__":
    main()
