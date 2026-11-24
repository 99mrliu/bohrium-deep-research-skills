#!/usr/bin/env python3
"""contract_validate.py — 交付前契约合规校验。

对照 case.json 的 output_contract 逐字段校验已回填的 result.json：
  - case_id 与 case.json 逐字一致（硬失败）；
  - 契约声明的字段全部存在（缺失=硬失败）；
  - 字段仍为空的比例（null/空串/空数组/空对象计为未回填）；
  - status ∈ {success, partial, failed}，且 status=success 时不允许存在
    未回填的契约字段（否则强制要求改判 partial）；
  - 多出契约未声明的字段：只警告（允许运行状态字段），不判失败。

用法：
  python3 contract_validate.py --case /input/case.json \
      --result /app/output/result.json --out /app/work/contract_check

输出 contract_check.json / contract_check.md；全部硬检查通过退出码 0，
存在硬失败为 1，参数错误为 2。仅依赖 Python 3.8+ 标准库。
"""
import argparse
import json
import sys
from pathlib import Path

VALID_STATUS = {"success", "partial", "failed"}


def extract_fields(contract):
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        out = []
        for item in contract:
            out.append(item if isinstance(item, str)
                       else str(item.get("name", item)))
        return out
    if isinstance(contract, str):
        return [t.strip() for t in contract.replace("\n", ",").split(",")
                if t.strip()]
    return []


def is_empty(value):
    return value is None or value == "" or value == [] or value == {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    fields = extract_fields(case.get("output_contract"))

    hard_fails, warnings = [], []
    if result.get("case_id") != case.get("case_id"):
        hard_fails.append("case_id 不一致：result=%r case=%r"
                          % (result.get("case_id"), case.get("case_id")))
    missing = [f for f in fields if f not in result]
    if missing:
        hard_fails.append("契约字段缺失: " + ", ".join(missing))
    unfilled = [f for f in fields if f in result and is_empty(result[f])]
    status = result.get("status")
    if status not in VALID_STATUS:
        hard_fails.append("status 非法: %r（应为 success/partial/failed）"
                          % (status,))
    elif status == "success" and unfilled:
        hard_fails.append("status=success 但以下契约字段未回填: "
                          + ", ".join(unfilled))
    extras = [k for k in result
              if k not in fields and k not in ("case_id", "status")]
    if extras:
        warnings.append("契约未声明的字段（警告，不判失败）: " + ", ".join(extras))
    if status == "partial" and not result.get("uncertainty") \
            and "uncertainty" in fields:
        warnings.append("status=partial 但 uncertainty 字段为空，应写明缺口")

    report = {"hard_fails": hard_fails, "warnings": warnings,
              "contract_fields": len(fields), "missing": missing,
              "unfilled": unfilled,
              "fill_rate": (len(fields) - len(missing) - len(unfilled))
                           / len(fields) if fields else None,
              "status": status, "passed": not hard_fails}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    lines = ["# 契约合规校验", "",
             "判定：**%s**" % ("通过" if report["passed"] else "未通过"),
             "契约字段 %d 个；缺失 %d；已声明但未回填 %d；回填率 %s。"
             % (len(fields), len(missing), len(unfilled),
                "%.0f%%" % (report["fill_rate"] * 100)
                if report["fill_rate"] is not None else "-"), ""]
    if hard_fails:
        lines.append("## 硬失败")
        lines += ["- " + h for h in hard_fails]
    if warnings:
        lines.append("## 警告")
        lines += ["- " + w for w in warnings]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n",
                                      encoding="utf-8")
    print(json.dumps({"passed": report["passed"],
                      "hard_fails": len(hard_fails),
                      "fill_rate": report["fill_rate"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
