#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_validate.py — result.json 对 case.json output_contract 的机械逐字段验收。

验收内容（全部机械、确定性）：
  1. required_fields 逐字段：存在性 + 非空（空字符串/空列表/空字典/null 一律视为空）；
  2. status 枚举：complete / partial / blocked；
  3. findings 每条要素：id/type/severity/location{file,page,quote}/evidence/suggestion/
     verdict_status；severity 枚举合法；quote 非空；verdict_status 以「确认」或「待复核」开头。

输出 validation.json（PASS/FAIL + 逐字段明细）。FAIL 且未指定 --no-fix 时自动改写
result.json：status 降级为 partial（原为 blocked 则保持）、change_log 追加降级记录、
uncertainty 追加缺失/非法字段清单。

输入缺键、JSON 损坏、文件不存在均不崩溃：exit 0，输出中如实记录 error。
"""
import argparse
import json
import os
import sys

VALID_STATUS = ["complete", "partial", "blocked"]
VALID_SEVERITY = ["critical", "major", "minor", "info"]
VALID_CATEGORY = ["fact_error", "insufficient_evidence", "norm_issue", "suggestion"]
STATUS_RANK = {"complete": 2, "partial": 1, "blocked": 0}
FINDING_REQUIRED = ["id", "type", "severity", "location", "evidence", "suggestion",
                    "verdict_status"]
LOCATION_REQUIRED = ["file", "page", "quote"]  # section 建议有但不做硬性 FAIL


def load_json(path):
    """读 JSON；任何失败返回 (None, error_message)，不抛异常。"""
    if not os.path.isfile(path):
        return None, "file not found: %s" % path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:  # JSON 损坏、编码问题等
        return None, "cannot parse %s: %s" % (path, e)


def is_empty(v):
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def check_required_fields(result, required_fields):
    details = []
    missing = []
    for field in required_fields:
        if not isinstance(result, dict) or field not in result:
            details.append({"field": field, "check": "exists", "ok": False,
                            "message": "required field missing"})
            missing.append(field)
        elif is_empty(result.get(field)):
            details.append({"field": field, "check": "non_empty", "ok": False,
                            "message": "required field is empty"})
            missing.append(field)
        else:
            details.append({"field": field, "check": "exists+non_empty", "ok": True,
                            "message": "ok"})
    return details, missing


def check_status(result):
    status = result.get("status") if isinstance(result, dict) else None
    if status not in VALID_STATUS:
        return [{"field": "status", "check": "enum", "ok": False,
                 "message": "status must be one of %s, got %r" % (VALID_STATUS, status)}]
    return [{"field": "status", "check": "enum", "ok": True, "message": "ok"}]


def check_findings(result):
    details = []
    if not isinstance(result, dict):
        return details
    findings = result.get("findings")
    if findings is None:
        return details  # findings 本身缺失已由 required_fields 检查覆盖
    if not isinstance(findings, list):
        return [{"field": "findings", "check": "type", "ok": False,
                 "message": "findings must be a list, got %s" % type(findings).__name__}]
    for i, f in enumerate(findings):
        tag = "findings[%d]" % i
        if not isinstance(f, dict):
            details.append({"field": tag, "check": "type", "ok": False,
                            "message": "finding must be an object"})
            continue
        fid = f.get("id", tag)
        for key in FINDING_REQUIRED:
            if key not in f or is_empty(f.get(key)):
                details.append({"field": "%s.%s" % (tag, key), "check": "exists+non_empty",
                                "ok": False,
                                "message": "finding %s missing or empty '%s'" % (fid, key)})
        sev = f.get("severity")
        if sev is not None and sev not in VALID_SEVERITY:
            details.append({"field": "%s.severity" % tag, "check": "enum", "ok": False,
                            "message": "finding %s severity must be one of %s, got %r"
                                       % (fid, VALID_SEVERITY, sev)})
        cat = f.get("category")
        if cat is not None and cat not in VALID_CATEGORY:
            details.append({"field": "%s.category" % tag, "check": "enum", "ok": False,
                            "message": "finding %s category must be one of %s, got %r"
                                       % (fid, VALID_CATEGORY, cat)})
        loc = f.get("location")
        if isinstance(loc, dict):
            for key in LOCATION_REQUIRED:
                if is_empty(loc.get(key)):
                    details.append({"field": "%s.location.%s" % (tag, key),
                                    "check": "exists+non_empty", "ok": False,
                                    "message": "finding %s location missing or empty '%s'"
                                               % (fid, key)})
        elif loc is not None:
            details.append({"field": "%s.location" % tag, "check": "type", "ok": False,
                            "message": "finding %s location must be an object" % fid})
        vs = f.get("verdict_status")
        if isinstance(vs, str) and vs.strip():
            if not (vs.startswith("确认") or vs.startswith("待复核")):
                details.append({"field": "%s.verdict_status" % tag, "check": "format",
                                "ok": False,
                                "message": "finding %s verdict_status must start with "
                                           "'确认' or '待复核', got %r" % (fid, vs)})
    if not details:
        details.append({"field": "findings", "check": "elements", "ok": True,
                        "message": "%d finding(s) well-formed" % len(findings)})
    return details


def downgrade_result(result, missing_fields, fail_messages):
    """机械验收 FAIL 时自动改写 result.json（诚实降级）。返回改动说明列表。"""
    changes = []
    if not isinstance(result, dict):
        return changes
    old_status = result.get("status")
    # 只在现状不比 partial 更差时降级；blocked 保持 blocked
    if STATUS_RANK.get(old_status, STATUS_RANK["complete"]) > STATUS_RANK["partial"]:
        result["status"] = "partial"
        changes.append("status: %r -> 'partial'" % old_status)
    cl = result.get("change_log")
    if not isinstance(cl, list):
        cl = [] if cl is None else [str(cl)]
        result["change_log"] = cl
    entry = ("机械验收未过，状态自动降级为 partial；缺失/非法字段：%s"
             % ("、".join(missing_fields) if missing_fields else "见 validation.json 明细"))
    if entry not in cl:
        cl.append(entry)
        changes.append("change_log appended")
    uc = result.get("uncertainty")
    if not isinstance(uc, list):
        uc = [] if uc is None else [str(uc)]
        result["uncertainty"] = uc
    appended = 0
    for m in fail_messages:
        note = "机械验收未通过项：%s" % m
        if note not in uc:
            uc.append(note)
            appended += 1
    if appended:
        changes.append("uncertainty appended (%d item(s))" % appended)
    return changes


def main():
    ap = argparse.ArgumentParser(
        description="result.json 对 case.json output_contract.required_fields 的机械逐字段验收；"
                    "FAIL 时自动把 result.json 降级为诚实 partial（可用 --no-fix 关闭）。")
    ap.add_argument("--case", required=True, help="case.json 路径（取 output_contract.required_fields）")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--out", required=True, help="validation.json 输出路径")
    ap.add_argument("--no-fix", action="store_true",
                    help="只验收不改写 result.json（关闭自动降级）")
    args = ap.parse_args()

    case, case_err = load_json(args.case)
    result, result_err = load_json(args.result)

    required_fields = []
    if isinstance(case, dict):
        contract = case.get("output_contract")
        if isinstance(contract, dict) and isinstance(contract.get("required_fields"), list):
            required_fields = [str(x) for x in contract["required_fields"]]

    details = []
    if case_err:
        details.append({"field": "<case>", "check": "load", "ok": False, "message": case_err})
    if result_err:
        details.append({"field": "<result>", "check": "load", "ok": False,
                        "message": result_err})
    if not required_fields and not case_err:
        details.append({"field": "output_contract.required_fields", "check": "load",
                        "ok": False,
                        "message": "case.json 缺少 output_contract.required_fields，按空契约处理"})

    missing = []
    if isinstance(result, dict):
        d, missing = check_required_fields(result, required_fields)
        details.extend(d)
        details.extend(check_status(result))
        details.extend(check_findings(result))

    verdict = "PASS" if details and all(d["ok"] for d in details) else "FAIL"

    fail_messages = ["%s: %s" % (d["field"], d["message"]) for d in details if not d["ok"]]
    fixes = []
    if verdict == "FAIL" and not args.no_fix and isinstance(result, dict):
        fixes = downgrade_result(result, missing, fail_messages)
        if fixes:
            tmp = args.result + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, args.result)

    validation = {
        "note": "机械验收输出，由 contract_validate.py 确定性生成",
        "case_id": (case or {}).get("case_id") if isinstance(case, dict) else None,
        "verdict": verdict,
        "required_fields": required_fields,
        "summary": {
            "checks_total": len(details),
            "checks_failed": len(fail_messages),
            "missing_or_empty_fields": missing,
        },
        "auto_fix_applied": fixes,
        "details": details,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("verdict=%s checks=%d failed=%d fixes=%d -> %s"
          % (verdict, len(details), len(fail_messages), len(fixes), args.out))
    return 0  # 缺键/失败均 exit 0，验收结论见 validation.json


if __name__ == "__main__":
    sys.exit(main())
