#!/usr/bin/env python3
"""step3_freeze.py — 合成示例流水线·步骤3：全文级筛选、冻结纳入清单、生成 flow.json。

玩具条款（确定性）：fulltext_available 为 false → 排除「全文不可得」，其余纳入。

产物：
  decisions.jsonl  — 题录+全文两阶段完整决策（重写，排序确定性）
  included.json    — 冻结的纳入清单
  flow.json        — 由真实产物计算的 PRISMA 计数（可被 reconcile 轧平）
退出码：0=成功；2=输入缺失或非法（R1/R2）；3=内部计数自检失败（F0）。
"""
import argparse
import json
import os
import sys


def eprint(*a):
    print(*a, file=sys.stderr)


def load_json(path, label):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        eprint(f"R1: {label} 不存在: {path}")
        sys.exit(2)
    except json.JSONDecodeError as e:
        eprint(f"R2: {label} JSON 非法: {e}")
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description="全文筛选、冻结纳入清单并生成 flow.json。")
    ap.add_argument("--records", required=True, help="原始 records.json（取 identified）")
    ap.add_argument("--deduped", required=True, help="step1 产物 deduped.json")
    ap.add_argument("--decisions", required=True, help="step2 产物 decisions.jsonl（题录阶段）")
    ap.add_argument("--output-decisions", required=True, help="输出完整 decisions.jsonl")
    ap.add_argument("--output-included", required=True, help="输出 included.json")
    ap.add_argument("--output-flow", required=True, help="输出 flow.json")
    args = ap.parse_args()

    records = load_json(args.records, "原始题录")
    deduped = load_json(args.deduped, "去重产物")
    if not isinstance(records, list) or "records" not in deduped:
        eprint("R2: 输入结构不符（records 应为数组，deduped 应含 records）")
        return 2
    by_id = {r.get("record_id"): r for r in records}

    ta_decisions = []
    try:
        with open(args.decisions, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    d = json.loads(line)
                    # 只取题录阶段决策：本步骤可能重跑（断点续跑/replay 二次执行），
                    # 输入文件可能已是上一轮的完整 decisions，必须按 stage 过滤保持幂等。
                    if d.get("stage") == "ta":
                        ta_decisions.append(d)
    except FileNotFoundError:
        eprint(f"R1: 题录决策文件不存在: {args.decisions}")
        return 2
    except json.JSONDecodeError as e:
        eprint(f"R2: 题录决策第 {i} 行 JSON 非法: {e}")
        return 2

    ft_decisions = []
    ft_excluded = {}
    included_ids = []
    for d in sorted(ta_decisions, key=lambda x: str(x.get("record_id", ""))):
        if d.get("decision") != "include":
            continue
        rid = d.get("record_id")
        rec = by_id.get(rid, {})
        if not rec.get("fulltext_available", False):
            ft_decisions.append({"record_id": rid, "stage": "ft",
                                 "decision": "exclude", "reason": "全文不可得"})
            ft_excluded["全文不可得"] = ft_excluded.get("全文不可得", 0) + 1
        else:
            ft_decisions.append({"record_id": rid, "stage": "ft",
                                 "decision": "include", "reason": ""})
            included_ids.append(rid)

    all_decisions = sorted(ta_decisions + ft_decisions,
                           key=lambda x: (str(x.get("record_id", "")), str(x.get("stage", ""))))
    with open(args.output_decisions, "w", encoding="utf-8") as f:
        for d in all_decisions:
            f.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")

    included = {"frozen": True, "n_included": len(included_ids),
                "included_record_ids": sorted(included_ids)}
    with open(args.output_included, "w", encoding="utf-8") as f:
        json.dump(included, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    ta_excluded = {}
    n_ta_passed = 0
    for d in ta_decisions:
        if d.get("decision") == "exclude":
            r = d.get("reason") or "未注明理由"
            ta_excluded[r] = ta_excluded.get(r, 0) + 1
        else:
            n_ta_passed += 1

    flow = {
        "identified": len(records),
        "duplicates_removed": deduped.get("duplicates_removed", 0),
        "screened": len(deduped["records"]),
        "excluded_title_abstract": ta_excluded,
        "fulltext_assessed": n_ta_passed,
        "excluded_fulltext": ft_excluded,
        "included": len(included_ids),
    }
    # 内部自检：写盘前先轧一遍（F1–F3）
    errs = []
    if flow["identified"] - flow["duplicates_removed"] != flow["screened"]:
        errs.append("F1")
    if flow["screened"] != sum(ta_excluded.values()) + flow["fulltext_assessed"]:
        errs.append("F2")
    if flow["fulltext_assessed"] != sum(ft_excluded.values()) + flow["included"]:
        errs.append("F3")
    if errs:
        eprint(f"F0: 内部计数自检失败（{'/'.join(errs)}），flow.json 未写出")
        return 3
    with open(args.output_flow, "w", encoding="utf-8") as f:
        json.dump(flow, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"screen_ft+freeze: fulltext_assessed={flow['fulltext_assessed']} "
          f"excluded_ft={sum(ft_excluded.values())} included={flow['included']}，flow.json 已冻结")
    return 0


if __name__ == "__main__":
    sys.exit(main())
