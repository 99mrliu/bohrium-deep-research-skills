#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renumber_plan.py -- 由扫描报告生成重编号方案（只出方案，不动文件）。

原则：编号修正必须先有**全量方案**再动手——题注改号与正文所有引用点
同步改号，漏一个就是悬空引用。本工具按题注出现顺序生成 old->new 映射，
并列出每个需要同步修改的正文引用点（块号+上下文），交 Agent 执行与复核。

用法: python3 renumber_plan.py xref_report.json --out renumber_plan.json
退出码: 0 方案已生成（含"无需改号"）; 2 输入不可读。
"""
import argparse, json, re, sys

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xref_report")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        rep = json.load(open(a.xref_report, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        sys.exit(2)

    plans = {}
    for kind in ("figure", "table"):
        caps = [c for c in rep.get("captions", []) if c["kind"] == kind]
        caps.sort(key=lambda c: c["block"])
        # 只对简单整数编号做 1..N 重排；含子编号（3-1 式）跳过并点名
        simple = [c for c in caps if c["num"].isdigit()]
        compound = [c for c in caps if not c["num"].isdigit()]
        mapping = {}
        for i, c in enumerate(simple, 1):
            if c["num"] != str(i):
                mapping[c["num"]] = str(i)
        caption_edits = [{"block": c["block"], "old": c["num"],
                          "new": mapping.get(c["num"], c["num"]), "text": c["text"]}
                         for c in simple if c["num"] in mapping]
        ref_edits = [{"block": r["block"], "old": r["num"], "new": mapping[r["num"]],
                      "context": r["context"]}
                     for r in rep.get("references", [])
                     if r["kind"] == kind and r["num"] in mapping]
        cap_nums = {c["num"] for c in caps}
        dangling = [{"block": r["block"], "num": r["num"], "context": r["context"]}
                    for r in rep.get("references", [])
                    if r["kind"] == kind and r["num"] not in cap_nums]
        plans[kind] = {"mapping": mapping, "caption_edits": caption_edits,
                       "intext_ref_edits": ref_edits,
                       "dangling_refs_manual": [d for d in dangling],
                       "compound_numbers_skipped": [{"num": c["num"], "block": c["block"]} for c in compound]}
    plan = {"source_report": a.xref_report,
            "note": "合成/正式通用：先按本方案改题注，再逐点改正文引用，改完重跑 xref_scan 验证；"
                    "dangling_refs_manual 与 compound_numbers_skipped 必须人工裁定，不自动处理。",
            "plans": plans}
    json.dump(plan, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    n_map = sum(len(p["mapping"]) for p in plans.values())
    n_ref = sum(len(p["intext_ref_edits"]) for p in plans.values())
    print("renumber mappings=%d, in-text ref edits=%d -> %s" % (n_map, n_ref, a.out))

if __name__ == "__main__":
    main()
