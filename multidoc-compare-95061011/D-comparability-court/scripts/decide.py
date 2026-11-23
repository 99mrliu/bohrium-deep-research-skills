#!/usr/bin/env python3
"""decide.py — 裁定引擎：对每对论文 × 每维度按规则表产出 decisions.jsonl，并给出任务级总裁定。

裁定逻辑（逐对、逐维度，确定性、无模型参与）：
  1. 任一方该维度未报告 → undecidable；
  2. 规范化取值（小写、空白归一、别名归一）一致 → comparable；
  3. 不一致且该维度配了 conversions 且命中 → convertible（附换算说明）；
  4. 不一致且配了 conversions 但未命中 → unconvertible_verdict；
  5. 其余不一致 → mismatch_verdict。
任务级总裁定 = 全部维度裁定中取 severity_order 最严者。

用法：
  python3 decide.py --profiles profiles.json --rules comparability-rules.json --out decisions.jsonl
"""
import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path


def norm_value(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().lower()


def canonical(dim: str, v, rules: dict) -> str:
    nv = norm_value(v)
    return rules.get("aliases", {}).get(dim, {}).get(nv, nv)


def get_rule(dim: str, rules: dict) -> dict:
    if dim in rules.get("dimensions", {}):
        return rules["dimensions"][dim]
    if dim in rules.get("extension_dimensions", {}):
        return rules["extension_dimensions"][dim]
    return dict(rules.get("unknown_dimension_default", {"mismatch_verdict": "undecidable"}))


def decide_dimension(dim, slot_a, slot_b, rules):
    """返回 (verdict, note, conversion_or_None)。"""
    a_missing = slot_a is None or not slot_a.get("reported", True)
    b_missing = slot_b is None or not slot_b.get("reported", True)
    if a_missing or b_missing:
        who = [n for n, m in (("A", a_missing), ("B", b_missing)) if m]
        return "undecidable", f"维度未报告（{'、'.join(who)} 侧缺失），无法裁定", None

    va, vb = canonical(dim, slot_a["value"], rules), canonical(dim, slot_b["value"], rules)
    if va == vb:
        return "comparable", "规范化取值一致", None

    rule = get_rule(dim, rules)
    for c in rule.get("conversions", []):
        ca, cb = norm_value(c["a"]), norm_value(c["b"])
        if {va, vb} == {ca, cb}:
            if va == ca:
                note = f"单位可换算：{slot_a['value']} → {slot_b['value']}（{c.get('note', '')}；factor={c.get('factor_a_to_b')}）"
            else:
                inv = c.get("factor_a_to_b")
                note = f"单位可换算：{slot_a['value']} ← {slot_b['value']}（{c.get('note', '')}；factor={inv}）"
            return "convertible", note, c
    if rule.get("conversions"):
        v = rule.get("unconvertible_verdict", "blocked")
        return v, f"取值不一致且不在可换算表内（{rule.get('note', '')}）", None
    return rule.get("mismatch_verdict", "blocked"), f"取值不一致（{rule.get('note', '')}）", None


def detail(dim, slot_a, slot_b):
    def side(slot):
        if slot is None:
            return {"value": None, "paragraph_id": None, "quote": None, "reported": False}
        return {
            "value": slot["value"],
            "paragraph_id": slot["paragraph_id"],
            "quote": slot["quote"],
            "reported": slot.get("reported", True),
        }
    return {"value_a": side(slot_a), "value_b": side(slot_b)}


def main() -> int:
    ap = argparse.ArgumentParser(description="可比性裁定引擎")
    ap.add_argument("--profiles", required=True, help="build_profiles.py 输出的 profiles.json")
    ap.add_argument("--rules", required=True, help="comparability-rules.json")
    ap.add_argument("--out", required=True, help="输出 decisions.jsonl")
    args = ap.parse_args()

    profiles = json.loads(Path(args.profiles).read_text(encoding="utf-8"))
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    severity = rules.get("severity_order",
                         ["blocked", "undecidable", "subset_only", "convertible", "comparable"])
    sev_rank = {v: i for i, v in enumerate(severity)}  # 越小越严重

    docs = profiles["docs"]
    doc_ids = sorted(docs)
    if len(doc_ids) < 2:
        print("[ERROR] 至少需要 2 篇文档的 profiles 才能做两两裁定", file=sys.stderr)
        return 1

    # 维度顺序：核心维度在前，其余（扩展键）按字典序
    core = [d for d in rules.get("core_dimensions", []) ]
    extra = sorted({dim for d in docs.values() for dim in d} - set(core))
    dimensions = core + extra

    records = []
    summary_counts: dict = {}
    for a, b in combinations(doc_ids, 2):
        pair = [a, b]
        dim_verdicts = {}
        for dim in dimensions:
            slot_a, slot_b = docs[a].get(dim), docs[b].get(dim)
            verdict, note, conv = decide_dimension(dim, slot_a, slot_b, rules)
            dim_verdicts[dim] = verdict
            summary_counts[verdict] = summary_counts.get(verdict, 0) + 1
            rec = {
                "decision_id": f"DEC-{a}--{b}-{dim}",
                "doc_pair": pair,
                "dimension": dim,
                "verdict": verdict,
                "note": note,
                "blocking_detail": detail(dim, slot_a, slot_b),
            }
            if conv:
                rec["conversion"] = conv
            records.append(rec)

        overall = min(dim_verdicts.values(), key=lambda v: sev_rank.get(v, len(sev_rank)))
        strictest = sorted(d for d, v in dim_verdicts.items() if v == overall)
        blocking = sorted(d for d, v in dim_verdicts.items()
                          if sev_rank.get(v, 99) <= sev_rank.get("subset_only", 2))
        records.append({
            "decision_id": f"DEC-{a}--{b}-__overall__",
            "doc_pair": pair,
            "dimension": "__overall__",
            "verdict": overall,
            "note": "任务级总裁定 = 各维度裁定之最严者",
            "strictest_dimensions": strictest,
            "blocking_dimensions": blocking,
            "dimension_verdicts": dim_verdicts,
        })
        summary_counts[overall + " (overall)"] = summary_counts.get(overall + " (overall)", 0) + 1

    with open(args.out, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"OK: {len(records)} 条裁定（含 {len(list(combinations(doc_ids, 2)))} 条任务级总裁定）→ {args.out}")
    print("裁定统计:")
    for k in sorted(summary_counts, key=lambda x: sev_rank.get(x.replace(' (overall)', ''), 99)):
        print(f"  {k}: {summary_counts[k]}")
    for rec in records:
        if rec["dimension"] == "__overall__":
            pair = " × ".join(rec["doc_pair"])
            print(f"  [OVERALL] {pair}: {rec['verdict']}（最严维度: {', '.join(rec['strictest_dimensions'])}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
