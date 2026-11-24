#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_kit.py — 契约驱动 result.json 工具（process-qc-runner 版）。

与过程控制配合：每个阶段结束后都应调用一次 checkpoint，把当前最好结果
落盘——保证「任何时刻中断都有诚实交付」。

  python3 result_kit.py scaffold --case /input/case.json --out /app/output/result.json
  python3 result_kit.py checkpoint --out result.json --stage STAGE_ID \
      [--set k=v]... [--status S] [--limitation L] [--source S] [--uncertainty U]
  python3 result_kit.py verify --case case.json --out result.json
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
        f = oc.get("fields") or oc.get("required_fields") or oc.get("properties")
        if isinstance(f, dict):
            fields = list(f)
        elif isinstance(f, list):
            fields = [i if isinstance(i, str) else i.get("name") for i in f]
        if not fields:
            fields = [k for k, v in oc.items() if isinstance(v, (str, dict))]
    elif isinstance(oc, list):
        fields = [i if isinstance(i, str) else i.get("name") for i in oc]
    return cid, [x for x in fields if x]


def maybe_json(s):
    t = s.strip()
    if t[:1] in "[{":
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass
    for c in (int, float):
        try:
            return c(t)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(t.lower(), s)


def cmd_scaffold(a):
    case = json.load(open(a.case, encoding="utf-8"))
    cid, fields = contract_of(case)
    res = {"case_id": cid, "status": "partial",
           "limitations": ["过程化执行骨架；各阶段 checkpoint 将逐步填充"],
           "sources": [], "uncertainty": [],
           "change_records": ["scaffold: partial-first checkpoint"]}
    for f in fields:
        res[f] = None
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[result_kit] scaffold case_id=%s fields=%d" % (cid, len(fields)))


def cmd_checkpoint(a):
    res = json.load(open(a.out, encoding="utf-8"))
    for kv in a.set or []:
        k, v = kv.split("=", 1)
        res[k] = maybe_json(v)
    if a.status:
        if a.status not in VALID:
            sys.exit("bad status")
        res["status"] = a.status
    for key, vals in (("limitations", a.limitation), ("sources", a.source),
                      ("uncertainty", a.uncertainty)):
        for v in vals or []:
            res.setdefault(key, []).append(v)
    res.setdefault("change_records", []).append("checkpoint after stage: " + a.stage)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[result_kit] checkpoint(%s) status=%s" % (a.stage, res["status"]))


def cmd_verify(a):
    case = json.load(open(a.case, encoding="utf-8"))
    res = json.load(open(a.out, encoding="utf-8"))
    cid, fields = contract_of(case)
    bad = []
    if res.get("case_id") != cid:
        bad.append("case_id mismatch")
    for f in fields:
        if res.get(f) in (None, "", [], {}):
            bad.append("empty: " + f)
    for m in META[1:]:
        if m not in res:
            bad.append("missing meta: " + m)
    if bad:
        print("[result_kit] VERIFY FAIL")
        [print("  -", b) for b in bad]
        sys.exit(1)
    print("[result_kit] VERIFY OK (%d fields)" % len(fields))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scaffold")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_scaffold)
    p = sub.add_parser("checkpoint")
    p.add_argument("--out", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--set", action="append")
    p.add_argument("--status")
    p.add_argument("--limitation", action="append")
    p.add_argument("--source", action="append")
    p.add_argument("--uncertainty", action="append")
    p.set_defaults(fn=cmd_checkpoint)
    p = sub.add_parser("verify")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
