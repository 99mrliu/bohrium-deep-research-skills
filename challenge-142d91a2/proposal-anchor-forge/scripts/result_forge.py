#!/usr/bin/env python3
"""result_forge.py -- result.json 锻造器（本 bundle 独立实现的 init/final 契约工具）。

契约的唯一来源是 case.json 的 output_contract：字段名逐字段抄录，绝不凭题面猜。

  init  CASE_JSON OUT_JSON
      生成骨架：case_id、全部契约字段（初值 null）、status=partial、
      sources / uncertainty / change_records。工作一开始就写，任何时刻
      result.json 都是有效的诚实 partial。

  final CASE_JSON OUT_JSON [--status ok|partial|failed]
      [--set 字段=值]（可重复，值先按 JSON 解析，失败按字符串）
      [--verification 核验报告.json]
      收尾校验：
      - 契约字段仍为空（null）→ 强制 status=partial 并在 uncertainty 点名；
      - --verification 的报告 all_verified=false → 强制 partial，并把被拦截
        的 claim_id 写入 uncertainty 与 verification_audit；
      - 字段齐备且核验通过才允许落 status=ok。
"""
import argparse
import datetime
import json
import os
import sys

BUILDER = "proposal-anchor-forge result_forge/1.0"


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read_case(case_path):
    with open(case_path, encoding="utf-8") as fh:
        case = json.load(fh)
    contract = case.get("output_contract") or {}
    if isinstance(contract, dict):
        fields = list(contract.keys())
    elif isinstance(contract, list):
        fields = list(contract)
    else:
        fields = []
    return case.get("case_id", "unknown"), fields


def write_json(path, doc):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)


def cmd_init(args):
    case_id, fields = read_case(args.case)
    now = utc_now()
    doc = {"case_id": case_id,
           "status": "partial",
           "builder": BUILDER,
           "created_at": now,
           "sources": [],
           "uncertainty": ["契约已读取；锚定抽取与论断核验尚未完成，"
                           "本文件为诚实的 partial 结果。"],
           "change_records": [{"ts": now, "action": "init",
                               "detail": args.note}]}
    for field in fields:
        doc[field] = None
    write_json(args.out, doc)
    print(json.dumps({"case_id": case_id, "status": "partial",
                      "contract_fields": fields}, ensure_ascii=False))
    return 0


def parse_set(pair):
    if "=" not in pair:
        raise SystemExit("--set 需要 字段=值 形式，收到: %s" % pair)
    key, raw = pair.split("=", 1)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    return key, value


def cmd_final(args):
    case_id, fields = read_case(args.case)
    with open(args.out, encoding="utf-8") as fh:
        doc = json.load(fh)
    now = utc_now()
    doc["case_id"] = case_id
    doc.setdefault("sources", [])
    doc.setdefault("uncertainty", [])
    doc.setdefault("change_records", [])
    for field in fields:  # 契约字段缺失时补 null 并点名，不留空档
        if field not in doc:
            doc[field] = None
            doc["uncertainty"].append("契约字段 %s 此前未生成，已补 null" % field)

    for pair in args.set or []:
        key, value = parse_set(pair)
        doc[key] = value

    gate_failed = False
    if args.verification:
        with open(args.verification, encoding="utf-8") as fh:
            ver = json.load(fh)
        blocked_ids = [b.get("claim_id") for b in ver.get("blocked", [])]
        doc["verification_audit"] = {
            "report": os.path.basename(args.verification),
            "total": ver.get("total"), "ok": ver.get("ok"),
            "fail": ver.get("fail"), "unverifiable": ver.get("unverifiable"),
            "all_verified": ver.get("all_verified"),
            "link_back_rate": ver.get("link_back_rate"),
            "blocked_claim_ids": blocked_ids}
        if not ver.get("all_verified"):
            gate_failed = True
            doc["uncertainty"].append(
                "论断核验未全部通过，被拦截论断 %s 已按纪律排除出交付稿；"
                "修正并复验通过前状态不得为 ok" % "、".join(blocked_ids or ["(未列出)"]))

    missing = [f for f in fields if doc.get(f) is None]
    if missing:
        doc["uncertainty"].append("契约字段未填写: %s" % "、".join(missing))
    doc["contract_audit"] = {"required": fields, "missing": missing,
                             "complete": not missing}

    if args.status == "ok" and (missing or gate_failed):
        doc["status"] = "partial"  # 齐备度/核验门不通过，强制 partial
    else:
        doc["status"] = args.status
    doc["updated_at"] = now
    if args.note:
        doc["note"] = args.note
    doc["change_records"].append(
        {"ts": now, "action": "final",
         "detail": "requested=%s enforced=%s" % (args.status, doc["status"])})
    write_json(args.out, doc)
    print(json.dumps({"status": doc["status"],
                      "requested": args.status,
                      "contract_complete": not missing,
                      "missing": missing,
                      "gate_failed": gate_failed}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="读契约，生成诚实 partial 骨架")
    p_init.add_argument("case")
    p_init.add_argument("out")
    p_init.add_argument("--note", default="contract read; extraction pending")

    p_fin = sub.add_parser("final", help="收尾校验并按齐备度/核验门强制状态")
    p_fin.add_argument("case")
    p_fin.add_argument("out")
    p_fin.add_argument("--status", choices=["ok", "partial", "failed"],
                       default="partial")
    p_fin.add_argument("--set", action="append", default=[],
                       metavar="字段=值", help="填写契约字段，可重复")
    p_fin.add_argument("--verification", default=None,
                       help="verify_claims.py 的核验报告；未全过则强制 partial")
    p_fin.add_argument("--note", default="")

    args = ap.parse_args()
    return {"init": cmd_init, "final": cmd_final}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
