#!/usr/bin/env python3
"""make_result.py — 按 case.json 的 output_contract.fields 运行时逐字段装配 result.json。

规则：
- 字段集合绝不硬编码：运行时读取 output_contract.fields，逐字段填充；
  未知字段填 null 并在 problems 记录。
- edited_chapters：把编辑后章节复制到 <out>/chapters/，字段值为相对路径列表。
- 原子写入：<out>/result.json.tmp -> os.replace(result.json)。
- status：complete（无 problem/manual/FAIL）/ partial（有但未崩）/ failed（关键输入缺失）。
- 先存可用 partial 再增量改进：本脚本幂等，可随时重跑覆盖 result.json。

仅使用 python3 标准库；所有路径均由命令行参数传入。
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main():
    ap = argparse.ArgumentParser(description="装配并原子写出 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True, help="含 ops.json/change_log.json/acceptance_report.json")
    ap.add_argument("--chapters", required=True, help="编辑后章节目录")
    ap.add_argument("--out", required=True, help="输出目录（result.json 与 chapters/ 落此处）")
    ap.add_argument("--note", default="", help="可选标注（合成示例必传）")
    args = ap.parse_args()

    work, out_dir = Path(args.work), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    case = load_json(args.case)
    if case is None:
        print(f"[make_result] FATAL: 无法读取 case.json: {args.case}", file=sys.stderr)
        return 2
    case_id = case.get("case_id", "UNKNOWN")
    contract = case.get("output_contract", {}) or {}
    fields = contract.get("fields", []) or []

    change_log = load_json(work / "change_log.json")
    acceptance = load_json(work / "acceptance_report.json")
    ops_doc = load_json(work / "ops.json")

    problems, uncertainty = [], []

    # ---- 收集 uncertainty 来源 ----
    if change_log:
        for p in change_log.get("problems", []):
            uncertainty.append(f"{p.get('op_id','?')}: {p.get('reason','')}")
        for m in change_log.get("manual_ops", []):
            uncertainty.append(f"{m.get('op_id','?')}（人工项）: {m.get('reason','')}")
    else:
        problems.append("change_log.json 缺失：apply_ops 未运行或失败")
    if acceptance and acceptance.get("overall") == "FAIL":
        uncertainty.append("acceptance 存在 FAIL 项，详见 acceptance_report")
    if acceptance is None:
        problems.append("acceptance_report.json 缺失：verify_acceptance 未运行或失败")

    # ---- 字段填充器 ----
    def fill_edited_chapters():
        ch_src = Path(args.chapters)
        ch_dst = out_dir / "chapters"
        ch_dst.mkdir(exist_ok=True)
        copied = []
        for p in sorted(ch_src.glob("*.md")):
            shutil.copyfile(p, ch_dst / p.name)
            copied.append(f"chapters/{p.name}")
        if not copied:
            problems.append("编辑后章节目录为空")
            return None
        return copied

    def fill_change_record():
        if change_log is None:
            return None
        (out_dir / "change_record.json").write_text(
            json.dumps(change_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return change_log

    def fill_consistency_report():
        if acceptance is None:
            return None
        fi = acceptance.get("float_integrity", {})
        term_checks = []
        for it in acceptance.get("items", []):
            for c in it.get("checks", []):
                if "不再出现" in c.get("desc", ""):
                    term_checks.append({"desc": c["desc"], "result": c["result"],
                                        "detail": c["detail"]})
        return {"float_integrity": fi, "term_absence_checks": term_checks}

    def fill_acceptance_report():
        return acceptance

    def fill_uncertainty():
        return uncertainty

    FILLERS = {
        "edited_chapters": fill_edited_chapters,
        "change_record": fill_change_record,
        "consistency_report": fill_consistency_report,
        "acceptance_report": fill_acceptance_report,
        "verification": fill_acceptance_report,
        "uncertainty": fill_uncertainty,
    }

    result = {"case_id": case_id, "task": case.get("task", "")}
    for field in fields:
        filler = FILLERS.get(field)
        if filler is None:
            result[field] = None
            problems.append(f"output_contract 字段 “{field}” 无填充器，置 null")
            continue
        try:
            result[field] = filler()
        except Exception as exc:  # 填充器失败不拖垮整体
            result[field] = None
            problems.append(f"字段 “{field}” 填充失败: {exc}")

    # ---- status ----
    if change_log is None or not fields:
        status = "failed"
    elif problems or uncertainty or (acceptance or {}).get("overall") == "FAIL":
        status = "partial"
    else:
        status = "complete"

    result["status"] = status
    result["sources"] = {
        "case": Path(args.case).name,
        "workorder": "organizer-edit-workorder.json",
        "chapters": sorted(p.name for p in Path(args.chapters).glob("*.md")),
        "ops": "ops.json" if ops_doc else None,
    }
    result["problems"] = problems
    result["uncertainty"] = uncertainty
    result["contract_fields"] = fields
    if args.note:
        result["note"] = args.note

    # ---- 原子写 ----
    tmp = out_dir / "result.json.tmp"
    final = out_dir / "result.json"
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, final)
    print(f"[make_result] case_id={case_id} status={status} "
          f"fields={len(fields)} problems={len(problems)} uncertainty={len(uncertainty)}")
    print(f"[make_result] -> {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
