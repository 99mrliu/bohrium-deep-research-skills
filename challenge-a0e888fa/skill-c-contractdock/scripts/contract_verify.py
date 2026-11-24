#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_verify.py — 交付前合同验收（标准库）。

三道机械验收，任一不过即非零退出，**不过不交付**：
  1. 字段覆盖：result.json 含 contract.json 声明的每个字段路径，且必填字段
     非 null/占位空值；类型与合同一致（string/integer/number/boolean/array/
     object；合同为 any 时不限）。
  2. 产物存在：result.json 中以相对路径引用的文件（字符串值且以已知数据
     扩展名结尾）在输出目录内真实存在。
  3. 报告自洽（可选）：给定 --cleaned/--ledger/--raw 时，现场重算质量数字
     并与 --report 的 quality_report.json 比对，不一致即失败。

输出 verify_verdict.json（逐项 PASS/FAIL 与差距清单）。
退出码：0 全过；5 存在失败项；2 参数错误。
"""
import argparse
import csv
import json
import os
import sys

DATA_EXTS = (".csv", ".json", ".jsonl", ".md", ".svg", ".txt", ".tsv", ".html")
TYPEOF = {"string": str, "integer": int, "number": (int, float),
          "boolean": bool, "array": list, "object": dict}


def get_path(obj, path):
    node = obj
    for p in path.split("."):
        if not isinstance(node, dict) or p not in node:
            return None, False
        node = node[p]
    return node, True


def walk_strings(obj, prefix=""):
    out = []
    if isinstance(obj, str):
        out.append((prefix, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out += walk_strings(v, "%s.%s" % (prefix, k) if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += walk_strings(v, "%s[%d]" % (prefix, i))
    return out


def recompute(cleaned, ledger, raw):
    with open(cleaned, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    data = rows[1:] if rows else []
    rc = {"rows_out": len(data), "actions": {}}
    if raw:
        with open(raw, encoding="utf-8-sig", newline="") as f:
            rc["rows_in"] = max(0, len(list(csv.reader(f))) - 1)
    if ledger and os.path.isfile(ledger):
        with open(ledger, encoding="utf-8-sig", newline="") as f:
            lrows = list(csv.reader(f))
        rc["ledger_entries"] = max(0, len(lrows) - 1)
        if lrows and "action" in lrows[0]:
            ai = lrows[0].index("action")
            for r in lrows[1:]:
                if ai < len(r):
                    rc["actions"][r[ai]] = rc["actions"].get(r[ai], 0) + 1
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contract", required=True, help="contract_extract 的 contract.json")
    ap.add_argument("--result", required=True, help="待验收的 result.json")
    ap.add_argument("--output-dir", required=True, help="交付目录（产物存在性核查根）")
    ap.add_argument("--report", default=None, help="quality_report.json（可选自洽核查）")
    ap.add_argument("--cleaned", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--raw", default=None)
    ap.add_argument("--out", required=True, help="verdict 输出目录")
    args = ap.parse_args()

    contract = json.load(open(args.contract, encoding="utf-8"))
    try:
        result = json.load(open(args.result, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: result.json 不可读: %s" % e, file=sys.stderr)
        sys.exit(2)
    checks = []

    def record(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    # 0) case_id 一致
    rid = result.get("case_id")
    record("case_id_present", rid == contract.get("case_id"),
           {"expected": contract.get("case_id"), "actual": rid})

    # 1) 字段覆盖与类型
    missing, wrong_type, empty_required = [], [], []
    for f in contract.get("fields", []):
        val, ok = get_path(result, f["path"])
        if not ok:
            missing.append(f["path"])
            continue
        t = f.get("type", "any")
        if t in TYPEOF and val is not None:
            texp = TYPEOF[t]
            if t == "integer" and isinstance(val, bool):
                wrong_type.append(f["path"])
            elif t == "number" and isinstance(val, bool):
                wrong_type.append(f["path"])
            elif not isinstance(val, texp):
                wrong_type.append("%s(期望%s)" % (f["path"], t))
        if f.get("required", True) and (val is None or val == ""):
            empty_required.append(f["path"])
    record("contract_fields_present", not missing, {"missing": missing})
    record("contract_field_types", not wrong_type, {"wrong_type": wrong_type})
    record("required_fields_filled", not empty_required,
           {"empty_required": empty_required})

    # 2) 引用产物存在
    missing_files = []
    for path, s in walk_strings(result):
        if s.lower().endswith(DATA_EXTS) and not os.path.isabs(s) \
                and not s.startswith(("http://", "https://")):
            if not os.path.isfile(os.path.join(args.output_dir, s)):
                missing_files.append(s)
    record("referenced_artifacts_exist", not missing_files,
           {"missing_files": missing_files})

    # 3) 报告自洽 + result.json 摘要数字一致
    if args.report and args.cleaned:
        try:
            rep = json.load(open(args.report, encoding="utf-8"))
            rc = recompute(args.cleaned, args.ledger, args.raw)
            diffs = {}
            if rep.get("table", {}).get("rows_out") != rc["rows_out"]:
                diffs["rows_out"] = {"report": rep.get("table", {}).get("rows_out"),
                                     "recomputed": rc["rows_out"]}
            if "rows_in" in rc and rep.get("table", {}).get("rows_in") != rc["rows_in"]:
                diffs["rows_in"] = {"report": rep.get("table", {}).get("rows_in"),
                                    "recomputed": rc["rows_in"]}
            if "ledger_entries" in rc and \
               rep.get("ledger_entries") != rc["ledger_entries"]:
                diffs["ledger_entries"] = {"report": rep.get("ledger_entries"),
                                           "recomputed": rc["ledger_entries"]}
            record("report_self_consistent", not diffs, {"diffs": diffs})
            # 3b) result.json 的 summary 数字与重算/台账一致
            summ = result.get("summary") if isinstance(result.get("summary"), dict) else {}
            sdiff = {}
            for key, rckey in (("rows_out", "rows_out"), ("rows_in", "rows_in")):
                if key in summ and rckey in rc and summ[key] != rc[rckey]:
                    sdiff[key] = {"result": summ[key], "recomputed": rc[rckey]}
            for key, act in (("missing_marked", "missing_marked"),
                             ("units_converted", "unit_converted")):
                if key in summ and act in rc["actions"] \
                        and summ[key] != rc["actions"][act]:
                    sdiff[key] = {"result": summ[key],
                                  "ledger_action_count": rc["actions"][act]}
            record("result_numbers_consistent", not sdiff, {"diffs": sdiff})
        except (OSError, json.JSONDecodeError) as e:
            record("report_self_consistent", False, {"error": str(e)})

    all_pass = all(c["pass"] for c in checks)
    verdict = {"all_pass": all_pass, "checks": checks}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "verify_verdict.json"), "w",
              encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=2)
    print(json.dumps({"verdict": "PASS" if all_pass else "FAIL",
                      "checks": {c["check"]: c["pass"] for c in checks}},
                     ensure_ascii=False))
    sys.exit(0 if all_pass else 5)


if __name__ == "__main__":
    main()
