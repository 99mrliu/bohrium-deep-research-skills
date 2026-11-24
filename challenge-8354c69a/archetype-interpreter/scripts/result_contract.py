#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_contract.py — 契约驱动的 result.json 骨架构建与更新（archetype-interpreter 版）。

从 case.json 提取 case_id 与 output_contract 要求的全部字段，生成诚实占位的
result.json；之后随分析推进反复调用本模块/CLI 更新。任何时刻磁盘上都存在一份
诚实可用的（partial）结果。

CLI:
  python3 result_contract.py init --case /input/case.json --out /app/output/result.json \
      [--note "启动骨架"]
  python3 result_contract.py update --out /app/output/result.json \
      [--status success|partial|unable_to_determine|refused] \
      [--set key=JSON-or-string] ... [--source "..."] [--uncertainty "..."] \
      [--limitation "..."] [--note "..."]
  python3 result_contract.py check --case /input/case.json --out /app/output/result.json
"""
import argparse
import json
import sys

VALID_STATUS = {"success", "partial", "unable_to_determine", "refused"}


def extract_contract(case):
    """宽容地从 case.json 提取 (case_id, 契约字段名列表)。"""
    case_id = case.get("case_id") or case.get("id") or case.get("caseId") or "unknown_case"
    contract = case.get("output_contract") or case.get("outputContract") or {}
    fields = []
    if isinstance(contract, dict):
        f = (contract.get("fields") or contract.get("required_fields")
             or contract.get("required") or contract.get("properties"))
        if isinstance(f, dict):
            fields = list(f.keys())
        elif isinstance(f, list):
            for it in f:
                if isinstance(it, str):
                    fields.append(it)
                elif isinstance(it, dict) and "name" in it:
                    fields.append(it["name"])
        if not fields:
            fields = [k for k, v in contract.items() if isinstance(v, (str, dict))]
    elif isinstance(contract, list):
        for it in contract:
            if isinstance(it, str):
                fields.append(it)
            elif isinstance(it, dict) and "name" in it:
                fields.append(it["name"])
    return case_id, fields


def init_result(case, note=None):
    case_id, fields = extract_contract(case)
    res = {
        "case_id": case_id,
        "status": "partial",
        "limitations": ["骨架已建立：契约字段尚未填写，分析进行中"],
        "sources": [],
        "uncertainty": [],
        "change_records": [],
    }
    for f in fields:
        res[f] = None
    if note:
        res["change_records"].append(note)
    return res


def maybe_json(s):
    t = s.strip()
    if t[:1] in "[{":
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    for cast in (int, float):
        try:
            return cast(t)
        except ValueError:
            pass
    return s


def cmd_init(a):
    case = json.load(open(a.case, encoding="utf-8"))
    res = init_result(case, note=a.note)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[result_contract] partial skeleton ->", a.out,
          "| case_id=%s | contract fields=%d" % (res["case_id"],
                                                 len([k for k in res if k not in
                                                      ("case_id", "status", "limitations",
                                                       "sources", "uncertainty",
                                                       "change_records")])))


def cmd_update(a):
    res = json.load(open(a.out, encoding="utf-8"))
    if a.status:
        if a.status not in VALID_STATUS:
            sys.exit("invalid status: " + a.status)
        res["status"] = a.status
    for kv in (a.set or []):
        if "=" not in kv:
            sys.exit("--set 需要 key=value: " + kv)
        k, v = kv.split("=", 1)
        res[k] = maybe_json(v)
    for lst, items in (("sources", a.source), ("uncertainty", a.uncertainty),
                       ("limitations", a.limitation), ("change_records", a.note)):
        res.setdefault(lst, [])
        for it in (items or []):
            res[lst].append(it)
    if a.status == "success":
        res["limitations"] = [x for x in res.get("limitations", [])
                              if "骨架已建立" not in x]
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[result_contract] updated", a.out, "status=", res["status"])


def cmd_check(a):
    case = json.load(open(a.case, encoding="utf-8"))
    res = json.load(open(a.out, encoding="utf-8"))
    case_id, fields = extract_contract(case)
    problems = []
    if res.get("case_id") != case_id:
        problems.append("case_id 不一致: result=%r case=%r" % (res.get("case_id"), case_id))
    for f in fields:
        if f not in res:
            problems.append("缺契约字段: " + f)
        elif res[f] in (None, "", [], {}):
            problems.append("契约字段为空: " + f)
    for k in ("status", "sources", "uncertainty", "change_records"):
        if k not in res:
            problems.append("缺元字段: " + k)
    if problems:
        print("[result_contract] CHECK FAIL")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("[result_contract] CHECK OK: %d 个契约字段均已填写" % len(fields))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--note", default=None)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("update")
    p.add_argument("--out", required=True)
    p.add_argument("--status", default=None)
    p.add_argument("--set", action="append")
    p.add_argument("--source", action="append")
    p.add_argument("--uncertainty", action="append")
    p.add_argument("--limitation", action="append")
    p.add_argument("--note", action="append")
    p.set_defaults(fn=cmd_update)
    p = sub.add_parser("check")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_check)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
