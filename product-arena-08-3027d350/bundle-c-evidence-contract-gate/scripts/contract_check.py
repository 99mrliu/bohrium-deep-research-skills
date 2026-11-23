#!/usr/bin/env python3
"""contract_check.py — 交付契约校验器（证据与契约核验技能 C 的组件 3）。

对照 /input/case.json 的 output_contract 逐项校验 /app/output/result.json：
    1. case_id 一致；
    2. output_contract 声明的字段全部出现（required 缺失 → FAIL；
       非 required 缺失 → WARN）；
    3. 字段值非空（null/""/[] 视为未填充 → 要求 uncertainty 中有对应说明）；
    4. status ∈ {success, partial, failed}，且 partial/failed 必须带
       uncertainty 或 handoff 说明；
    5. 主结果字段的证据定位（evidence/sources 至少其一非空）。
用法：
    python3 contract_check.py --case /input/case.json \
        --result /app/output/result.json --out /app/work
输出 contract_report.json；退出码 0=PASS；1=FAIL；3=输入不可用。
"""
import argparse
import json
import os
import sys

STATUS_ENUM = ("success", "partial", "failed")


def contract_fields(case):
    c = case.get("output_contract") or {}
    fields = c.get("fields", c) if isinstance(c, dict) else c
    out = []
    if isinstance(fields, dict):
        for k, v in fields.items():
            req = True
            if isinstance(v, dict):
                req = bool(v.get("required", True))
            out.append((k, req))
    elif isinstance(fields, list):
        for x in fields:
            if isinstance(x, dict):
                out.append((x.get("name"), bool(x.get("required", True))))
            else:
                out.append((str(x), True))
    return out


def is_empty(v):
    return v is None or v == "" or v == [] or v == {}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    for p, tag in ((args.case, "case"), (args.result, "result")):
        if not os.path.exists(p):
            print(json.dumps({"status": "failed",
                              "reason": f"{tag}_missing"}))
            return 3
    case = json.load(open(args.case, encoding="utf-8"))
    result = json.load(open(args.result, encoding="utf-8"))

    checks, fails, warns = [], [], []

    cid_case = case.get("case_id") or case.get("id")
    cid_res = result.get("case_id")
    ok = cid_case is not None and cid_case == cid_res
    checks.append({"check": "case_id_match", "ok": ok,
                   "case": cid_case, "result": cid_res})
    if not ok:
        fails.append("case_id 不一致或缺失")

    fields = contract_fields(case)
    res_payload = result.get("result", result)
    uncertainty_text = json.dumps(result.get("uncertainty", []),
                                  ensure_ascii=False)
    for name, required in fields:
        present = name in res_payload
        empty = is_empty(res_payload.get(name))
        explained = name in uncertainty_text
        if not present:
            ok, level = (False, "fail") if required else (True, "warn")
        elif empty and not explained:
            ok, level = False, "fail"
        elif empty and explained:
            ok, level = True, "ok-explained-empty"
        else:
            ok, level = True, "ok"
        checks.append({"check": f"field:{name}", "ok": ok, "level": level,
                       "required": required, "present": present,
                       "empty": empty})
        if level == "fail":
            fails.append(f"契约字段 {name} 缺失或未解释置空")
        elif level == "warn":
            warns.append(f"非必需字段 {name} 缺失")

    status = result.get("status")
    ok = status in STATUS_ENUM
    checks.append({"check": "status_enum", "ok": ok, "value": status})
    if not ok:
        fails.append(f"status {status!r} 不在 {STATUS_ENUM}")
    if status in ("partial", "failed"):
        ok = bool(result.get("uncertainty") or result.get("handoff"))
        checks.append({"check": "partial_explained", "ok": ok})
        if not ok:
            fails.append("partial/failed 缺少 uncertainty 或 handoff 说明")

    ev_ok = bool(result.get("evidence") or result.get("sources"))
    checks.append({"check": "evidence_present", "ok": ev_ok})
    if not ev_ok:
        fails.append("缺少 evidence/sources 定位信息")

    verdict = "PASS" if not fails else "FAIL"
    report = {"verdict": verdict, "fails": fails, "warns": warns,
              "checks": checks,
              "rule": "FAIL 的 result.json 不得交付；修复后重新校验"}
    with open(os.path.join(args.out, "contract_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"verdict": verdict, "fails": len(fails),
                      "warns": len(warns)}, ensure_ascii=False))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
