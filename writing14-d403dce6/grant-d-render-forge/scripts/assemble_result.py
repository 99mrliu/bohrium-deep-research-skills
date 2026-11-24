#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 按 case.json 的 output_contract 装配/校验 result.json。

装配模式（默认）：
  读取 case.json 的 case_id 与 output_contract（字段清单运行时读取，不硬编码），
  在输出目录装配（或幂等更新）result.json：
    - 必含原始 case_id、status、reason、sources、uncertainty、deliverables；
    - output_contract 声明的每个字段都必须出现：本次未提供的填诚实占位
      【缺失：待补充】并列入 missing；占位存在时 status 不得为 success
      （自动降为 partial 并写明原因）；
    - deliverables 所列文件逐一校验真实存在于输出目录，不存在即报错退出 1；
    - 无时间戳，键排序输出：同样参数二次运行字节一致（幂等）。

校验模式（--validate）：
  只做合同符合性检查，不写文件。发现违规逐条报告并以退出码 1 结束。

用法：
  python3 assemble_result.py --case case.json --outdir /app/output \
      --status partial --reason "…" --source "…" --uncertainty "…" \
      --deliverable draft_v2.docx --set change_records='"change_record.md"'
  python3 assemble_result.py --validate --case case.json \
      --result /app/output/result.json --outdir /app/output

退出码：0 成功/校验通过；1 错误或校验不通过；2 参数错误。
"""
import argparse
import json
import os
import sys

VALID_STATUS = ("success", "partial", "unable_to_determine", "refused")
PLACEHOLDER = "【缺失：待补充】"
BASE_FIELDS = ("status", "reason", "sources", "uncertainty", "deliverables")


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        print("错误：无法读取%s %s: %s" % (what, path, exc), file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print("错误：%s %s 不是合法 JSON: %s" % (what, path, exc), file=sys.stderr)
        sys.exit(1)


def contract_fields(case):
    """从 case.json 提取 output_contract 字段清单（兼容 list / dict / 字符串）。"""
    oc = case.get("output_contract")
    if oc is None:
        return []
    if isinstance(oc, str):
        return [oc]
    if isinstance(oc, list):
        return [str(x) for x in oc]
    if isinstance(oc, dict):
        if isinstance(oc.get("fields"), list):
            return [str(x) for x in oc["fields"]]
        return [str(k) for k in oc.keys()]
    return []


def parse_set_value(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_assemble(args):
    case = load_json(args.case, "case.json")
    case_id = case.get("case_id")
    if not case_id:
        print("错误：case.json 缺少 case_id。", file=sys.stderr)
        return 1
    fields = contract_fields(case)

    outdir = args.outdir or "/app/output"
    os.makedirs(outdir, exist_ok=True)
    result_path = args.result or os.path.join(outdir, "result.json")

    result = {}
    if os.path.isfile(result_path):
        result = load_json(result_path, "已有 result.json")
    result["case_id"] = case_id

    if args.status:
        result["status"] = args.status
    elif result.get("status") not in VALID_STATUS:
        result["status"] = "partial"
    for key, default in (("reason", ""), ("sources", []),
                         ("uncertainty", []), ("deliverables", [])):
        result.setdefault(key, default)
    if args.reason is not None:
        result["reason"] = args.reason
    if args.source:
        result["sources"] = sorted(set(result["sources"]) | set(args.source))
    if args.uncertainty:
        result["uncertainty"] = sorted(set(result["uncertainty"]) | set(args.uncertainty))

    # deliverables：记录相对路径与字节数，并逐一核验真实存在
    deliverables = list(result["deliverables"])
    known = {d["path"] if isinstance(d, dict) else str(d) for d in deliverables}
    for rel in args.deliverable or []:
        if rel not in known:
            deliverables.append(rel)
    checked = []
    for item in deliverables:
        rel = item["path"] if isinstance(item, dict) else str(item)
        full = os.path.join(outdir, rel)
        if not os.path.isfile(full):
            print("错误：deliverable 不存在于输出目录: %s" % full, file=sys.stderr)
            return 1
        checked.append({"path": rel, "bytes": os.path.getsize(full)})
    result["deliverables"] = checked

    for pair in args.set or []:
        if "=" not in pair:
            print("错误：--set 须为 字段=值 形式: %s" % pair, file=sys.stderr)
            return 1
        key, raw = pair.split("=", 1)
        result[key] = parse_set_value(raw)

    # 合同字段全覆盖：缺失填诚实占位并列入 missing
    missing = []
    for field in fields:
        if field == "case_id":
            continue
        if field not in result or result[field] in (None, "", []):
            result[field] = PLACEHOLDER
        if result[field] == PLACEHOLDER:
            missing.append(field)
    result["missing"] = sorted(missing)

    if missing and result["status"] == "success":
        result["status"] = "partial"
        note = "合同字段 %s 仍为占位【缺失：待补充】，status 由 success 降为 partial。" \
               % "、".join(result["missing"])
        result["reason"] = (result["reason"] + " " + note).strip()

    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print("result.json 已装配: %s（status=%s，missing=%s）"
          % (result_path, result["status"], "、".join(result["missing"]) or "无"))
    return 0


def cmd_validate(args):
    case = load_json(args.case, "case.json")
    case_id = case.get("case_id")
    fields = contract_fields(case)
    result_path = args.result
    if not result_path:
        outdir = args.outdir or "/app/output"
        result_path = os.path.join(outdir, "result.json")
    result = load_json(result_path, "result.json")
    outdir = args.outdir or os.path.dirname(os.path.abspath(result_path))

    problems = []
    if result.get("case_id") != case_id:
        problems.append("case_id 缺失或与 case.json 不符: %r != %r"
                        % (result.get("case_id"), case_id))
    if result.get("status") not in VALID_STATUS:
        problems.append("status 非法: %r（须为 %s 之一）"
                        % (result.get("status"), "/".join(VALID_STATUS)))
    for key in ("reason", "sources", "uncertainty", "deliverables"):
        if key not in result:
            problems.append("缺少基础字段: %s" % key)
    for field in fields:
        if field == "case_id":
            continue
        if field not in result:
            problems.append("缺少 output_contract 字段: %s" % field)
        elif result[field] == PLACEHOLDER:
            problems.append("字段 %s 仍是占位 %s，未落实" % (field, PLACEHOLDER))
    for item in result.get("deliverables", []):
        rel = item["path"] if isinstance(item, dict) else str(item)
        if not os.path.isfile(os.path.join(outdir, rel)):
            problems.append("deliverable 文件不存在: %s" % rel)

    if problems:
        print("合同符合性校验不通过（%d 项）：" % len(problems), file=sys.stderr)
        for p in problems:
            print("  - %s" % p, file=sys.stderr)
        return 1
    print("合同符合性校验通过: %s" % result_path)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按 case.json 的 output_contract 装配/校验 result.json。")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--outdir", help="输出目录（运行时通常为 /app/output）")
    ap.add_argument("--result", help="result.json 路径（缺省 <outdir>/result.json）")
    ap.add_argument("--validate", action="store_true",
                    help="校验模式：只检查合同符合性，不写文件")
    ap.add_argument("--status", choices=VALID_STATUS, help="四态之一")
    ap.add_argument("--reason", help="status 原因说明")
    ap.add_argument("--source", action="append", help="来源条目（可多次）")
    ap.add_argument("--uncertainty", action="append", help="不确定项（可多次）")
    ap.add_argument("--deliverable", action="append",
                    help="交付物相对路径（可多次；须真实存在于 outdir）")
    ap.add_argument("--set", action="append", metavar="字段=值",
                    help="设置任意合同字段（值按 JSON 解析，失败按字符串）")
    args = ap.parse_args(argv)
    if args.validate:
        return cmd_validate(args)
    return cmd_assemble(args)


if __name__ == "__main__":
    sys.exit(main())
