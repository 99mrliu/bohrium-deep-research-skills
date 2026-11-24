#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""final_audit.py — 交付前最终对账脚本（仅标准库，无网络，确定性输出）。

对 /app/output 中的 result.json 及相关记录执行契约审计，写出
contract_audit.json 报告；exit 0 当且仅当 verdict 为 pass。

检查项：
  1. result.json 可解析；
  2. case_id 与 case.json 一致；
  3. output_contract 每个字段均存在且不为 "__pending__"；
  4. result.json 登记的每个 artifact 路径在磁盘上存在且非空；
  5. 状态一致性：success 要求零契约违例且零占位；partial 要求非空 partial_reason/limits；
  6. uncertainty 条目均为非空字符串；
  7. change_record.md 存在且至少有 1 条记录。
"""

import argparse
import json
import os
import sys

PLACEHOLDER = "__pending__"


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def extract_case_id(case):
    if not isinstance(case, dict):
        return None
    for key in ("case_id", "id", "caseId"):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if val is not None and not isinstance(val, (dict, list)):
            return str(val)
    return None


def extract_contract_fields(case):
    if not isinstance(case, dict):
        return []
    raw = case.get("output_contract")
    names = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    elif isinstance(raw, dict):
        names = [k for k in raw.keys() if isinstance(k, str) and k.strip()]
    seen = set()
    ordered = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def resolve_artifact_path(path, out_dir):
    """相对路径依次按当前工作目录与 --out 的父目录解析。"""
    if os.path.isabs(path):
        return path
    candidates = [path, os.path.join(os.path.dirname(os.path.abspath(out_dir)), path)]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return candidates[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="最终对账：审计 result.json 是否满足运行契约")
    parser.add_argument("--case", required=True, help="case.json 路径，如 /input/case.json")
    parser.add_argument("--out", required=True, help="输出目录，如 /app/output")
    parser.add_argument("--report", required=True, help="审计报告写出路径，如 /app/output/contract_audit.json")
    args = parser.parse_args(argv)

    checks = []

    def add(check, ok, detail):
        checks.append({"check": check, "ok": bool(ok), "detail": detail})

    # 1. result.json 可解析
    result_path = os.path.join(args.out, "result.json")
    result, rerr = load_json(result_path)
    add("result_json_parses", result is not None and isinstance(result, dict),
        "result.json 解析成功" if isinstance(result, dict) else "result.json 缺失或不可解析: %s" % rerr)
    if not isinstance(result, dict):
        result = {}

    # 2. case_id 一致
    case, cerr = load_json(args.case)
    expected_id = extract_case_id(case)
    actual_id = result.get("case_id")
    if expected_id is None:
        add("case_id_matches", False, "case.json 缺失、不可解析或无 case_id: %s" % (cerr or "无 case_id 字段"))
    else:
        add("case_id_matches", actual_id == expected_id,
            "case_id=%s" % actual_id if actual_id == expected_id
            else "case_id 不一致: result=%r case=%r" % (actual_id, expected_id))

    # 3. 契约字段覆盖
    contract_fields = extract_contract_fields(case) if isinstance(case, dict) else []
    violations = []
    for field in contract_fields:
        if field not in result:
            violations.append("%s(缺失)" % field)
        elif result.get(field) == PLACEHOLDER:
            violations.append("%s(仍为占位)" % field)
    filled = len(contract_fields) - len(violations)
    add("contract_fields_filled", not violations,
        "契约字段 %d/%d 已填写" % (filled, len(contract_fields)) if not violations
        else "契约违例: %s" % ", ".join(violations))

    # 4. artifact 路径存在且非空
    artifacts = result.get("artifacts")
    bad_artifacts = []
    if isinstance(artifacts, list):
        for entry in artifacts:
            if not isinstance(entry, dict):
                bad_artifacts.append("<非对象条目>")
                continue
            raw_path = entry.get("path", "")
            resolved = resolve_artifact_path(raw_path, args.out)
            if not os.path.isfile(resolved):
                bad_artifacts.append("%s(不存在)" % raw_path)
            elif os.path.getsize(resolved) == 0:
                bad_artifacts.append("%s(空文件)" % raw_path)
    add("artifacts_exist_nonempty", not bad_artifacts,
        "全部 artifact 存在且非空" if not bad_artifacts
        else "artifact 异常: %s" % ", ".join(bad_artifacts))

    # 5. 状态一致性
    status = result.get("status")
    pending = [f for f in contract_fields if result.get(f) == PLACEHOLDER]
    if status == "success":
        ok = not violations and not pending
        add("status_consistency", ok,
            "status=success 且契约零违例" if ok
            else "status=success 但存在契约违例或占位字段: %s" % ", ".join(violations + pending))
    elif status == "partial":
        reason = result.get("partial_reason") or result.get("limits")
        ok = isinstance(reason, str) and bool(reason.strip())
        add("status_consistency", ok,
            "status=partial 且附有限制说明" if ok
            else "status=partial 但缺少非空 partial_reason/limits 说明")
    elif status in ("unable_to_determine", "refused"):
        add("status_consistency", True, "status=%s（终态，无需契约覆盖）" % status)
    else:
        add("status_consistency", False, "status 非法或缺失: %r" % status)

    # 6. uncertainty 条目均为非空字符串
    uncertainty = result.get("uncertainty", [])
    bad_unc = []
    if isinstance(uncertainty, list):
        for i, item in enumerate(uncertainty, 1):
            if not isinstance(item, str) or not item.strip():
                bad_unc.append("第%d条" % i)
    else:
        bad_unc.append("uncertainty 不是列表")
    add("uncertainty_entries_nonempty", not bad_unc,
        "uncertainty 共 %d 条，均为非空字符串" % (len(uncertainty) if isinstance(uncertainty, list) else 0)
        if not bad_unc else "uncertainty 异常条目: %s" % ", ".join(bad_unc))

    # 7. change_record.md 存在且至少 1 条记录
    record_path = os.path.join(args.out, "change_record.md")
    n_entries = 0
    if os.path.isfile(record_path):
        with open(record_path, "r", encoding="utf-8") as fh:
            n_entries = sum(1 for ln in fh if ln.strip().startswith("- seq "))
    add("change_record_present", n_entries >= 1,
        "change_record.md 含 %d 条记录" % n_entries if n_entries >= 1
        else "change_record.md 缺失或无任何 seq 记录")

    verdict = "pass" if all(c["ok"] for c in checks) else "fail"
    report = {
        "verdict": verdict,
        "checks": checks,
        "contract_coverage": {"required": len(contract_fields), "filled": filled},
    }
    report_dir = os.path.dirname(os.path.abspath(args.report))
    os.makedirs(report_dir, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("[final_audit] verdict=%s coverage=%d/%d -> %s" % (
        verdict, filled, len(contract_fields), args.report))
    for c in checks:
        print("  [%s] %s: %s" % ("OK" if c["ok"] else "FAIL", c["check"], c["detail"]))
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
