#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_engine.py — 输出契约工程：result.json 全生命周期管理 + 交付 QA。

子命令：
  scaffold  --case /input/case.json --out /app/output/result.json
      partial-first 骨架：case_id 原样、契约字段占位、元字段齐备。
  set       --out result.json --field F (--value V | --file F.json) [--status S]
      填字段；--file 从 JSON 文件读值（避免命令行转义事故）。
  lint      --case case.json --out result.json
      交付 QA 门禁，逐项检查并给出 exit code：
        L1 case_id 与 case.json 一致
        L2 契约字段全覆盖（非 null/空）
        L3 证据定位：每个字符串字段至少含一个可机检定位
           （文件名.扩展名 或 文件::位置 或 页码 p.N）
        L4 status 合法且与 limitations 自洽（success 时 limitations 不得含「待」「未」）
        L5 元字段齐备：sources/uncertainty/change_records 非空
      全部通过 exit 0，否则 exit 1 并列出失败项。
"""
import argparse
import json
import re
import sys

VALID = {"success", "partial", "unable_to_determine", "refused"}
META = ("case_id", "status", "limitations", "sources", "uncertainty", "change_records")
LOCATOR = re.compile(
    r"([\w\-./\\一-鿿]+\.(?:csv|txt|dat|tsv|json|xlsx|pdf|md|m|py))"
    r"(::[\w:.,!\-一-鿿]+)?|p\.\s?\d+|第\s?\d+\s?页")


def contract_of(case):
    cid = case.get("case_id") or case.get("id") or case.get("caseId") or "unknown_case"
    oc = case.get("output_contract") or case.get("outputContract") or {}
    fields = []
    if isinstance(oc, dict):
        f = oc.get("fields") or oc.get("required_fields") or oc.get("required") \
            or oc.get("properties")
        if isinstance(f, dict):
            fields = list(f)
        elif isinstance(f, list):
            fields = [i if isinstance(i, str) else i.get("name") for i in f]
        if not fields:
            fields = [k for k, v in oc.items() if isinstance(v, (str, dict))]
    elif isinstance(oc, list):
        fields = [i if isinstance(i, str) else i.get("name") for i in oc]
    return cid, [x for x in fields if x]


def cmd_scaffold(a):
    case = json.load(open(a.case, encoding="utf-8"))
    cid, fields = contract_of(case)
    res = {"case_id": cid, "status": "partial",
           "limitations": ["交付骨架已建立；全部契约字段待填写"],
           "sources": [], "uncertainty": ["尚未开始分析"],
           "change_records": ["scaffold: partial-first"]}
    for f in fields:
        res[f] = None
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[contract] scaffold: case_id=%s fields=%s" % (cid, fields))


def cmd_set(a):
    res = json.load(open(a.out, encoding="utf-8"))
    if a.file:
        res[a.field] = json.load(open(a.file, encoding="utf-8"))
    else:
        v = a.value
        if v.strip()[:1] in "[{":
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                pass
        res[a.field] = v
    if a.status:
        if a.status not in VALID:
            sys.exit("bad status")
        res["status"] = a.status
    res.setdefault("change_records", []).append("set field: " + a.field)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[contract] set %s (status=%s)" % (a.field, res.get("status")))


def _field_text(v):
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def cmd_lint(a):
    case = json.load(open(a.case, encoding="utf-8"))
    res = json.load(open(a.out, encoding="utf-8"))
    cid, fields = contract_of(case)
    fails = []
    # L1
    if res.get("case_id") != cid:
        fails.append("L1 case_id 不一致: %r != %r" % (res.get("case_id"), cid))
    # L2
    empty = [f for f in fields if res.get(f) in (None, "", [], {})]
    if empty:
        fails.append("L2 契约字段未填写: " + ", ".join(empty))
    # L3
    no_loc = []
    for f in fields:
        v = res.get(f)
        if v in (None, "", [], {}):
            continue
        if not LOCATOR.search(_field_text(v)):
            no_loc.append(f)
    if no_loc:
        fails.append("L3 以下字段缺可机检证据定位(文件名/::位置/页码): " + ", ".join(no_loc))
    # L4
    st = res.get("status")
    if st not in VALID:
        fails.append("L4 status 非法: %r" % st)
    if st == "success":
        bad_lim = [x for x in res.get("limitations", [])
                   if any(k in x for k in ("待", "未完成", "尚未"))]
        if bad_lim:
            fails.append("L4 status=success 但 limitations 含未完成表述: %s" % bad_lim)
    # L5
    for m in ("sources", "uncertainty", "change_records"):
        if not res.get(m):
            fails.append("L5 元字段为空: " + m)
    if fails:
        print("[contract] LINT FAIL (%d)" % len(fails))
        for x in fails:
            print("  -", x)
        sys.exit(1)
    print("[contract] LINT PASS: %d 字段覆盖 + 定位齐全 + 元字段齐备" % len(fields))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scaffold")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_scaffold)
    p = sub.add_parser("set")
    p.add_argument("--out", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--value", default="")
    p.add_argument("--file", default=None)
    p.add_argument("--status", default=None)
    p.set_defaults(fn=cmd_set)
    p = sub.add_parser("lint")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_lint)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
