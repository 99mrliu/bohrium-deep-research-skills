#!/usr/bin/env python3
"""scaffold_result.py — 尽早在 /app/output/result.json 落盘骨架，防超时零交付。

读取 <work>/case_summary.json 的 case_id 与 output_contract 字段列表；
骨架中每个合同字段先置 null，status 置 "in_progress"，
并预置 sources / uncertainty / change_records 三个通用字段。
后续 fill_result.py 会在此基础上逐字段填充；填不了的字段保持 null 并说明。

退出码：0 正常；2 无 case_summary（用最小骨架兜底）。
"""
import argparse
import sys
from pathlib import Path

from common_lib import dump_json, eprint, load_json


def main(argv=None):
    ap = argparse.ArgumentParser(description="按 output_contract 生成 result.json 骨架")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args(argv)

    work, out_dir = Path(args.work), Path(args.output_dir)
    summary_path = work / "case_summary.json"
    rc = 0
    if summary_path.exists():
        summary = load_json(summary_path)
        case_id = summary.get("case_id")
        fields = list(summary.get("output_contract") or [])
    else:
        eprint("[scaffold_result] 警告: 无 case_summary.json，使用最小骨架")
        case_id, fields = None, []
        rc = 2

    skeleton = {"case_id": case_id, "status": "in_progress"}
    for f in fields:
        if f not in skeleton:
            skeleton[f] = None
    # 通用字段即使不在合同列表中也预置，保证运行时随时有可读交付
    skeleton.setdefault("sources", [])
    skeleton.setdefault("uncertainty", ["骨架阶段：排序流水线尚未完成，除 case_id/status 外均为占位。"])
    skeleton.setdefault("change_records", [{"step": "scaffold",
                                            "detail": "按 output_contract 落盘 result.json 骨架"}])
    skeleton["_skeleton"] = True

    dump_json(out_dir / "result.json", skeleton)
    print(f"[scaffold_result] 骨架已写入 {out_dir / 'result.json'}，合同字段数={len(fields)}")
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[scaffold_result] 未预期异常: {exc!r}")
        sys.exit(3)
