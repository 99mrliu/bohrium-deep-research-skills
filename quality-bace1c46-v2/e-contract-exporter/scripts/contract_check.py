#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_check.py — result.json 交付契约检查器（纯 Python3 标准库，离线）。

检查项：
  1. result 是合法 JSON 对象；
  2. case_id 存在（提供 --case 时须与案例中的 case_id 一致）；
  3. 在 case.json 中防御式递归发现 output_contract / contract / output_fields /
     required_fields，结果中必须镜像其声明的每一个字段（缺失/多余均列出）；
     支持“字段名列表”与“对象”两种形态；
  4. status ∈ {success, partial, failed}；
  5. status == partial ⇒ uncertainties 非空 且 partial_limits 存在且非空
     （诚实部分交付语义）；
  6. 占位符扫描：字符串值中禁止出现 TODO/TBD/FIXME/lorem/xxx 类占位符；
  7. evidence 若存在且为列表，每行必须带非空 source 或 locator 字段。

退出码：0 = 通过；1 = 发现违规（含 JSON 损坏）；2 = 用法错误。
报告：人类可读报告输出到 stdout；--report 给出路径时额外写 JSON 报告。
"""
import argparse
import json
import re
import sys

STATUS_ENUM = ("success", "partial", "failed")

# 防御式发现契约时识别的键名（按优先级）
CONTRACT_KEYS = ("output_contract", "contract", "output_fields", "required_fields")

# 占位符模式（大小写不敏感）
PLACEHOLDER_PATTERNS = [
    (re.compile(r"\bTODO\b", re.IGNORECASE), "TODO"),
    (re.compile(r"\bTBD\b", re.IGNORECASE), "TBD"),
    (re.compile(r"\bFIXME\b", re.IGNORECASE), "FIXME"),
    (re.compile(r"lorem", re.IGNORECASE), "lorem"),
    (re.compile(r"\bx{3,}\b", re.IGNORECASE), "xxx-placeholder"),
]


def load_json(path):
    """返回 (obj, error)。出错时 error 为人类可读字符串。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "文件不存在: %s" % path
    except json.JSONDecodeError as e:
        return None, "JSON 解析失败: %s (第 %d 行第 %d 列: %s)" % (
            path, e.lineno, e.colno, e.msg)
    except OSError as e:
        return None, "读取失败: %s (%s)" % (path, e)


def find_contract(obj, path="$"):
    """防御式递归搜索契约声明。返回 (fields, found_path) 或 (None, None)。

    支持两种形态：
      - 列表：["field_a", "field_b", ...]（元素取字符串）
      - 对象：{"fields": [...]} 或 {"field_a": {...}, ...}（取键名）
    """
    if isinstance(obj, dict):
        for key in CONTRACT_KEYS:
            if key in obj:
                node = obj[key]
                fields = contract_fields(node)
                if fields is not None:
                    return fields, "%s.%s" % (path, key)
        for key, val in obj.items():
            fields, found = find_contract(val, "%s.%s" % (path, key))
            if fields is not None:
                return fields, found
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            fields, found = find_contract(val, "%s[%d]" % (path, i))
            if fields is not None:
                return fields, found
    return None, None


def contract_fields(node):
    """把契约节点规整为字段名列表；无法识别返回 None。"""
    if isinstance(node, list):
        fields = [x for x in node if isinstance(x, str)]
        return fields if fields else None
    if isinstance(node, dict):
        inner = node.get("fields")
        if isinstance(inner, list):
            fields = [x for x in inner if isinstance(x, str)]
            if fields:
                return fields
        keys = [k for k in node.keys() if isinstance(k, str) and k != "fields"]
        return keys if keys else None
    return None


def find_case_id(obj):
    """在 case.json 中找 case_id（先顶层，再浅层递归）。"""
    if isinstance(obj, dict):
        if isinstance(obj.get("case_id"), str):
            return obj["case_id"]
        for val in obj.values():
            if isinstance(val, dict) and isinstance(val.get("case_id"), str):
                return val["case_id"]
    return None


def scan_placeholders(obj, path="$"):
    """递归扫描字符串值中的占位符。返回 [(path, pattern_name, snippet), ...]。"""
    hits = []
    if isinstance(obj, str):
        for rx, name in PLACEHOLDER_PATTERNS:
            m = rx.search(obj)
            if m:
                snippet = obj[:80] + ("..." if len(obj) > 80 else "")
                hits.append((path, name, snippet))
                break  # 同一字符串只报一次
    elif isinstance(obj, dict):
        for key, val in obj.items():
            # change_records 是审计历史：old_value/rationale 合法引用旧占位符，不扫描
            if path == "$" and key == "change_records":
                continue
            hits.extend(scan_placeholders(val, "%s.%s" % (path, key)))
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            hits.extend(scan_placeholders(val, "%s[%d]" % (path, i)))
    return hits


def check(result, case, case_path):
    """返回违规列表（字符串）。空列表 = 通过。"""
    violations = []

    if not isinstance(result, dict):
        return ["result.json 顶层必须是 JSON 对象"]

    # --- case_id ---
    rid = result.get("case_id")
    if not isinstance(rid, str) or not rid.strip():
        violations.append("缺少必填顶层字段 case_id（非空字符串）")
    if case is not None:
        cid = find_case_id(case)
        if cid is None:
            violations.append(
                "案例文件 %s 中未找到 case_id，无法执行一致性比对" % case_path)
        elif isinstance(rid, str) and rid != cid:
            violations.append(
                "case_id 不一致: result=%r 而 case=%r" % (rid, cid))

    # --- output_contract 镜像 ---
    if case is not None:
        fields, found = find_contract(case)
        if fields is None:
            violations.append(
                "在案例文件中未能防御式发现 output_contract/contract/"
                "output_fields/required_fields 声明")
        else:
            missing = [f for f in fields if f not in result]
            extra = []
            if missing:
                violations.append(
                    "契约(%s)声明的字段在 result.json 中缺失: %s"
                    % (found, ", ".join(missing)))
            # 多余字段仅提示（契约声明之外、保留字段之外的顶层键）
            reserved = {"case_id", "status", "uncertainties", "change_records",
                        "partial_limits", "evidence", "meta"}
            extra = [k for k in result.keys()
                     if k not in fields and k not in reserved]
            if extra:
                violations.append(
                    "result.json 含契约(%s)未声明的顶层字段（建议移除或在契约中登记）: %s"
                    % (found, ", ".join(extra)))
    else:
        # 无 --case 时仅能检查保留字段存在性
        for key in ("uncertainties", "change_records"):
            if key not in result:
                violations.append("缺少保留顶层字段 %s（未提供 --case，按最小契约检查）" % key)

    # --- status 枚举 ---
    status = result.get("status")
    if status not in STATUS_ENUM:
        violations.append(
            "status 必须是 %s 之一，当前为 %r" % ("/".join(STATUS_ENUM), status))

    # --- 诚实部分交付语义 ---
    if status == "partial":
        unc = result.get("uncertainties")
        if not isinstance(unc, list) or len(unc) == 0:
            violations.append(
                "status=partial 要求 uncertainties 为非空列表（说明哪里不确定）")
        pl = result.get("partial_limits")
        if pl is None or pl == "" or pl == [] or pl == {}:
            violations.append(
                "status=partial 要求 partial_limits 存在且非空（说明覆盖范围的边界）")

    # --- 占位符扫描 ---
    for path, name, snippet in scan_placeholders(result):
        violations.append(
            "发现占位符 %s @ %s: %r" % (name, path, snippet))

    # --- evidence 行定位信息 ---
    ev = result.get("evidence")
    if ev is not None:
        if not isinstance(ev, list):
            violations.append("evidence 字段若存在必须是列表")
        else:
            for i, row in enumerate(ev):
                if not isinstance(row, dict):
                    violations.append("evidence[%d] 不是对象" % i)
                    continue
                src = row.get("source")
                loc = row.get("locator")
                src_ok = isinstance(src, str) and src.strip()
                loc_ok = isinstance(loc, str) and loc.strip()
                if not (src_ok or loc_ok):
                    violations.append(
                        "evidence[%d] 缺少非空 source 或 locator 定位字段" % i)

    return violations


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="result.json 交付契约检查器（离线，纯标准库）")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--case", default=None,
                    help="可选：case.json 路径（启用 case_id 一致性与契约镜像检查）")
    ap.add_argument("--report", default=None,
                    help="可选：JSON 格式检查报告输出路径")
    args = ap.parse_args(argv)

    result, err = load_json(args.result)
    if err:
        print("[FAIL] %s" % err)
        if args.report:
            _write_report(args.report, args, None, [err])
        return 1

    case = None
    if args.case:
        case, err = load_json(args.case)
        if err:
            print("[FAIL] 案例文件读取失败: %s" % err)
            if args.report:
                _write_report(args.report, args, None, [err])
            return 1

    violations = check(result, case, args.case)

    if args.report:
        _write_report(args.report, args, result, violations)

    if violations:
        print("[FAIL] 契约检查未通过，共 %d 项违规：" % len(violations))
        for i, v in enumerate(violations, 1):
            print("  %2d. %s" % (i, v))
        print("")
        print("修复提示：先补齐缺失字段与占位符，再确认 partial 语义"
              "（uncertainties 非空 + partial_limits 非空）。")
        return 1

    print("[PASS] 契约检查通过: %s" % args.result)
    if args.case:
        print("  case_id 一致性 ✓；output_contract 字段镜像 ✓")
    print("  status=%r；占位符扫描 ✓；evidence 定位 ✓"
          % result.get("status"))
    return 0


def _write_report(path, args, result, violations):
    report = {
        "result_path": args.result,
        "case_path": args.case,
        "case_id": (result or {}).get("case_id") if isinstance(result, dict) else None,
        "status": (result or {}).get("status") if isinstance(result, dict) else None,
        "passed": not violations,
        "violation_count": len(violations),
        "violations": violations,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("[WARN] JSON 报告写入失败: %s (%s)" % (path, e), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
