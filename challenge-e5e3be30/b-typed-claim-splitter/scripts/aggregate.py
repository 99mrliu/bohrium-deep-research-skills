#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggregate.py — 子判定 → 整论断判定的确定性聚合器（纯标准库）

输入子判定 JSON：
{
  "claim_id": "c1",
  "subjudgments": [
    {"id": "c1#a1", "verdict": "supported", "type": "comparison",
     "core": true,              # 可选；缺省：type=modifier → core=false，其余 → core=true
     "weight": 1.0,             # 可选；仅用于报告占比，不改变判定
     "note": "…"},
    …
  ]
}

聚合规则（与 references/aggregation-rules.md 逐条对应）：
  R1 全部 supported                                    → supported
  R2 任一 core=true 子判断为 contradicted              → contradicted
  R3 contradicted 仅出现在 core=false（修饰）子判断    → partially_supported
  R4 无 contradicted、全部 insufficient_evidence       → insufficient_evidence
  R5 无 contradicted、无任何 supported                 → insufficient_evidence
  R6 其余混合（supported + insufficient，或含
     partially_supported 子判断）                      → partially_supported
规则按 R2 → R1 → R3 → R4/R5 → R6 的顺序求值；--explain 输出逐步推导。

子判断 verdict 取值：supported / partially_supported / contradicted / insufficient_evidence。

退出码：0 成功；1 输入/校验错误；2 用法错误（argparse）。

用法：
  python3 aggregate.py --subjudgments sub.json [--explain] [--out verdict.json]
  python3 aggregate.py --help
"""
import argparse
import json
import sys

VALID_VERDICTS = ("supported", "partially_supported", "contradicted", "insufficient_evidence")
VALID_TYPES = ("fact", "comparison", "causal", "scope", "modifier")


def is_core(sub):
    if "core" in sub:
        return bool(sub["core"])
    return sub.get("type", "fact") != "modifier"


def aggregate(subs, explain=False):
    steps = []
    n = len(subs)
    by_verdict = {v: [s for s in subs if s["verdict"] == v] for v in VALID_VERDICTS}
    core_contra = [s for s in by_verdict["contradicted"] if s["_core"]]
    mod_contra = [s for s in by_verdict["contradicted"] if not s["_core"]]
    steps.append("步骤1：%d 个子判定分布：%s" % (
        n, ", ".join("%s=%d" % (v, len(by_verdict[v])) for v in VALID_VERDICTS)))
    steps.append("步骤2：核心/修饰划分：core=true %d 个，core=false %d 个（缺省规则：type=modifier 为修饰，其余为核心）"
                 % (sum(1 for s in subs if s["_core"]), sum(1 for s in subs if not s["_core"])))

    # R2
    steps.append("步骤3（R2）：检查 core=true 且 contradicted：%d 个" % len(core_contra))
    if core_contra:
        ids = ", ".join(s["id"] for s in core_contra)
        steps.append("  → 命中 R2：核心子判断 %s 被反驳，整论断判定为 contradicted。" % ids)
        verdict, rule = "contradicted", "R2"
    # R1
    elif len(by_verdict["supported"]) == n:
        steps.append("  未命中 R2。步骤4（R1）：全部子判断 supported → supported。")
        verdict, rule = "supported", "R1"
    # R3
    elif mod_contra and not core_contra:
        steps.append("  未命中 R2。步骤4（R3）：contradicted 仅出现在修饰子判断 %s → partially_supported。"
                     % ", ".join(s["id"] for s in mod_contra))
        verdict, rule = "partially_supported", "R3"
    # R4
    elif len(by_verdict["insufficient_evidence"]) == n:
        steps.append("  未命中 R2/R3。步骤4（R4）：全部子判断 insufficient_evidence → insufficient_evidence。")
        verdict, rule = "insufficient_evidence", "R4"
    # R5
    elif not by_verdict["supported"] and not by_verdict["partially_supported"]:
        steps.append("  未命中 R2/R3/R4。步骤5（R5）：无任何 supported/partially_supported → insufficient_evidence。")
        verdict, rule = "insufficient_evidence", "R5"
    # R6
    else:
        steps.append("  未命中 R2–R5。步骤6（R6）：supported 与 insufficient_evidence/partially_supported 混合 "
                     "→ partially_supported。")
        verdict, rule = "partially_supported", "R6"

    total_w = sum(float(s.get("weight", 1.0)) for s in subs) or 1.0
    breakdown = [{
        "id": s["id"], "type": s.get("type", "fact"), "core": s["_core"],
        "verdict": s["verdict"], "weight": float(s.get("weight", 1.0)),
        "weight_share": round(float(s.get("weight", 1.0)) / total_w, 4),
        "note": s.get("note", ""),
    } for s in subs]
    rationale = {
        "R2": "核心子判断 %s 与文献证据冲突，方向/数值/极性被推翻，整论断 contradicted。"
              % ", ".join(s["id"] for s in core_contra),
        "R1": "全部 %d 个原子子判断均获文献直接支持，整论断 supported。" % n,
        "R3": "被反驳的仅为修饰性子判断（%s），核心谓词成立但被限定，整论断 partially_supported。"
              % ", ".join(s["id"] for s in mod_contra),
        "R4": "全部子判断均缺乏可核验证据，整论断 insufficient_evidence。",
        "R5": "无任一子判断获得支持且亦无直接反驳，整论断 insufficient_evidence。",
        "R6": "部分子判断获支持、部分证据不足或部分成立，整论断 partially_supported。",
    }[rule]
    return verdict, rule, rationale, breakdown, steps


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="子判定→整论断判定的确定性聚合。规则全集见 references/aggregation-rules.md。")
    ap.add_argument("--subjudgments", required=True, help="子判定 JSON 路径（含 claim_id 与 subjudgments 数组）")
    ap.add_argument("--explain", action="store_true", help="输出逐步推导过程到标准输出")
    ap.add_argument("--out", default=None, help="聚合结果 JSON 输出路径（默认写到标准输出）")
    args = ap.parse_args(argv)

    try:
        with open(args.subjudgments, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("错误：无法读取子判定文件：%s" % e, file=sys.stderr)
        return 1
    subs = data.get("subjudgments")
    if not isinstance(subs, list) or not subs:
        print("错误：subjudgments 必须是非空数组。", file=sys.stderr)
        return 1
    for s in subs:
        if not isinstance(s, dict) or "id" not in s or "verdict" not in s:
            print("错误：每个子判断必须含 id 与 verdict 字段。", file=sys.stderr)
            return 1
        if s["verdict"] not in VALID_VERDICTS:
            print("错误：子判断 %s 的 verdict '%s' 非法，取值限 %s。"
                  % (s.get("id"), s["verdict"], "/".join(VALID_VERDICTS)), file=sys.stderr)
            return 1
        if s.get("type", "fact") not in VALID_TYPES:
            print("错误：子判断 %s 的 type '%s' 非法，取值限 %s。"
                  % (s.get("id"), s.get("type"), "/".join(VALID_TYPES)), file=sys.stderr)
            return 1
        s["_core"] = is_core(s)

    verdict, rule, rationale, breakdown, steps = aggregate(subs, explain=args.explain)
    if args.explain:
        print("聚合推导（claim_id=%s）：" % data.get("claim_id", "?"))
        for st in steps:
            print("  " + st)
        print("  结论：%s（规则 %s）" % (verdict, rule))

    result = {
        "claim_id": data.get("claim_id"),
        "verdict": verdict,
        "rule": rule,
        "rationale": rationale,
        "breakdown": breakdown,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print("聚合结果已写入 %s（verdict=%s，规则 %s）" % (args.out, verdict, rule))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
