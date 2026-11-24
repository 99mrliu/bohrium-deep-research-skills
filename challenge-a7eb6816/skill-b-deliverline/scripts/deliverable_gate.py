#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deliverable_gate.py — 交付前机械验收门（不过门不交付）。

对照 contract_map.json 机械校验最终 result.json：
  1. case_id 与 case.json 一致；
  2. 契约字段全覆盖（支持点分嵌套路径）；
  3. 类型正确——boolean 不可当 integer（JSON 的 1 不是 true）；
  4. 必填字符串非空（去空白后），必填数组非空（limitations 除外，其空/非空
     由 status 一致性规则管辖）；
  5. enum 约束（若契约给出）；
  6. 产物引用类字段（deliverables / files / paths / artifacts / outputs）
     中的相对路径在 --base-dir 下真实存在；
  7. status 与 limitations 一致：status=complete 时 limitations 必须为空；
     status=partial 而 limitations 为空时记警告（诚实 partial 应说明缺口）。

产出 gate_report.json 与 gate_report.md，列出全部失败项（不在第一个
失败处停下）。

退出码
------
  0  PASS
  5  FAIL（gate_report 中列出全部失败项）
  2  输入文件缺失
  3  contract_map.json 非法
  4  result.json 非法 JSON 或不是对象
  6  报告写出失败

依赖：Python 3 标准库。输出确定性（不含时间戳）。
"""
import argparse
import json
import os
import sys

PATH_FIELD_HINTS = ("deliverable", "artifact", "file", "path", "output")


def get_path(obj, path):
    """按点分路径取值。返回 (found, value)。"""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def type_ok(value, t):
    """严格类型检查：bool 不是 integer/number。"""
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return True  # any / 未知类型不检查


def is_path_field(path):
    low = path.lower()
    return any(h in low for h in PATH_FIELD_HINTS)


def main(argv=None):
    ap = argparse.ArgumentParser(description="交付前机械验收门")
    ap.add_argument("--case", required=True, help="case.json 路径（只读）")
    ap.add_argument("--contract-map", required=True, help="contract_map.json 路径")
    ap.add_argument("--result", required=True, help="待验收的 result.json 路径")
    ap.add_argument("--base-dir", default=None,
                    help="产物相对路径的解析基准（默认: result.json 所在目录）")
    ap.add_argument("--outdir", default=None,
                    help="报告输出目录（默认: result.json 所在目录）")
    ap.add_argument("--report-json", default=None, help="JSON 报告完整路径（覆盖 --outdir）")
    ap.add_argument("--report-md", default=None, help="Markdown 报告完整路径（覆盖 --outdir）")
    args = ap.parse_args(argv)

    # --- 读输入 ---
    for p, label in ((args.case, "case.json"),
                     (args.contract_map, "contract_map.json"),
                     (args.result, "result.json")):
        if not os.path.isfile(p):
            print("ERROR: 输入缺失: %s (%s)" % (p, label), file=sys.stderr)
            return 2
    try:
        with open(args.case, "r", encoding="utf-8") as fh:
            case = json.load(fh)
    except ValueError as e:
        print("ERROR: case.json 非法: %s" % e, file=sys.stderr)
        return 2
    try:
        with open(args.contract_map, "r", encoding="utf-8") as fh:
            cmap = json.load(fh)
    except ValueError as e:
        print("ERROR: contract_map.json 非法: %s" % e, file=sys.stderr)
        return 3
    if not isinstance(cmap, dict) or not isinstance(cmap.get("fields"), list):
        print("ERROR: contract_map.json 缺少 fields 列表", file=sys.stderr)
        return 3
    try:
        with open(args.result, "r", encoding="utf-8") as fh:
            result = json.load(fh)
    except ValueError as e:
        print("ERROR: result.json 非法 JSON: %s" % e, file=sys.stderr)
        return 4
    if not isinstance(result, dict):
        print("ERROR: result.json 顶层不是对象", file=sys.stderr)
        return 4

    base_dir = args.base_dir or os.path.dirname(os.path.abspath(args.result))
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.result))
    report_json = args.report_json or os.path.join(outdir, "gate_report.json")
    report_md = args.report_md or os.path.join(outdir, "gate_report.md")

    checks = []   # {name, status: pass/fail, detail}
    warnings = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "status": "pass" if ok else "fail",
                       "detail": detail})
        return ok

    # --- 1. case_id 一致 ---
    case_id = case.get("case_id")
    if case_id is None:
        warnings.append("case.json 无 case_id 字段，跳过一致性检查")
    else:
        check("case_id_match", result.get("case_id") == case_id,
              "case.json case_id=%r, result case_id=%r"
              % (case_id, result.get("case_id")))

    # --- 2/3/4/5. 字段覆盖、类型、必填非空、枚举 ---
    for f in cmap["fields"]:
        path = f.get("path", "")
        t = f.get("type", "any")
        required = bool(f.get("required"))
        found, value = get_path(result, path)
        if not found:
            check("field_present:%s" % path, False,
                  "字段缺失（契约要求%s，类型 %s）"
                  % ("必填" if required else "可选", t))
            continue
        check("field_present:%s" % path, True)
        check("field_type:%s" % path, type_ok(value, t),
              "期望类型 %s，实际 %s（值 %r；注意 boolean 不可当 integer）"
              % (t, type(value).__name__, value)[:300])
        if required:
            if t == "string":
                check("required_nonempty:%s" % path,
                      isinstance(value, str) and bool(value.strip()),
                      "必填字符串去空白后为空")
            elif t == "array" and path.split(".")[-1] != "limitations":
                check("required_nonempty:%s" % path,
                      isinstance(value, list) and len(value) > 0,
                      "必填数组为空")
        if isinstance(f.get("enum"), list):
            check("field_enum:%s" % path, value in f["enum"],
                  "值 %r 不在枚举 %r 内" % (value, f["enum"]))

    # --- 6. 产物路径真实存在 ---
    for f in cmap["fields"]:
        path = f.get("path", "")
        if not is_path_field(path):
            continue
        found, value = get_path(result, path)
        if not found:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, str) or not item.strip():
                continue
            p = item if os.path.isabs(item) else os.path.join(base_dir, item)
            check("artifact_exists:%s=%s" % (path, item), os.path.exists(p),
                  "解析路径 %s 不存在（base_dir=%s）" % (p, base_dir))

    # --- 7. status 与 limitations 一致 ---
    has_status, status = get_path(result, "status")
    if has_status:
        check("status_value", status in ("complete", "partial"),
              "status=%r，应为 complete 或 partial" % (status,))
        has_lim, lim = get_path(result, "limitations")
        if status == "complete":
            if has_lim:
                check("status_limitations_consistency",
                      isinstance(lim, list) and len(lim) == 0,
                      "status=complete 时 limitations 必须为空数组，实际 %r" % (lim,))
            else:
                check("status_limitations_consistency", True,
                      "无 limitations 字段，视为空")
        elif status == "partial":
            if has_lim and isinstance(lim, list) and len(lim) == 0:
                warnings.append("status=partial 但 limitations 为空：诚实 partial 应列出缺口")
    else:
        warnings.append("result.json 无 status 字段")

    failures = [c for c in checks if c["status"] == "fail"]
    gate = "PASS" if not failures else "FAIL"
    exit_code = 0 if not failures else 5

    report = {
        "gate": gate,
        "exit_code": exit_code,
        "case_id": result.get("case_id"),
        "result_file": os.path.abspath(args.result),
        "base_dir": os.path.abspath(base_dir),
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failures),
        "checks_failed": len(failures),
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
    }

    md_lines = [
        "# 交付验收门报告",
        "",
        "- 结论：**%s**（退出码 %d）" % (gate, exit_code),
        "- case_id：%s" % (result.get("case_id"),),
        "- 检查总数：%d；通过 %d；失败 %d" % (len(checks), len(checks) - len(failures), len(failures)),
        "",
        "## 失败项",
        "",
    ]
    if failures:
        for c in failures:
            md_lines.append("- ❌ `%s` — %s" % (c["name"], c["detail"]))
    else:
        md_lines.append("（无）")
    md_lines += ["", "## 警告", ""]
    if warnings:
        for w in warnings:
            md_lines.append("- ⚠️ %s" % w)
    else:
        md_lines.append("（无）")
    md_lines += ["", "## 全部检查", ""]
    for c in checks:
        mark = "✅" if c["status"] == "pass" else "❌"
        detail = (" — " + c["detail"]) if c["detail"] else ""
        md_lines.append("- %s `%s`%s" % (mark, c["name"], detail))
    md_lines.append("")

    try:
        os.makedirs(os.path.dirname(os.path.abspath(report_json)), exist_ok=True)
        with open(report_json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        with open(report_md, "w", encoding="utf-8") as fh:
            fh.write("\n".join(md_lines))
    except OSError as e:
        print("ERROR: 报告写出失败: %s" % e, file=sys.stderr)
        return 6

    print("gate=%s exit=%d 检查 %d 项，失败 %d 项" % (gate, exit_code, len(checks), len(failures)))
    for c in failures:
        print("FAIL: %s — %s" % (c["name"], c["detail"]), file=sys.stderr)
    print("报告: %s / %s" % (report_json, report_md))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
