#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 按 output_contract 尽早在 /app/output/result.json 落盘骨架。

用法:
    python3 scaffold_result.py [--work /app/work] [--output-dir /app/output] [--force]

行为:
    - 读取 <work>/case_summary.json 的 case_id 与 output_contract；
    - 生成 {case_id: ..., 每个合同字段: null} 骨架；
    - 默认不覆盖已存在的 result.json（幂等），--force 才重建；
    - 之后各阶段只增量填充字段，防超时零交付。

退出码: 0=成功, 2=用法或IO错误, 3=校验失败
"""
import argparse
import json
import sys
import traceback
from pathlib import Path


def eprint(*a):
    print(*a, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="生成 result.json 合同骨架（默认不覆盖）")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 result.json")
    args = ap.parse_args()

    work = Path(args.work)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.json"

    if result_path.exists() and not args.force:
        print(f"[scaffold_result] 已存在，未覆盖: {result_path}")
        return 0

    summary_path = work / "case_summary.json"
    if not summary_path.exists():
        eprint(f"[scaffold_result] 缺少 {summary_path}，请先运行 parse_case.py")
        return 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    skeleton = {"case_id": summary.get("case_id", "unknown_case")}
    for field in summary.get("output_contract", []):
        if field != "case_id":
            skeleton[field] = None
    skeleton["_meta"] = {
        "status": "scaffold",
        "notice": "骨架文件；各字段由后续阶段增量填充；null 表示尚未填充。",
    }
    result_path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"[scaffold_result] 骨架字段数={len(skeleton) - 1} -> {result_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[scaffold_result] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
