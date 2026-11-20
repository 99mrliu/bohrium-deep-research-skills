#!/usr/bin/env python3
"""scaffold_result.py - 按 output_contract 生成 /app/output/result.json 骨架。

默认不覆盖已存在的 result.json（保护增量填充成果）；--force 强制重建。

退出码: 0=成功; 2=缺少 case_summary 时以默认骨架降级; 3=失败。
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_FIELDS = ["case_id", "skill_name", "status", "product", "evidence_matrix",
                  "sources", "uncertainty", "change_records", "counts", "checks"]
SKILL_NAME = "identitylineage-dedup-first"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 result.json 骨架（默认不覆盖）")
    ap.add_argument("--work", default="/app/work", help="工作目录 (默认 /app/work)")
    ap.add_argument("--output-dir", default="/app/output", help="交付目录 (默认 /app/output)")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 result.json")
    args = ap.parse_args()

    work = Path(args.work)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.json"

    if result_path.exists() and not args.force:
        print(json.dumps({"ok": True, "skipped": True,
                          "reason": "result.json 已存在（用 --force 覆盖）",
                          "path": str(result_path)}, ensure_ascii=False))
        return 0

    code = 0
    summary_path = work / "case_summary.json"
    contract = []
    case_id = "UNKNOWN"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            contract = summary.get("output_contract") or []
            case_id = summary.get("case_id") or "UNKNOWN"
        except Exception as e:  # noqa: BLE001
            print(f"警告: case_summary.json 解析失败: {e}", file=sys.stderr)
            code = 2
    else:
        print("警告: case_summary.json 不存在，使用默认骨架", file=sys.stderr)
        code = 2

    fields = list(dict.fromkeys(list(contract) + DEFAULT_FIELDS))
    skeleton = {}
    for f in fields:
        if f == "case_id":
            skeleton[f] = case_id
        elif f == "skill_name":
            skeleton[f] = SKILL_NAME
        elif f == "status":
            skeleton[f] = "in_progress"
        elif f in ("sources", "change_records", "checks", "evidence_matrix"):
            skeleton[f] = []
        elif f in ("product", "counts", "uncertainty"):
            skeleton[f] = {}
        else:
            skeleton[f] = None  # 合同额外字段：待运行时按语义填充

    result_path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(result_path), "fields": fields},
                     ensure_ascii=False))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
