#!/usr/bin/env python3
"""合成示例辅助：读取 claims_skeleton.json，演示两种填法。
默认故意填错两处（伪造 quote；把 Smith et al. 的转述定为 author_claim/unsupported），
用于演示 lint 门禁；--fix 时填成合规版本。"""
import argparse
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("--work", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--fix", action="store_true")
a = ap.parse_args()

sk = json.load(open(os.path.join(a.work, "claims_skeleton.json"), encoding="utf-8"))
claims = sk["claims"]
for c in claims:
    sid = c["sentence_id"]
    if "Smith et al." in c["quote"]:
        if a.fix:
            c["attribution"] = "cited_view"
            c["verdict"] = "pending"
            c["note"] = "转述 Smith et al. (2021) 观点，原文不可得，不计作者缺陷，待复核原文"
        else:
            c["attribution"] = "author_claim"
            c["verdict"] = "unsupported"
    elif "假设" in c["quote"] or "有望" in c["quote"]:
        c["attribution"] = "hypothesis"
        c["verdict"] = "pending"
        c["note"] = "作者明确标注的假设情形，不构成缺陷"
    elif "对照组" in c["quote"]:
        c["attribution"] = "control_or_design"
        c["verdict"] = "supported"
        c["evidence_sentence_ids"] = [sid]
        c["note"] = "有意设置的对照组，属设计而非矛盾"
    else:
        c["attribution"] = "author_claim"
        c["verdict"] = "insufficient"
        c["evidence_sentence_ids"] = ["S0008", "S0009"]
        c["note"] = "演示：主张强度需与结果章数值核对"
    if not a.fix and "显著提高" in c["quote"] and not c.get("_broken"):
        c["quote"] = "实验表明该工艺使疲劳寿命显著提高 50%"  # 伪造 quote（原文是 40%）
        c["_broken"] = True
for c in claims:
    c.pop("_broken", None)
json.dump({"claims": claims}, open(a.out, "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("wrote", a.out, "(%d claims, fix=%s)" % (len(claims), a.fix))
