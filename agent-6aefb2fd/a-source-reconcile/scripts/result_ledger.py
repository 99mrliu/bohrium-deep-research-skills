#!/usr/bin/env python3
"""result_ledger.py — result.json 契约记账器（partial-first，seal 前强校验）。

用法：
  init  --case /input/case.json --out /app/output/result.json
        立即写一份 status=partial 的 result.json，镜像 case_id 与全部 output_contract 字段（空值）。
  fill  --out result.json --set 字段=值 [--set ...]     值可为 /app/output 路径或 JSON 字面量。
  note  --out result.json --uncertainty "..."            追加不确定性/异常说明（不覆盖）。
  seal  --case /input/case.json --out result.json [--status success|partial]
        seal 校验：case_id 一致、契约字段全非空、所有 /app/output 路径真实存在；
        任一不满足且要求 success 时拒绝封口（退出码 3），只允许以 partial 封口并说明原因。

设计取向：本 bundle 的重心是上游真实性，因此 init 会自动把 source_audit.json 的
哈希与主源裁决写入 sources（若存在），保证交付物的来源声明与审计证据同源。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_case(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def contract_fields(case):
    return [f["name"] for f in case.get("output_contract", {}).get("fields", [])]


def cmd_init(args):
    case = load_case(args.case)
    res = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "created_at": now(),
        "sources": [],
        "uncertainty": [],
        "change_log": [{"at": now(), "event": "init", "detail": "partial-first 占位"}],
    }
    for name in contract_fields(case):
        res[name] = None
    audit = find_audit(args.out)
    if audit:
        a = json.load(open(audit, encoding="utf-8"))
        for fl in a.get("files", []):
            res["sources"].append({"path": fl["path"], "sha256": fl["sha256"]})
        res["change_log"].append({"at": now(), "event": "sources_from_audit",
                                  "detail": f"primary={a.get('adjudication', {}).get('primary')}"})
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"RESULT_LEDGER: init partial fields={len(contract_fields(case))}")


def cmd_fill(args):
    res = json.load(open(args.out, encoding="utf-8"))
    for kv in args.set:
        k, _, v = kv.partition("=")
        if not k or not _:
            sys.exit(f"--set 需要 字段=值 形式: {kv}")
        try:
            res[k] = json.loads(v)
        except json.JSONDecodeError:
            res[k] = v
    res["change_log"].append({"at": now(), "event": "fill",
                              "detail": ";".join(kv.split("=")[0] for kv in args.set)})
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"RESULT_LEDGER: filled {len(args.set)} fields")


def cmd_note(args):
    res = json.load(open(args.out, encoding="utf-8"))
    res.setdefault("uncertainty", []).append(args.uncertainty)
    res["change_log"].append({"at": now(), "event": "uncertainty", "detail": args.uncertainty})
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("RESULT_LEDGER: uncertainty appended")


def find_audit(out_path):
    """按常见布局寻找 source_audit.json：输出目录、其兄弟 work 目录、/app/work。"""
    outdir = os.path.dirname(os.path.abspath(out_path))
    for cand in (os.path.join(outdir, "source_audit.json"),
                 os.path.join(os.path.dirname(outdir), "work", "source_audit.json"),
                 "/app/work/source_audit.json"):
        if os.path.exists(cand):
            return cand
    return None


def cmd_seal(args):
    case = load_case(args.case)
    res = json.load(open(args.out, encoding="utf-8"))
    if not res.get("sources"):
        audit = find_audit(args.out)
        if audit:
            a = json.load(open(audit, encoding="utf-8"))
            res["sources"] = [{"path": fl["path"], "sha256": fl["sha256"]}
                              for fl in a.get("files", [])]
            res.setdefault("change_log", []).append(
                {"at": now(), "event": "sources_from_audit", "detail": "seal 时补记审计哈希"})
    problems = []
    if res.get("case_id") != case.get("case_id"):
        problems.append(f"case_id 不一致: {res.get('case_id')} != {case.get('case_id')}")
    empty = [n for n in contract_fields(case) if res.get(n) in (None, "", [], {})]
    if empty:
        problems.append(f"契约字段为空: {empty}")
    def walk(v):
        if isinstance(v, str) and v.startswith("/app/output") and not os.path.exists(v):
            problems.append(f"路径不存在: {v}")
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    for n in contract_fields(case):
        walk(res.get(n))
    if problems and args.status == "success":
        for p in problems:
            print(f"SEAL_REFUSE: {p}", file=sys.stderr)
        print("SEAL_REFUSE: 存在空缺，禁止以 success 封口；修复后重试或以 partial 封口", file=sys.stderr)
        sys.exit(3)
    res["status"] = args.status if not problems else "partial"
    if problems:
        res.setdefault("uncertainty", []).append(
            "seal 时仍存在空缺（" + "; ".join(problems) + "），按诚实原则以 partial 交付")
    res["change_log"].append({"at": now(), "event": "seal", "detail": res["status"]})
    json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"RESULT_LEDGER: sealed status={res['status']} problems={len(problems)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--case", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("fill"); p.add_argument("--out", required=True); p.add_argument("--set", action="append", default=[])
    p = sub.add_parser("note"); p.add_argument("--out", required=True); p.add_argument("--uncertainty", required=True)
    p = sub.add_parser("seal"); p.add_argument("--case", required=True); p.add_argument("--out", required=True)
    p.add_argument("--status", default="success", choices=["success", "partial"])
    args = ap.parse_args()
    {"init": cmd_init, "fill": cmd_fill, "note": cmd_note, "seal": cmd_seal}[args.cmd](args)


if __name__ == "__main__":
    main()
