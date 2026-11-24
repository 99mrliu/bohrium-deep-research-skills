#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_result.py — 契约驱动 result.json 构建/更新（upstream-forensics-gate 版）。

子命令:
  init    --case /input/case.json --out /app/output/result.json
  update  --out result.json [--status S] [--set k=v]... [--source s]...
          [--uncertainty u]... [--limitation l]... [--note n]...
  check   --case case.json --out result.json   # 契约字段覆盖率，失败 exit 1
"""
import argparse
import json
import sys

VALID = {"success", "partial", "unable_to_determine", "refused"}
META = ("case_id", "status", "limitations", "sources", "uncertainty", "change_records")


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
    return cid, [f for f in fields if f]


def maybe_json(s):
    t = s.strip()
    if t[:1] in "[{":
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    for cast in (int, float):
        try:
            return cast(t)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(t.lower(), s)


def cmd_init(a):
    case = json.load(open(a.case, encoding="utf-8"))
    cid, fields = contract_of(case)
    res = {"case_id": cid, "status": "partial",
           "limitations": ["取证骨架已建立，真实性检查进行中"],
           "sources": [], "uncertainty": [], "change_records": ["gate init"]}
    for f in fields:
        res[f] = None
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[gate] partial skeleton: case_id=%s fields=%d" % (cid, len(fields)))


def cmd_update(a):
    res = json.load(open(a.out, encoding="utf-8"))
    if a.status:
        if a.status not in VALID:
            sys.exit("bad status")
        res["status"] = a.status
    for kv in a.set or []:
        k, v = kv.split("=", 1)
        res[k] = maybe_json(v)
    for key, vals in (("sources", a.source), ("uncertainty", a.uncertainty),
                      ("limitations", a.limitation), ("change_records", a.note)):
        for v in vals or []:
            res.setdefault(key, []).append(v)
    if a.status == "success":
        res["limitations"] = [x for x in res.get("limitations", []) if "骨架" not in x]
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[gate] updated status=%s" % res["status"])


def cmd_check(a):
    case = json.load(open(a.case, encoding="utf-8"))
    res = json.load(open(a.out, encoding="utf-8"))
    cid, fields = contract_of(case)
    bad = []
    if res.get("case_id") != cid:
        bad.append("case_id mismatch")
    for f in fields:
        if res.get(f) in (None, "", [], {}):
            bad.append("empty contract field: " + f)
    for m in META[1:]:
        if m not in res:
            bad.append("missing meta: " + m)
    if bad:
        print("[gate] CHECK FAIL")
        [print("  -", b) for b in bad]
        sys.exit(1)
    print("[gate] CHECK OK (%d fields)" % len(fields))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "update", "check"):
        p = sub.add_parser(name)
        p.add_argument("--case")
        p.add_argument("--out", required=True)
        if name == "init":
            p.set_defaults(fn=cmd_init)
        elif name == "check":
            p.set_defaults(fn=cmd_check)
        else:
            p.add_argument("--status")
            p.add_argument("--set", action="append")
            p.add_argument("--source", action="append")
            p.add_argument("--uncertainty", action="append")
            p.add_argument("--limitation", action="append")
            p.add_argument("--note", action="append")
            p.set_defaults(fn=cmd_update)
    a = ap.parse_args()
    if a.cmd in ("init", "check") and not a.case:
        sys.exit("--case required")
    a.fn(a)


if __name__ == "__main__":
    main()
