#!/usr/bin/env python3
"""make_result.py — 汇总契约感知 result.json(math-symbol-fidelity-lab 第 4 步)

读取 case.json(含 case_id 与 output_contract 字段名列表)与前三步产物,
按 output_contract 逐字段填充:
  - 已知字段名 → 从对应产物抽取;
  - 未知字段名 → 置 null, 在 uncertainty 说明, status 降为 partial(绝不伪造)。
result.json 固定含: case_id, status, sources, uncertainty, change_record,
以及 output_contract 声明的全部字段。

已知字段名映射:
  equations        → equations.json 的方程列表(含 verbatim/linear/number/anchor)
  unmapped_symbols → fidelity_report.json 的 unmapped 台账
  fidelity_summary → fidelity_report.json 的计数与状态
  math_zones       → math_zones.json 的公式区列表
  engine_info      → extract_report.json 的引擎与降级信息

用法:
  python3 make_result.py --case case.json --glyphs glyphs.jsonl \
      --zones math_zones.json --equations equations.json \
      --fidelity fidelity_report.json [--extract-report extract_report.json] \
      --out result.json

退出码: 0=success, 2=partial, 3=failed。仅标准库。
"""

import argparse
import json
import sys
import time


def load_json(path, what, errors, required=True):
    if not path:
        if required:
            errors.append(f"缺少输入: {what}")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        errors.append(f"读取 {what}({path})失败: {e}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="汇总契约感知 result.json")
    ap.add_argument("--case", required=True, help="case.json(含 case_id 与 output_contract)")
    ap.add_argument("--glyphs", default=None)
    ap.add_argument("--zones", default=None)
    ap.add_argument("--equations", default=None)
    ap.add_argument("--fidelity", default=None)
    ap.add_argument("--extract-report", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    errors, uncertainty = [], []
    case = load_json(args.case, "case.json", errors)
    if case is None:
        print("ERROR: case.json 不可读", file=sys.stderr)
        return 3
    zones = load_json(args.zones, "math_zones.json", errors)
    equations = load_json(args.equations, "equations.json", errors)
    fidelity = load_json(args.fidelity, "fidelity_report.json", errors)
    extract = load_json(args.extract_report, "extract_report.json", errors, required=False)
    glyphs_path = args.glyphs

    case_id = case.get("case_id", "unknown")
    contract = case.get("output_contract") or []
    if isinstance(contract, dict):  # 兼容 {字段名: 说明} 形式
        contract = list(contract.keys())

    sources = []
    inputs = case.get("inputs") or {}
    if isinstance(inputs, dict):
        for k, v in inputs.items():
            sources.append(str(v))
    elif isinstance(inputs, list):
        sources.extend(str(v) for v in inputs)
    if args.case not in sources:
        sources.append(args.case)

    fillers = {
        "equations": lambda: (equations or {}).get("equations"),
        "unmapped_symbols": lambda: (fidelity or {}).get("unmapped_symbols"),
        "fidelity_summary": lambda: (
            {k: fidelity.get(k) for k in ("counts", "replacement_detail",
                                          "baseline_anomalies", "status", "thresholds")}
            if fidelity else None),
        "math_zones": lambda: (zones or {}).get("zones"),
        "engine_info": lambda: (
            {k: extract.get(k) for k in ("engine", "degrade_reason", "page_modes",
                                         "degraded_pages", "counts")}
            if extract else None),
    }

    result = {"case_id": case_id}
    missing_fields = []
    for field in contract:
        if field in fillers:
            value = fillers[field]()
            if value is None:
                missing_fields.append(field)
                uncertainty.append(f"契约字段 '{field}': 对应产物缺失或为空, 置 null")
            result[field] = value
        else:
            missing_fields.append(field)
            uncertainty.append(f"契约字段 '{field}': 本 Skill 不产出该字段, 置 null")
            result[field] = None

    if errors:
        uncertainty.extend(errors)

    # 状态判定
    fidelity_status = (fidelity or {}).get("status")
    if equations is None or fidelity is None or zones is None:
        status = "failed"
    elif missing_fields or fidelity_status == "partial" or (extract or {}).get("degraded_pages"):
        status = "partial"
    else:
        status = "success"

    if fidelity_status == "partial":
        reasons = []
        c = (fidelity or {}).get("counts", {})
        if c.get("unmapped"):
            reasons.append(f"未映射符号 {c['unmapped']} 个(见 unmapped_symbols 台账)")
        if c.get("baseline_anomalies"):
            reasons.append(f"基线异常告警 {c['baseline_anomalies']} 条")
        if c.get("partial_zones"):
            reasons.append(f"partial 公式区 {c['partial_zones']} 个")
        uncertainty.append("保真度状态 partial: " + ("; ".join(reasons) or "见 fidelity_summary"))
    if (extract or {}).get("degraded_pages"):
        uncertainty.append(
            f"抽取降级: 页 {(extract or {}).get('degraded_pages')} 为 word 级, "
            f"原因: {(extract or {}).get('degrade_reason')}")

    result["status"] = status
    result["sources"] = sources
    result["uncertainty"] = uncertainty
    result["change_record"] = [
        {"step": "extract_glyphs", "artifact": glyphs_path,
         "engine": (extract or {}).get("engine")},
        {"step": "detect_math_zones", "artifact": args.zones,
         "zones": (zones or {}).get("counts", {}).get("zones")},
        {"step": "linearize_math", "artifact": args.equations,
         "equations": (fidelity or {}).get("counts", {}).get("equations"),
         "fidelity_status": fidelity_status},
        {"step": "make_result", "artifact": args.out,
         "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
    ]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"case_id": case_id, "status": status,
                      "missing_fields": missing_fields}, ensure_ascii=False))
    return {"success": 0, "partial": 2}.get(status, 3)


if __name__ == "__main__":
    sys.exit(main())
