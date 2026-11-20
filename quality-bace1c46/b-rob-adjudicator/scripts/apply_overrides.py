#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_overrides.py -- human review entry point.

If /app/work/review_overrides.jsonl exists (one JSON object per line:
{doc_id, domain, original, override, reason, reviewer}), merge the human
re-judgments into the verified records, log every change, and generate the
scale-revision skeleton (scale_revision_suggestions.md): which signaling
questions repeatedly triggered disagreements or human overrides, with
suggested wording/threshold revisions. This is the sedimentation
mechanism -- not a one-off patch.

Reads : verified/<doc_id>.jsonl, review_overrides.jsonl (optional),
        adjudication_ledger.jsonl, domain_plan.json
Writes: final/<doc_id>.jsonl, overrides_applied.json,
        scale_revision_suggestions.md
"""
import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_utils as cu
import domain_specs as ds

SCRIPT_VERSION = "apply_overrides/1.0"

OVERRIDE_REQUIRED = ["doc_id", "domain", "override", "reason", "reviewer"]


def load_overrides(path):
    rows, problems = [], []
    for i, raw in enumerate(cu.read_jsonl(path), start=1):
        if raw.get("_parse_error"):
            problems.append("line %d: unparseable JSON" % i)
            continue
        missing = [k for k in OVERRIDE_REQUIRED if not raw.get(k)]
        if missing:
            problems.append("line %d: missing fields %s" % (i, missing))
            continue
        if not cu.valid_judgment(raw.get("override")):
            problems.append("line %d: invalid override judgment %r"
                            % (i, raw.get("override")))
            continue
        rows.append(raw)
    return rows, problems


def main():
    ap = argparse.ArgumentParser(description="Apply human review overrides")
    ap.add_argument("--workdir", default="/app/work")
    args = ap.parse_args()

    ver_dir = os.path.join(args.workdir, "verified")
    out_dir = os.path.join(args.workdir, "final")
    os.makedirs(out_dir, exist_ok=True)

    ov_path = os.path.join(args.workdir, "review_overrides.jsonl")
    overrides, problems = [], []
    if os.path.exists(ov_path):
        overrides, problems = load_overrides(ov_path)

    applied, rejected = [], list(problems)
    try:
        names = sorted(os.listdir(ver_dir))
    except Exception:
        names = []

    override_counter = Counter()
    for name in names:
        if not name.endswith(".jsonl"):
            continue
        doc_id = name[:-len(".jsonl")]
        rows = cu.read_jsonl(os.path.join(ver_dir, name))
        by_domain = {r.get("domain"): r for r in rows}
        for ov in [o for o in overrides if o.get("doc_id") == doc_id]:
            dom = ov.get("domain")
            target = by_domain.get(dom)
            if target is None:
                rejected.append(
                    "override for %s/%s: domain not present" % (doc_id, dom))
                continue
            if ov.get("original") and \
                    ov.get("original") != target.get("judgment"):
                rejected.append(
                    "override for %s/%s: stated original %r != current %r"
                    % (doc_id, dom, ov.get("original"),
                       target.get("judgment")))
                continue
            target["judgment_original"] = target.get("judgment")
            target["judgment"] = ov["override"]
            target["human_override"] = {
                "original": target["judgment_original"],
                "override": ov["override"],
                "reason": ov.get("reason"),
                "reviewer": ov.get("reviewer"),
                "quote": ov.get("quote", ""),
                "locator": ov.get("locator", ""),
            }
            if ov.get("quote"):
                target["quote"] = ov["quote"]
                target["quote_verified"] = None  # needs re-verification
            applied.append({"doc_id": doc_id, "domain": dom,
                            "original": target["judgment_original"],
                            "override": ov["override"],
                            "reviewer": ov.get("reviewer")})
            override_counter[dom] += 1
        cu.write_jsonl(os.path.join(out_dir, name), rows)

    cu.write_json(os.path.join(args.workdir, "overrides_applied.json"), {
        "version": SCRIPT_VERSION,
        "override_file_present": os.path.exists(ov_path),
        "applied": applied, "rejected": rejected})

    # --- scale revision suggestions (sedimentation, not patching) ---
    ledger = cu.read_jsonl(os.path.join(args.workdir,
                                        "adjudication_ledger.jsonl"))
    disagree_counter = Counter(i.get("domain") for i in ledger
                               if i.get("type") == "disagreement")
    single_counter = Counter(i.get("domain") for i in ledger
                             if i.get("type") in ("channel_missing",
                                                  "no_channel"))

    lines = ["# 量表改进建议（自动生成骨架）",
             "",
             "> 由 apply_overrides.py 生成。统计口径：裁决台账中的分歧次数、"
             "通道缺失次数与人工改判次数，按偏倚领域聚合。",
             "> 目的：把人工复核的改动沉淀为信号问题措辞/阈值的修订，"
             "而非一次性修补。",
             ""]
    if not disagree_counter and not override_counter and not single_counter:
        lines.append("本轮无分歧、无通道缺失、无人工改判记录；量表暂不"
                     "需要修订。")
    else:
        all_domains = sorted(set(list(disagree_counter) +
                                 list(override_counter) +
                                 list(single_counter)))
        for dom in all_domains:
            spec = ds.DOMAIN_MAP.get(dom, {})
            lines.append("## 领域：%s（%s）"
                         % (dom, spec.get("name", "未在 domain_specs 中登记")))
            lines.append("- 双通道分歧次数：%d" % disagree_counter.get(dom, 0))
            lines.append("- 通道缺失/无通道次数：%d" % single_counter.get(dom, 0))
            lines.append("- 人工改判次数：%d" % override_counter.get(dom, 0))
            if spec.get("questions"):
                lines.append("- 该领域信号问题：")
                for q in spec["questions"]:
                    lines.append("  - %s：%s" % (q["id"], q["text"]))
            lines.append("- 改进建议（待人工填写/确认）：")
            if disagree_counter.get(dom, 0) >= 2:
                lines.append("  - 分歧反复出现，建议拆分信号问题或补充"
                             "判定示例（肯定性/否定性证据各 1 条）。")
            if override_counter.get(dom, 0) >= 1:
                lines.append("  - 存在人工改判，建议核对改判理由是否可"
                             "形式化为新的判定阈值。")
            if single_counter.get(dom, 0) >= 2:
                lines.append("  - 通道覆盖不足，建议为该领域补充召回"
                             "关键词（channel N 尤其）。")
            lines.append("")
    sugg_path = os.path.join(args.workdir, "scale_revision_suggestions.md")
    with open(sugg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print({"applied": len(applied), "rejected": len(rejected),
           "suggestions": sugg_path})


if __name__ == "__main__":
    main()
