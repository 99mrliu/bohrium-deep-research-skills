#!/usr/bin/env python3
"""step2_screen_count.py — 合成示例流水线·步骤2：题录级筛选与计数。

玩具条款（确定性，真实任务中由模型按条款化纳排标准判定，此处仅为可重放演示）：
  E1 非随机对照试验：study_type != "RCT"
  E2 人群不符：population 不含「抗生素」或「antibiotic」（大小写不敏感）
按 E1→E2 顺序取首个命中理由（一篇只计一个主排除理由，避免双计）。

产物：screening.json（计数汇总）+ decisions.jsonl（题录阶段逐条决策）。
退出码：0=成功；2=输入缺失或非法（R1/R2）。
"""
import argparse
import json
import os
import sys


def eprint(*a):
    print(*a, file=sys.stderr)


def decide(record):
    if record.get("study_type") != "RCT":
        return "exclude", "非随机对照试验"
    pop = str(record.get("population", "")).lower()
    if "抗生素" not in pop and "antibiotic" not in pop:
        return "exclude", "人群不符"
    return "include", ""


def main():
    ap = argparse.ArgumentParser(description="题录级筛选并输出逐条决策与计数。")
    ap.add_argument("--input", required=True, help="step1 产物 deduped.json")
    ap.add_argument("--output", required=True, help="输出 screening.json")
    ap.add_argument("--decisions", required=True, help="输出 decisions.jsonl（题录阶段）")
    args = ap.parse_args()

    try:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        eprint(f"R1: 输入文件不存在: {args.input}")
        return 2
    except json.JSONDecodeError as e:
        eprint(f"R2: 输入 JSON 非法: {e}")
        return 2
    records = data.get("records")
    if not isinstance(records, list):
        eprint("R2: 输入缺少 records 数组（应为 step1 产物）")
        return 2

    decisions = []
    excluded = {}
    passed = 0
    for r in sorted(records, key=lambda x: str(x.get("record_id", ""))):
        dec, reason = decide(r)
        decisions.append({"record_id": r.get("record_id", ""), "stage": "ta",
                          "decision": dec, "reason": reason})
        if dec == "exclude":
            excluded[reason] = excluded.get(reason, 0) + 1
        else:
            passed += 1

    screening = {
        "counts": {
            "screened": len(records),
            "excluded_title_abstract": excluded,
            "fulltext_assessed": passed,
        }
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(screening, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    with open(args.decisions, "w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"screen_ta: screened={len(records)} excluded={sum(excluded.values())} "
          f"fulltext_assessed={passed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
