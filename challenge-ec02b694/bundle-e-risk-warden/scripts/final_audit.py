#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""final_audit.py — 交付前最终审计（risk-warden 收尾必做）。

审计 /app/output/result.json：
  C1 readable            result.json 存在且可解析
  C2 case_id             非空、非 "unknown"；提供 --case 时必须与 case.json 一致
  C3 contract_coverage   output_contract 全部字段存在且非占位（契约动态读取自 --case）
  C4 no_placeholder      契约字段内无占位残留（null / TODO / TBD / PLACEHOLDER /
                         待填写 / 占位 / {"_placeholder": true}，递归扫描）
  C5 evidence            每条推荐参数值（含 value 与 param/name/parameter 的字典）
                         必须带可行性证据引用（evidence/evidence_ref/source/sources 非空）
                         或显式标注 "待确认"/confirmed=false
  C6 assumption_confirm  存在 assumption=true 的条目时，confirmation_items 必须非空
  C7 status_consistency  status ∈ {success, partial, unable_to_determine, refused}；
                         存在未消解违例时不得声称 success——强制回退 partial 并写明
                         partial_reason（就地改写 result.json 并追加 change_log）
  C8 meta_fields         sources / uncertainty / change_log 三个元字段存在且为列表

输出：audit_report.json（逐项检查 + verdict）。通过 exit 0，失败 exit 3。
任何输入不得产生 traceback。
"""
import argparse
import json
import os
import sys
import time

EXIT_OK = 0
EXIT_FAIL = 3

ALLOWED_STATUS = ("success", "partial", "unable_to_determine", "refused")
PLACEHOLDER_TOKENS = ("TODO", "TBD", "PLACEHOLDER", "<PENDING>", "待填写", "占位符")
EVIDENCE_KEYS = ("evidence", "evidence_ref", "evidence_refs", "source", "sources", "citation")
PARAM_NAME_KEYS = ("param", "name", "parameter")


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_write_json(path, obj):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[final_audit] 写文件失败 %s: %s\n" % (path, exc))
        return False


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def extract_contract_fields(case):
    if not isinstance(case, dict):
        return []
    oc = case.get("output_contract")
    if isinstance(oc, list):
        return [str(x) for x in oc]
    if isinstance(oc, dict):
        return [str(k) for k in oc.keys()]
    return []


def is_placeholder_value(v):
    """判断单个值是否为占位残留。"""
    if v is None:
        return True
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return True
        up = s.upper()
        return any(tok in up for tok in PLACEHOLDER_TOKENS if tok.isascii()) or \
            any(tok in s for tok in PLACEHOLDER_TOKENS if not tok.isascii())
    if isinstance(v, dict):
        if v.get("_placeholder") is True:
            return True
        return any(is_placeholder_value(x) for x in v.values())
    if isinstance(v, list):
        if not v:
            return True
        return any(is_placeholder_value(x) for x in v)
    return False


def walk(node, path="$"):
    """生成 (path, value) 先序遍历。"""
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, "%s[%d]" % (path, i))


def find_param_recommendations(result):
    """找出所有形似推荐参数的字典：含 value 且含 param/name/parameter。"""
    found = []
    for path, v in walk(result):
        if isinstance(v, dict) and "value" in v and any(k in v for k in PARAM_NAME_KEYS):
            found.append((path, v))
    return found


def has_evidence_or_unconfirmed(d):
    for k in EVIDENCE_KEYS:
        ev = d.get(k)
        if isinstance(ev, str) and ev.strip():
            return True
        if isinstance(ev, list) and ev:
            return True
    if d.get("confirmed") is False:
        return True
    for v in d.values():
        if isinstance(v, str) and "待确认" in v:
            return True
    return False


def find_assumptions(result):
    return [(p, v) for p, v in walk(result)
            if isinstance(v, dict) and v.get("assumption") is True]


def run_audit(result, result_path, contract_fields, expected_case_id):
    checks = []

    def add(check_id, name, passed, details):
        checks.append({"check_id": check_id, "name": name,
                       "passed": bool(passed), "details": details})

    # C2 case_id
    cid = result.get("case_id")
    cid_ok = isinstance(cid, str) and cid.strip() and cid != "unknown"
    if expected_case_id is not None:
        cid_ok = cid_ok and (cid == expected_case_id)
    add("C2", "case_id 有效且与 case.json 一致", cid_ok,
        "case_id=%r expected=%r" % (cid, expected_case_id))

    # C3 契约覆盖
    missing_fields, placeholder_fields = [], []
    if contract_fields:
        for f in contract_fields:
            if f not in result:
                missing_fields.append(f)
            elif is_placeholder_value(result[f]):
                placeholder_fields.append(f)
        add("C3", "output_contract 全部字段存在且非占位",
            not missing_fields and not placeholder_fields,
            "missing=%s placeholder=%s" % (missing_fields, placeholder_fields))
    else:
        add("C3", "output_contract 全部字段存在且非占位", True,
            "未提供 --case 或 case.json 无 output_contract，跳过覆盖检查")

    # C4 占位残留递归扫描（范围：契约字段；无契约时扫全文档）
    scan_roots = {f: result.get(f) for f in contract_fields} if contract_fields else result
    residue = []
    for root_name, root_val in (scan_roots.items() if isinstance(scan_roots, dict) else []):
        for p, v in walk(root_val, path="$." + root_name):
            if isinstance(v, dict) and v.get("_placeholder") is True:
                residue.append(p)
            elif isinstance(v, str) and any(tok in v for tok in PLACEHOLDER_TOKENS):
                residue.append("%s=%r" % (p, v[:40]))
    add("C4", "无占位残留", not residue, "residue=%s" % residue[:10])

    # C5 推荐参数证据
    recs = find_param_recommendations(result)
    no_ev = [p for p, d in recs if not has_evidence_or_unconfirmed(d)]
    add("C5", "每条推荐参数值带可行性证据引用或标注待确认", not no_ev,
        "recommendations=%d lacking_evidence=%s" % (len(recs), no_ev[:10]))

    # C6 假设 -> confirmation_items
    assumptions = find_assumptions(result)
    ci = result.get("confirmation_items")
    ci_ok = (not assumptions) or (isinstance(ci, list) and len(ci) > 0)
    add("C6", "存在假设时 confirmation_items 非空", ci_ok,
        "assumptions=%d confirmation_items=%s"
        % (len(assumptions), len(ci) if isinstance(ci, list) else "缺失/非列表"))

    # C7 status 合法性（与违例的一致性在下方 verdict 处理）
    status = result.get("status")
    add("C7", "status 取值合法", status in ALLOWED_STATUS, "status=%r" % (status,))

    # C8 元字段
    bad_meta = [k for k in ("sources", "uncertainty", "change_log")
                if not isinstance(result.get(k), list)]
    add("C8", "sources/uncertainty/change_log 存在且为列表", not bad_meta,
        "bad=%s" % bad_meta)

    violations = [c for c in checks if not c["passed"]]
    return checks, violations, status


def main():
    ap = argparse.ArgumentParser(description="risk-warden 交付前最终审计")
    ap.add_argument("--result", default="/app/output/result.json", help="待审计 result.json")
    ap.add_argument("--case", default=None, help="case.json（动态读取 output_contract 与 case_id）")
    ap.add_argument("--out", default=None, help="audit_report.json 输出路径（默认与 result.json 同目录）")
    args = ap.parse_args()

    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.result)),
                                        "audit_report.json")
    expected_case_id, contract_fields = None, []
    if args.case:
        case, cerr = load_json(args.case)
        if isinstance(case, dict):
            cid = case.get("case_id")
            expected_case_id = cid if isinstance(cid, str) and cid.strip() else None
            contract_fields = extract_contract_fields(case)
        else:
            sys.stderr.write("[final_audit] case.json 不可读（继续审计，跳过契约比对）: %s\n" % cerr)

    result, rerr = load_json(args.result)
    if not isinstance(result, dict):
        report = {
            "generated_at": utc_now(),
            "result_path": args.result,
            "checks": [{"check_id": "C1", "name": "result.json 存在且可解析",
                        "passed": False, "details": rerr or "顶层不是对象"}],
            "verdict": "fail",
            "forced_partial": False,
            "note": "result.json 不可读，禁止交付",
        }
        safe_write_json(out_path, report)
        sys.stderr.write("[final_audit] result.json 不可读: %s\n" % (rerr or "顶层不是 JSON 对象"))
        return EXIT_FAIL

    checks, violations, status = run_audit(result, args.result, contract_fields,
                                           expected_case_id)
    checks.insert(0, {"check_id": "C1", "name": "result.json 存在且可解析",
                      "passed": True, "details": "ok"})

    forced_partial = False
    if violations:
        verdict = "fail"
        # 有未消解违例时：强制回退 partial 并写明 partial_reason（就地改写）
        if status not in ("partial", "unable_to_determine", "refused"):
            forced_partial = True
        reasons = ["%s(%s): %s" % (c["check_id"], c["name"], c["details"])
                   for c in violations]
        result["status"] = "partial"
        result["partial_reason"] = "final_audit 检出未消解违例，强制回退 partial：" + "；".join(reasons)
        cl = result.get("change_log")
        if not isinstance(cl, list):
            cl = []
            result["change_log"] = cl
        cl.append({"ts": utc_now(), "event": "final_audit_forced_partial",
                   "detail": result["partial_reason"]})
        safe_write_json(args.result, result)
    else:
        verdict = "pass"

    report = {
        "generated_at": utc_now(),
        "result_path": args.result,
        "case_id": result.get("case_id"),
        "checks": checks,
        "verdict": verdict,
        "forced_partial": forced_partial,
        "note": ("审计通过，可交付" if verdict == "pass"
                 else "审计失败：已强制回退 partial，修复违例后重新审计"),
    }
    safe_write_json(out_path, report)
    sys.stdout.write("[final_audit] verdict=%s violations=%d forced_partial=%s\n"
                     % (verdict, len(violations), forced_partial))
    return EXIT_OK if verdict == "pass" else EXIT_FAIL


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 —— 兜底：任何输入不得 traceback
        sys.stderr.write("[final_audit] 未预期异常（已捕获，不崩溃）: %s\n" % exc)
        safe_write_json(os.path.abspath("audit_report.json"), {
            "generated_at": utc_now(),
            "checks": [{"check_id": "C0", "name": "审计器自身异常",
                        "passed": False, "details": str(exc)}],
            "verdict": "fail", "forced_partial": False,
            "note": "审计器异常时一律视为失败，禁止交付",
        })
        sys.exit(EXIT_FAIL)
