#!/usr/bin/env python3
"""scaffold_result.py — 按案例输出合同生成 result.json 骨架并落盘。

骨架在流程早期落盘，之后各环节增量填充（诚实纪律：先 partial 后 complete）。
退出码：0=成功；2=输入缺失或无法解析；3=校验失败。
"""
import argparse
import json
import sys

SKILL_NAME = "slr-claim-backlink"

PLACEHOLDERS = {
    "case_id": None,
    "skill_name": SKILL_NAME,
    "status": "partial",
    "product": None,
    "evidence_matrix": None,
    "sources": [],
    "uncertainty": [],
    "change_records": [],
    "counts": {},
    "checks": [],
}


def fail_input(msg):
    print(f"[E-INPUT] {msg}", file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(
        description="生成 result.json 骨架（skill_name=%s），字段取自案例 output_contract。" % SKILL_NAME)
    ap.add_argument("--case-summary", required=True, help="parse_case.py 输出的 case_summary.json")
    ap.add_argument("--out", required=True, help="输出 result.json 路径（建议 /app/output/result.json）")
    args = ap.parse_args()

    try:
        with open(args.case_summary, encoding="utf-8") as f:
            summary = json.load(f)
    except OSError as e:
        fail_input(f"无法读取 {args.case_summary}：{e}")
    except json.JSONDecodeError as e:
        fail_input(f"case_summary 不是合法 JSON：{e}")
    if not isinstance(summary, dict) or "case_id" not in summary:
        fail_input("case_summary 缺少 case_id 字段。")

    contract = summary.get("output_contract") or list(PLACEHOLDERS.keys())
    result = {}
    for field in contract:
        if field in PLACEHOLDERS:
            # 深拷贝可变占位值
            result[field] = json.loads(json.dumps(PLACEHOLDERS[field]))
        else:
            result[field] = None
    result["case_id"] = summary["case_id"]
    result["skill_name"] = SKILL_NAME
    result["status"] = "partial"
    result["status_reason"] = "result.json 骨架已生成，各综述环节尚未完成，待增量填充。"
    result["change_records"] = [
        {"step": "scaffold",
         "note": "scaffold_result.py 生成骨架；后续环节按工作流程增量填充。"}
    ]
    result["checks"] = [
        {"item": "骨架落盘", "status": "pass",
         "note": "output_contract 全部字段已就位，缺省值为 null/空。"}
    ]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"已生成 {args.out}：skill_name={SKILL_NAME}，status=partial，"
          f"字段 {len(result)} 个。")
    sys.exit(0)


if __name__ == "__main__":
    main()
