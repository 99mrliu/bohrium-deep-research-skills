#!/usr/bin/env python3
"""selfcheck_gate.py — 交付门禁。

检查项（任一不过即 verdict=BLOCK，全部通过才 DELIVER）：
  1. result_json_valid     result.json 存在且为合法 JSON 对象
  2. case_id_match         result.case_id 与 contract/case.json 一致
  3. required_fields_filled 必填契约字段齐全率 100%（附 null 字段清单）
  4. provenance_coverage   每个已填充字段都有 field_provenance 条目
  5. preview_artifacts     preview.svg / preview.png 存在，且 sha256 与
                           preview_record.json 记录一致（现场重算）
  6. svg_wellformed        preview.svg 可被 xml.etree 解析
  7. status_consistency    status=成功 时不允许存在 null 必填字段；status
                           取值须在 {成功, 部分完成, 无法判断, 拒答}

BLOCK 时不删除、不覆盖 result.json —— 诚实保留部分结果（partial）。
仅使用标准库（python3 >= 3.8）。exit 0=DELIVER，2=BLOCK，绝不崩溃。
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

VALID_STATUS = {"成功", "部分完成", "无法判断", "拒答"}


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_json_safe(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="交付门禁：契约 + 渲染双重自检")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--contract", default="/app/work/contract.json")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--record", default="/app/output/preview_record.json")
    ap.add_argument("--out", default="/app/output/gate_report.json")
    args = ap.parse_args(argv)

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    # 1. result.json 合法
    result = load_json_safe(args.result)
    if not isinstance(result, dict):
        add("result_json_valid", False,
            "result.json 缺失或不是合法 JSON 对象：%s" % args.result)
        result = {}
    else:
        add("result_json_valid", True, "result.json 为合法 JSON 对象")

    # 2. case_id 一致
    contract = load_json_safe(args.contract)
    contract = contract if isinstance(contract, dict) else {}
    case = load_json_safe(args.case)
    case = case if isinstance(case, dict) else {}
    cid_r = result.get("case_id")
    cid_c = contract.get("case_id") or case.get("case_id")
    add("case_id_match", bool(cid_r) and cid_r == cid_c,
        "result.case_id=%r vs contract/case.case_id=%r" % (cid_r, cid_c))

    # 3. 必填字段齐全率
    fields = contract.get("fields") or []
    req = [f for f in fields
           if isinstance(f, dict) and f.get("required", True)]
    null_fields = [f.get("name") for f in req
                   if result.get(f.get("name")) is None]
    rate = (len(req) - len(null_fields)) / len(req) if req else 1.0
    add("required_fields_filled", not null_fields,
        "必填字段齐全率 %.0f%%（%d/%d）；null 字段清单：%s"
        % (rate * 100, len(req) - len(null_fields), len(req),
           "、".join(str(n) for n in null_fields) if null_fields else "无"))

    # 4. provenance 覆盖
    prov = result.get("field_provenance")
    prov = prov if isinstance(prov, dict) else {}
    filled_names = [f.get("name") for f in fields
                    if isinstance(f, dict)
                    and result.get(f.get("name")) is not None]
    missing_prov = [n for n in filled_names
                    if n not in prov
                    or not isinstance(prov.get(n), dict)
                    or not prov[n].get("work_file")]
    cov = (len(filled_names) - len(missing_prov)) / len(filled_names) \
        if filled_names else 1.0
    add("provenance_coverage", not missing_prov,
        "provenance 覆盖率 %.0f%%；缺 provenance 的字段：%s"
        % (cov * 100,
           "、".join(str(n) for n in missing_prov) if missing_prov else "无"))

    # 5. 预览产物存在且 sha256 与 record 一致（现场重算）
    record = load_json_safe(args.record)
    record = record if isinstance(record, dict) else {}
    out_dir = os.path.dirname(os.path.abspath(args.record))
    svg_path = record.get("preview_svg") or os.path.join(out_dir, "preview.svg")
    png_path = record.get("preview_png") or os.path.join(out_dir, "preview.png")
    problems = []
    for key, path in (("svg_sha256", svg_path), ("png_sha256", png_path)):
        if not os.path.isfile(path):
            problems.append("缺失 %s" % path)
            continue
        actual = sha256_file(path)
        if record.get(key) and actual != record[key]:
            problems.append("%s sha256 与 record 不一致" % os.path.basename(path))
        elif not record.get(key):
            problems.append("record 缺 %s 记录" % key)
    add("preview_artifacts", not problems,
        "；".join(problems) if problems
        else "preview.svg / preview.png 存在且 sha256 与 record 一致")

    # 6. SVG well-formed
    svg_ok, svg_msg = False, "preview.svg 缺失"
    if os.path.isfile(svg_path):
        try:
            ET.parse(svg_path)
            svg_ok, svg_msg = True, "preview.svg well-formed"
        except ET.ParseError as e:
            svg_msg = "preview.svg XML 解析失败：%s" % e
    add("svg_wellformed", svg_ok, svg_msg)

    # 7. status 诚实一致
    status = result.get("status")
    if status not in VALID_STATUS:
        add("status_consistency", False,
            "status=%r 不在合法取值 %s" % (status, sorted(VALID_STATUS)))
    elif status == "成功" and null_fields:
        add("status_consistency", False,
            "status=成功 但存在 null 必填字段：%s" % "、".join(null_fields))
    else:
        add("status_consistency", True, "status=%s 与字段填充情况一致" % status)

    verdict = "DELIVER" if all(c["pass"] for c in checks) else "BLOCK"
    report = {
        "case_id": cid_r or cid_c or "UNKNOWN_CASE_ID",
        "checks": checks,
        "null_fields": [str(n) for n in null_fields],
        "required_field_rate": round(rate, 4),
        "verdict": verdict,
    }
    if verdict == "BLOCK":
        report["block_reasons"] = ["%s: %s" % (c["check"], c["detail"])
                                   for c in checks if not c["pass"]]
        report["note"] = ("BLOCK：result.json 按原样保留（诚实 partial），"
                          "修复后重跑 fill_result/render_preview/selfcheck_gate")
    atomic_write_json(args.out, report)
    print("selfcheck_gate: verdict=%s -> %s" % (verdict, args.out))
    for c in checks:
        print("  [%s] %s — %s" % ("PASS" if c["pass"] else "FAIL",
                                  c["check"], c["detail"]))
    return 0 if verdict == "DELIVER" else 2


if __name__ == "__main__":
    sys.exit(main())
