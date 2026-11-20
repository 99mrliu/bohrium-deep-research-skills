#!/usr/bin/env python3
"""build_criteria_skeleton.py — 生成 criteria_table.json 骨架（步骤 5，脚本环节）。

生成 {version: v1.0.0, research_question, eligible_languages, criteria: [],
changelog: []} 骨架并附填写说明，供模型按案例标准文本填充。
若 criteria_table.json 已存在则默认保留（--force 覆盖），避免冲掉模型已填内容。

退出码：0=通过；2=输入不足；3=校验失败。幂等。
"""
import argparse
import json
import sys
from pathlib import Path

INSTRUCTIONS = (
    "请模型按案例标准文本填充 criteria 数组。每条标准必须含："
    "criterion_id（INC1../EXC1..）、type（inclusion/exclusion）、statement（原文）、"
    "predicate（可判定检查点描述，逐条落到可判定判据）、evidence_required（true）、"
    "reason_code（取自 rules/reason_codes.md 注册表）、boundary_notes（边界说明）。"
    "eligible_languages 填允许的语言代码列表（如 [\"en\"]），空列表表示不限制。"
    "填充完成后删除 _instructions 与 _criteria_source_fragments 字段。"
    "任何后续修改必须升 version 并写 changelog（见 rules/criteria_versioning.md）。"
)


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 criteria_table.json 骨架")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--force", action="store_true", help="覆盖已有 criteria_table.json")
    args = ap.parse_args(argv)
    work = Path(args.work)
    summary_path = work / "case_summary.json"
    if not summary_path.exists():
        print(f"[build_criteria_skeleton] 缺少 {summary_path}，请先运行 parse_case.py。",
              file=sys.stderr)
        return 2
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[build_criteria_skeleton] case_summary 解析失败: {e}", file=sys.stderr)
        return 2

    out_path = work / "criteria_table.json"
    if out_path.exists() and not args.force:
        print(f"[build_criteria_skeleton] {out_path} 已存在，保留（用 --force 覆盖）。")
        return 0

    rq = (summary.get("research_question") or {}).get("value") or ""
    skeleton = {
        "version": "v1.0.0",
        "research_question": rq,
        "eligible_languages": [],
        "criteria": [],
        "changelog": [],
        "_instructions": INSTRUCTIONS,
        "_criteria_source_fragments": summary.get("criteria_fragments") or [],
    }
    out_path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build_criteria_skeleton] 骨架 -> {out_path}（待模型填充 criteria）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[build_criteria_skeleton] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
