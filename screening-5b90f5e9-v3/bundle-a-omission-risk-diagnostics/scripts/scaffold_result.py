#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 尽早落 result.json 骨架（工作流第 1 步）。

职责：
  1. 读取 input-dir/case.json，提取 case_id 与 output_contract.required_fields；
  2. 立即在 output-dir/result.json 生成骨架：合同字段全部就位、填不了的置 null、
     status=partial、uncertainty 记录降级原因、change_records 开始记账；
  3. 幂等：result.json 已存在时只补缺省字段，绝不覆盖已填内容。

退出码：0=通过；2=输入不足诚实降级（骨架仍尽力落盘）；3=校验失败（case.json 非法）。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

EXIT_OK, EXIT_INSUFFICIENT, EXIT_INVALID = 0, 2, 3

DEFAULT_FIELDS = [
    "case_id", "status", "near_misses", "fragility_report", "facet_coverage",
    "omission_statement", "recheck_worklist", "sources", "uncertainty",
    "change_records",
]


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)  # 原子覆盖，保证幂等与中途失败不留半个文件


def main():
    ap = argparse.ArgumentParser(description="尽早生成 result.json 骨架")
    ap.add_argument("--input-dir", default="/input", help="输入目录（含 case.json）")
    ap.add_argument("--work", default="/app/work", help="中间产物目录")
    ap.add_argument("--output-dir", default="/app/output", help="交付目录")
    args = ap.parse_args()

    try:
        os.makedirs(args.work, exist_ok=True)
        os.makedirs(args.output_dir, exist_ok=True)
        case_path = os.path.join(args.input_dir, "case.json")
        result_path = os.path.join(args.output_dir, "result.json")

        if not os.path.exists(case_path):
            # 合同不可知：只能写最小骨架，诚实 failed
            minimal = {
                "case_id": None,
                "status": "failed",
                "uncertainty": [
                    "case.json 不存在，无法读取 output_contract；流程在骨架阶段诚实终止。"
                ],
                "change_records": [
                    {"ts": utcnow(),
                     "action": "scaffold_result: case.json missing, minimal skeleton written",
                     "files": [result_path]}
                ],
            }
            save_json(result_path, minimal)
            print("case.json 缺失：已写最小骨架 %s" % result_path, file=sys.stderr)
            return EXIT_INSUFFICIENT

        try:
            case = load_json(case_path)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print("case.json 解析失败: %s" % e, file=sys.stderr)
            return EXIT_INVALID

        contract = case.get("output_contract") or {}
        fields = contract.get("required_fields")
        degrade_notes = []
        exit_code = EXIT_OK
        if not fields:
            fields = list(DEFAULT_FIELDS)
            degrade_notes.append(
                "case.json 未提供 output_contract.required_fields，骨架使用默认字段集合，"
                "需人工与 task.md 合同核对。")
            exit_code = EXIT_INSUFFICIENT

        if os.path.exists(result_path):
            result = load_json(result_path)  # 幂等：保留已有填充
        else:
            result = {}

        result["case_id"] = case.get("case_id")
        if result.get("status") != "completed":
            result["status"] = "partial"
        for field in fields:
            result.setdefault(field, None)
        # 结构性字段给出空容器而非 null，便于后续脚本增量写入
        for field in ("sources", "uncertainty", "change_records"):
            if field in fields and not isinstance(result.get(field), list):
                result[field] = []
        existing_unc = result.get("uncertainty") or []
        for note in degrade_notes:
            if note not in existing_unc:
                existing_unc.append(note)
        result["uncertainty"] = existing_unc
        result["change_records"].append({
            "ts": utcnow(),
            "action": "scaffold_result: skeleton ensured (%d contract fields)" % len(fields),
            "files": [result_path],
        })
        save_json(result_path, result)
        print("result.json 骨架就绪：%s（合同字段 %d 个）" % (result_path, len(fields)))
        return exit_code
    except Exception as e:  # 顶层兜底：任何意外都不向评测器抛 traceback
        print("scaffold_result 未预期失败: %s" % e, file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
