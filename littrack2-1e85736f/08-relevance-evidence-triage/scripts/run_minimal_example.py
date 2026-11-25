#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_minimal_example.py — 端到端运行 examples/minimal 并自检。

管道：prefilter -> rubric_score -> evidence_bind(--auto-select)
      -> prisma_flow -> assemble_result

自检（任一失败则退出码非 0）：
1. 证据逐字性：随机抽查（并对全部 selected 逐条）复核
   quote == 原文 field[char_start:char_end]；
2. PRISMA 守恒：identified == prefiltered_out + screened；
   screened == included + needs_human_review + excluded_at_screening；
3. 决策正确性：合成埋点的预期去向逐一比对（included / review / 各排除类别）；
4. output_contract：result.json 含全部 required_fields，无 null 必填项；
5. bundle 约束：文件数 ≤50、单文件 ≤500KB、总计 ≤2MB、无符号链接、
   每个文件带扩展名。

用法：python3 run_minimal_example.py
"""
from __future__ import annotations

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import prefilter
import rubric_score
import evidence_bind
import prisma_flow
import assemble_result

BUNDLE = common.BUNDLE_ROOT
EXAMPLE = os.path.join(BUNDLE, "examples", "minimal")
CASE = os.path.join(EXAMPLE, "case.json")

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024

# 合成埋点预期：record_id -> (decision, category)
EXPECTED = {
    "crossref:10.0000/syn-metab-2024-001": ("included", None),
    "europepmc:SYN000101": ("included", None),
    "arxiv:SYN-ARXIV-2024-00201": ("included", None),
    "europepmc:SYN000104": ("included", None),  # title_only
    "europepmc:SYN000102": ("needs_human_review", None),
    "europepmc:SYN000103": ("needs_human_review", None),
    "crossref:10.0000/syn-ped-2024-002": ("excluded", "wrong_population"),
    "europepmc:SYN000105": ("excluded", "wrong_method"),
    "arxiv:SYN-ARXIV-2024-00202": ("excluded", "wrong_outcome"),
    "arxiv:SYN-ARXIV-2024-00203": ("excluded", "duplicate_of_kept"),
    "crossref:10.0000/syn-old-2021-003": ("excluded", "out_of_window"),
    "crossref:10.0000/syn-edit-2024-004": ("excluded", "non_research_type"),
    "crossref:10.0000/syn-es-2024-005": ("excluded", "language"),
}

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok, detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         (" — " + detail) if detail else ""))
    return ok


def main():
    print("== pipeline ==")
    prefilter.run(CASE)
    rubric_score.run(CASE)
    evidence_bind.run(CASE, do_auto_select=True)
    prisma_flow.run(CASE)
    result = assemble_result.run(CASE)

    out_dir = os.path.join(EXAMPLE, "output")
    materials_dir = os.path.join(EXAMPLE, "materials")
    records, index, _files = common.load_materials(materials_dir)
    case = common.load_case(CASE)

    print("\n== self-checks ==")
    ok_all = True

    # 1. 证据逐字性：全部 selected + 随机抽查 candidates
    selected = common.read_json(os.path.join(out_dir, "evidence_selected.json"))
    bindings = selected["bindings"]
    bad = [b for b in bindings if not evidence_bind.verify_binding(index, b)]
    ok_all &= check("evidence verbatim: all %d selected bindings" % len(bindings),
                    not bad, ("failures: %s" % [b["record_id"] for b in bad]) if bad else
                    "quote == text[char_start:char_end] for every binding")

    cands = common.read_json(os.path.join(out_dir, "evidence_candidates.json"))["candidates"]
    random.seed(20241125)
    sample = random.sample(cands, min(5, len(cands)))
    bad_s = [c for c in sample if not evidence_bind.verify_binding(index, c)]
    ok_all &= check("evidence verbatim: random sample of %d candidates" % len(sample),
                    not bad_s)

    # 2. PRISMA 守恒
    flow = common.read_json(os.path.join(out_dir, "prisma_flow.json"))
    ok_all &= check("prisma invariants", flow.get("ok") is True,
                    json.dumps(flow.get("invariants"), ensure_ascii=False))

    # 3. 决策正确性（埋点比对）
    with open(os.path.join(out_dir, "screening_decisions.jsonl"),
              "r", encoding="utf-8") as f:
        decisions = {json.loads(l)["record_id"]: json.loads(l)
                     for l in f if l.strip()}
    mismatches = []
    for rid, (exp_dec, exp_cat) in EXPECTED.items():
        d = decisions.get(rid)
        if d is None:
            mismatches.append("%s: missing" % rid)
        elif d["decision"] != exp_dec or (
                exp_cat and d.get("category") != exp_cat):
            mismatches.append("%s: got %s/%s, want %s/%s"
                              % (rid, d["decision"], d.get("category"),
                                 exp_dec, exp_cat))
    ok_all &= check("planted expectations: %d records" % len(EXPECTED),
                    not mismatches, "; ".join(mismatches))

    # included 条目必须带证据
    no_evi = [e["record_id"] for e in result["included"] if not e.get("evidence")]
    ok_all &= check("included records carry verbatim evidence", not no_evi,
                    "; ".join(no_evi))

    # 4. output_contract
    required = case["output_contract"]["required_fields"]
    missing = [k for k in required if k not in result]
    nulls = [k for k in required if result.get(k) is None]
    ok_all &= check("output_contract required_fields present", not missing,
                    "missing: %s" % missing)
    ok_all &= check("output_contract no null required fields", not nulls,
                    "null: %s" % nulls)
    ok_all &= check("result status", result["status"] in ("ok", "partial"),
                    result["status"])

    # 5. bundle 约束
    n_files, total, oversize, noext, nlinks = 0, 0, [], [], 0
    for dirpath, dirnames, filenames in os.walk(BUNDLE):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if os.path.islink(p):
                nlinks += 1
                continue
            n_files += 1
            sz = os.path.getsize(p)
            total += sz
            if sz > MAX_FILE_BYTES:
                oversize.append(p)
            if "." not in fn:
                noext.append(p)
    ok_all &= check("bundle file count <= %d" % MAX_FILES,
                    n_files <= MAX_FILES, "%d files" % n_files)
    ok_all &= check("bundle single file <= 500KB", not oversize,
                    "; ".join(oversize))
    ok_all &= check("bundle total <= 2MB", total <= MAX_TOTAL_BYTES,
                    "%.1f KB" % (total / 1024.0))
    ok_all &= check("bundle no symlinks", nlinks == 0, "%d links" % nlinks)
    ok_all &= check("bundle every file has extension", not noext,
                    "; ".join(noext))

    print("\n== summary ==")
    print("prisma: %s" % json.dumps(
        {k: v for k, v in flow.items() if isinstance(v, int)},
        ensure_ascii=False))
    print("included: %s" % [e["record_id"] for e in result["included"]])
    print("needs_human_review: %s"
          % [e["record_id"] for e in result["needs_human_review"]])
    print("result.status = %s" % result["status"])
    n_pass = sum(1 for _, ok, _ in CHECKS if ok)
    print("self-checks: %d/%d passed" % (n_pass, len(CHECKS)))
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
